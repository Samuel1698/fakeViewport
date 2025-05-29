#!/usr/bin/venv python3
import os, psutil, sys, time, argparse, signal, subprocess
import math, threading, logging, concurrent
from logging_config                      import configure_logging
from validate_config                     import validate_config
from pathlib                             import Path
from datetime                            import datetime, timedelta
from webdriver_manager.chrome            import ChromeDriverManager
from webdriver_manager.firefox           import GeckoDriverManager
from webdriver_manager.core.os_manager   import ChromeType
from selenium                            import webdriver
from selenium.webdriver.chrome.service   import Service
from selenium.webdriver.chrome.options   import Options
from selenium.webdriver.firefox.service  import Service as FirefoxService
from selenium.webdriver.firefox.options  import Options as FirefoxOptions
from selenium.webdriver.firefox.firefox_profile import FirefoxProfile
from selenium.webdriver.common.keys      import Keys
from selenium.webdriver.common.by        import By
from selenium.webdriver.common.action_chains    import ActionChains
from selenium.webdriver.support.ui       import WebDriverWait
from selenium.webdriver.support          import expected_conditions as EC
from selenium.common.exceptions          import TimeoutException, NoSuchElementException
from selenium.common.exceptions          import InvalidSessionIdException, WebDriverException
from urllib3.exceptions                  import NewConnectionError, MaxRetryError, NameResolutionError
from css_selectors import (
    CSS_FULLSCREEN_PARENT,
    CSS_FULLSCREEN_BUTTON,
    CSS_LOADING_DOTS,
    CSS_LIVEVIEW_WRAPPER,
    CSS_PLAYER_OPTIONS,
    CSS_CURSOR
)
# ----------------------------------------------------------------------------- 
# Variable Declaration and file paths
# -------------------------------------------------------------------
_mod = sys.modules[__name__]
driver = None # Declare it globally so that it can be accessed in the signal handler function
os.environ['DISPLAY'] = ':0' # Sets Display 0 as the display environment. Very important for selenium to launch the browser.
# Directory and file paths
_base = Path(__file__).parent
config_file = _base / 'config.ini'
env_file    = _base / '.env'
logs_dir    = _base / 'logs'
api_dir     = _base / 'api'
ver_file    = api_dir / 'VERSION'
__version__ = ver_file.read_text().strip()
# Initial non strict config parsing
cfg = validate_config(strict=False, print=False)
for name, val in vars(cfg).items():
    setattr(_mod, name, val)
