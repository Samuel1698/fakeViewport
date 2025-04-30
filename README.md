# SNAPSHOT
 
You are currently seeing the snapshot branch. This is where I make rapid changes and experiment with new code. If this branch is ahead of main, it is most likely broken. 
Check the [latest release](https://github.com/Samuel1698/fakeViewport/releases) or go to [main](https://github.com/Samuel1698/fakeViewport/tree/main) for a stable version of the code.

# Fake Viewport

Tired of refreshing the Unifi store only to see the Viewport out of stock? Me too. So I created a $30 alternative using a **Dell Wyse Thin Client** and this script. With this setup, you can automatically and remotely launch the Protect Live View of your choosing, handle login if the session expires, recover from temporary connection issues, and resolve random webpage hiccups.

---

## Features

- Handles login expiration and reconnects automatically.
- Detects if the console or application are offline and waits before reloading.
- Detects if chrome is running too slow and restarts it.
- Automatically clicks the full screen button and hides the cursor and controls from the cameras.
- Very robust error handling and failsafes.
- Customizable by changing the `config.ini` file.
- Easy to set up by running the `setup.sh` bash script.
- Most uptime I've seen is 6 months uninterrupted (v1.0.0). 
- Compatible with Chromium 
- Logs output of the terminal to logs/viewport.log for troubleshooting or checking status remotely.
- Optional API integration for remote monitoring (e.g., with [Rainmeter](https://www.rainmeter.net/)).

---

## Requirements

### Hardware
- A **Dell Wyse Thin Client** or similar device.
- Tested on:
  - Dell Wyse 5070 with Linux Mint. 
  - Dell Wyse Dx0Q with antiX Linux. (CPU Might be too weak for unifi.ui.com - Remains untested in local access)

### Software
- A lightweight Linux distribution of your choice (Preferably Debian based).
- Chrome or Chromium installed (Chromium preferred as it is more lightweight).
- OPTIONAL but recommended: ssh installed and configured for remote monitoring.

---

## Installation

1. **Clone the Repository**  
   Clone the repo or download the zip file from the [latest release](https://github.com/Samuel1698/fakeViewport/releases).

   ```bash
   git clone https://github.com/Samuel1698/fakeViewport.git
   cd fakeViewport
   ```

2. **Run the Initialization Script**  
   Execute the `setup.sh` script to set up the environment.

   ```bash
   ./setup.sh
   ```

3. **Configure the `.env` and `config.ini` File**  
   The `setup.sh` script will rename the `.env.example` file to `.env`. 
   
   Open the `.env` file and update it with your credentials* and the URL of your Protect Live View. You can use vim or nano for this.

   You will also see a `config.ini` file, open it and check what options there are available for customization of how the script runs.
   ```
   *I strongly recommend a local-only account for this use case.
   ```
4. **Run the Script**  
   Run this command first to make sure everything is working
   ```bash
   viewport -h
   ```

   Start the script using the following command:
   ```bash
   viewport
   ```

   If you chose to install the desktop shortcut during setup, simply click on it.
---

## Usage
   If running remotely or in a detached session (so you can close the terminal without stopping the script), use the `-b` or `--background` argument:
   ```bash
   viewport -b
   ```
   
   If you wish to see the status of the script, use the `-s` or `--status` argument:
   ```bash
   viewport -s
   ```

   If the `viewport` alias does not work, you can manually execute it with:
   ```bash
   venv/bin/python3 viewport.py
   ```
   or by activating the virtual environment and running it with python3:
   ```bash
   source venv/bin/activate
   python3 viewport.py
   ```

### Stopping the Script
If the script is running and you cannot use `CTRL+C` to stop it, you can call the script with the `-q` argument: 
```bash
viewport -q
```
```bash
python3 viewport.py -q
```
or manually kill the process with pgrep:
```bash
ps aux | grep viewport.py
kill <pid>
```

### API Integration (Optional)
The script includes an optional API for remote monitoring. It is disabled by default. Enable it in the `config.ini` file by setting `USE_API=True` under the `[API]` section. Once enabled, restart the script so you can access the script's status remotely (with appropriate network permissions) by navigating to the Thin Client's IP address in your browser. For example: `http://[machine's IP]:5000/api`

In v2.1.5 I've included a simple page to control the script from your local network. To run it, generate a secret token with python
```
python3 - <<EOF
import secrets
print(secrets.token_urlsafe(32))
EOF
```
and paste it in your `.env` file with the name `SECRET=`

Api Endpoints:
```
/api
   - Displays a list of all the urls
/health_interval
   - Number of seconds between each 'health' check. Corresponds to SLEEP_TIME in config.ini
/log_entry
   - Displays the last line logged into the log file
/log_interval
   - Number of minutes between each 'log' entry into log file. Corresponds to LOG_INTERVAL in config.ini
/ram
   - Ram Total/Used
/script_uptime
   - Timestamp of when the script started running
/status
   - Self-Reported status of the script's health
/system_uptime
   - Timestamp of when the system was turned on
```

---

## Notes

- The thin clients used in this setup only have DisplayPort outputs. Ensure your monitor or TV supports DisplayPort, or use a compatible adapter.
- The tested Thin Clients do not include built-in WiFi antennas. However, you can use a USB WiFi adapter to connect wirelessly, provided your network has sufficient bandwidth for the video streams.

---
