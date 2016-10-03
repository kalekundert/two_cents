#!/usr/bin/env python3

import appdirs
import contextlib
import datetime
import itertools
import ofxparse
import os
import pathlib
import tempfile
import warnings

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support.expected_conditions import staleness_of, element_to_be_clickable
from selenium.common.exceptions import NoSuchElementException

dirs = appdirs.AppDirs('two_cents', 'username')

# Debug Mode
# ==========
# 1. Show GUI
# 2. Save OFX files to non-temporary file.
# 3. Print out more status updates.

@contextlib.contextmanager
def firefox_driver(download_dir, gui=False, max_load_time=30):
    from xvfbwrapper import Xvfb

    # If the GUI was not explicitly requested, use the X virtual frame buffer 
    # (Xvfb) to gobble it.

    if not gui:
        xvfb = Xvfb()
        xvfb.start()

    try:

        # Change some of the Firefox's default preferences.  In particular, 
        # have it automatically download files without asking questions.

        profile = webdriver.FirefoxProfile()
        profile.set_preference('browser.download.folderList',2)
        profile.set_preference('browser.download.manager.showWhenStarting',False)
        profile.set_preference('browser.download.dir', download_dir)
        profile.set_preference('browser.helperApps.neverAsk.saveToDisk','application/vnd.intu.QFX')
        
        # If the GUI is disabled, don't bother downloading images, CSS, or 
        # flash content.

        if not gui:
            profile.set_preference('permissions.default.image', 2)
            profile.set_preference('permissions.default.stylesheet', 2)
            profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', 'false')

        # Use the Marionette driver, which is required for Firefox >= 47.

        capabilities = DesiredCapabilities.FIREFOX
        capabilities['marionette'] = True

        # Use the firefox 48 beta binary.  This will be unnecessary once 
        # firefox 48 is released.
        from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
        binary = FirefoxBinary('/home/kale/hacking/third_party/firefox/firefox')

        # Construct and yield a Firefox driver.

        driver = webdriver.Firefox(profile, capabilities=capabilities, firefox_binary=binary)
        driver.implicitly_wait(max_load_time)

        yield driver

    finally:

        # If the GUI is disabled, close the browser as soon as the scraping is 
        # complete.

        if not gui:
            driver.close()
            xvfb.stop()

def wait_for_element(driver, element_type, element_identifier, timeout=30):
    wait = WebDriverWait(driver, timeout)
    wait.until(element_to_be_clickable((element_type, element_identifier)))

    # It shouldn't be necessary to manually sleep here, and I suspect that it 
    # only is necessary because of a bug in the Marionette driver.  For one 
    # thing, the line just above is supposed to wait until the relevant element 
    # is clickable.  For another, the driver has an implicit wait set anyways, 
    # so it should wait for a few seconds for elements to load.  But despite 
    # that, immediately calling click() on the element returned by this method 
    # does nothing.
    import time; time.sleep(1)

    return driver.find_element(element_type, element_identifier)

def wait_for_element_by_id(driver, id, timeout=30):
    return wait_for_element(driver, By.ID, id, timeout)

def wait_for_element_by_name(driver, name, timeout=30):
    return wait_for_element(driver, By.NAME, name, timeout)

def wait_for_element_by_link_text(driver, link_text, timeout=30):
    return wait_for_element(driver, By.LINK_TEXT, link_text, timeout)


class WellsFargo:

    def __init__(self, username, password, gui=False):
        self.username = username
        self.password = password
        self.gui = gui

    def download(self, from_date=None, to_date=None):
        # Create a temporary directory that the scraper can download all the 
        # financial data into.

        with tempfile.TemporaryDirectory(prefix='two_cents_') as ofx_dir:

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
            username_form = wait_for_element_by_id(driver, 'userid')
            password_form = wait_for_element_by_id(driver, 'password')
            username_form.send_keys(self.username)
            password_form.send_keys(self.password)
            password_form.submit()

            # Go to the "Account Activity" page.
            wait_for_element_by_link_text(driver, "Account Activity").click()

            # Go to the "Download" page.
            wait_for_element_by_link_text(driver, "Download Account Activity").click()

            # Download account activity in the OFX format.
            for i in itertools.count():

                # Pick the next account to download.
                accounts = wait_for_element_by_name(driver, 'primaryKey')
                try: account = Select(accounts).options[i]
                except IndexError: break
                driver.execute_script("arguments[0].selected = true", account)
                driver.find_element_by_name("Select").click()

                # Not totally sure why this is necessary, but without it only 
                # the first account in the dropdown box is downloaded.
                import time; time.sleep(1)

                # Pick the date range to download.
                driver.find_element_by_id('toDate').clear()
                driver.find_element_by_id('fromDate').clear()
                driver.find_element_by_id('toDate').send_keys(to_date)
                driver.find_element_by_id('fromDate').send_keys(from_date)

                # Download it.
                driver.find_element_by_id('quickenOFX').click()
                driver.find_element_by_name('Download').click()

                import time; time.sleep(1)

    def _parse(self, ofx_dir):
        accounts = []

        for ofx_path in os.listdir(ofx_dir):
            ofx_path = os.path.join(ofx_dir, ofx_path)
            with open(ofx_path, 'rb') as ofx_file:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
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
