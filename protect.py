  GNU nano 6.2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          protect.py
import subprocess
import time
import threading
import os
import sys
import logging
import getpass
from datetime import datetime
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
os.environ['DISPLAY'] = ':0'
# Chrome directory
user = getpass.getuser()
chrome_data_dir = f"/home/{username}/.config/google-chrome/Default"

load_dotenv()
# dotenv variables
# Protect credentials in separate .env file. Format shoud be
# USERNAME=InsertUsernameHere
# PASSWORD=InsertPasswordHere
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
# Link to the live view you want to display
url = os.getenv('URL')
# Global variables
SLEEP_TIME = 300 # 5 minutes delay between each check of the status of the live view
WAIT_TIME = 30   # How long the script will wait each time it attempts to locate an element in chrome
MAX_RETRIES = 5  # Amount of retries the script will attempt of launching chrome, or getting back into the live view if the window is no longer loading

# Construct the path to the file in the user's home directory
# Only needed if using API. Everything with #api is optional
script_start_time_file = os.path.join(os.path.expanduser('~'), 'script_start_time.txt')
# Store the start time when the script starts
with open(script_start_time_file, 'w') as f:
    f.write(str(datetime.now()))

# Check if the API is already running, start it otherwise
# api
def check_python_script():
    logging.info("Checking if API script is already running...")
    result = subprocess.run(['pgrep', '-f', 'api.py'], stdout=subprocess.PIPE)
    if result.stdout:
        logging.info("API already running.")
    else:
        logging.info("Starting API...")
        subprocess.Popen(['python3', '/usr/local/bin/api.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# Starts a chrome 'driver' and handles 3 error reattempts
def start_chrome(url):
    retry_count = 0
    max_retries = MAX_RETRIES
    while retry_count < max_retries:
        try:
            chrome_options = Options()
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-infobars")
            chrome_options.add_argument("--disable-translate")
            chrome_options.add_argument("--no-default-browser-check")
            chrome_options.add_argument("--no-first-run")
            chrome_options.add_argument("--disable-dev-smh-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument(f"--user-data-dir={chrome_data_dir}")
            chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
            chrome_options.binary_location = "/usr/bin/google-chrome-stable"
            # Add the preference to disable the "Save password" prompt
            chrome_options.add_experimental_option("prefs", {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            })
            webdriver_service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)
            driver.get(url)
            return driver
        except Exception as e:
            logging.info(f"An error occurred while starting Chrome: {e}")
            retry_count += 1
            logging.info(f"Retrying... (Attempt {retry_count} of {max_retries})")
            # If this is the final attempt, kill all existing Chrome processes
            if retry_count == max_retries:
                logging.info("Killing existing Chrome processes...")
                subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(5)  # wait for a while before retrying

    logging.info("Failed to start Chrome after maximum retries. Exiting...")
    sys.exit(1)  # exit with error code

# Waits for the fullscreen button to appear, then clicks it.
def click_fullscreen_button(driver):
    try:
        WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div.LiveviewControls__Container-sc-6n7ics-0.ihZxIP button.button__jTNy2Cxe'))
        ).click()
        logging.info("Live view is in fullscreen.")
    except TimeoutException:
        logging.info("Fullscreen button not found.")
# Waits for the specified title to appear
def wait_for_title(driver, title):
    try:
        WebDriverWait(driver, WAIT_TIME).until(EC.title_contains(title))
    except TimeoutException:
        logging.info(f"Failed to load the {title} page.")
        return False
    return True
# Checks every 5 minutes if the live view is loaded. Calls the fullscreen function if it is
# If it unloads for any reason and it can't find the live view container, it navigates to the page again
def check_view(driver, url):
    # Construct the path to the file in the user's home directory
    view_status_file = os.path.join(os.path.expanduser('~'), 'view_status.txt') #api

    def handle_retry(driver, url, attempt, max_retries):
        logging.info(f"Retrying... (Attempt {attempt} of {max_retries})")
        if attempt == max_retries - 1:
            logging.info("Refreshing page")
            driver.refresh()
            time.sleep(10) # Wait for page to refresh before retrying
        elif attempt == max_retries:
            logging.info("Killing existing Chrome processes...")
            subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(5)  # wait for a while before retrying
            logging.info("Starting chrome instance...")
            driver = start_chrome(url)
            # Wait for the page to load
            WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
            if handle_page(driver):
                logging.info("Page loaded")
        return driver

    retry_count = 0
    max_retries = MAX_RETRIES
    while True:
        try:
            # Wait for the video feeds to load
            video_feeds = WebDriverWait(driver, WAIT_TIME).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.liveview__ViewportsWrapper-xf5wrh-2"))
            )
            with open(view_status_file, 'w') as f: #api
                f.write('True') #api
            logging.info("Video feeds are present.")
            # Reset count
            retry_count = 0
            # Check if browser is in fullscreen
            screen_size = driver.get_window_size()
            if screen_size['width'] != driver.execute_script("return screen.width;") or \
               screen_size['height'] != driver.execute_script("return screen.height;"):
                logging.info("Browser is not in fullscreen, making it fullscreen")
                click_fullscreen_button(driver)
            time.sleep(SLEEP_TIME)
        except (TimeoutException, NoSuchElementException) as e:
            logging.info(f"Error: {e}")
            logging.info("Video feeds not found or other error occurred, refreshing the page.")
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            try:
                driver.get(url)
                wait_for_title(driver, "Live View | UNVR")
                click_fullscreen_button(driver)
                with open(view_status_file, 'w') as f: #api
                    f.write('True') #api
            except TimeoutException as e:
                logging.info(f"Error: {e}")
                with open(view_status_file, 'w') as f: #api
                    f.write('False') #api
                logging.info("Page load timed out.")
                retry_count += 1
                handle_retry(driver, url, retry_count, max_retries)

# Waits for the login elements to appear and inputs the username and password
# Only returns true if the page after pressing Return is the Live View
def login(driver):
    try:
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.NAME, 'username'))).send_keys(username)
        WebDriverWait(driver, WAIT_TIME).until(EC.presence_of_element_located((By.NAME, 'password'))).send_keys(password, Keys.RETURN)
        return wait_for_title(driver, "Live View | UNVR")
    except TimeoutException:
        logging.info("Failed to login, elements not found.")
        return False
# Restarts the program with execv to prevent stack overflow
def restart_program(driver):
    logging.info("Unexpected window detected, restarting...")
    driver.quit()
    os.execv(sys.executable, ['python3'] + sys.argv)
# Handles whether or not the page loaded directly or got redirected to the login page upon chrome opening
# Restarts program if unexpected results from loggin in, or opening the link.
def handle_page(driver):
    while True:
        if "Live View | UNVR" in driver.title:
            return True
        elif "Ubiquiti Account" in driver.title:
            if not login(driver):
                restart_program(driver)
        time.sleep(3)

def main():
    logging.info("Starting Fake Viewport v1.2")
    check_python_script()
    logging.info("Waiting for chrome to load...")
    driver = start_chrome(url)
    # Wait for the page to load
    WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")

    if handle_page(driver):
        # Start the check_view function in a separate thread
        threading.Thread(target=check_view, args=(driver, url)).start()


if __name__ == "__main__":
    main()