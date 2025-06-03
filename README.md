<!-- [START BADGES] -->

[![Python](https://github.com/Samuel1698/fakeViewport/actions/workflows/python-test.yml/badge.svg?branch=snapshot)](https://github.com/Samuel1698/fakeViewport/actions/workflows/python-test.yml)

<!-- [END BADGES] -->

# SNAPSHOT
You are currently seeing the snapshot branch. This is where I make rapid changes and experiment with new code. If this branch is ahead of main, it is most likely broken. 
Check the [latest release](https://github.com/Samuel1698/fakeViewport/releases) or go to [main](https://github.com/Samuel1698/fakeViewport/tree/main) for a stable version of the code.

---

# Fake Viewport

Tired of refreshing the Unifi store only to see the Viewport out of stock? Me too. So I created a $30 alternative using a **Dell Wyse Thin Client** and this script. The script will automatically and remotely launch the Protect Live View of your choosing, handle login if the session expires, recover from temporary connection issues, and resolve random webpage hiccups.


<!-- markdownlint-disable no-inline-html -->
<table><tr>
<td>Jump</td>
<td><a href="#Installation">🗃️ Download</a></td>
<td><a href="#usage">❓ How To Use</a></td>
<td><a href="#why">💭 Why Choose This?</a></td>
<td><a href="https://github.com/Samuel1698/fakeViewport/releases">🎉 Latest Release</a></td>
</tr><tr>
<td><a href="#API">🌐 API</a></td>
<td><a href="CHANGELOG.md">📋 Changelog</a></td>
<td><a href="#Update">🚀 Updating</a></td>
<td><a href="#Uninstalling">❌ Uninstall</a></td>
<td><a href="#show">🖼️ Showcase</a></td>

</tr></table>

---

## Features

- Handles login expiration and reconnects automatically.
- Detects if the console or application are offline and waits before reloading.
- Detects if your browser is running too slow and restarts it.
- Automatically clicks the full screen button and hides the cursor and control elements from the cameras.
- Very robust error handling and failsafe.
- Customizable by changing the `config.ini` file.
- Easy to set up by running the `setup.sh` bash script.
- Most uptime I've seen is 6 months uninterrupted (v1.0.0). 
- Compatible with Firefox, Chrome and Chromium 
- Logs output of the terminal to logs/viewport.log for troubleshooting or checking status remotely.
- Optional API integration for remote monitoring (e.g., with [Rainmeter](https://www.rainmeter.net/)).
- API features a simple and lightweight `Viewport Control` webpage capable of displaying status of the script, the log file, sending commands to `Start`, `Quit`, or `Restart` the script, and update the script to the newest version. 


---

## Requirements

### Hardware
- A **Dell Wyse Thin Client**, **NUC**, **Raspberry Pi** or a similar small computer capable of running Linux.
- Personally Tested on:
  - Dell Wyse 5070 with Linux Mint. 
  - Dell Wyse Dx0Q with antiX Linux.

### Software
- A lightweight Linux distribution of your choice (Must be Debian based).
- Firefox, Chrome, or Chromium installed.
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
   If you cloned the repository or got the `full` version of the zip file, you can save space and de-clutter the directory by running the `minimize.sh` script. It will remove all test and development files, `.md` files, and github specific files while leaving the script fully functional.
   ```bash
   ./minimize.sh
   ```

3. **Run the Initialization Script**  
   Execute the `setup.sh` script to set up the environment.

   ```bash
   ./setup.sh
   ```

   After running the setup script, you will be prompted to refresh your shell. Depending on if you're using bash or zsh, run:

   `source ~/.bashrc` or `source ~/.zshrc` (The script will tell you which).

4. **Configure the `.env` file**  
   The `setup.sh` script will rename the `.env.example` file to `.env`. 
   
   Open the `.env` file and update it with your credentials* and the URL of your Protect Live View. You can use vim or nano for this. This is also where you could put your API IP and Port, if different than the default, and where you would put the `SECRET` key if using one.

   $${\color{red}*I \space strongly \space recommend \space using \space a \space local-only \space account \space for \space this \space use \space case.}$$
   
   Here's how the .env file might look like:
   ```ini
   USERNAME=YourLocalUsername
   PASSWORD=YourLocalPassword
   URL=http://192.168.100.100/protect/dashboard/multiviewurl
   # Optional keys
   FLASK_RUN_HOST=0.0.0.0
   FLASK_RUN_PORT=5000
   SECRET=jgrkJvmTmCrF9Utt2dGAOS158Nh-sBoB_OykkAcjsh0
   ```

   The `FLASK_RUN_HOST`, `FLASK_RUN_PORT` and `SECRET` are optional. Feel free to delete them if you're not using the API.

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

## <a name="usage"></a>How To Use
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
   Alternatively, you can activate the virtual environment and run it with python3:
   ```bash
   source venv/bin/activate
   python3 viewport.py
   ```
   Most convenient way is to use the alias. Run `./setup.sh` and then reload the shell by running:
   
   `source ~/.bashrc` or `source ~/.zshrc` (The script will tell you which).


### Stopping the Script
If the script is running and you cannot use `CTRL+C` to stop it, you can call the script with the `-q` argument: 
```bash
viewport -q
```
or manually kill the process with pgrep:
```bash
ps aux | grep viewport.py
kill <pid>
```
If you wish to pause the script's health checks in order to use the computer for something else, the page will display a banner prompting you to `Pause` or `Resume` the script. You may also call the script with the `-p` or `--pause` argument:
```bash
viewport -p
```


---

## Update
If you're running an older version of the script, the easiest way to update is through the Dashboard. An `Update` button will appear (see <a href="#API">API</a>), read the Changelog for any possible breaking changes, and click the Update button. 

Note that updating through the Dashboard will also run the `minimize.sh` script and remove all the developmental/test files. 

Updating manually takes opening a console, or using ssh to the machine and running `git pull` inside the `fakeViewport` directory. If you downloaded a release manually, you can grab the latest version and unzip it over your current directory.

Any breaking changes will be clearly marked with a 💥 in the release notes and changelog, along with instructions on how to transition from the old version.

---

---

## Uninstalling
If you wish to remove all the files and changes this script makes, run the `uninstall.sh` script. Make sure you do run it in the `fakeViewport` directory.

It does the following:
   - Removes cron job if present
   - Removes alias entry in the .bashrc/.zshrc files
   - Removes Desktop shortcut if present
   - Removes all files from the directory except `.env` (in case you want a fresh re-install and want to keep the credentials and url saved.)

```shell
./uninstall.sh
```
Because this script executes in a child shell, it cannot reload the parent shell, and the alias persists. Manually type:
`unalias viewport` after running the uninstall script.

---

## API
The script includes an optional API for remote monitoring. It is disabled by default. Enable it in the `config.ini` file by setting `USE_API=True` under the `[API]` section. Once enabled, run `viewport -a` to toggle the API. You can access the script's status remotely (with appropriate network permissions) by navigating to the machine's IP address in your browser. eg: `http://[machine's IP]:5000`

The API features a Control Dashboard. 

The purpose is saving the machine's IP address to your phone/computer while on the same network. You can change the port and the IP address of the Flask server in the `.env` file.

If you wish to lock it behind a secure token/password, run this:
```python
python3 - <<EOF
import secrets
print(secrets.token_urlsafe(32))
EOF
```
Paste the output in your `.env` file with the name `SECRET=`. This will serve as your password for accessing the website.

Here's how the Dashboard looks like:

![Image](https://github.com/user-attachments/assets/f09defc5-ec47-41a0-8d97-ddd8c84df68f)

<sup>Button will flash blue and yellow when there's an update available</sup>

### <a name="endpoints"></a>Endpoints:

These endpoints display raw data, meant to be integrated into a third party tool like HomeAssistant or Rainmeter. 
```
/api | Displays a list of all the urls
/api/config | Displays all the values in your config file
   - browser
      - binary_path
      - profile_path
      - headless
   - general
      - health_interval_sec
      - wait_time_sec
      - max_retries
      - next_restart
      - restart_times
         - 0
         - 1
         ...
   - logging
      - log_interval_min
      - log_file_flag
      - log_console_flag
      - log_days
      - debug_logging
      - error_logging
      - ERROR_PRTSCR
/api/logs 
/api/logs?limit= | Displays the last N logs in the logfile. Default 100
/api/status | Self-Reported status of the script's health
/api/system_info
   - disk space available
   - hardware model
   - Operating System
   - System Uptime
   - CPU
      - cores
      - percent used
      - threads
   - RAM
      - used
      - total
      - percent used
   - network
      - interfaces
         - download
         - upload
         - total download
         - total upload
/api/update | Displays version numbers
   - current
   - latest
/api/update/changelog | Grabs the changelog from the latest release
```

---

## <a name="why"></a>Why Choose This?

Because this script simply displays the live view on a webpage, it has several advantages to running it over a TV App or even a real Viewport. Below is a comparison of it's advantages and disadvantages:

### Advantages:
  - **Vintage Point Support** - Display several consoles' cameras in a single view.
  - **Enhanced Encoding** - Native TV Apps are slow to adapt enhanced encoding, but firefox supports it on Linux.
  - **Cost Effective** - Less than $50 **total** as opposed to $100-$200+
  - **4K Streaming** - Some native TV Apps cannot display 4K cameras.
  - **WiFi Compatible** - Viewport requires wired connection.
  - **No Vendor Lock-in** - AppleTV requires an AppleID to use.
  - **Local & Private** - No cloud dependency; runs entirely on your local network.
  - **360 Camera Support** - Protect Viewport does not support de-warping 360 camera feeds into separate views.

### Limitations:
  - **Initial Setup Required** – More configuration than plug-and-play alternatives
  - **Larger Footprint** – Slightly bulkier than some devices (but easily hidden behind a TV/monitor)
  - **Requires internet access at least once** - If you want to run it locally you must have internet access once when running the script to download the drivers to control the browser.


---

## <a name="show"></a>Showcase
<img width="466" alt="Console showing viewport -s output" src="https://github.com/user-attachments/assets/f80ae222-874c-4ffe-8327-67134a5c97a4" />

<sup>`viewport -s` output</sup>

<img width="623" alt="thin client" src="https://github.com/user-attachments/assets/cc81774c-303d-4501-991b-0365496e66b8" />

<sup>Initial install behind TV</sup>

<img width="554" alt="Full Setup" src="https://github.com/user-attachments/assets/fc5dc452-bed7-4399-9604-538c25436fa5" />

<sup>Setup at my parent's house—blurred for privacy</sup>

![Image](https://github.com/user-attachments/assets/9cdfe8f5-a62b-4d20-ab10-08452e6f2602)

<sup>Control Panel | Status Tab</sup>

![Image](https://github.com/user-attachments/assets/7bdb2cd4-40a0-4da0-b86e-1c59491ea506)

<sup>Control Panel | Device Tab</sup>

![Image](https://github.com/user-attachments/assets/1f1167c4-5682-471e-b65b-678eaba77ad9)

<sup>Control Panel | Config Tab</sup>

![Image](https://github.com/user-attachments/assets/cde75dd5-0428-4e25-b907-47f28a5ad771)

<sup>Control Panel | Logs Tab</sup>

---

## Notes

- The thin clients used in this setup only have DisplayPort outputs. Ensure your monitor or TV supports DisplayPort, or use a compatible adapter.
- The tested Thin Clients do not include built-in WiFi antennas. However, you can use a USB WiFi adapter to connect wirelessly. Some thin clients do include wifi.
- If you use the machine for things other than just a viewport display, make sure you do your other internet browsing in a different browser than the script uses. The browser window it launches is very limited and stripped of functionality (for better resource management), and the script will kill all other instances of the same browser when resurrecting itself. 


---
