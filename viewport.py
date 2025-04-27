#!/usr/bin/venv python3
import os
import psutil
import sys
import time
import argparse
import signal
import configparser
import getpass
import logging
import subprocess
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
# -------------------------------------------------------------------
# Variable Declaration and file paths
# -------------------------------------------------------------------
driver = None # Declare it globally so that it can be accessed in the signal handler function
_chrome_driver_path = None  # Cache for the ChromeDriver path
viewport_version = "2.1.2"
os.environ['DISPLAY'] = ':0' # Sets Display 0 as the display environment. Very important for selenium to launch chrome.
# Directory and file paths
script_dir = Path(__file__).resolve().parent
logs_dir = script_dir / 'logs'
env_dir = script_dir / '.env'
if not logs_dir.exists():
    logs_dir.mkdir(parents=True, exist_ok=True)
log_file = logs_dir / 'viewport.log'
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN = "\033[36m"
NC="\033[0m"
# -------------------------------------------------------------------
# Argument Handlers
# -------------------------------------------------------------------
def args_helper():
    # Parse command-line arguments for the script.
    parser = argparse.ArgumentParser(
        description=f"{YELLOW}===== Fake Viewport {viewport_version} ====={NC}"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-s", "--status",
        action="store_true",
        dest="status",
        help="Display status information about the script."
    )
    group.add_argument(
        "-b","--background",
        action="store_true",
        dest="background",
        help="Runs the script in the background."
    )
    group.add_argument(
        "-r", "--restart",
        action="store_true",
        dest="restart",
        help="Force restarts the script (in background)."
    )
    group.add_argument(
        "-q", "--quit",
        action="store_true",
        dest="quit",
        help="Stops the running Viewport script."
    )
    group.add_argument(
        "-l", "--logs",
        nargs="?",
        type=int,
        const=5,
        metavar="n",
        dest="logs",
        help="Display the last n lines from the log file (default: 5)."
    )
    group.add_argument(
        "-a", "--api",
        action="store_true",
        dest="api",
        help="Toggles the API on or off. Requires USA_API=True in config.ini"
    )
    return parser.parse_args()
args = args_helper()
if not any(vars(args).values()) or args.background:
    import threading
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.core.os_manager import ChromeType
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, InvalidSessionIdException, WebDriverException
    from urllib3.exceptions import NewConnectionError
    try:
        from css_selectors import (
            CSS_FULLSCREEN_PARENT,
            CSS_FULLSCREEN_BUTTON,
            CSS_LOADING_DOTS,
            CSS_LIVEVIEW_WRAPPER,
            CSS_PLAYER_OPTIONS,
            CSS_CURSOR
        )
    except ImportError:
        CSS_FULLSCREEN_PARENT = "div[class*='LiveviewControls__ButtonGroup']"
        CSS_FULLSCREEN_BUTTON = ":nth-child(2) > button"
        CSS_LOADING_DOTS = "div[class*='TimedDotsLoader']"
        CSS_LIVEVIEW_WRAPPER = "div[class*='liveview__ViewportsWrapper']"
        CSS_PLAYER_OPTIONS = "aeugT"
        CSS_CURSOR = "hMbAUy"