class DriverDownloadStuckError(Exception): pass
# Colors
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
CYAN = "\033[36m"
NC="\033[0m"
# ----------------------------------------------------------------------------- 
# Argument Handlers
# ----------------------------------------------------------------------------- 
def args_helper():
    # Parse command-line arguments for the script.
    parser = argparse.ArgumentParser(
        description=f"{YELLOW}===== Fake Viewport {__version__} ====={NC}"
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
        "-d", "--diagnose",
        action="store_true",
        dest="diagnose",
        help="Checks validity of your config and env files."
    )
    group.add_argument(
        "-a", "--api",
        action="store_true",
        dest="api",
        help="Toggles the API on or off. Requires USA_API=True in config.ini"
    )
    args, _ = parser.parse_known_args()
    return args
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
                    elif "[DEBUG]" in line:
                        colored_line = f"{CYAN}{line.strip()}{NC}"
                    elif "[ERROR]" in line:
                        colored_line = f"{RED}{line.strip()}{NC}"
                    else:
                        colored_line = f"{NC}{line.strip()}{NC}"
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
        script_path = os.path.realpath(sys.argv[0])
        subprocess.Popen(
            [sys.executable, script_path] + child_argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        sys.exit(0)
    if args.quit:
        logging.info("Stopping the Fake Viewport script...")
        process_handler("viewport.py", action="kill")
        process_handler(BROWSER, action="kill")
        clear_sst()
        sys.exit(0)
    if args.diagnose:
        logging.info("Checking validity of config.ini and .env variables...")
        diag_cfg = validate_config(strict=False)
        if diag_cfg: logging.info("No errors found.")       
        sys.exit(0)
    if args.api:
        if process_handler("monitoring.py", action="check"):
            logging.info("Stopping the API...")
            process_handler('monitoring.py', action="kill")
        elif API: api_handler()
        else: logging.info("API is not enabled in config.ini. Please set USE_API=True and restart script to use this feature.")
        sys.exit(0)
    if args.restart:
        # --restart from the CLI should kill the existing daemon
        # and spawn a fresh background instance, then exit immediately.
        if process_handler("viewport.py", action="check"):
            logging.info("Restarting script...")  
            child_argv = args_child_handler(
                args,
                drop_flags={"restart"},
                add_flags={"background": None},  # force --background on the child
            )
            script_path = os.path.realpath(sys.argv[0])
            subprocess.Popen(
                [sys.executable, script_path] + child_argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            logging.info("Viewport started in the background")
        else:
            logging.info("Fake Viewport is not running.")
        sys.exit(0)
    else:
        return "continue"
def args_child_handler(args, *, drop_flags=(), add_flags=None):
    # Returns a list of flags for a child invocation.
    # If we're dropping 'restart', force-add '--background'.
    
    # normalize drop_flags to a set
    drop = set(drop_flags or ())

    # Normalize add_flags to a dict mapping dest → override
    if add_flags is None:
        add = {}
    elif isinstance(add_flags, dict):
        add = dict(add_flags)
    else:
        add = {name: None for name in add_flags}
    # Canonical mapping of each dest to its CLI tokens
    mapping = {
        "status":     ["--status"],
        "background": ["--background"],
        "restart":    ["--restart"],
        "quit":       ["--quit"],
        "diagnose":   ["--diagnose"],
        "api":        ["--api"],
        "logs":       (["--logs", str(args.logs)] if args.logs is not None else []),
    }
    child = []
    # Re-emit any flags the user originally set,
    #    except those in drop_flags or those we’ll override via add_flags
    for dest, flags in mapping.items():
        if dest in drop or dest in add:
            continue
        if getattr(args, dest, False):
            child.extend(flags)
    # Force-add any overrides from add_flags (e.g. background after restart)
    for dest, override in add.items():
        if override is None:
            # No explicit value ⇒ use the canonical tokens
            child.extend(mapping.get(dest, [f"--{dest}"]))
        else:
            # Explicit override could be a list or single value
            if isinstance(override, (list, tuple)):
                child.extend(override)
            else:
                child.extend([f"--{dest}", str(override)])
    return child
# ----------------------------------------------------------------------------- 
# Logging setup
# ----------------------------------------------------------------------------- 
configure_logging(
    log_file_path=str(log_file),
    log_file=LOG_FILE_FLAG,
    log_console=LOG_CONSOLE,
    log_days=LOG_DAYS,
    Debug_logging=DEBUG_LOGGING
)
def log_error(message, exception=None, driver=None):
    if ERROR_LOGGING and exception:
        logging.exception(message)  # Logs the message with the stacktrace
    else:
        logging.error(message)  # Logs the message without any exception
    # Screenshot on error if driver is provided
    if driver and ERROR_PRTSCR:
        screenshot_handler(logs_dir, LOG_DAYS)
        try:
            check_driver(driver)
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            screenshot_path = logs_dir / f"screenshot_{timestamp}.png"
            driver.save_screenshot(str(screenshot_path))
            logging.info(f"Saved screenshot to {screenshot_path}")
            api_status("Saved error screenshot.")
        except (InvalidSessionIdException, WebDriverException) as e:
            logging.warning(f"Could not take screenshot: WebDriver not alive ({e})")
        except Exception as e:
            logging.warning(f"Unexpected error taking screenshot: {e}")
# ----------------------------------------------------------------------------- 
# API setup
# ----------------------------------------------------------------------------- 
def clear_sst():
    # Clear the SST file to reset uptime data on script exit or failure
    try:
        # Opening with 'w' and immediately closing truncates the file to zero length
        if sst_file.exists(): open(sst_file, 'w').close()
    except Exception as e:
        log_error("Error clearing SST file:", e)
def api_status(msg):
    # Although this function is named api_status, it is not exclusively an API function.
    # It is used to update the status of the script in a file, which is also used by the --status argument.
    with open(status_file, 'w') as f:
        f.write(msg)
def api_handler():
    if not process_handler('monitoring.py', action="check"):
        logging.info("Starting API...")
        api_script = _base / 'monitoring.py'
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
# ----------------------------------------------------------------------------- 
# Signal Handler (Closing gracefully with CTRL+C)
# ----------------------------------------------------------------------------- 
def signal_handler(signum, frame, driver=None):
    if driver is not None:
        logging.info(f'Gracefully shutting down {BROWSER}.')
        driver.quit()
    api_status("Stopped ")
    logging.info("Gracefully shutting down script instance.")
    clear_sst()
    os._exit(0)
signal.signal(signal.SIGINT, lambda s, f: signal_handler(s, f, driver))
signal.signal(signal.SIGTERM, lambda s, f: signal_handler(s, f, driver))
# ----------------------------------------------------------------------------- 
# Helper functions for getting information
# ----------------------------------------------------------------------------- 
def get_cpu_color(name, pct):
    # viewport.py & monitoring.py thresholds
    if name in ("viewport.py", "monitoring.py"):
        if pct < 1:
            return GREEN
        if pct <= 10:
            return YELLOW
        return RED
    # Browser thresholds
    if pct < 50:
        return GREEN
    if pct <= 70:
        return YELLOW
    return RED
def get_mem_color(pct):
    if pct <= 35:
        return GREEN
    if pct <= 60:
        return YELLOW
    return RED
def get_browser_version(binary_path):
    # e.g. returns "135.0.7049.95"
    out = subprocess.check_output([binary_path, "--version"], stderr=subprocess.DEVNULL)
    return out.decode().split()[1].strip()
def get_next_restart(now):
    # build the next run datetimes
    next_runs = []
    for t in RESTART_TIMES:
        run_dt = datetime.combine(now.date(), t)
        if run_dt <= now:
            run_dt += timedelta(days=1)
        next_runs.append(run_dt)
    return min(next_runs)
def get_next_interval(interval_seconds, now=None):
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
def get_driver_path(browser: str, timeout: int = 60) -> str:
    # Downloads and returns the local path to the browser driver binary.
    # Supports 'chrome', 'chromium', and 'firefox'. Raises DriverDownloadStuckError
    # if the install() call does not finish within `timeout` seconds.
    if browser in ("chrome", "chromium"):
        is_chromium = "chromium" in BROWSER_BINARY.lower()
        mgr = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM if is_chromium else ChromeType.GOOGLE)
    elif browser == "firefox":
        mgr = GeckoDriverManager()
    else:
        raise ValueError(f"Unsupported browser for driver install: {browser!r}")

    # spin up a single-worker executor
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(mgr.install)

    try:
        # this will raise concurrent.futures.TimeoutError if it’s stuck
        return future.result(timeout=timeout)

    except concurrent.futures.TimeoutError:
        msg = f"{browser.title()} driver download stuck (> {timeout}s)"
        log_error(msg)
        api_status("Driver download stuck; restart computer if it persists")
        # shut down without waiting on the hung worker thread
        executor.shutdown(wait=False)
        raise DriverDownloadStuckError(msg)

    finally:
        # ensure we always tear down the executor
        executor.shutdown(wait=False)
# ----------------------------------------------------------------------------- 
# Helper Functions for installing packages and handling processes
# ----------------------------------------------------------------------------- 
def screenshot_handler(logs_dir, max_age_days):
    #Deletes screenshot files in logs_dir older than max_age_days.
    cutoff = time.time() - (max_age_days * 86400)  # 86400 seconds in a day
    for file in logs_dir.glob("screenshot_*.png"):
        try:
            if file.stat().st_mtime < cutoff:
                file.unlink()
                logging.info(f"Deleted old screenshot: {file.name}")
                api_status("Deleted old screenshot.")
        except Exception as e:
            log_error(f"Failed to delete screenshot {file.name}: ", e)
def usage_handler(match_str):
    # Sum CPU & RSS for processes whose name or cmdline contains match_str.
    # Returns (total_cpu, total_mem_bytes).
    # build the list of substrings to look for
    names_to_match = [match_str]
    total_cpu = 0.0
    total_mem = 0
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # normalize cmdline → string
            raw = p.info.get('cmdline') or []
            cmd = " ".join(raw) if isinstance(raw, (list, tuple)) else str(raw)

            # if any of our target names appear in name or cmdline
            if any(ns in (p.info.get('name') or "") or ns in cmd for ns in names_to_match):
                # block for 100 ms so psutil can sample real CPU usage
                total_cpu += p.cpu_percent(interval=0.1)
                total_mem += p.memory_info().rss

        except Exception:
            # skip processes we can’t inspect
            continue

    return total_cpu, total_mem
def status_handler():
    # Displays the status of the script.
    # Script Version, Uptime, Status of API, config values for SLEEP and INTERVAL, and last log message
    try:
        try:
            with open(sst_file, 'r') as f:
                content = f.read().strip()
        except FileNotFoundError:
            content = ''
        if content:
            try:
                script_start_time = datetime.strptime(content, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                # malformed timestamp ⇒ treat like new
                script_start_time = datetime.now()
        else:
            # empty file ⇒ generic timestamp
            script_start_time = datetime.now()
        script_uptime = datetime.now() - script_start_time
        uptime_seconds = script_uptime.total_seconds()

        # Check if viewport and api are running
        uptime = process_handler("viewport.py", action="check")
        monitoring = process_handler("monitoring.py", action="check")
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
        # gather raw sums (each sum can exceed 100%)
        cpu_vp, mem_vp = usage_handler("viewport.py")
        cpu_mon, mem_mon = usage_handler("monitoring.py")
        cpu_ch,  mem_ch  = usage_handler(BROWSER)

        # normalize across all logical cores (so 0–100%)
        ncpus = psutil.cpu_count(logical=True) or 1
        cpu_vp  /= ncpus
        cpu_mon /= ncpus
        cpu_ch  /= ncpus

        total_ram = psutil.virtual_memory().total
        # Individual memory colors based on their percentage
        mem_vp_cl = get_mem_color(mem_vp / total_ram * 100)
        mem_mon_cl = get_mem_color(mem_mon / total_ram * 100)
        mem_ch_cl = get_mem_color(mem_ch / total_ram * 100)
        # overall RAM used
        total_used    = mem_vp + mem_mon + mem_ch
        used_pct      = total_used / total_ram * 100
        ram_color     = get_mem_color(used_pct)
        # helper to format bytes→GB
        fmt_mem = lambda b: f"{b/(1024**3):.1f}GB"
        # next health-check countdown
        next_ts = get_next_interval(SLEEP_TIME)
        secs = int(next_ts - time.time())
        hrs, rem = divmod(secs, 3600)
        mins, sc = divmod(rem, 60)
        if hrs:
            next = f"{YELLOW}{hrs}h {mins}m{NC}"
        elif mins:
            next = f"{GREEN}{mins}m {sc}s{NC}"
        else:
            next = f"{GREEN}{sc}s{NC}"
        next_str = next if uptime else f"{RED}Not Running{NC}"
        # Printing
        print(f"{YELLOW}======= Fake Viewport {__version__} ========{NC}")
        print(f"{CYAN}Script Uptime:{NC}      {uptime_str}")
        print(f"{CYAN}Monitoring API:{NC}     {monitoring_str}")
        print(f"{CYAN}Next Health Check:{NC}  {next_str}")
        print(
            f"{CYAN}RAM Used/Available:{NC} "
            f"{ram_color}{fmt_mem(total_used)}/"
            f"{fmt_mem(total_ram)}{NC}"
        )
        print(f"{CYAN}Usage:{NC}")
        # CPU & Memory usage (normalized % already applied)
        metrics = [
            ("viewport.py", "viewport", cpu_vp, mem_vp, mem_vp_cl),
            ("monitoring.py", "api",     cpu_mon, mem_mon, mem_mon_cl),
            (BROWSER,        BROWSER,  cpu_ch,  mem_ch, mem_ch_cl),
        ]
        for proc_name, label, cpu, mem, mem_color in metrics:
            # determine colors per metric
            cpu_color = get_cpu_color(proc_name, cpu)
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
                f" {CYAN}CPU:{NC} {cpu_color}{cpu:04.1f}%{NC}"
                f"   {CYAN}Mem:{NC} {mem_color}{fmt_mem(mem)}{NC}"
            )
        print(f"{CYAN}Check Health Every:{NC} {sleep_str}")
        print(f"{CYAN}Print to Log Every:{NC}{GREEN} {LOG_INTERVAL} min{NC}")
        if RESTART_TIMES:
            now = datetime.now()
            next_run = get_next_restart(now)
            print(f"{CYAN}Scheduled Restart:{NC}  {GREEN}{next_run}{NC}")
        try:
            with open(status_file, "r") as f:
                # Read the status file
                status_line = f.readlines()[-1].strip()
                # Conditionally color the status line based on its content
                if any(keyword in status_line for keyword in ["Error", "Crashed", "Timed Out", "Crash"]):
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
                lines = f.readlines()
            if not lines:
                # No entries yet in the log
                colored_log_line = (f"{RED}No log entries yet.{NC}")
            else:
                log_line = lines[-1].strip()
                # Conditionally color the log line based on its content
                if "[ERROR]" in log_line:
                    colored_log_line = f"{RED}{log_line}{NC}"
                elif "[DEBUG]" in log_line:
                    colored_log_line = f"{CYAN}{log_line}{NC}"
                elif "[WARNING]" in log_line:
                    colored_log_line = f"{YELLOW}{log_line}{NC}"
                elif "[INFO]" in log_line:
                    colored_log_line = f"{GREEN}{log_line}{NC}"
                else:
                    colored_log_line = f"{NC}{log_line}{NC}"
            print(f"{CYAN}Last Log Entry:{NC} {colored_log_line}")
        except FileNotFoundError:
            # Log file does not exist
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
        me = os.geteuid()
        current_pid = os.getpid()
        matches = []

        # prepare lowercase tokens
        lower_name   = name.lower()
        script_token = lower_name[:-3] if lower_name.endswith(".py") else lower_name

        # iterate with both name & cmdline available
        for proc in psutil.process_iter(['pid', 'name', 'uids', 'cmdline']):
            try:
                info = proc.info
                proc_name = (info.get('name') or '').lower()
                raw_cmd  = info.get('cmdline') or []
                cmd = " ".join(raw_cmd) if isinstance(raw_cmd, (list,tuple)) else str(raw_cmd)

                # match if either the exe-name or the cmdline contains our token
                if not (
                    proc_name in (lower_name, script_token)
                    or lower_name in cmd
                    or script_token in cmd
                ):
                    continue

                # only kill/check processes _you_ own
                uids = info.get('uids')
                if uids is not None and uids.real != me:
                    continue

                pid = info.get('pid')
                # skip yourself
                if pid == current_pid:
                    continue

                matches.append(pid)
                if action == "check":
                    return True

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # in "kill" mode: terminate them all
        if action == "kill" and matches:
            for pid in matches:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    logging.warning(f"Process {pid} already gone")
            pids = ', '.join(str(x) for x in matches)
            logging.info(f"Killed process '{name}' with PIDs: {pids}")
            api_status(f"Killed process '{name}'")
            return False

        return bool(matches)
    except Exception as e:
        # catch-all: log and notify API on unexpected errors
        log_error(f"Error while checking process '{name}'", e)
        api_status(f"Error Checking Process '{name}'")
        return False
def browser_handler(url):
    # Kills any browser instance, then launches a new one with the specified URL
    # Starts a browser 'driver' and handles error reattempts
    # If the driver fails to start, it will retry a few times before killing all existing browser processes and restarting the script
    process_handler(BROWSER, action="kill")
    retry_count = 0
    max_retries = MAX_RETRIES
    while retry_count < max_retries:
        # Kill before the last retry to give it a clean slate
        if retry_count == max_retries - 1:
            logging.info(f"Killing existing {BROWSER} processes before final attempt...")
            process_handler(BROWSER, action="kill")
        
        try:
            driver_path = get_driver_path(BROWSER, timeout=WAIT_TIME)
            if BROWSER in ("chrome", "chromium"):
                chrome_options = Options()
                if HEADLESS:
                    chrome_options.add_argument("--headless")
                    chrome_options.add_argument("--disable-gpu")
                    chrome_options.add_argument("--window-size=1920,1080")
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
                chrome_options.add_argument(f"--user-data-dir={BROWSER_PROFILE_PATH}")
                chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
                chrome_options.binary_location = BROWSER_BINARY
                chrome_options.add_experimental_option("prefs", {
                    "credentials_enable_service": False,
                    "profile.password_manager_enabled": False
                })
                driver = webdriver.Chrome(
                    service=Service(driver_path),
                    options=chrome_options
                )
            elif BROWSER == "firefox":
                opts = FirefoxOptions()
                if HEADLESS:
                    opts.add_argument("--headless")
                    opts.add_argument("--width=1920")
                    opts.add_argument("--height=1080")
                opts.set_preference("browser.shell.checkDefaultBrowser", False)
                opts.set_preference("browser.startup.homepage_override.mstone", "ignore")
                opts.set_preference("toolkit.telemetry.reportingpolicy.firstRun", False)
                opts.set_preference("browser.sessionstore.resume_from_crash", False)
                opts.set_preference("devtools.debugger.remote-enabled", True)
                opts.set_preference("devtools.debugger.remote-port", 9222)
                opts.set_preference("dom.webdriver.enabled", False)
                opts.set_preference("useAutomationExtension", False)
                opts.add_argument("-start-debugger-server")
                opts.set_preference("signon.rememberSignons", False)
                opts.set_preference("signon.autofillForms", False)
                opts.add_argument("-profile")
                opts.add_argument(BROWSER_PROFILE_PATH)
                opts.binary_location = BROWSER_BINARY
                opts.accept_insecure_certs = True
                service = FirefoxService(executable_path=driver_path)
                driver  = webdriver.Firefox(service=service, options=opts)
            else:
                log_error(f"Unsupported browser: {BROWSER}")
                api_status(f"Unsupported browser: {BROWSER}")
                return None
            driver.get(url)
            return driver
        except DriverDownloadStuckError:
            process_handler(BROWSER, action="kill")
            log_error(f"Error downloading {BROWSER}WebDrivers; Restart machine if it persists.")
        except NameResolutionError as e:
            # catch lower-level DNS failures
            log_error(f"DNS resolution failed while starting {BROWSER}; retrying in {int(SLEEP_TIME/2)}s", e)
            time.sleep(SLEEP_TIME/2)
        except NewConnectionError as e:
            # Connection refused
            log_error(f"Connection refused while starting {BROWSER}; regtrying in {int(SLEEP_TIME/2)}s", e)
            time.sleep(SLEEP_TIME/2)
        except MaxRetryError as e:
            # network issue resolving or fetching metadata
            log_error(f"Network issue while starting {BROWSER}; retrying in {int(SLEEP_TIME/2)}s", e)
            time.sleep(SLEEP_TIME/2)
        except Exception as e:
            log_error(f"Error starting {BROWSER}: ", e)
            api_status(f"Error Starting {BROWSER}")
        retry_count += 1
        if retry_count < max_retries:
            logging.info(f"Retrying... (Attempt {retry_count} of {max_retries})")
    log_error(f"Failed to start {BROWSER} after maximum retries.")
    logging.info(f"Starting Script again in {int(SLEEP_TIME/2)} seconds.")
    api_status(f"Restarting Script in {int(SLEEP_TIME/2)} seconds.")
    time.sleep(SLEEP_TIME/2)
    restart_handler(driver=None)
def browser_restart_handler(url):
    # Restarts browser, checks for the title and logs the result
    # This used to be in handle_retry but gets repeated in handle_view
    try:
        logging.info(f"Restarting {BROWSER}...")
        api_status(f"Restarting {BROWSER}")
        driver = browser_handler(url)
        check_for_title(driver)
        if handle_page(driver):
            logging.info("Page successfully reloaded.")
            api_status("Feed Healthy")
            time.sleep(WAIT_TIME)
        return driver
    except Exception as e:
        log_error(f"Error while killing {BROWSER} processes: ", e)
        api_status(f"Error Killing {BROWSER}")
        raise
def restart_handler(driver):
    # Reparse args
    args = args_helper()
    try:
        # notify API & shut down driver if present
        api_status("Restarting script...")
        # Mark a restart intent
        with open(restart_file, "w") as f:
            f.write("1")
        if driver is not None:
            driver.quit()
        time.sleep(2)
        child_argv = args_child_handler(
            args,
            drop_flags={"restart"},  # don’t re-daemonize when the child starts
        )
        script_path = os.path.realpath(sys.argv[0])
        # If we're in a real terminal, replace ourselves (and keep stdout/stderr)
        if sys.stdout.isatty():
            os.execv(sys.executable, [sys.executable, script_path] + child_argv)
            # (os.execv never returns on success)
        else:
            # otherwise, truly detach into the background
            subprocess.Popen(
                [sys.executable, script_path] + child_argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                start_new_session=True,
            )
            sys.exit(0) 
    except Exception as e:
        log_error("Error during restart process:", e, driver)
        api_status("Error Restarting, exiting...")
        clear_sst()
        sys.exit(1)
# ----------------------------------------------------------------------------- 
# Helper Functions for main script
# These functions return true or false but don't interact directly with the webpage
# ----------------------------------------------------------------------------- 
def check_crash(driver):
    # Explicitly checks for the message in page that come from a crashed tab
    # Would only get called if for some reason the tab crashed but driver is still responsive
    return "Aw, Snap!" in driver.page_source or "Tab Crashed" in driver.page_source
def check_driver(driver):
    # Checks if WebDriver is still alive
    # Returns True if driver is responsive, False otherwise
    try:
        driver.title  # Accessing the title will raise an exception if the driver is not alive
        return True
    except (WebDriverException, InvalidSessionIdException, Exception):
        raise
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
    except TimeoutException as e:
        if title is None:
            log_error("Timed out waiting for the page title to not be empty.", e, driver)
            api_status("Paged Timed Out")
        else:
            log_error(f"Timed out waiting for the title '{title}' to load.", e, driver)
            api_status(f"Timed Out Waiting for Title '{title}'")
        return False
    except WebDriverException:
        log_error("Tab Crashed.")
        api_status("Tab Crashed")
        return False
    except Exception as e:
        log_error(f"Error while waiting for title '{title}': ", e, driver)
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
        log_error("Error while checking for 'Unable to Stream' message: ", e, driver)
        api_status("Error Checking Unable to Stream")
        return False
# ----------------------------------------------------------------------------- 
# Interactive Functions for main logic
# These functions directly interact with the webpage
# ----------------------------------------------------------------------------- 
def handle_clear(driver, element):
    # Wipes a text-input even when the browser/password-manager has
    # pre-filled it.  Works around the fact that WebElement.clear()
    # often leaves the text selected but still present.

    # • element.clear() ................  normal Selenium clear  
    # • JS “value = ''” ................. brute-force fallback  
    # • CTRL/⌘ + A → DEL ............... belt-and-suspenders  
    try:
        element.clear()
        driver.execute_script("arguments[0].value = '';", element)
        element.send_keys(Keys.CONTROL, "a", Keys.DELETE)
    except Exception:
        # Best-effort – if this fails the subsequent send_keys will
        # still overwrite the field in most cases.
        pass
def handle_elements(driver, hide_delay_ms: int = 3000):
    # • Hides the custom UniFi cursor.
    # • Automatically *unhides* while the mouse is moving and
    #   re-hides after `hide_delay_ms` of inactivity.
    # • Hides Player-Options bar
    driver.execute_script(
        """
        (function () {
            if (window.__cursorHideInit__) return;
            window.__cursorHideInit__ = true;

            const CURSORS  = Array.isArray(arguments[0]) ? arguments[0] : [arguments[0]];
            const OPTIONS  = Array.isArray(arguments[1]) ? arguments[1] : [arguments[1]];
            const DELAY    = arguments[2];
            const STYLE_ID = 'hideCursorAndOptionsStyle';

            const cursorSel  = CURSORS.map(c => '.' + c).join(',');
            const optionSel  = OPTIONS.map(c => '.' + c).join(',');

            function addStyle() {
                if (!document.getElementById(STYLE_ID)) {
                    const s = document.createElement('style');
                    s.id = STYLE_ID;
                    s.textContent = `
                        ${cursorSel} { cursor: none !important; }
                        ${optionSel} { z-index: 0 !important; }`;
                    document.head.appendChild(s);
                }
            }
            function removeStyle() {
                const s = document.getElementById(STYLE_ID);
                if (s) s.remove();
            }

            addStyle();                       // hidden at first
            let t;
            window.addEventListener('mousemove', () => {
                removeStyle();                // show on movement
                clearTimeout(t);
                t = setTimeout(addStyle, DELAY);
            }, { passive: true });
        })();
        """,
        CSS_CURSOR,          
        CSS_PLAYER_OPTIONS,
        hide_delay_ms
    )
def handle_loading_issue(driver):
    # Checks if the loading dots are present in the live view
    # If they are, it starts a timer to check if the loading issue persists for 15 seconds and log as an error.
    # If the loading issue persists for 15 seconds, it refreshes the page and waits for it to load.
    # If the page loads successfully, it returns. Otherwise, it waits SLEEP_TIME and returns.
    trouble_loading_start_time = None
    # Do 30 “instant” checks, once per second
    for _ in range(30):
        try:
            # Instant check for the loading-dots element (no blocking wait)
            loading_elems = driver.find_elements(By.CSS_SELECTOR, CSS_LOADING_DOTS)
            has_loading = bool(loading_elems)
        except Exception as e:
            # If something goes wrong inspecting the page, treat as “no loading” 
            log_error("Error checking loading dots: ", e, driver)
            has_loading = False
            raise
        if has_loading:
            # First time we see trouble, record the time
            if trouble_loading_start_time is None:
                trouble_loading_start_time = time.time()
            # If it’s been persisting 15 s or more, handle refresh
            elif time.time() - trouble_loading_start_time >= 15:
                log_error("Video feed trouble persisting for 15 seconds, refreshing the page.", None, driver=driver)
                api_status("Loading Issue Detected")
                driver.refresh()
                time.sleep(5)  # let it load

                # Validate after refresh
                if not handle_page(driver):
                    log_error("Unexpected page loaded after refresh. Waiting before retrying...", None, driver=driver)
                    api_status("Error Reloading")
                    time.sleep(SLEEP_TIME)
                    return
                return
        else:
            # If it cleared up, reset the timer
            trouble_loading_start_time = None
        # Wait exactly 1 second before next instant check
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
    except Exception as e:
        log_error("Error while clicking the fullscreen button: ", e, driver)
        api_status("Error Clicking Fullscreen")
        return False
def handle_login(driver):
    # Handles the login process for the Ubiquiti account
    try:
        # Clear and input username with explicit waits
        username_field = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                'input[name^="user"]'      # any name that begins with "user"
            ))
        )
        handle_clear(driver, username_field)
        username_field.send_keys(username)
        # Add small delay between fields (sometimes needed)
        time.sleep(0.5)
        # Clear and input password with explicit wait
        password_field = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.NAME, 'password'))
        )
        handle_clear(driver, password_field)
        password_field.send_keys(password)
        # Add another small delay before submitting
        time.sleep(0.5)
        # Find and click the Login button
        submit_button = WebDriverWait(driver, WAIT_TIME).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        submit_button.click()
        # Verify successful login
        if check_for_title(driver, "Dashboard"):
            return True
         # If not logged in yet, look for a "Trust This Device" prompt
        try:
            trust_span = WebDriverWait(driver, WAIT_TIME).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//span[translate(normalize-space(.), "
                    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                    "'abcdefghijklmnopqrstuvwxyz')="
                    "'trust this device']"
                ))
            )
            # click its parent <button>
            btn = trust_span.find_element(By.XPATH, "./ancestor::button")
            btn.click()
            time.sleep(1)
        except TimeoutException:
            # no trust-device prompt appeared
            pass
        # One more shot at Dashboard
        return check_for_title(driver, "Dashboard")
    except Exception as e: 
        log_error("Error during login: ", e, driver)
        api_status("Error Logging In")
        return False
