#!/usr/bin/env python3
import subprocess
import time
import threading
import os
import sys
import getpass
import configparser
import logging
import signal
from datetime import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
def install(package):
    # Check if the script is running inside a virtual environment
    if not os.getenv('VIRTUAL_ENV'):
        logging.warning("The script is not running inside a Python virtual environment. "
                        "\nStart it with: source venv/bin/activate")
        sys.exit(1)
    attempts = [
        [sys.executable, "-m", "pip", "install", package],
        [sys.executable, "-m", "pip", "install", package,
        "--trusted-host", "pypi.org",
        "--trusted-host", "files.pythonhosted.org"],
        ["pip", "install", "--user", package]  # Final fallback
    ]
    for attempt in attempts:
        try:
            subprocess.check_call(attempt)
            return True
        except subprocess.CalledProcessError:
            continue
    return False
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import InvalidSessionIdException
from urllib3.exceptions import NewConnectionError
try:
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
except ImportError:
    install('webdriver_manager')
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
def check_chrome_version():
    try:
        chrome_version = subprocess.check_output(["google-chrome-stable", "--version"]).decode('utf-8').strip()
        logging.info(f"Chrome version: {chrome_version}")
        return chrome_version.split()[-1].split('.')[0]  # Returns major version number
    except Exception as e:
        logging.error(f"Could not verify Chrome version: {e}")
        return None
config = configparser.ConfigParser()
config.read('config.ini')
# General
SLEEP_TIME = int(config.get('General', 'SLEEP_TIME', fallback=300))
WAIT_TIME = int(config.get('General', 'WAIT_TIME', fallback=30))
MAX_RETRIES = int(config.get('General', 'MAX_RETRIES', fallback=5))
# CSS Selectors. Prone to breaking with any website update Ubiquiti pushes
# Using Selenium's substring matching for better future proofing
CSS_FULLSCREEN_PARENT = config.get('CSS', 'CSS_FULLSCREEN_PARENT', fallback="div[class*='LiveviewControls__ButtonGroup']")
CSS_FULLSCREEN_BUTTON = config.get('CSS', 'CSS_FULLSCREEN_BUTTON', fallback=":nth-child(2) > button")
CSS_LOADING_DOTS = config.get('CSS', 'CSS_LOADING_DOTS', fallback="div[class*='TimedDotsLoader']")
CSS_LIVEVIEW_WRAPPER = config.get('CSS', 'CSS_LIVEVIEW_WRAPPER', fallback="div[class*='liveview__ViewportsWrapper']")
CSS_PLAYER_OPTIONS = config.get('CSS', 'CSS_PLAYER_OPTIONS', fallback="aeugT")
# Validate config variables
if SLEEP_TIME <= 0:
    logging.error("Invalid value for SLEEP_TIME. It should be a positive integer.")
    sys.exit(1)
if WAIT_TIME <= 5:
    logging.error("Invalid value for WAIT_TIME. It should be a positive integer greater than 5.")
    sys.exit(1)
if MAX_RETRIES <= 1:
    logging.error("Invalid value for MAX_RETRIES. It should be a positive integer greater than 1.")
    sys.exit(1)
# Logging
LOG_FILE = config.getboolean('Logging', 'LOG_FILE', fallback=True)
LOG_CONSOLE = config.getboolean('Logging', 'LOG_CONSOLE', fallback=True)
LOGFILE_PATH = config.get('Logging', 'LOG_FILE_PATH', fallback='~')
log_file_path = os.path.join(os.path.expanduser(LOGFILE_PATH), 'viewport.log')
# Validate LOGFILE_PATH
if not os.path.isdir(os.path.expanduser(LOGFILE_PATH)):
    logging.error(f"Invalid LOG_FILE_PATH: {LOGFILE_PATH}. The directory does not exist.")
    sys.exit(1)
# API
API = config.getboolean('API', 'USE_API', fallback=False)
API_PATH = config.get('API', 'API_FILE_PATH', fallback='~').strip()
# Validate API_PATH
if not os.path.isdir(os.path.expanduser(API_PATH)):
    logging.error(f"Invalid API_PATH: {API_PATH}. The directory does not exist.")
    sys.exit(1)
# Sets Display 0 as the display environment. Very important for selenium to launch chrome.
os.environ['DISPLAY'] = ':0'
# Chrome
user = getpass.getuser()
default_profile_path = f"/home/{user}/.config/google-chrome/Default"
CHROME_PROFILE_PATH = config.get('Chrome', 'CHROME_PROFILE_PATH', fallback=default_profile_path).strip()
CHROME_BINARY = config.get('Chrome', 'CHROME_BINARY', fallback='/usr/bin/google-chrome-stable').strip()
# Get the directory this script is in
script_dir = Path(__file__).resolve().parent
env_path = script_dir / '.env'
if not env_path.exists():
    logging.error("Missing .env file.")
    sys.exit(1)