def args_handler(args):
    if args.status:
        status_handler()
        sys.exit(1)
    if args.logs is not None:
        try:
            with open(log_file, "r") as f:
                # Read the last X lines from the log file
                lines = f.readlines()[-args.logs:]
                for line in lines:
                    # Conditionally color the log line based on its content
                    if "[INFO]" in line:
                        colored_line = f"{GREEN}{line.strip()}{NC}"
                    elif "[WARNING]" in line:
                        colored_line = f"{YELLOW}{line.strip()}{NC}"
                    else:
                        colored_line = f"{RED}{line.strip()}{NC}"
                    print(colored_line)  # Print the colored line to the console
        except FileNotFoundError:
            print(f"{RED}Log file not found: {log_file}{NC}")
        except Exception as e:
            log_error(f"Error reading log file: {e}")
        sys.exit(0)
    if args.background:
        logging.info("Starting the script in the background...")
        child_argv = args_child_handler(
            args,
            drop_flags={"background"},  # don’t re-daemonize when the child starts
        )
        subprocess.Popen(
            [sys.executable, __file__] + child_argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        sys.exit(0)
    if args.quit:
        logging.info("Stopping the Fake Viewport script...")
        process_handler('viewport.py', action="kill")
        process_handler('chrome', action="kill")
        sys.exit(0)
    if args.api:
        if process_handler('monitoring.py', action="check"):
            logging.info("Stopping the API...")
            process_handler('monitoring.py', action="kill")
        elif API: api_handler()
        else: logging.info("API is not enabled in config.ini. Please set USE_API=True and restart script to use this feature.")
        sys.exit(0)
    if args.restart:
        logging.info("Restarting the Fake Viewport script...")
        restart_handler(driver=None)
    else:
        return "continue"
def args_child_handler(args, *, drop_flags=(), add_flags=None):
    # Returns a list of (flag, maybe:value) for restarting or backgrounding.
    # drop_flags  = a set of dest-names to omit (e.g. {"restart"} when backgrounding)
    # add_flags   = a dict of dest -> override-value to force-add
    
    # normalize drop_flags to a set
    drop = set(drop_flags or ())
    # normalize add_flags to a dict
    if add_flags is None:
        add = {}
    elif isinstance(add_flags, dict):
        add = add_flags
    else:
        # treat any sequence of names as { name: None }
        add = {name: None for name in add_flags}
    mapping = {
        "status":     ["--status"],
        "background": ["--background"],
        "restart":    ["--restart"],
        "quit":       ["--quit"],
        "api":        ["--api"],
        "logs":       ["--logs", str(args.logs)] if args.logs is not None else [],
    }
    child = []
    # 1) re-emit any flags the user originally set,
    #    except those in drop_flags *or* those we’re going to force-add
    for dest, flags in mapping.items():
        if dest in drop or dest in add:
            continue
        if getattr(args, dest):
            child.extend(flags)
    # 2) force-add any extras from add_flags (e.g. restart→background)
    for dest, override in add.items():
        # even if dest was in drop_flags, we still want to apply overrides here
        if override is None:
            # no explicit value, so use your canonical mapping or fallback
            child.extend(mapping.get(dest, [f"--{dest}"]))
        else:
            # override could be a str or list of strs
            if isinstance(override, (list, tuple)):
                child.extend(override)
            else:
                child.extend([f"--{dest}", str(override)])
    return child
# -------------------------------------------------------------------
# Config file initialization
# -------------------------------------------------------------------
config = configparser.ConfigParser()
config.read('config.ini')
# Conditional variables if code executes with no arguments or with --background
if not any(vars(args).values()) or args.background:
    user = getpass.getuser()
    default_profile_path = f"/home/{user}/.config/google-chrome/Default"
    CHROME_PROFILE_PATH = config.get('Chrome', 'CHROME_PROFILE_PATH', fallback=default_profile_path).strip()
    CHROME_BINARY = config.get('Chrome', 'CHROME_BINARY', fallback='/usr/bin/google-chrome-stable').strip()
    WAIT_TIME = int(config.get('General', 'WAIT_TIME', fallback=30))
    MAX_RETRIES = int(config.get('General', 'MAX_RETRIES', fallback=5))
SLEEP_TIME = int(config.get('General', 'SLEEP_TIME', fallback=300))
LOG_FILE = config.getboolean('Logging', 'LOG_FILE', fallback=True)
LOG_CONSOLE = config.getboolean('Logging', 'LOG_CONSOLE', fallback=True)
VERBOSE_LOGGING = config.getboolean('Logging', 'VERBOSE_LOGGING', fallback=False)
LOG_DAYS = int(config.getint('Logging', 'LOG_DAYS', fallback=7))
LOG_INTERVAL = int(config.getint('Logging', 'LOG_INTERVAL', fallback=60))
API = config.getboolean('API', 'USE_API', fallback=False)
API_PATH = config.get('API', 'API_FILE_PATH', fallback=str(script_dir / 'api')).strip()
# -------------------------------------------------------------------
# Config variables validation
# -------------------------------------------------------------------
if not any(vars(args).values()) or args.background:
    if SLEEP_TIME < 60:
        logging.error("Invalid value for SLEEP_TIME. It should be at least 60 seconds.")
        sys.exit(1)
    if WAIT_TIME <= 5:
        logging.error("Invalid value for WAIT_TIME. It should be a positive integer greater than 5.")
        sys.exit(1)
    if MAX_RETRIES < 3:
        logging.error("Invalid value for MAX_RETRIES. It should be a positive integer greater than 3.")
        sys.exit(1)
if LOG_DAYS < 1:
    logging.error("Invalid value for LOG_DAYS. It should be a positive integer greater than 0.")
    sys.exit(1)
if LOG_INTERVAL < 1:
    logging.error("Invalid value for LOG_INTERVAL. It should be a positive integer greater than 0.")
    sys.exit(1)
api_dir = Path(API_PATH)
if not api_dir.exists():
    api_dir.mkdir(parents=True, exist_ok=True)
sst_file = api_dir / 'sst.txt'
status_file = api_dir / 'status.txt'
# -------------------------------------------------------------------
# .env variables validation
# -------------------------------------------------------------------
if not env_dir.exists():
    logging.error("Missing .env file.")
    sys.exit(1)
global username, password, url
load_dotenv()
username = os.getenv('USERNAME')
password = os.getenv('PASSWORD')
url = os.getenv('URL')
EXAMPLE_URL = "http://192.168.100.100/protect/dashboard/multiviewurl"
if url == EXAMPLE_URL:
    logging.error("The URL in the .env file is still set to the example value. Please update it to your actual URL.")
    sys.exit(1)
if not url:
    logging.error("No URL detected. Please make sure you have a .env file in the same directory as this script.")
    sys.exit(1)
# -------------------------------------------------------------------
# Logging setup
# -------------------------------------------------------------------
class ColoredFormatter(logging.Formatter):
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN = "\033[36m"
    NC='\033[0m'
    def format(self, record):
        # Add colors based on the log level
        if record.levelno == logging.ERROR:
            color = self.RED
        elif record.levelno == logging.WARNING:
            color = self.YELLOW
        elif record.levelno == logging.INFO:
            color = self.GREEN
        else:
            color = self.CYAN  # Default color for other levels (e.g., DEBUG)
        # Format the message with the color
        record.msg = f"{color}{record.msg}{self.NC}"
        return super().format(record)
logger = logging.getLogger()
formatter = logging.Formatter(f'[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger.setLevel(logging.INFO)
def log_error(message, exception=None):
    if VERBOSE_LOGGING and exception:
        logging.exception(message)  # Logs the message with the stacktrace
    else:
        logging.error(message)  # Logs the message without any exception
if LOG_FILE:
    #  Define a handler for the file
    file_handler = TimedRotatingFileHandler(log_file, when="D", interval=1, backupCount=LOG_DAYS)
    file_handler.setLevel(logging.INFO)
    # Set the formatter for the handler
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
if LOG_CONSOLE:
    # Define a handler for the console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    # Set the formatter for the handler
    console_formatter = ColoredFormatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
# -------------------------------------------------------------------
# API setup
# -------------------------------------------------------------------
def api_status(msg):
    # Although this function is named api_status, it is not exclusively an API function.
    # It is used to update the status of the script in a file, which is also used by the --status argument.
    with open(status_file, 'w') as f:
        f.write(msg)
def api_handler():
    if not process_handler('monitoring.py', action="check"):
        logging.info("Starting API...")
        api_script = script_dir / 'monitoring.py'
        try:
            subprocess.Popen(
                [sys.executable, api_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True  # Detach from the terminal
            )
            api_status("Starting API...")
        except Exception as e:
            log_error("Error starting API: ", e)
            api_status("Error Starting API")
# -------------------------------------------------------------------
# Signal Handler (Closing gracefully with CTRL+C)
# -------------------------------------------------------------------
def signal_handler(signum, frame, driver=None):
    if driver is not None:
        logging.info('Gracefully shutting down Chrome.')
        driver.quit()
    api_status("Stopped ")
    logging.info("Gracefully shutting down script instance.")
    sys.exit(0)
signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, driver))
signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, driver))
# -------------------------------------------------------------------
# Helper Functions for installing packages and handling processes
# -------------------------------------------------------------------
def get_cpu_color(name, pct):
    # viewport.py & monitoring.py thresholds
    if name in ("viewport.py", "monitoring.py"):
        if pct < 1:
            return GREEN
        if pct <= 10:
            return YELLOW
        return RED
    # chrome thresholds
    if pct < 50:
        return GREEN
    if pct <= 70:
        return YELLOW
    return RED
