#!/usr/bin/env python3

import os, sys, re, io, datetime
import requests, ssl, ofxparse
from bs4 import BeautifulSoup
from urllib3.poolmanager import PoolManager

class WellsFargo:

    title = "Wells Fargo"

    def __init__(self, username, password):
        self.username = username
        self.password = password

        if not username or not password:
            raise LoginError(self)

    def download(self, from_date=None, to_date=None):
        if to_date is None: to_date = datetime.date.today()
        if from_date is None: from_date = to_date - datetime.timedelta(30)

        self.setup_ssl_session()
        account_page = self.load_account_page()
        activity_page = self.load_activity_page(account_page)
        download_page = self.load_download_page(activity_page)
        return self.download_transactions(download_page, from_date, to_date)

    def setup_ssl_session(self):
        # Wells Fargo hangs if the default SSL configuration provided by 
        # requests is used, so a custom one is used instead.  See:
        # http://lukasa.co.uk/2013/01/Choosing_SSL_Version_In_Requests

        class TLSv1Adapter(requests.adapters.HTTPAdapter):

            def init_poolmanager(self, connections, maxsize, **kwargs):
                self.poolmanager = PoolManager(
                        num_pools=connections,
                        maxsize=maxsize,
                        ssl_version=ssl.PROTOCOL_TLSv1)

        self.scraper = requests.Session()
        self.scraper.mount('https://', TLSv1Adapter())

    def load_account_page(self):
        self.scraper.get('https://www.wellsfargo.com/')
        login_data = {
            'userid': self.username,
            'password': self.password,
            'screenid': 'SIGNON',
            'origination': 'WebCons',
            'LOB': 'Cons',
            'u_p': '',
        }
        self.scraper.post('https://online.wellsfargo.com/signon', login_data)
        response = self.scraper.get('https://online.wellsfargo.com/das/cgi-bin/session.cgi?screenid=SIGNON_PORTAL_PAUSE')

        with open('debug/login_response.html', 'w') as file:
            file.write(response.text)

        # Make sure the login worked.

        soup = BeautifulSoup(response.text)
        error_message = soup.find(text=re.compile(
            "^We do not recognize your username and/or password"))
        if error_message: raise LoginError(self)

        try:
            return self.skip_online_statement(response.text)
        except:
            return response.text

    def skip_online_statement(self, html):
        soup = BeautifulSoup(html)
        cancel_url = soup.find(
                name='input', attrs={'name': 'Considering'}).parent['action']
        data = {'Considering': 'Remind me later'}
        response = self.scraper.post(cancel_url, data)

        with open('debug/skip_question_response.html', 'w') as file:
            file.write(response.text)

        return response.text

    def load_activity_page(self, html):
        soup = BeautifulSoup(html)
        link_attrs = {'title': re.compile('Account Activity')}
        account_link = soup.find(name='a', attrs=link_attrs)
        account_url = account_link['href']
        response = self.scraper.get(account_url)

        with open('debug/activity_response.html', 'w') as file:
            file.write(response.text)

        return response.text

    def load_download_page(self, html):
        soup = BeautifulSoup(html)
        section = soup.find('div', id='transactionSectionWrapper')
        url = section.div.a['href']
        response = self.scraper.get(url)

        with open('debug/download_response.html', 'w') as file:
            file.write(response.text)

        return response.text

    def download_transactions(self, html, from_date, to_date):
        soup = BeautifulSoup(html)
        form = soup.find('form', {'name': 'DownloadFormBean'})
        select = form.find('select', id='Account')
        form_url = form['action']
        accounts = []

        for option in select.find_all('option'):

            # For some reason, the whole form has to be submitted after an 
            # account is selected.  So do that...

            option_data = {
                    'primaryKey': option['value'],
                    'selectButton': ' Select ',
            }
            self.scraper.post(form_url, option_data)

            # ...and then download the financial data.

            form_data = {
                    'primaryKey': option['value'],
                    'fromDate': from_date.strftime('%m/%d/%y'),
                    'toDate': to_date.strftime('%m/%d/%y'),
                    'fileFormat': 'quickenOfx',
                    'downloadButton': 'Download',
            }
            response = self.scraper.post(form_url, form_data)
            content_type = response.headers['content-type']

            # If an HTML page is returned, that means there was an error 
            # processing the form.  I'll assume the error is that there were no 
            # transactions in the given date range, but this may be too naive.

            if content_type.startswith('text/html'):
                continue

            # Financial data is returned in the proprietary QFX format, which 
            # should be compatible with the open OFX standard.  Conveniently, 
            # python already has a module for parsing this type of data.

            bytes_io = io.BytesIO(response.text.encode('utf-8'))
            ofx = ofxparse.OfxParser.parse(bytes_io)
            accounts += ofx.accounts

        return accounts


class LoginError (Exception):

    def __init__(self, bank):
        self.bank = bank.title
        self.username = bank.username
        self.password = bank.password



if __name__ == '__main__':
    from pprint import pprint

    with open('/home/kale/download.html') as file:
        html = file.read()
    with open('transactions.qfx') as file:
        qfx = file.read()

    print("Connecting to Wells Fargo...")
    state = {'last_date': datetime.date(2013, 11, 1)}
    #state = {'last_date': datetime.date(2014, 1, 26)}
    scraper = WellsFargo('username', 'password', state)
    debits = scraper.download()
    pprint(state)
    pprint(debits)
    #scraper.download_transactions(html)
    #print(scraper.parse_transactions(qfx))
