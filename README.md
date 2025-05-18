<!-- [START BADGES] -->

[![Python](https://github.com/Samuel1698/fakeViewport/actions/workflows/python-test.yml/badge.svg)](https://github.com/Samuel1698/fakeViewport/actions/workflows/python-test.yml)
[![CodeQL](https://github.com/Samuel1698/fakeViewport/actions/workflows/codeql.yml/badge.svg)](https://github.com/Samuel1698/fakeViewport/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/github/Samuel1698/fakeViewport/graph/badge.svg?token=mPKJSAYXH5)](https://codecov.io/github/Samuel1698/fakeViewport)

<!-- [END BADGES] -->

# Fake Viewport

Tired of refreshing the Unifi store only to see the Viewport out of stock? Me too. So I created a $30 alternative using a **Dell Wyse Thin Client** and this script. With this setup, you can automatically and remotely launch the Protect Live View of your choosing, handle login if the session expires, recover from temporary connection issues, and resolve random webpage hiccups.

**Already running the script and want to update it? Check the [changelog](https://github.com/Samuel1698/fakeViewport/blob/main/CHANGELOG.md) for breaking changes.**


<!-- markdownlint-disable no-inline-html -->
<table><tr>
<td>Jump</td>
<td><a href="#Installation">🗃️ Download</a></td>
<td><a href="#Usage">❓ How To Use</a></td>
<td><a href="https://github.com/Samuel1698/fakeViewport/releases">🎉 Latest Release</a></td>
</tr><tr>
<td><a href="#API">🌐 API</a></td>
<td><a href="CHANGELOG.md">📋 Changelog</a></td>
<td><a href="#Update">🚀 Updating</a></td>
<td><a href="#Uninstalling">❌ Uninstall</a></td>
</tr></table>


---

## Features

- Handles login expiration and reconnects automatically.
- Detects if the console or application are offline and waits before reloading.
- Detects if your browser is running too slow and restarts it.
- Automatically clicks the full screen button and hides the cursor and controls from the cameras.
- Very robust error handling and failsafes.
- Customizable by changing the `config.ini` file.
- Easy to set up by running the `setup.sh` bash script.
- Most uptime I've seen is 6 months uninterrupted (v1.0.0). 
- Compatible with Firefox, Chrome and Chromium 
- Logs output of the terminal to logs/viewport.log for troubleshooting or checking status remotely.
- Optional API integration for remote monitoring (e.g., with [Rainmeter](https://www.rainmeter.net/)).
- API features a simple and lightweight `Viewport Control` webpage capable of displaying status of the script as well as sending commands to `Start`, `Quit`, or `Restart`. 
---

## Requirements

### Hardware
- A **Dell Wyse Thin Client** or similar device.
- Tested on:
  - Dell Wyse 5070 with Linux Mint. 
  - Dell Wyse Dx0Q with antiX Linux. (CPU Might be too weak for unifi.ui.com - Remains untested in local access)

### Software
- A lightweight Linux distribution of your choice (Preferably Debian based).
- Firefox, Chrome, Chromium installed.
- Python3
- OPTIONAL but recommended: ssh installed and configured for remote monitoring.

---

## Installation

1. **Clone the Repository**  
   Clone the repo or download your chosen zip file from the [latest release](https://github.com/Samuel1698/fakeViewport/releases).

   ```bash
   git clone https://github.com/Samuel1698/fakeViewport.git
   cd fakeViewport
   ```


2. **Optional: Minimize the directory**
   If you cloned the repository or got the `full` version of the zip file, you can save space and declutter the directory by running the `minimize.sh` script. It will remove all test and development files, `.md` files, and github specific files while leaving the script fully functional.
   ```bash
   ./minimize.sh
   ```

3. **Run the Initialization Script**  
   Execute the `setup.sh` script to set up the environment.

   ```bash
   ./setup.sh
   ```

4. **Configure the `.env` file**  
   The `setup.sh` script will rename the `.env.example` file to `.env`. 
   
   Open the `.env` file and update it with your credentials* and the URL of your Protect Live View. You can use vim or nano for this. This is also where you could put your API IP and Port, if different than the default, and where you would put the `SECRET` key if using one.

   $${\color{red}*I \space strongly \space recommend \space using \space a \space local-only \space account \space for \space this \space use \space case.}$$
   
   Here's how the .env file might look like:
   ```ini
   USERNAME=YourLocalUsername
   PASSWORD=YourLocalPassword
   URL=http://192.168.100.100/protect/dashboard/multiviewurl
   FLASK_RUN_HOST=0.0.0.0
   FLASK_RUN_PORT=5000
   SECRET=jgrkJvmTmCrF9Utt2dGAOS158Nh-sBoB_OykkAcjsh0
   ```

5. **Configure the `config.ini` file**

   Open the `config.ini` file and check what options there are available for customization of how the script runs.
   
   The script will default to using Chrome for **Profile Path** and **Browser Binary**. If you are okay with this, you do not need to change those variables in the config file. Still, might be useful to go through this step to make sure the script executes the browser from the correct path.

   #### Chrome or Chromium
   Navigate to `chrome://version/` and check the **Profile Path.** It should say something along the lines of:

   `/home/your-user/.config/chromium/Default`. 
   
   Drop the `Default` and copy the parent folder, in this case it would be `/home/your-user/.config/chromium/`. That path goes in your `BROWSER_PROFILE_PATH=` config.

   Next, look for **Command Line** in `chrome://version/` and copy the executable path without the `--flags`. For instance:
   `/usr/lib/chromium/chromium` or `/usr/bin/google-chrome-stable` and paste it next to `BROWSER_BINARY=`.
   #### Firefox

   Navigate to `about:support`, copying the **Profile Folder** path as well as the **Application Binary** path into `BROWSER_PROFILE_PATH=` and `BROWSER_BINARY=`, dropping the `Default` and the `--flags` as well.

   This is how that might look like: 
   ```ini
   # Firefox
   BROWSER_PROFILE_PATH=/home/your-user/.mozilla/firefox/
   BROWSER_BINARY=/usr/lib/firefox-esr/firefox-esr
   # Chromium
   BROWSER_PROFILE_PATH=/home/your-user/.config/chromium/
   BROWSER_BINARY=/usr/lib/chromium/chromium
   # Chrome | This is what the script will default to if unchanged
   BROWSER_PROFILE_PATH=/home/your-user/.config/google-chrome/
   BROWSER_BINARY=/usr/bin/google-chrome-stable
   ```

5. **Run the Script**  
   Run this command first to make sure everything is working
   ```bash
   viewport -h
   ```

   This command will validate the variables you have in your `.env` and `config.ini` files.
   ```bash
   viewport -d
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

## Update
If you're running an older version of the script, the easiest way to update is by running `git pull` inside the `fakeViewport` directory. If you downloaded a release manually, you can grab the latest version and unzip it over your current setup.

Any breaking changes will be clearly marked with a 💥 in the release notes and changelog, along with instructions on how to transition from the old version.

If Ubiquiti changes their page layout and breaks the script, I'll usually just update `css_selectors.py`. A quick `git pull` will be enough to get that fix, even if you're using the `minimal` or `no-api` version.

In the future, I might add an “Update” button to the dashboard itself (see [Issue #27](https://github.com/Samuel1698/fakeViewport/issues/27) for progress)

## Uninstalling
If you wish to remove all the files and changes this script makes, run the `uninstall.sh` script. Make sure you do run it in the `fakeViewport` directory.

It does the following:
   - Removes cron job if present
   - Removes alias in bashrc/zshrc if present
   - Removes Desktop shortcut if present
   - Removes all files from the directory except `.env` (in case you want a fresh re-install and want to keep the credentials and url saved.)

```shell
./uninstall.sh
```

## API
The script includes an optional API for remote monitoring. It is disabled by default. Enable it in the `config.ini` file by setting `USE_API=True` under the `[API]` section. Once enabled, run `viewport -a` to toggle the API. You can access the script's status remotely (with appropriate network permissions) by navigating to the Thin Client's IP address in your browser. For example: `http://[machine's IP]:5000`

In v2.1.5 I've included a simple page to control the script from your local network. The purpose is saving the machine's IP address to your phone/computer while on the same network as the machine. You can change the port and the IP address of the Flask server in the `.env` file.

If you wish to lock it behind a secure token/password, run this:
```python
python3 - <<EOF
import secrets
print(secrets.token_urlsafe(32))
EOF
```
and paste it in your `.env` file with the name `SECRET=`. This will serve as your password for accessing the website.

Here's how the control page looks like:

<img width="600" alt="Viewport Control Panel" src="https://github.com/user-attachments/assets/8caa3576-d761-46d3-9bf4-3eb30618fc03" />

Api Endpoints:

These endpoints display raw data, meant to be integrated into a third party tool like HomeAssistant or Rainmeter. 
```
/api
   - Displays a list of all the urls
/api/health_interval
   - Number of seconds between each 'health' check. Corresponds to SLEEP_TIME in config.ini
/api/log_entry
   - Displays the last line logged into the log file
/api/log_interval
   - Number of minutes between each 'log' entry into log file. Corresponds to LOG_INTERVAL in config.ini
/api/logs
/api/logs?limit=
   - Displays the last N logs in the logfile. Default 100
/api/ram
   - Ram Total/Used
/api/script_uptime
   - Timestamp of when the script started running
/api/status
   - Self-Reported status of the script's health
/api/next_restart
   - Datetime in which the script will restart itself
/api/system_uptime
   - Timestamp of when the system was turned on
```

---

## Notes

- The thin clients used in this setup only have DisplayPort outputs. Ensure your monitor or TV supports DisplayPort, or use a compatible adapter.
- The tested Thin Clients do not include built-in WiFi antennas. However, you can use a USB WiFi adapter to connect wirelessly, provided your network has sufficient bandwidth for the video streams.

---