def get_mem_color(name, mem_bytes):
    # convert to GB
    gb = mem_bytes / (1024 ** 3)
    # viewport.py & monitoring.py thresholds
    if name in ("viewport.py", "monitoring.py"):
        if gb <= 0.2:
            return GREEN
        if gb <= 0.6:
            return YELLOW
        return RED
    # chrome thresholds
    if gb < 2:
        return GREEN
    if gb <= 3.5:
        return YELLOW
    return RED
def usage_handler(match_str):
    total_cpu = 0.0
    total_mem = 0
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(p.info.get('cmdline') or [])
            if match_str in p.info.get('name', "") or match_str in cmd:
                # block for 100 ms so psutil can sample real CPU usage
                total_cpu += p.cpu_percent(interval=0.1)
                total_mem += p.memory_info().rss
        except Exception:
            continue
    return total_cpu, total_mem
def status_handler():
    # Displays the status of the script.
    # Script Version, Uptime, Status of API, config values for SLEEP and INTERVAL, and last log message
    try:
        with open(sst_file, 'r') as f:
            script_start_time = datetime.strptime(f.read(), '%Y-%m-%d %H:%M:%S.%f')
        script_uptime = datetime.now() - script_start_time
        uptime_seconds = script_uptime.total_seconds()

        # Check if viewport and api are running
        uptime = process_handler('viewport.py', action="check")
        monitoring = process_handler('monitoring.py', action="check")
        # Convert uptime_seconds to months, days, hours, minutes, and seconds
        uptime_months = int(uptime_seconds // 2592000)
        uptime_days = int(uptime_seconds // 86400)
        uptime_hours = int((uptime_seconds % 86400) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        uptime_seconds = int(uptime_seconds % 60)

        # Format the uptime string
        uptime_parts = []
        if uptime_months > 0: uptime_parts.append(f"{uptime_months}M")
        if uptime_days > 0: uptime_parts.append(f"{uptime_days}d")
        if uptime_hours > 0: uptime_parts.append(f"{uptime_hours}h")
        if uptime_minutes > 0: uptime_parts.append(f"{uptime_minutes}m")
        if uptime_seconds > 0: uptime_parts.append(f"{uptime_seconds}s")
        uptime_str = f"{GREEN}{' '.join(uptime_parts)}{NC}" if uptime else f"{RED}Not Running{NC}"
        # Check if monitoring.py is running
        monitoring_str = f"{GREEN}Running{NC}" if monitoring else f"{RED}Not Running{NC}"
        # Convert SLEEP_TIME to minutes and seconds
        sleep_minutes = SLEEP_TIME // 60
        sleep_seconds = SLEEP_TIME % 60
        sleep_parts = []
        if sleep_minutes > 0: sleep_parts.append(f"{sleep_minutes} min")
        if sleep_seconds > 0: sleep_parts.append(f"{sleep_seconds} sec")
        sleep_str = f"{GREEN}{' '.join(sleep_parts)}{NC}"
        # CPU & Memory usage
        # gather raw sums (each sum can exceed 100 %)
        cpu_vp, mem_vp = usage_handler('viewport.py')
        cpu_mon, mem_mon = usage_handler('monitoring.py')
        cpu_ch,  mem_ch  = usage_handler('chrome')

        # normalize across all logical cores (so 0–100 %)
        ncpus = psutil.cpu_count(logical=True) or 1
        cpu_vp  /= ncpus
        cpu_mon /= ncpus
        cpu_ch  /= ncpus

        total_ram = psutil.virtual_memory().total
        # helper to format bytes→GB
        fmt_mem = lambda b: f"{b/(1024**3):.1f}GB"
        # next health-check countdown
        next_ts = check_next_interval(SLEEP_TIME)
        secs = int(next_ts - time.time())
        hrs, rem = divmod(secs, 3600)
        mins, sc = divmod(rem, 60)
        if hrs:
            next = f"{YELLOW}{hrs}h {mins}m{NC}"
        elif mins:
            next = f"{GREEN}{mins}m {sc}s{NC}"
        else:
            next = f"{GREEN}{sc}s{NC}"
        next_str = next if monitoring else f"{RED}Not Running{NC}"
        # Printing
        print(f"{YELLOW}===== Fake Viewport {viewport_version} ======{NC}")
        print(f"{CYAN}Script Uptime:{NC} {uptime_str}")
        print(f"{CYAN}Monitoring API:{NC} {monitoring_str}")
        print(f"{CYAN}Usage:{NC}")
       # CPU & Memory usage (normalized % already applied)
        metrics = [
            ("viewport.py", "viewport", cpu_vp, mem_vp),
            ("monitoring.py", "api",     cpu_mon, mem_mon),
            ("chrome",        "chrome",  cpu_ch,  mem_ch),
        ]
        for proc_name, label, cpu, mem in metrics:
            # determine colors per metric
            cpu_color = get_cpu_color(proc_name, cpu)
            mem_color = get_mem_color(proc_name, mem)
            # label takes worst-case color
            if RED in (cpu_color, mem_color):
                label_color = RED
            elif YELLOW in (cpu_color, mem_color):
                label_color = YELLOW
            else:
                label_color = GREEN
            # print with colored label, CPU, and Mem
            print(
                f"  {label_color}{label:<9}{NC}"
                f" CPU: {cpu_color}{cpu:.1f}%{NC}"
                f"   Mem: {mem_color}{fmt_mem(mem)}{NC}"
            )
        print(f"{CYAN}RAM Used/Available:{NC} {fmt_mem(mem_vp+mem_mon+mem_ch)}/{fmt_mem(total_ram)}")
        print(f"{CYAN}Checking Page Health Every{NC}: {sleep_str}")
        print(f"{CYAN}Next Health Check in:{NC} {next_str}")
        print(f"{CYAN}Printing to Log Every{NC}:{GREEN} {LOG_INTERVAL} min{NC}")
        try:
            with open(status_file, "r") as f:
                # Read the status file
                status_line = f.readlines()[-1].strip()
                # Conditionally color the status line based on its content
                if any(keyword in status_line for keyword in ["Error", "Crashed", "Timed Out"]):
                    colored_status_line = f"{RED}{status_line}{NC}"
                elif any(keyword in status_line for keyword in ["Restarting", "Starting", "Stopped", "Offline"]):
                    colored_status_line = f"{YELLOW}{status_line}{NC}"
                else:
                    colored_status_line = f"{GREEN}{status_line}{NC}"  # Default to green if no other color is matched
                print(f"{CYAN}Last Status Update:{NC} {colored_status_line}")
        except FileNotFoundError:
            print(f"{RED}Status file not found.{NC}")
            log_error("Status File not found")
        try:
            with open(log_file, "r") as f:
                # Read the last line from the log file
                log_line = f.readlines()[-1].strip()
                # Conditionally color the log line based on its content
                if "[ERROR]" in log_line:
                    colored_log_line = f"{RED}{log_line}{NC}"
                elif "[WARNING]" in log_line:
                    colored_log_line = f"{YELLOW}{log_line}{NC}"
                elif "[INFO]" in log_line:
                    colored_log_line = f"{GREEN}{log_line}{NC}"
                else:
                    colored_log_line = f"{RED}{log_line}{NC}"
                print(f"{CYAN}Last Log Entry:{NC} {colored_log_line}")
        except FileNotFoundError:
            print(f"{RED}Log file not found.{NC}")
            log_error("Log File not found")
    except FileNotFoundError:
        print(f"{RED}Uptime file not found.{NC}")
        log_error("Uptime File not found")
    except Exception as e:
        log_error("Error while checking status: ", e)
def process_handler(name, action="check"):
    # Handles process management for the script. Checks if a process is running and takes action based on the specified behavior
    # Ensures the current instance is not affected if told to kill the process
    # Args: name (str): The name of the process to check (e.g., 'monitoring.py', 'viewport.py').
    # action (str): The action to take if the process is found. Options are:
    # - "check": Checks that the process is running and return True. 
    # - "kill": Kill the process if it is running (excluding the current instance).
    # Returns: bool: True if a process exists with that name, False otherwise.
    try:
        current = os.getpid()
        matches = []
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                if name in " ".join(p.info["cmdline"]):
                    pid = p.info["pid"]
                    if pid != current:
                        matches.append(pid)
                # early-exit if you just wanted to check
                if action == "check" and matches:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if action == "kill" and matches:
            for pid in matches:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    api_status(f"Process {pid} already gone")
            api_status(f"Killed process '{name}'")
            return False

        return bool(matches)
    except Exception as e:
        # catches errors from psutil.process_iter or anything above
        log_error(f"Error while checking process '{name}'", e)
        api_status(f"Error Checking Process '{name}'")
        return False
def service_handler():
    global _chrome_driver_path
    if not _chrome_driver_path:
        _chrome_driver_path = ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install()
    return _chrome_driver_path
def chrome_handler(url):
    # Kills any chrome instance, then launches a new one with the specified URL
    # Starts a chrome 'driver' and handles error reattempts
    # If the driver fails to start, it will retry a few times before killing all existing chrome processes and restarting the script
    process_handler("chrome", action="kill")
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
            chrome_options.add_argument('--ignore-certificate-errors') 
            chrome_options.add_argument('--ignore-ssl-errors')
            chrome_options.add_argument("--hide-crash-restore-bubble")
            chrome_options.add_argument("--remote-debugging-port=9222")
            chrome_options.add_argument(f"--user-data-dir={CHROME_PROFILE_PATH}")
            chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
            chrome_options.binary_location = CHROME_BINARY
            chrome_options.add_experimental_option("prefs", {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False
            })
            driver = webdriver.Chrome(service=Service(service_handler()), options=chrome_options)
            driver.get(url)
            return driver
        except Exception as e:
            log_error("Error starting Chrome: ", e)
            api_status("Error Starting Chrome")
            retry_count += 1
            logging.info(f"Retrying... (Attempt {retry_count} of {max_retries})")
            # If this is the final attempt, kill all existing Chrome processes
            if retry_count == max_retries:
                logging.info("Killing existing Chrome processes...")
                process_handler("chrome", action="kill")
            time.sleep(5)
    log_error("Failed to start Chrome after maximum retries.")
    logging.info(f"Starting Script again in {int(SLEEP_TIME/2)} seconds.")
    api_status(f"Restarting Script in {int(SLEEP_TIME/2)} seconds.")
    time.sleep(SLEEP_TIME/2)
    os.execv(sys.executable, ['python3'] + sys.argv)
def chrome_restart_handler(url):
    # Restarts chrome, checks for the title and logs the result
    # This used to be in handle_retry but gets repeated in handle_view
    try:
        logging.info("Restarting chrome...")
        api_status("Restarting Chrome")
        driver = chrome_handler(url)
        check_for_title(driver)
        if handle_page(driver):
            logging.info("Page successfully reloaded.")
            api_status("Feed Healthy")
            time.sleep(WAIT_TIME)
        return driver
    except Exception as e:
        log_error("Error while killing Chrome processes: ", e)
        api_status("Error Killing Chrome")
def restart_handler(driver):
    try:
        # 1) notify API & shut down Chrome if present
        api_status("Restarting script...")
        if driver is not None:
            driver.quit()
        time.sleep(2)

        # 2) build the new flags: drop --restart, force --background
        child_argv = args_child_handler(
            args,
            drop_flags={"restart"},
            add_flags={"background": None}
        )
        os.execv(sys.executable, [sys.executable, sys.argv[0]] + child_argv)
    except Exception as e:
        log_error("Error during restart process:", e)
        api_status("Error Restarting, exiting...")
        sys.exit(1)
# -------------------------------------------------------------------
# Helper Functions for main script
# These functions return true or false but don't interact directly with the webpage
# -------------------------------------------------------------------
def check_driver(driver):
    # Checks if WebDriver is still alive
    # Returns True if driver is responsive, False otherwise
    try:
        driver.title  # Accessing the title will raise an exception if the driver is not alive
        return True
    except (WebDriverException, Exception):
        return False
def check_next_interval(interval_seconds, now=None):
    # Calculates the next whole interval based on the current time
    # Seconds until next interval would for a time of 10:51 and interval of 5 minutes, calculate
    # 300 - (51*60 + 0) mod 300 = 240 seconds until next interval
    # Which would be 10:55
    now = now or datetime.now()
    seconds_until_next_interval = interval_seconds - (now.minute * 60 + now.second) % interval_seconds
    if seconds_until_next_interval <= 30:
        seconds_until_next_interval += interval_seconds
    next_interval = now + timedelta(seconds=seconds_until_next_interval)
    return next_interval.timestamp()
def check_for_title(driver, title=None):
    # Waits for the title of the page to contain a specific string
    # If the title is not found within the specified time, it logs an error and returns false.
    # If the title is found, it logs the title and returns true.
    try:
        if title is None:
            # Wait for the title to not be empty
            WebDriverWait(driver, WAIT_TIME).until(lambda d: d.title != "")
        else:
            # Wait for the title to contain the specified string
            WebDriverWait(driver, WAIT_TIME).until(EC.title_contains(title))
            logging.info(f"Loaded page: '{title}'")
            api_status(f"Loaded page: '{title}'")
        return True
    except TimeoutException:
        if title is None:
            log_error("Timed out waiting for the page title to not be empty.")
            api_status("Paged Timed Out")
        else:
            log_error(f"Timed out waiting for the title '{title}' to load.")
            api_status(f"Timed Out Waiting for Title '{title}'")
        return False
    except WebDriverException:
        log_error("Tab Crashed.")
        api_status("Tab Crashed")
        return False
    except Exception as e:
        log_error(f"Error while waiting for title '{title}': ", e)
        api_status(f"Error Waiting for Title '{title}'")
        return False
def check_unable_to_stream(driver):
    # Checks if the "Unable to Stream" message is present in the live view
    # If it is, it returns true. Otherwise, it returns false.
    # This function uses JavaScript to check for the presence of the message in the innerHTML of elements on the page.
    try:
        elements = driver.execute_script("""
            return Array.from(document.querySelectorAll('*')).filter(el => el.innerHTML.includes('Unable to Stream'));
        """)
        return bool(elements)
    except WebDriverException:
        log_error("Tab Crashed.")
        api_status("Tab Crashed")
        return False
    except Exception as e:
        log_error("Error while checking for 'Unable to Stream' message: ", e)
        api_status("Error Checking Unable to Stream")
        return False
# -------------------------------------------------------------------
# Interactive Functions for main logic
# These functions directly interact with the webpage
# -------------------------------------------------------------------
def handle_elements(driver):
    # Removes ubiquiti's custom cursor from the page
    driver.execute_script("""
    var styleId = 'hideCursorStyle';
    var cssClass = arguments[0];
    if (!document.getElementById(styleId)) {
        var style = document.createElement('style');
        style.type = 'text/css';
        style.id = styleId;
        style.innerHTML = '.' + cssClass + ' { cursor: none !important; }';
        document.head.appendChild(style);
    }
    """, CSS_CURSOR)
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
def handle_loading_issue(driver):
    # Checks if the loading dots are present in the live view
    # If they are, it starts a timer to check if the loading issue persists for 15 seconds and log as an error.
    # If the loading issue persists for 15 seconds, it refreshes the page and waits for it to load.
    # If the page loads successfully, it returns. Otherwise, it waits SLEEP_TIME and returns.
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
                    log_error("Video feed trouble persisting for 15 seconds, refreshing the page.")
                    logging.info("Video feed trouble persisting for 15 seconds, refreshing the page.")
                    api_status("Loading Issue Detected")
                    driver.refresh()
                    time.sleep(5)  # Allow the page to load after refresh
                    
                    # Validate the page after refresh
                    if not handle_page(driver):
                        log_error("Unexpected page loaded after refresh. Waiting before retrying...")
                        api_status("Error Reloading")
                        time.sleep(SLEEP_TIME)
                        return  # Exit the function to allow retry logic in the caller
                    return  # Exit the function if the page is valid
        except TimeoutException:
            trouble_loading_start_time = None  # Reset the timer if the issue resolved
        time.sleep(1)
def handle_fullscreen_button(driver):
    # Clicks the fullscreen button in the live view. If it fails, it will log the error and return false.
    # If it succeeds, it logs "Fullscreen activated" and returns true.
    try:
        # Wait for the parent container which holds the button to be present
        parent = WebDriverWait(driver, WAIT_TIME).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, CSS_FULLSCREEN_PARENT))
        )
        # Move to the parent to trigger hover effects.
        actions = ActionChains(driver)
        actions.move_to_element(parent).perform()
        # A small delay to allow UI elements to become interactive
        time.sleep(0.5)  
        # Wait until the child button is visible and clickable.
        button = WebDriverWait(parent, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_FULLSCREEN_BUTTON))
        )
        actions.move_to_element(button).click().perform()
        logging.info("Fullscreen activated")
        api_status("Fullscreen Activated")
        return True
    except WebDriverException:
        log_error("Tab Crashed. Restarting Chrome...")
        api_status("Tab Crashed")
        driver = chrome_restart_handler(url)
    except Exception as e:
        log_error("Error while clicking the fullscreen button: ", e)
        api_status("Error Clicking Fullscreen")
        return False