# dotenv variables
load_dotenv()
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
url = os.getenv('URL')
driver = None # Declare it globally so that it can be accessed in the signal handler function
# Check if the URL is still the example URL
EXAMPLE_URL = "http://192.168.20.2/protect/dashboard/multiviewurl"
if url == EXAMPLE_URL:
    logging.error("The URL in the .env file is still set to the example value. Please update it to your actual URL.")
    sys.exit(1)
if not url:
    logging.error("No URL detected. Please make sure you have a .env file in the same directory as this script.")
    sys.exit(1)
logger = logging.getLogger()
formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger.setLevel(logging.INFO)
if LOG_FILE:
    #  Define a handler for the file
    file_handler = TimedRotatingFileHandler(log_file_path, when="D", interval=1, backupCount=7)
    file_handler.setLevel(logging.INFO)  # or whatever level you want for the file
    # Set the formatter for the handler
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
if LOG_CONSOLE:
    # Define a handler for the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    # Set the formatter for the handler
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
if API:
    # get the directory of the current script
    current_dir = os.path.dirname(os.path.realpath(__file__))
    # Construct the path to the file in the user's home directory
    view_status_file = os.path.join(os.path.expanduser(API_PATH), 'view_status.txt')
    script_start_time_file = os.path.join(os.path.expanduser(API_PATH), 'script_start_time.txt')
    with open(script_start_time_file, 'w') as f:
        f.write(str(datetime.now()))
    def api_status(msg):
        with open(view_status_file, 'w') as f:
            f.write(msg)
    # Check if the API is already running, start it otherwise
    def check_python_script():
        logging.info("Checking if API is already running...")
        result = subprocess.run(['pgrep', '-f', 'api.py'], stdout=subprocess.PIPE)
        if result.stdout:
            logging.info("API already running.")
        else:
            logging.info("Starting API...")
            # construct the path to api.py
            api_script = os.path.join(current_dir, 'api.py')
            subprocess.Popen(['python3', api_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
# Handles the closing of the script with CTRL+C
def signal_handler(signum, frame):
    logging.info('Gracefully shutting down Chrome.')
    if driver is not None:
        driver.quit()
    if API:
        api_status("Quit")
    logging.info("Quitting.")
    sys.exit(0)
# Register the signal handler
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
# Starts a chrome 'driver' and handles error reattempts
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
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument('--ignore-certificate-errors')  # Ignore SSL certificate errors
            chrome_options.add_argument('--ignore-ssl-errors')  # Ignore SSL errors
            chrome_options.add_argument("--hide-crash-restore-bubble")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
            chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
            chrome_options.binary_location = CHROME_BINARY
            # Add the preference to disable the "Save password" prompt
            chrome_options.add_experimental_option("prefs", {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            })
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install()),
                options=chrome_options
            )
            driver.get(url)
            return driver
        except Exception:
            logging.exception(f"An error occurred while starting Chrome: ")
            retry_count += 1
            logging.info(f"Retrying... (Attempt {retry_count} of {max_retries})")
            # If this is the final attempt, kill all existing Chrome processes
            if retry_count == max_retries:
                logging.info("Killing existing Chrome processes...")
                subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(5)  # wait for a while before retrying
    logging.info("Failed to start Chrome after maximum retries.")
    logging.info(f"Starting script again in {int(SLEEP_TIME/120)} minutes.")
    if API:
        api_status("Restarting Chrome")
    time.sleep(SLEEP_TIME/2)
    os.execv(sys.executable, ['python3'] + sys.argv)
# Finds the fullscreen button and clicks it.
def click_fullscreen_button(driver):
    try:
        # Wait for the parent container which holds the button to be present
        parent = WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, CSS_FULLSCREEN_PARENT))
        )
        # Move to the parent to trigger hover effects.
        actions = ActionChains(driver)
        actions.move_to_element(parent).perform()
        time.sleep(0.5)  # A small delay to allow UI elements to become interactive
        # Wait until the child button is visible and clickable.
        button = WebDriverWait(parent, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_FULLSCREEN_BUTTON))
        )
        actions.move_to_element(button).click().perform()
        logging.info("Fullscreen activated")
        return True
    except Exception as e:
        logging.exception("Failed to click the fullscreen button: ")
        logging.error(str(e))
        return False