def handle_page(driver):
    # Handles the page loading and login process
    # It waits for the page title to load and checks if it contains "Dashboard" or "Ubiquiti Account" (login page)
    # If it contains "Dashboard", it calls the handle_elements function and returns true.
    check_for_title(driver)   # Check for non-empty title
    start_time = time.time()  # Capture the starting time
    while True:
        if "Dashboard" in driver.title:
            time.sleep(3)
            if HIDE_CURSOR: handle_elements(driver)
            return True
        elif "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
            logging.info("Log-in page found. Inputting credentials...")
            return handle_login(driver)
        elif time.time() - start_time > WAIT_TIME * 2:  # If timeout limit is reached
            log_error("Unexpected page loaded. The page title is: " + driver.title, None, driver=driver)
            api_status(f"Error Loading Page {driver.title}")
            return False
        time.sleep(3)
def handle_retry(driver, url, attempt, max_retries):
    # Handles the retry logic for the main loop
    # First checks if the title of the page indicate a login page, and if not, reloads the page.
    # If it's the second to last attempt, it kills all existing browser processes and calls browser_handler again.
    # If it's the last attempt, it restarts the script.
    logging.info(f"Retrying... (Attempt {attempt} of {max_retries})")
    api_status(f"Retrying: {attempt} of {max_retries}")
    if attempt < max_retries - 1:
        try:
            if not check_driver(driver):
                logging.warning("WebDriver crashed.")
                driver = browser_restart_handler(url)
            if "Ubiquiti Account" in driver.title or "UniFi OS" in driver.title:
                logging.info("Log-in page found. Inputting credentials...")
                handle_login(driver) and (
                handle_fullscreen_button(driver) or
                logging.warning("Failed to activate fullscreen, but continuing anyway.")
                )
                api_status("Feed Healthy")
            else:
                logging.info("Attempting to load page from URL.")
                driver.get(url)
                page_ok = handle_page(driver)
        
                 # log success or failure with one ternary; no need for an else just to log
                logging.info("Page successfully reloaded." if page_ok else "Couldn't reload page.")
        
                 # only if it succeeded do we do the fullscreen + healthy-feed status
                if page_ok:
                    time.sleep(WAIT_TIME)
                    # inline-or to fire warning if fullscreen fails
                    handle_fullscreen_button(driver) \
                        or logging.warning("Failed to activate fullscreen, but continuing anyway.")
                    api_status("Feed Healthy")
                else:
                    logging.warning("Page reload failed; skipping fullscreen and healthy-feed status.")
                    api_status("Couldn't verify feed")
        except InvalidSessionIdException as e:
            log_error(f"{BROWSER} session is invalid. Restarting the program.", e)
            api_status("Restarting Program")
            restart_handler(driver)
        except WebDriverException as e:
            log_error(f"Tab Crashed. Restarting {BROWSER}...", e)
            api_status("Tab Crashed")
            driver = browser_restart_handler(url)
        except Exception as e:
            log_error("Error while handling retry logic: ", e, driver)
            api_status("Error refreshing")
    if attempt == max_retries - 1:
        driver = browser_restart_handler(url)
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
    # how many loops between regular logs
    log_interval_iterations = round(max(LOG_INTERVAL * 60, SLEEP_TIME) / SLEEP_TIME)
    # Align the first log to the next "even" boundary:
    #   e.g. if LOG_INTERVAL=10 (minutes), we want the first
    #   log at the next multiple of 10 past the hour.
    now = datetime.now()
    if RESTART_TIMES:
        next_run = get_next_restart(now)
        logging.info(f"Next scheduled restart: {next_run}")
    else:
        next_run = None
    interval_secs = LOG_INTERVAL * 60
    secs_since_hour = now.minute * 60 + now.second
    # seconds until the next multiple of interval_secs
    secs_to_boundary = (interval_secs - (secs_since_hour % interval_secs)) % interval_secs
    # how many sleep‐cycles that is
    boundary_loops = math.ceil(secs_to_boundary / SLEEP_TIME) if secs_to_boundary > 0 else 0
    # set iteration_counter so that after `boundary_loops` loops we hit the log
    iteration_counter = log_interval_iterations - boundary_loops
    if handle_page(driver):
        logging.info(f"Checking health of page every {SLEEP_TIME} seconds...")
    else:
        log_error("Error loading the live view. Restarting the program.", None, driver=driver)
        api_status("Error Loading Live View. Restarting...")
        restart_handler(driver)
    while True:
        try:
            now = datetime.now()
            if RESTART_TIMES and next_run and now >= next_run:
                logging.info("Performing scheduled restart")
                api_status("Performing scheduled restart")
                restart_handler(driver)
            elif check_driver(driver):
                # Check for "Console Offline" or "Protect Offline"
                offline_status = driver.execute_script("""
                    return Array.from(document.querySelectorAll('span')).find(el => 
                        el.innerHTML.includes('Console Offline') || el.innerHTML.includes('Protect Offline')
                    );
                """)
                if offline_status:
                    logging.warning("Detected offline status: Console or Protect Offline.")
                    api_status("Console or Protect Offline")
                    time.sleep(WAIT_TIME)  # Wait before retrying
                    retry_count += 1
                    handle_retry(driver, url, retry_count, max_retries)
                if check_crash(driver):
                    log_error(f"Tab Crashed. Restarting {BROWSER}...", None, driver=driver)
                    api_status("Tab Crashed")
                    driver = browser_restart_handler(url)
                    continue
                WebDriverWait(driver, WAIT_TIME).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, CSS_LIVEVIEW_WRAPPER))
                )
                retry_count = 0
                screen_size = driver.get_window_size()
                if screen_size['width'] != driver.execute_script("return screen.width;") or \
                    screen_size['height'] != driver.execute_script("return screen.height;"):
                    logging.info("Attempting to make live-view fullscreen.")
                    handle_fullscreen_button(driver) \
                    or logging.warning("Failed to activate fullscreen, but continuing anyway.")
                # Check for "Unable to Stream" message
                handle_loading_issue(driver)
                if HIDE_CURSOR: handle_elements(driver)
                api_status("Feed Healthy")
                if check_unable_to_stream(driver):
                    logging.warning("Live view contains cameras that the browser cannot decode.")
                    api_status("Decoding Error in some cameras")
                if iteration_counter >= log_interval_iterations:
                    logging.info("Video feeds healthy.")
                    iteration_counter = 0  # Reset the counter
                # Calculate the time to sleep until the next health check
                # Based on the difference between the current time and the next health check time
                sleep_duration = max(0, get_next_interval(SLEEP_TIME) - time.time())
                time.sleep(sleep_duration)
                iteration_counter += 1
            else:
                log_error("Driver unresponsive.")
                api_status("Driver unresponsive")
        except InvalidSessionIdException as e:
            log_error(f"{BROWSER} session is invalid. Restarting the program.", e)
            api_status("Restarting Program")
            restart_handler(driver)
        except (TimeoutException, NoSuchElementException) as e:
            log_error("Video feeds not found or page timed out.", e, driver)
            api_status("Video Feeds Not Found")
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except (NewConnectionError, NameResolutionError, MaxRetryError) as e:
            log_error("Connection error occurred. Retrying...", e, driver)
            api_status("Connection Error")
            time.sleep(SLEEP_TIME/2)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
            time.sleep(WAIT_TIME)
        except WebDriverException as e:
            log_error(f"Tab Crashed. Restarting {BROWSER}...", e)
            api_status("Tab Crashed")
            driver = browser_restart_handler(url)
        except Exception as e:
            log_error("Unexpected error occurred: ", e, driver)
            api_status("Unexpected Error")
            time.sleep(WAIT_TIME)
            retry_count += 1
            handle_retry(driver, url, retry_count, max_retries)
