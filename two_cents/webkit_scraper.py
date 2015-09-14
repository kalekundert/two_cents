#!/usr/bin/env python3

from PyQt4.QtCore import QByteArray, QUrl, QTimer
from PyQt4.QtGui import QApplication  
from PyQt4.QtWebKit import QWebView, QWebPage 
from PyQt4.QtNetwork import (
        QNetworkAccessManager, QNetworkRequest, QNetworkReply,
        QNetworkCookieJar,
)

from pprint import pprint

class ScrapingError (Exception):
    pass


class Browser(object):

    def __init__(self, app):
        self.app = app

        self.network_manager = QNetworkAccessManager()
        self.network_manager.finished.connect(self._request_finished)

        self.cookie_jar = QNetworkCookieJar()
        self.network_manager.setCookieJar(self.cookie_jar)

        self.web_page = QWebPage()
        self.web_page.setNetworkAccessManager(self.network_manager)

        #self.web_page.loadFinished.connect(app.quit)

    def _request_finished(self, reply):
        eid = reply.error()
        if eid:
            errors = {
                  0 : 'no error condition. Note: When the HTTP protocol returns a redirect no error will be reported. You can check if there is a redirect with the QNetworkRequest::RedirectionTargetAttribute attribute.',
                  1 : 'the remote server refused the connection (the server is not accepting requests)',
                  2 : 'the remote server closed the connection prematurely, before the entire reply was received and processed',
                  3 : 'the remote host name was not found (invalid hostname)',
                  4 : 'the connection to the remote server timed out',
                  5 : 'the operation was canceled via calls to abort() or close() before it was finished.',
                  6 : 'the SSL/TLS handshake failed and the encrypted channel could not be established. The sslErrors() signal should have been emitted.',
                  7 : 'the connection was broken due to disconnection from the network, however the system has initiated roaming to another access point. The request should be resubmitted and will be processed as soon as the connection is re-established.',
                101 : 'the connection to the proxy server was refused (the proxy server is not accepting requests)',
                102 : 'the proxy server closed the connection prematurely, before the entire reply was received and processed',
                103 : 'the proxy host name was not found (invalid proxy hostname)',
                104 : 'the connection to the proxy timed out or the proxy did not reply in time to the request sent',
                105 : 'the proxy requires authentication in order to honour the request but did not accept any credentials offered (if any)',
                201 : 'the access to the remote content was denied (similar to HTTP error 401)',
                202 : 'the operation requested on the remote content is not permitted',
                203 : 'the remote content was not found at the server (similar to HTTP error 404)',
                204 : 'the remote server requires authentication to serve the content but the credentials provided were not accepted (if any)',
                205 : 'the request needed to be sent again, but this failed for example because the upload data could not be read a second time.',
                301 : 'the Network Access API cannot honor the request because the protocol is not known',
                302 : 'the requested operation is invalid for this protocol',
                 99 : 'an unknown network-related error was detected',
                199 : 'an unknown proxy-related error was detected',
                299 : 'an unknown error related to the remote content was detected',
                399 : 'a breakdown in protocol was detected (parsing error, invalid or unexpected responses, etc.)',
            }
            print('Error %d: %s' % (eid, errors.get(eid, 'unknown error')))
            print(reply.errorString())

    def _make_request(self, url):
        request = QNetworkRequest()
        request.setUrl(QUrl(url))
        return request

    def _urlencode_post_data(self, post_data):
        post_params = QUrl()
        for (key, value) in post_data.items():
            post_params.addQueryItem(key, value)

        return post_params.encodedQuery()

    def _check_if_finished(self):
        print('_check_if_finished()')
        self.app.quit()

    def perform(self, url, method='GET', post_data={}, wait=0):
        print("Requesting <{}>".format(url))
        request = self._make_request(url)

        QTimer.singleShot(wait * 1000, self._check_if_finished)

        if method == 'GET':
            self.web_page.mainFrame().load(request)
        else:
            encoded_data = self._urlencode_post_data(post_data)
            request.setRawHeader(
                    'Content-Type', 'application/x-www-form-urlencoded')
            self.web_page.mainFrame().load(
                    request, QNetworkAccessManager.PostOperation, encoded_data)


def get_page(url, method='GET', post_data={}, wait=0):
    app = QApplication([])
    browser = Browser(app, wait)
    browser.perform(url, method, data)
    app.exec_()
    return browser.web_page.mainFrame().toHtml()



url = 'https://online.wellsfargo.com/signon'
url = 'https://connect.secure.wellsfargo.com/auth/login/do'
method = 'POST'

data = {
    'LOB': 'Cons',
    'destination': 'AccountSummary',
    'homepage': 'true',
    'j_password': 'password',
    'j_username': 'username',
    'jsenabled': 'false',
    'origin': 'cob',
    'origination': 'WebCons',
    'screenid': 'SIGNON',
    'u_p': '',
}


app = QApplication([])
browser = Browser(app)

# Get key wells fargo cookies.
browser.perform('https://www.wellsfargo.com/', wait=5)
app.exec_()
#for cookie in browser.cookie_jar.allCookies():
    #print (cookie.name(), cookie.value())

# Log in.
browser.perform(url, method, data, wait=10)
app.exec_()
#for cookie in browser.cookie_jar.allCookies():
    #print (cookie.name(), cookie.value())

import time
time.sleep(1)

# Show that HTML.
print(browser.web_page.mainFrame().toHtml())