# Waits for the specified title to appear
def wait_for_title(driver, title):
    try:
        WebDriverWait(driver, WAIT_TIME).until(EC.title_contains(title))
        logging.info(f"Loaded {title}")
    except TimeoutException:
        logging.exception(f"Failed to load the {title} page.")
        return False
    return True
# Checks if the "Unable to Stream" message is present in the live view
def check_unable_to_stream(driver):
    try:
        # Use JavaScript to find elements with innerHTML containing "Unable to Stream"
        elements = driver.execute_script("""
            return Array.from(document.querySelectorAll('*')).filter(el => el.innerHTML.includes('Unable to Stream'));
        """)
        if elements:
            return True
        return False
    except Exception as e:
        logging.exception("Error while checking for 'Unable to Stream' message: ")
        return False
# Checks if the live view feed is constantly loading with the three dots and needs a refresh
def check_loading_issue(driver):
    trouble_loading_start_time = None
    for _ in range(30):  # Check every second for 30 seconds
        try:
            trouble_loading = WebDriverWait(driver, 1).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, CSS_LOADING_DOTS))
            )
            if trouble_loading:
                if trouble_loading_start_time is None:
                    trouble_loading_start_time = time.time()
                elif time.time() - trouble_loading_start_time >= 15:  # if loading issue persists for 15 seconds
                    logging.info("Video feed trouble persisting for 15 seconds, refreshing the page.")
                    driver.refresh()
                    handle_page(driver)
                    time.sleep(5)
                    return  # Exit the function
        except TimeoutException:
            trouble_loading_start_time = None  # Reset the timer if the issue resolved
        time.sleep(1)
# Checks every 5 minutes if the live view is loaded. Calls the fullscreen function if it is
# If it unloads for any reason and it can't find the live view container, it navigates to the page again
def check_view(driver, url):
    def handle_retry(driver, url, attempt, max_retries):
        logging.info(f"Retrying... (Attempt {attempt} of {max_retries})")
        if API:
            api_status(f"Retrying: {attempt} of {max_retries}")
        if attempt < max_retries - 1:
            try:
                if "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
                    logging.info("Log-in page found. Inputting credentials...")
                    if login(driver):
                        if not click_fullscreen_button(driver):
                            logging.warning("Failed to activate fullscreen, but continuing anyway.")
                    if API:
                        api_status("Feed Healthy")
                else:
                    logging.info("Attempting to load page from URL.")
                    driver.get(url)
                    if handle_page(driver):
                        if not click_fullscreen_button(driver):
                            logging.warning("Failed to activate fullscreen, but continuing anyway.")
                    if API:
                        api_status("Feed Healthy")
            except InvalidSessionIdException:
                logging.error("Chrome session is invalid. Restarting the program.")
                restart_program(driver)
            except Exception as e:
                logging.exception("Error while handling retry logic: ")
                logging.error(str(e))
                if API:
                    api_status("Error refreshing")
        if attempt == max_retries - 1:
            try:
                logging.info("Killing existing Chrome processes...")
                subprocess.run(['pkill', '-f', 'chrome'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(5)
                logging.info("Starting chrome instance...")
                driver = start_chrome(url)
                WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
                if handle_page(driver):
                    logging.info("Page successfully reloaded.")
                    if API:
                        api_status("Feed Healthy")
            except Exception as e:
                logging.exception("Error killing chrome: ")
                logging.error(str(e))
                if API:
                    api_status("Error Killing Chrome")
        elif attempt == max_retries:
            logging.info("Max Attempts reached, restarting script...")
            restart_program(driver)
        return driver
    interval_counter = 0
    retry_count = 0
    max_retries = MAX_RETRIES
    if handle_page(driver):
        logging.info(f"Checking health of page every {int(SLEEP_TIME/60)} minutes...")
    else:
        logging.error("Error loading the live view. Restarting the program.")
        restart_program(driver)
    while True:
        try:
            WebDriverWait(driver, WAIT_TIME).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, CSS_LIVEVIEW_WRAPPER))
            )
            if API:
                api_status("Feed Healthy")
            retry_count = 0
            screen_size = driver.get_window_size()
            if screen_size['width'] != driver.execute_script("return screen.width;") or \
                screen_size['height'] != driver.execute_script("return screen.height;"):
                logging.info("Attempting to make live-view fullscreen.")
                if not click_fullscreen_button(driver):
                    logging.warning("Failed to activate fullscreen, but continuing anyway.")
            # Check for "Unable to Stream" message
            if check_unable_to_stream(driver):
                logging.warning("Live view contains cameras that the browser cannot decode.")
            check_loading_issue(driver)
            hide_cursor(driver)
            interval_counter += 1
            if interval_counter % 12 == 0:
                logging.info("Video feeds healthy.")
            time.sleep(SLEEP_TIME)
        except InvalidSessionIdException:
            logging.error("Chrome session is invalid. Restarting the program.")
            restart_program(driver)
        except (TimeoutException, NoSuchElementException):
            logging.exception("Video feeds not found or page timed out: ")
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except NewConnectionError:
            logging.exception("Connection error occurred: ")
            time.sleep(SLEEP_TIME/2)  # Wait for 2 minutes before retrying
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except Exception as e:
            logging.exception("Unexpected error occurred: ")
            logging.error(str(e))
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
# Waits for the login elements to appear and inputs the username and password
# Only returns true if the page after pressing Return is the Live View
def login(driver):
    try:
        # Clear and input username with explicit waits
        username_field = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.NAME, 'username'))
        )
        username_field.clear()
        username_field.send_keys(username)
        # Add small delay between fields (sometimes needed)
        time.sleep(0.5)
        # Clear and input password with explicit wait
        password_field = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.NAME, 'password'))
        )
        password_field.clear()
        password_field.send_keys(password)
        # Add another small delay before submitting
        time.sleep(0.5)
        # Find and click the Login button
        submit_button = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        submit_button.click()
        # Verify successful login
        return wait_for_title(driver, "Dashboard")
    except Exception as e:  # Catch broader exceptions
        logging.exception(f"Login failed: {str(e)}")
        return False