# ----------------------------------------------------------------------------- 
# Main function to start the script
# ----------------------------------------------------------------------------- 
def main():
    args = args_helper()
    if args_handler(args) != "continue":
        return
    cfg = validate_config()
    for name, val in vars(cfg).items():
        setattr(_mod, name, val)
    logging.info(f"===== Fake Viewport {__version__} =====")
    if API: api_handler()
    api_status("Starting...")
    intentional_restart = restart_file.exists()
    # Inspect SST File
    sst_exists = sst_file.exists()
    sst_size   = sst_file.stat().st_size if sst_exists else 0
    sst_non_empty = sst_size > 0
    # Check existence of another running instance of viewport.py
    # Used to determine if the previous process likely crashed based on sst file content
    other_running = process_handler("viewport.py", action="check")
    crashed = (not other_running) and sst_non_empty and not intentional_restart
    # Check and kill any existing instance of viewport.py and reset the restart_file flag
    if other_running: process_handler("viewport.py", action="kill")
    if restart_file.exists(): restart_file.unlink()
    # Write the start time to the SST file
    # Only if it's empty or if a crash likely happened
    if sst_size == 0 or crashed:
        with open(sst_file, 'w') as f:
            f.write(str(datetime.now()))
    driver = browser_handler(url)
    # Start the handle_view function in a separate thread
    threading.Thread(target=handle_view, args=(driver, url)).start()
if __name__ == "__main__":
    main()
