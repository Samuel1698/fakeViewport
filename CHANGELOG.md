# Changelog

Note: Entries marked with "💥" indicate crucial or breaking changes that might affect your current setup. Entries marked with "🐛" indicate a bug fix, "✨" indicates an improvement,
and "🔥" indicates a non-breaking change.
## 💥🔥✨ v2.1.6: Firefox Support

💥 **If you were using a previous version of `config.ini`, the category previously known as `[Chrome]` has been changed to `[Browser]`. Either delete the old config file and re-run `./setup.sh` or edit that category manually.**
### ✨ Added
- Firefox support.
- Option for Scheduled Restarts in `config.ini`, and display it in the `--status` of the script.
- Increase testing coverage.
### 🔥Changed
- Renamed all function and tests explicitly referencing `chrome` to `browser`.
### ✨ API
- Added new endpoints: 

    `/api/logs`
    
    `/api/logs?limit=` Displays the last N entries in the log file.
    
    `/api/next_restart` Displays the next scheduled restart.
- Added `logfile` button to control panel to fetch `/api/logs` and display the last 100 log entries.

---

## ✨🐛 v2.1.5: Bug Fix & Website

### ✨ Added
- Add an explicit function to check the content of the page for common messages indicating a crashed tab on top of checking for the responsiveness of `driver`
- Add control panel website with `Start` | `Quit` | `Restart` buttons.

### 🐛 Fixed
- Fix a bug where an exception would lead to an infinite restart loop instead of being handled correctly

---

## ✨🔥🐛 v2.1.4: Small Improvements to API and logging

### ✨ Added
- Add helper function in `setup.sh` to avoid deprecated `mv -n` and sometimes incompatible `--update=None`.
- Add `HEADLESS` option in `config.ini` for development/testing purposes.
- Improve test coverage with 150 tests.

### 🔥 Changed
- Revamp monitoring.api to include most of what it's displayed in `viewport --status`
- Rework how the script handles the `script start time (sst)` file to persist between manual and automatic restarts, as the script restarting itself to deal with an error is expected behavior. 
- Split `VERBOSE_LOGGING` option into` ERROR_LOGGING` and `DEBUG_LOGGING`.

### 🐛 Fixed
- Remove WebDriverException handling from login and fullscreen functions since execution will be returned to functions that can catch it.
- Logging the (default hourly) checks to the log file now happens on the hour, instead of 1 hour upon execution of the script. 

      For different intervals it logs at an "whole" number of minutes. 
      Ex: if interval is 30, every 30 minutes at `hh:30` and `hh:00`, 
      Ex: if interval is 15, every 15 minutes at `hh:15`, `hh:30`, `hh:45`, `hh:00`

---

## ✨🔥🐛 v2.1.3: Introducing tests

### ✨ Added
- Add 100+ tests to check the script is working as intended against changes while in development (Running the tests requires activating the virtual environment)
- Add github actions to `main` branch to see the status of the latest Action run

### 🔥Changed

- Script is now fully compatible with both Chrome and Chromium
- Arguments can now either be passed as `--argument` or `-a`. For instance: `viewport -s` is the same as `viewport --status`
- Rename `--stop` to `--quit` to avoid ambiguous abbreviations
- Add CPU and Memory usage to the `--status` output
- Make desktop shortcut creation at `./setup.sh` check if it already exists before asking again, with `--shortcut` argument to override the existing one

### 🐛 Fixed
- Catch WebDriverException error when the tab crashes for faster restart of the browser instance rather than attempting to refresh the page
- Fix desktop shortcut not executing correctly in certain cases

---

## 💥✨ v2.1.0: Introducing arguments

### ✨ Script now takes the following arguments

- **--status**
Displays status information about the script
- **--background** 
Runs the script in the background
- **--restart**           
Force restarts the script (in background)
- **--stop**             
Stops the currently running script
- **--logs n**         
Displays the last n lines from the log file (default: 5)
- **--api**                
Toggles the API on or off. Requires `USE_API=True` in `config.ini`

### ✨ Added
- Added `requirements.in` with a high-level list of actual dependencies. `requirements.txt` now generated with pip-compile.
- Added `/api` folder to contain everything the script requires to one folder instead of defaulting to `~`.
- pip install in `setup.sh` now prints dots to differentiate it working in the background from crashing.

### 💥 Changed
- `setup.sh` now creates an alias for executing the script: `viewport` instead of `venv/bin/python3 viewport.py`.
- Remove virtual environment check from `viewport.py`. 
- Color coding console logs. Green is normal. Yellow is a warning. Red is an error.
- Conditional importing of `webdriver_manager` to avoid it being imported when called with arguments that don't require it.
- `api_status` is now used in the `--status` handler and is capable of displaying all the errors that can get caught by code execution.


---

## ✨🔥 v2.0.3: Reorganization

### ✨ Added:
- Explicit check for console or application offline.
- Validate config variables are within expected ranges.
- Desktop shortcut creation when running `setup.sh.`
- `LOG_INTERVAL` variable to `config.ini` to change how often the script writes it's reported status to the logfile. 

### 🔥 Changed:
- Rename most files and functions.
- `check_view` function now runs relative to the system time to prevent drifts in logging times.
- Script will self-start a virtual environment if it detects it's not running in one.
- Logs are now more accurate in terms of when they get called and what they dispaly.
- Kill other `viewport.py` and `chrome` processes when script initializes. 

---
 
## 💥🐛✨ v2.0.0: Basic script functionality updated 

### ✨ Added:

- Add `init_project.sh` script to automatically install dependencies and python environment.

### 💥 Changed:
- Move logging from `~` to script directory.
- Move CSS Selectors to `css_selectors.py` for ease of update were Ubiquiti to change these.
- Run python in a virtual environment.

### 🐛 Fixed:
- Solve Issue #3 - Unifi changed the fullscreen button html structure. Use ActionChains instead of a simple click of the button.
- Restructure functions to catch edge-cases where chrome could crash before the thread for checking page health starts.

---

## ✨🔥🐛 v1.5: Update fullscreen button css selector [OUTDATED]

### ✨ Added:
- Add chrome options to prevent certificate error popup.
- Add more descriptive status updates.
- Add better error handling and trim console messages.

### 🔥 Changed: 
- Update class name of fullscreen button.
- Move creation of API directory to beginning of the script.
- Catch generic Exception in `handle_retry`.

### 🐛 Fixed:
- `hide_cursor` function checks the presence of the hidden style before attempting to apply new one

---

## ✨🔥 v1.4: Hide the cursor

### ✨ Added: 
- Add checks for url.
- Add `hide_cursor` function.
### 🔥 Changed:
- Move all retry logic to it's own `handle_retry` function. 

---

## ✨🔥 v1.3: Error handling
### ✨ Added:
- Add more error handling when starting new session.
- Check validity of paths from config file.
- Add rotating logs handler.
- Add `config.ini`
- Add example `.env`
- Add API_PATH config variable.
### 🔥 Changed:
- Remove unused imports.
- Default API state is False.
- Use logging.exceptions instead of logging.info for errors.

---

## ✨🔥🐛 v1.2: Initial Public Release
### ✨ Added:
- Add webdriver_manager installation inside script.
- Add `check_loading_issue` function.
- Add `requirements.txt`
### 🔥 Changed: 
- Gracefully handle CTRL+C shutdown.
- Make script console-agnostic.
### 🐛 Fixed:
- Disable crash bubble on chrome.
