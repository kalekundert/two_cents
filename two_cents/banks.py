#!/usr/bin/env python3

import appdirs
import contextlib
import datetime
import itertools
import ofxparse
import os
import pathlib
import tempfile
import time
import warnings

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
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
def chrome_driver(download_dir, gui=False, max_load_time=30):
    from xvfbwrapper import Xvfb

    # If the GUI was not explicitly requested, use the X virtual frame buffer 
    # (Xvfb) to gobble it.

    if not gui:
        xvfb = Xvfb()
        xvfb.start()

    try:
        # Use Chrome (instead of Firefox) because I can hack chromedriver to 
        # not be detected by Wells Fargo.  The hack is described here:
        #
        # https://stackoverflow.com/questions/33225947/can-a-website-detect-when-you-are-using-selenium-with-chromedriver
        #
        # Briefly, these are the steps you have to follow:
        #
        # - Download the most recent version of chromedriver for here:
        #
        #     https://sites.google.com/a/chromium.org/chromedriver/downloads
        # 
        # - Copy (or link) the excecutable onto your $PATH.
        #
        # - Open to chromedriver executable directly in vim.
        #
        # - Search for 'cdc_' (which should only appear once, in a javascript 
        #   block) and replace it with 'xxx_' (or anything else).

        options = webdriver.ChromeOptions()
        options.add_experimental_option(
                'prefs', {'download.default_directory': download_dir})
 
        driver = webdriver.Chrome()
        driver.implicitly_wait(max_load_time)
        yield driver

    finally:

        # If the GUI is disabled, close the browser as soon as the scraping is 
        # complete.

        if not gui:
            try: driver.close()
            except AttributeError: pass
            xvfb.stop()

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
        profile.set_preference('browser.download.folderList', 2)
        profile.set_preference('browser.download.manager.showWhenStarting', False)
        profile.set_preference('browser.download.dir', download_dir)
        profile.set_preference('browser.helperApps.neverAsk.saveToDisk','application/vnd.intu.QFX')
        
        # If the GUI is disabled, don't bother downloading images, CSS, or 
        # flash content.

        if not gui:
            profile.set_preference('permissions.default.image', 2)
            profile.set_preference('permissions.default.stylesheet', 2)
            profile.set_preference('dom.ipc.plugins.enabled.libflashplayer.so', 'false')

        # Use the Marionette driver, which is required for Firefox >= 47.
        
        # To install Marionette, download the most recent geckodriver binary 
        # from https://github.com/mozilla/geckodriver/releases, unpack it, and 
        # put the binary somewhere on your $PATH.

        capabilities = DesiredCapabilities.FIREFOX
        capabilities['marionette'] = True

        # Construct and yield a Firefox driver.

        driver = webdriver.Firefox(profile, capabilities=capabilities)
        driver.implicitly_wait(max_load_time)

        yield driver

    finally:

        # If the GUI is disabled, close the browser as soon as the scraping is 
        # complete.

        if not gui:
            try: driver.close()
            except AttributeError: pass
            xvfb.stop()


def wait_for_element(driver, element_type, element_identifier, timeout=30):
    print(f'Waiting for {element_type} {element_identifier}...')

    wait = WebDriverWait(driver, timeout)
    wait.until(element_to_be_clickable((element_type, element_identifier)))

    # It shouldn't be necessary to manually sleep here, and I suspect that it 
    # only is necessary because of a bug in the Marionette driver.  For one 
    # thing, the line just above is supposed to wait until the relevant element 
    # is clickable.  For another, the driver has an implicit wait set anyways, 
    # so it should wait for a few seconds for elements to load.  But despite 
    # that, immediately calling click() on the element returned by this method 
    # does nothing.
    #time.sleep(1)

    return driver.find_element(element_type, element_identifier)

def wait_for_element_by_id(driver, id, timeout=30):
    return wait_for_element(driver, By.ID, id, timeout)

def wait_for_element_by_name(driver, name, timeout=30):
    return wait_for_element(driver, By.NAME, name, timeout)

def wait_for_element_by_xpath(driver, name, timeout=30):
    return wait_for_element(driver, By.XPATH, name, timeout)