def handle_login(driver):
    # Handles the login process for the Ubiquiti account
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
        return check_for_title(driver, "Dashboard")
    except WebDriverException:
        log_error("Tab Crashed. Restarting Chrome...")
        api_status("Tab Crashed")
        driver = chrome_restart_handler(url)
    except Exception as e: 
        log_error("Error during login: ", e)
        api_status("Error Logging In")
        return False
def handle_page(driver):
    # Handles the page loading and login process
    # It waits for the page title to load and checks if it contains "Dashboard" or "Ubiquiti Account" (login page)
    # If it contains "Dashboard", it calls the handle_elements function and returns true.
    check_for_title(driver)
    start_time = time.time()  # Capture the starting time
    while True:
        if "Dashboard" in driver.title:
            time.sleep(3)
            handle_elements(driver)
            return True
        elif "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
            logging.info("Log-in page found. Inputting credentials...")
            if not handle_login(driver):
                return False
        elif time.time() - start_time > WAIT_TIME * 2:  # If timeout limit is reached
            log_error("Unexpected page loaded. The page title is: " + driver.title)
            api_status(f"Error Loading Page {driver.title}")
            return False
        time.sleep(3)
def handle_retry(driver, url, attempt, max_retries):
    # Handles the retry logic for the main loop
    # First checks if the title of the page indicate a login page, and if not, reloads the page.
    # If it's the second to last attempt, it kills all existing Chrome processes and calls chrome_handler again.
    # If it's the last attempt, it restarts the script.
    logging.info(f"Retrying... (Attempt {attempt} of {max_retries})")
    api_status(f"Retrying: {attempt} of {max_retries}")
    if attempt < max_retries - 1:
        try:
            if not check_driver(driver):
                logging.warning("WebDriver crashed.")
                driver = chrome_restart_handler(url)
            if "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
                logging.info("Log-in page found. Inputting credentials...")
                if handle_login(driver):
                    if not handle_fullscreen_button(driver):
                        logging.warning("Failed to activate fullscreen, but continuing anyway.")
                api_status("Feed Healthy")
            else:
                logging.info("Attempting to load page from URL.")
                driver.get(url)
                if handle_page(driver):
                    logging.info("Page successfully reloaded.")
                    time.sleep(WAIT_TIME)
                    if not handle_fullscreen_button(driver):
                        logging.warning("Failed to activate fullscreen, but continuing anyway.")
                api_status("Feed Healthy")
        except InvalidSessionIdException:
            log_error("Chrome session is invalid. Restarting the program.")
            api_status("Restarting Program")
            restart_handler(driver)
        except WebDriverException:
            log_error("Tab Crashed. Restarting Chrome...")
            api_status("Tab Crashed")
            driver = chrome_restart_handler(url)
        except Exception as e:
            log_error("Error while handling retry logic: ", e)
            api_status("Error refreshing")
    if attempt == max_retries - 1:
        driver = chrome_restart_handler(url)
    elif attempt == max_retries:
        logging.info("Max Attempts reached, restarting script...")
        api_status("Max Attempts Reached, restarting script")
        restart_handler(driver)
    return driver
