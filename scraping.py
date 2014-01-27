#!/usr/bin/env python3

import logging
import ssl
import os, sys, re, io, csv
import budget

import requests
from bs4 import BeautifulSoup
from urllib3.poolmanager import PoolManager
import datetime
from pprint import pprint
import ofxparse
import functools
import operator

# The classes in this module retrieve financial information from the internet.  
# This requires scraping for every bank I'm aware of, but maybe someday there 
# will be a bank that provides a nice API for programmatic access.  A very 
# specific interface is expected of the scraper classes.  The constructor must 
# take three arguments: a username, a password, and a state dictionary.  There 
# must be a download() method which returns all debits which have not already 
# been downloaded.  The purpose of the state dictionary given earlier is to 
# make it possible to determine which transactions have already been seen.  The 
# state dictionary is stored in the config database after being serialized via 
# YAML, so don't put anything into it that isn't compatible with YAML.

class WellsFargo:

    title = "Wells Fargo"

    def __init__(self, username, password, state=None):
        self.username = username
        self.password = password
        self.state = state if state is not None else {}
        self.state.setdefault('last_date', datetime.date.today())

    def download(self):
        self.setup_ssl_session()
        account_page = self.load_account_page()
        activity_page = self.load_activity_page(account_page)
        download_page = self.load_download_page(activity_page)
        accounts = self.download_transactions(download_page)
        return self.find_new_debits(accounts)

    def setup_ssl_session(self):
        # Wells Fargo hangs if you you the default SSL configuration provided 
        # by requests, so we have to use a custom one.  See:
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
        self.verify_login(response.text)

        try:
            return self.skip_online_statement(response.text)
        except:
            return response.text

    def verify_login(self, html):
        soup = BeautifulSoup(html)
        tag = soup.find('h1', id='bodycontent')
        if not tag: return

        message = str(tag.string)
        bad_login_message = 'For security reasons,'

        if message.startswith(bad_login_message):
            raise budget.LoginError(
                    'Wells Fargo', self.username, self.password)

    def skip_online_statement(self, html):
        soup = BeautifulSoup(html)
        cancel_url = soup.find(
                name='input', attrs={'name': 'Considering'}).parent['action']
        data = {'Considering': 'Remind me later'}
        response = self.scraper.post(cancel_url, data)
        return response.text

    def load_activity_page(self, html):
        soup = BeautifulSoup(html)
        link_attrs = {'title': re.compile('Account Activity')}
        account_link = soup.find(name='a', attrs=link_attrs)
        account_url = account_link['href']
        response = self.scraper.get(account_url)
        return response.text

    def load_download_page(self, html):
        soup = BeautifulSoup(html)
        section = soup.find('div', id='transactionSectionWrapper')
        url = section.div.a['href']
        response = self.scraper.get(url)
        return response.text

    def download_transactions(self, html):
        soup = BeautifulSoup(html)
        form = soup.find('form', {'name': 'DownloadFormBean'})
        select = form.find('select', id='Account')
        form_url = form['action']
        accounts = []

        for option in select.find_all('option'):
            option_data = {
                    'primaryKey': option['value'],
                    'selectButton': ' Select ',
            }
            self.scraper.post(form_url, option_data)
            form_data = {
                    'primaryKey': option['value'],
                    'fromDate': self.state['last_date'].strftime('%m/%d/%y'),
                    'toDate': datetime.date.today().strftime('%m/%d/%y'),
                    'fileFormat': 'quickenOfx',
                    'downloadButton': 'Download',
            }
            response = self.scraper.post(form_url, form_data)
            content_type = response.headers['content-type']

            # If an HTML page is returned, that means there was an error 
            # processing the form.  I'll assume the error is that there were no 
            # transactions in the given date range, but this may not be right.

            if content_type.startswith('text/html'):
                continue

            bytes_io = io.BytesIO(response.text.encode('utf-8'))
            account = ofxparse.OfxParser.parse(bytes_io).account
            accounts.append(account)

        return accounts

    def find_new_debits(self, accounts):
        all_new_debits = []

        for account in accounts:
            oldest_id = self.state.get(account.number)
            newest_id = oldest_id
            new_debits = []

            # The following code assumes that the transactions in the QFX file 
            # appear in the same order that they were posted.  This assumption 
            # is not guaranteed by the QFX file format.  If it's violated, it 
            # could result in transactions being spuriously ignored.

            for transaction in account.statement.transactions:
                if transaction.amount > 0:
                    continue

                debit = budget.Debit(
                        transaction.date,
                        transaction.payee + ' ' + transaction.memo,
                        abs(int(100 * transaction.amount)))

                new_debits.append(debit)
                newest_id = transaction.id

                # If the oldest ID is seen, it means that all the debits that 
                # have been encountered to this point are duplicates.  Any 
                # further transactions will certainly be new.

                if transaction.id == oldest_id:
                    new_debits = []
                    continue

            self.state[account.number] = newest_id
            all_new_debits += new_debits
            
        self.state = {'last_date': datetime.date.today()}
        all_new_debits.sort(key=operator.attrgetter('date'))
        return all_new_debits



modules = {
        'wells-fargo': WellsFargo
}

if __name__ == '__main__':
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
