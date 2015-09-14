#!/usr/bin/env python3

import itertools
import contextlib
import datetime
import tempfile
import ofxparse
import os

from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

# Debug Mode
# ==========
# 1. Show GUI
# 2. Save OFX files to non-temporary file.
# 3. Print out more status updates.

@contextlib.contextmanager
def firefox_driver(download_dir, gui=False, max_load_time=10):
    from xvfbwrapper import Xvfb

    # If the GUI was not explicitly requested, use the X virtual frame buffer 
    # (Xvfb) to gobble it.

    if not gui:
        xvfb = Xvfb()
        xvfb.start()

    # Change some of the Firefox's default preferences.  In particular, 
    # configure it to automatically download files without asking questions.

    profile = webdriver.FirefoxProfile()
    profile.set_preference('browser.download.folderList',2)
    profile.set_preference('browser.download.manager.showWhenStarting',False)
    profile.set_preference('browser.download.dir', download_dir)
    profile.set_preference('browser.helperApps.neverAsk.saveToDisk','application/vnd.intu.QFX')
    
    # If the GUI is disabled, don't bother downloading CSS or images.

    if not gui:
        profile.set_preference('permissions.default.stylesheet', 2)
        profile.set_preference('permissions.default.image', 2)
        profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', 'false')

    # Construct and yield a Firefox driver.

    driver = webdriver.Firefox(profile)
    driver.implicitly_wait(max_load_time)

    yield driver

    # If the GUI is disabled, close the browser as soon as the scraping is 
    # complete.

    if not gui:
        driver.close()
        xvfb.stop()


class WellsFargo:

    def __init__(self, username, password, gui=False):
        self.username = username
        self.password = password
        self.gui = gui

    def download(self, from_date=None, to_date=None):
        # Create a temporary directory that the scraper can download all the 
        # financial data into.

        with tempfile.TemporaryDirectory() as ofx_dir:

            # Download financial data from Wells Fargo, then parse it and make 
            # a list of transactions for each account.

            self._scrape(ofx_dir, from_date, to_date)
            return self._parse(ofx_dir)

    def _scrape(self, ofx_dir, from_date=None, to_date=None):
        if to_date is None: to_date = datetime.date.today()
        if from_date is None: from_date = to_date - datetime.timedelta(30)

        from_date = from_date.strftime('%m/%d/%y')
        to_date = to_date.strftime('%m/%d/%y')

        with firefox_driver(ofx_dir, gui=self.gui) as driver:

            # Login to Wells Fargo's website.
            driver.get('https://www.wellsfargo.com/')

            username_form = driver.find_element_by_id('userid')
            password_form = driver.find_element_by_id('password')
            username_form.send_keys(self.username)
            password_form.send_keys(self.password)
            password_form.submit()

            # Go to the "Account Activity" page.
            driver.find_element_by_link_text("Account Activity").click()

            # Go to the "Download" page.
            driver.find_element_by_link_text("Download Account Activity").click()

            # Download account activity in the OFX format.
            for i in itertools.count():

                # Pick the next account to download.
                accounts = driver.find_element_by_name('primaryKey')
                try: account = Select(accounts).select_by_index(i)
                except NoSuchElementException: break
                driver.find_element_by_name("Select").click()

                # Pick the date range to download.
                driver.find_element_by_id('fromDate').clear()
                driver.find_element_by_id('toDate').clear()
                driver.find_element_by_id('fromDate').send_keys(from_date)
                driver.find_element_by_id('toDate').send_keys(to_date)

                # Download it.
                driver.find_element_by_id('quickenOFX').click()
                driver.find_element_by_name('Download').click()

    def _parse(self, ofx_dir):
        accounts = []

        for ofx_path in os.listdir(ofx_dir):
            ofx_path = os.path.join(ofx_dir, ofx_path)
            with open(ofx_path, 'rb') as ofx_file:
                ofx = ofxparse.OfxParser.parse(ofx_file)
                accounts += ofx.accounts

        return accounts


class ScrapingError:

    def __init__(self, message):
        self.message = message



if __name__ == '__main__':
    from pprint import pprint
    scraper = WellsFargo('username', 'password', gui=False)
    pprint(scraper.download())