def handle_view(driver, url):
    # Main process that checks the health of the live view
    # It checks first for a truthy return of handle_page function, then checks "Console Offline" or "Protect Offline" messages.
    # It's main check is of the CSS_LIVEVIEW_WRAPPER element, which is the main wrapper for the live view.
    # While on the main loop, it calls the handle_retry, handle_fullscreen_button, check_unable_to_stream handle_loading_issue, and handle_elements functions.
    retry_count = 0
    max_retries = MAX_RETRIES
    # Calculate how many iterations correspond to one LOG_INTERVAL
    log_interval_iterations = max(1, round((LOG_INTERVAL * 60) / SLEEP_TIME))
    iteration_counter = 0
    if handle_page(driver):
        logging.info(f"Checking health of page every {SLEEP_TIME} seconds...")
    else:
        log_error("Error loading the live view. Restarting the program.")
        api_status("Error Loading Live View. Restarting...")
        restart_handler(driver)
    while True:
        try:
            if not check_driver(driver):
                logging.warning("WebDriver crashed.")
                driver = chrome_restart_handler(url)
            # Check for "Console Offline" or "Protect Offline"
            offline_status = driver.execute_script("""
                return Array.from(document.querySelectorAll('span')).find(el => 
                    el.innerHTML.includes('Console Offline') || el.innerHTML.includes('Protect Offline')
                );
            """)
            if offline_status:
                logging.warning("Detected offline status: Console or Protect Offline.")
                api_status("Console or Protect Offline")
                time.sleep(SLEEP_TIME)  # Wait before retrying
                retry_count += 1
                handle_retry(driver, url, retry_count, max_retries)
            WebDriverWait(driver, WAIT_TIME).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, CSS_LIVEVIEW_WRAPPER))
            )
            retry_count = 0
            screen_size = driver.get_window_size()
            if screen_size['width'] != driver.execute_script("return screen.width;") or \
                screen_size['height'] != driver.execute_script("return screen.height;"):
                logging.info("Attempting to make live-view fullscreen.")
                if not handle_fullscreen_button(driver):
                    logging.warning("Failed to activate fullscreen, but continuing anyway.")
            # Check for "Unable to Stream" message
            handle_loading_issue(driver)
            handle_elements(driver)
            api_status("Feed Healthy")
            if check_unable_to_stream(driver):
                logging.warning("Live view contains cameras that the browser cannot decode.")
                api_status("Decoding Error in some cameras")
            if iteration_counter >= log_interval_iterations:
                logging.info("Video feeds healthy.")
                iteration_counter = 0  # Reset the counter
            # Calculate the time to sleep until the next health check
            # Based on the difference between the current time and the next health check time
            sleep_duration = max(0, check_next_interval(SLEEP_TIME) - time.time())
            time.sleep(sleep_duration)
            iteration_counter += 1
        except InvalidSessionIdException:
            log_error("Chrome session is invalid. Restarting the program.")
            api_status("Restarting Program")
            restart_handler(driver)
        except (TimeoutException, NoSuchElementException):
            log_error("Video feeds not found or page timed out.")
            api_status("Video Feeds Not Found")
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except NewConnectionError:
            log_error("Connection error occurred. Retrying...")
            api_status("Connection Error")
            time.sleep(SLEEP_TIME/2)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except WebDriverException:
            log_error("Tab Crashed. Restarting Chrome...")
            api_status("Tab Crashed")
            driver = chrome_restart_handler(url)
        except Exception as e:
            log_error("Unexpected error occurred: ", e)
            api_status("Unexpected Error")
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
# -------------------------------------------------------------------
# Main function to start the script
# -------------------------------------------------------------------
def main():
    if args_handler(args) == "continue":
        logging.info(f"===== Fake Viewport {viewport_version} =====")
        if API: api_handler()
        api_status("Starting...")
        # Check and kill any existing instance of viewport.py
        process_handler('viewport.py', action="kill")
        # Write the start time to the SST file
        with open(sst_file, 'w') as f: f.write(str(datetime.now()))
        driver = chrome_handler(url)
        # Start the handle_view function in a separate thread
        threading.Thread(target=handle_view, args=(driver, url)).start()
if __name__ == "__main__":
    main()