def wait_for_element_by_link_text(driver, link_text, timeout=30):
    return wait_for_element(driver, By.LINK_TEXT, link_text, timeout)

def wait_for_element_by_partial_link_text(driver, link_text, timeout=30):
    return wait_for_element(driver, By.PARTIAL_LINK_TEXT, link_text, timeout)

def wait_for_element_by_css_selector(driver, css_selector, timeout=30):
    return wait_for_element(driver, By.CSS_SELECTOR, css_selector, timeout)

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
            input(f"Check downloads ({ofx_dir})?")
            return self._parse(ofx_dir)

    def _scrape(self, ofx_dir, from_date=None, to_date=None):
        if to_date is None: to_date = datetime.date.today()
        if from_date is None: from_date = to_date - datetime.timedelta(30)

        from_date = from_date.strftime('%m/%d/%y')
        to_date = to_date.strftime('%m/%d/%y')

        with chrome_driver(ofx_dir, gui=self.gui) as driver:

            # Login to Wells Fargo's website.
            driver.get('https://www.wellsfargo.com/')
            username_form = wait_for_element_by_id(driver, 'userid')
            password_form = wait_for_element_by_id(driver, 'password')
            username_form.send_keys(self.username)
            password_form.send_keys(self.password)
            password_form.submit()

            # Click on the "Accounts" menu.  This one is difficult to locate, 
            # because it seems to have a dynamically generated id.

            #wait_for_element_by_xpath(driver, '//li[@id="mwf-app-nav-accounts"]/button').click()
            #ActionChains(driver).move_to_element(accounts).perform()  # hover

            # Navigate to the "Download Account Activity" page.
            #wait_for_element_by_partial_link_text(driver, 'Download Account Activity').click()
            download = driver.find_element_by_link_text('Download Account Activity')
            driver.execute_script('arguments[0].click()', download)

            # Download account activity in the OFX format.
            #driver.get('file:///home/kale/wf.html')
            print(ofx_dir)
            for i in itertools.count():

                # Pick the next account to download.  This is inside the loop 
                # to protect against the page being reloaded when the form was 
                # submitted, ut that may not be an issue anymore.
                accounts = driver.find_element_by_id('selectedAccountId')
                try:
                    account = Select(accounts).options[i]
                    print(account.get_attribute('textContent'))
                except IndexError: break
                driver.execute_script("arguments[0].selected = true", account)

                # Pick the date range to download.

                # Need to use javascript because Wells Fargo makes the actual 
                # forms invisible, so selenium won't let us interact with them 
                # directly.  Not sure if this is actually working though, and 
                # the defaults are fine (now; they didn't used to be)...
                driver.execute_script(
                        f'arguments[0].value = "{from_date}"',
                        driver.find_element_by_id('fromDate'))

                driver.execute_script(
                        f'arguments[0].value = "{to_date}"',
                        driver.find_element_by_id('toDate'))

                # driver.find_element_by_id('fromDate').clear()
                # driver.find_element_by_id('toDate').send_keys(to_date)
                # driver.find_element_by_id('fromDate').send_keys(from_date)

                # Pick the Quicken file format.  Note that we have to click on 
                # the <span> element.  The actual <input> can't be clicked 
                # because it's not visible, and clicking the parent <div> 
                # doesn't do anything.
                wait_for_element_by_xpath(driver, '//input[@id="quicken"]/../span').click()

                # Download it.
                driver.find_element_by_name('Download').click()

    def _parse(self, ofx_dir):
        accounts = []

        for ofx_path in os.listdir(ofx_dir):
            ofx_path = os.path.join(ofx_dir, ofx_path)
            with open(ofx_path, 'rb') as ofx_file:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    ofx = ofxparse.OfxParser.parse(ofx_file)
                accounts += ofx.accounts

        pprint(accounts)
        return accounts


class ScrapingError:

    def __init__(self, message):
        self.message = message



if __name__ == '__main__':
    from pprint import pprint
    scraper = WellsFargo('username', 'password', gui=False)
    pprint(scraper.download())
