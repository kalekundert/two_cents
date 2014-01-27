#!/usr/bin/env python3

import logging
import ssl
import os, sys, re, io, csv
import budget

import requests
from bs4 import BeautifulSoup
from urllib3.poolmanager import PoolManager
import datetime

# Rename module to scraping

class WellsFargo:

    def __init__(self, username, password, last_update):
        self.username = username
        self.password = password
        self.staleness = datetime.date.today() - last_update

    def download(self):
        # Although it would be possible to download transaction data for any 
        # period of time, the current implementation can only download 
        # transactions from the last 90 days.  So if the last update was longer 
        # ago than that, some information will be missing.

        if self.staleness.days > 90:
            print("Warning: Only the last 90 days will be downloaded.")

        # The basic scraping strategy is: get to the login page, get to the 
        # accounts list, scrape transaction data from the table on that page.

        self.setup_ssl_session()
        account_page = self.load_account_page()
        transaction_page = self.load_transaction_page(account_page)
        return self.parse_transaction_page(transaction_page)

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

    def load_transaction_page(self, html):
        soup = BeautifulSoup(html)
        link_attrs = {'title': re.compile('Account Activity')}
        account_link = soup.find(name='a', attrs=link_attrs)
        account_url = account_link['href']
        response = self.scraper.get(account_url)
        return response.text

    def parse_transaction_page(self, html):
        soup = BeautifulSoup(html)
        table = soup.find(name='table', attrs=dict(id='DDATransactionTable'))
        rows = table.find('tbody').find_all('tr')
        debits = []

        for row in rows:
            debit = self.parse_transaction(row)
            if debit: debits.append(debit)

        return debits

    def parse_transaction(self, row):
        columns = row.find_all(recursive=False)
        if len(columns) != 4: return None

        date = columns[0].string
        date = datetime.datetime.strptime(date, '%m/%d/%y').date()
        age = datetime.date.today() - date
        if (age > self.staleness): return None

        description = columns[1].div.contents[0].string.strip()

        value = columns[3].string.strip()
        if not value: return None
        value = re.sub('[$.,]', '', value)
        value = int(value)

        return budget.Debit(date, description, value)



modules = {
        'wells-fargo': WellsFargo
}

if __name__ == '__main__':
    from pprint import pprint

    last_update = datetime.date.today() - datetime.timedelta(weeks=4)
    scraper = WellsFargo('username', 'password', last_update)
    debits = scraper.download()

    pprint(debits)