# Restarts the program with execv to prevent stack overflow
def restart_program(driver):
    if API:
        api_status("Restarting...")
    logging.info("Gracefully shutting down chrome...")
    driver.quit()
    if WAIT_TIME / 60 < 1:
        logging.info(f"Starting script again in {WAIT_TIME} seconds.")
    else:
        logging.info(f"Starting script again in {int(WAIT_TIME / 60)} minutes.")
    time.sleep(WAIT_TIME)
    os.execv(sys.executable, ['python3'] + sys.argv)
# Handles whether or not the page loaded directly or got redirected to the login page upon chrome opening
# Restarts program if unexpected results from logging in, or opening the link.
def handle_page(driver):
    try:
        # Wait for the page to load
        WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
    except TimeoutException:
        logging.error("Failed to load the page title. Chrome may have crashed.")
        restart_program(driver)  # Restart the script if the title doesn't load
    except Exception as e:
        logging.exception("Unexpected error occurred: ")
        logging.error(str(e))
        restart_program(driver)  # Restart if the session is invalid
    start_time = time.time()  # Capture the starting time
    while True:
        if "Dashboard" in driver.title:
            logging.info(f"{driver.title} started.")
            time.sleep(3)
            hide_cursor(driver)
            return True
        elif "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
            logging.info("Log-in page found. Inputting credentials...")
            if not login(driver):
                return False
        elif time.time() - start_time > WAIT_TIME * 2:  # If timeout limit is reached
            logging.error("Unexpected page loaded. The page title is: " + driver.title)
            return False
        time.sleep(3)
def hide_cursor(driver):
    # Removes ubiquiti's custom cursor from the page
    driver.execute_script("""
    var styleId = 'hideCursorStyle';
    if (!document.getElementById(styleId)) {
        var style = document.createElement('style');
        style.type = 'text/css';
        style.id = styleId;
        style.innerHTML = '.hMbAUy { cursor: none !important; }';
        document.head.appendChild(style);
    }
    """)
    # Remove visibility of the player options elements
    driver.execute_script("""
    var styleId = 'hidePlayerOptionsStyle';
    var cssClass = arguments[0];
    if (!document.getElementById(styleId)) {
        var style = document.createElement('style');
        style.type = 'text/css';
        style.id = styleId;
        style.innerHTML = '.' + cssClass + ' { z-index: 0 !important; }';
        document.head.appendChild(style);
    }
    """, CSS_PLAYER_OPTIONS)
def main():
    logging.info("Starting Fake Viewport v2.0.0")
    if API:
        check_python_script()
        # Defaults to 'False' until status updates
        api_status("Starting API...")
    logging.info("Waiting for chrome to load...")
    driver = start_chrome(url)
    # Start the check_view function in a separate thread
    threading.Thread(target=check_view, args=(driver, url)).start()
if __name__ == "__main__":
    main()
