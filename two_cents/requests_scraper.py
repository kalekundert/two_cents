#!/usr/bin/env python3

import os, sys, re, io, datetime
import requests, ssl, ofxparse
from bs4 import BeautifulSoup

def log_on_failure(method):

    def decorator(self, html, *args, **kwargs):
        try:
            method(self, html, *args, **kwargs)
        except:
            log_path = os.path.join(
                    os.path.expanduser('~'),
                    '.config', 'two_cents', 'error.html')
            with open(log_path, 'w') as file:
                file.write(html)
            raise


    return decorator

def log_html(name, html):
    if __debug__:
        log_path = os.path.join(
                os.path.expanduser('~'),
                '.config', 'two_cents', 'debug_log', name)
        with open(log_path, 'w') as file:
            file.write(html)


@contextmanager
def silence_stderr(to=os.devnull):
    '''
    import os

    with stderr_redirected(to=filename):
        print("from Python")
        os.system("echo non-Python applications are also supported")
    '''
    fd = sys.stderr.fileno()

    # assert that Python and C stdio write using the same file descriptor
    # assert libc.fileno(ctypes.c_void_p.in_dll(libc, "stderr")) == fd == 1

    def _redirect_stderr(to):
        sys.stderr.close() # + implicit flush()
        os.dup2(to.fileno(), fd) # fd writes to 'to' file
        sys.stderr = os.fdopen(fd, 'w') # Python writes to fd

    with os.fdopen(os.dup(fd), 'w') as old_stderr:
        with open(to, 'w') as file:
            _redirect_stderr(to=file)
        try:
            yield # allow code to be run with the redirected stderr
        finally:
            _redirect_stderr(to=old_stderr) # restore stderr.
                                            # buffering and flags such as
                                            # CLOEXEC may be different


def get_html(url):
    from PyQt4.QtGui import QApplication
    from PyQt4.QtWebKit import QWebPage
    from PyQt4.QtCore import QUrl

    with silence_stderr():
        app = QApplication([])
        webpage = QWebPage()
        webpage.loadFinished.connect(app.quit)
        webpage.mainFrame().load(QUrl(url))
        app.exec_()

    return webpage.mainFrame().toHtml()

def get_soup(url):
    return BeautifulSoup(get_html(url))


class WellsFargo:

    def __init__(self, username, password):
        self.username = username
        self.password = password

    def download(self, from_date=None, to_date=None):
        if to_date is None: to_date = datetime.date.today()
        if from_date is None: from_date = to_date - datetime.timedelta(30)

        self.setup_ssl_session()
        account_page = self.load_account_page()
        activity_page = self.load_activity_page(account_page)
        download_page = self.load_download_page(activity_page)
        return self.download_transactions(download_page, from_date, to_date)

    def setup_ssl_session(self):
        from requests.packages.urllib3.poolmanager import PoolManager

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
        login_data = {
            'LOB': 'Cons',
            'destination': 'AccountSummary',
            'homepage': 'true',
            'j_password': self.password,
            'j_username': self.username,
            'jsenabled': 'false',
            'origin': 'cob',
            'origination': 'WebCons',
            'screenid': 'SIGNON',
            'u_p': '',
        }
        self.scraper.post('https://online.wellsfargo.com/signon', login_data)

        # Make sure the login worked.

        soup = get_soup('https://online.wellsfargo.com/das/cgi-bin/session.cgi?screenid=SIGNON_PORTAL_PAUSE')
        error_message = soup.find(text=re.compile(
            "^We do not recognize your username and/or password"))
        if error_message:
            raise ScrapingError("failed to log into Wells Fargo")

        try:
            return self.skip_online_statement(soup)
        except:
            return response.text

    def skip_online_statement(self, soup):
        cancel_url = soup.find(
                name='input', attrs={'name': 'Considering'}).parent['action']
        data = {'Considering': 'Remind me later'}
        response = self.scraper.post(cancel_url, data)
        return response.text

    def load_activity_page(self, html):
        log_html('load_activity_page.html', html)
        soup = BeautifulSoup(html)
        link_attrs = {'title': re.compile('Account Activity')}
        account_link = soup.find(name='a', attrs=link_attrs)
        account_url = account_link['href']
        response = self.scraper.get(account_url)
        return response.text

    def load_download_page(self, html):
        log_html('load_download_page.html', html)
        soup = BeautifulSoup(html)
        section = soup.find('div', id='transactionSectionWrapper')
        url = section.div.a['href']
        response = self.scraper.get(url)
        return response.text

    def download_transactions(self, html, from_date, to_date):
        log_html('download_transactions.html', html)
        soup = BeautifulSoup(html)
        form = soup.find('form', id='accountActivityDownloadModel')
        select = form.find('select', id='primaryKey')
        form_url = form['action']
        accounts = []

        for option in select.find_all('option'):

            # For some reason, the whole form has to be submitted after an 
            # account is selected.  So do that...

            option_data = {
                    'primaryKey': option['value'],
                    'Select': ' Select ',
            }
            self.scraper.post(form_url, option_data)

            # ...and then download the financial data for each account within 
            # the given date range.

            form_data = {
                    'primaryKey': option['value'],
                    'fromDate': from_date.strftime('%m/%d/%y'),
                    'toDate': to_date.strftime('%m/%d/%y'),
                    'fileFormat': 'quickenOfx',
                    'Download': 'Download',
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


class ScrapingError:

    def __init__(self, message):
        self.message = message



