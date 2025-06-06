# Fake Viewport

<!-- [START BADGES] -->

[![Python](https://github.com/Samuel1698/fakeViewport/actions/workflows/python-test.yml/badge.svg?branch=snapshot)](https://github.com/Samuel1698/fakeViewport/actions/workflows/python-test.yml)

<!-- [END BADGES] -->

## SNAPSHOT

You are currently seeing the snapshot branch. This is where I make rapid changes and experiment with new code. If this branch is ahead of main, it is most likely broken.
Check the [latest release](https://github.com/Samuel1698/fakeViewport/releases) or go to [main](https://github.com/Samuel1698/fakeViewport/tree/main) for a stable version of the code.

---

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

- Automatically handles login expiration and reconnects.
- Detects offline status and reloads as needed.
- Restarts browser if unresponsive.
- Hides UI elements and cursor for clean display.
- Robust error handling and logging.
- Customizable via `config.ini`.
- Easy setup with `setup.sh`.
- Logs to `logs/viewport.log`.
- Compatible with Firefox, Chrome and Chromium
- Optional API for remote monitoring and control.

---

## Requirements

**Hardware:**  

- Dell Wyse Thin Client, NUC, Raspberry Pi, or similar Linux-capable device.

**Software:**

- Debian-based Linux.
- Firefox, Chrome, or Chromium.
- Python 3.
- (Optional) SSH for remote access.

---

## Installation

1. **Clone the Repository**  

   Clone the repo or download your chosen `tar.gz` file from the [latest release](https://github.com/Samuel1698/fakeViewport/releases).

   ```bash
   git clone https://github.com/Samuel1698/fakeViewport.git
   cd fakeViewport
   ```

2. **Optional: Minimize the directory**

   If you cloned the repository or got the `full` version of the `tar.gz` file, you can save space and de-clutter the directory by running the `minimize.sh` script. It will remove all test and development files, `.md` files, and github specific files while leaving the script fully functional.

   ```bash
   ./minimize.sh
   ```

3. **Run Setup**

   ```bash
   ./setup.sh
   ```

   Follow the prompt to reload your shell (`source ~/.bashrc` or `source ~/.zshrc`).

4. **Configure `.env`**

   Edit `.env` with your credentials and Protect Live View URL:

   ```ini
   USERNAME=YourLocalUsername
   PASSWORD=YourLocalPassword
   URL=http://192.168.100.100/protect/dashboard/multiviewurl
   # Optional:
   FLASK_RUN_HOST=0.0.0.0
   FLASK_RUN_PORT=5000
   SECRET=jgrkJvmTmCrF9Utt2dGAOS158Nh-sBoB_OykkAcjsh0
   ```

   ```diff
   @@ I strongly recommend using a Local Account for this @@
   ```

   The `FLASK_RUN_HOST`, `FLASK_RUN_PORT` and `SECRET` are optional. Feel free to delete them if you're not using the API.

5. **Configure the `config.ini` file**

   Open the `config.ini` file and check what options there are available for customization of how the script runs.

   The script will default to using Chrome for **Profile Path** and **Browser Binary**. If you are okay with this, you do not need to change those variables in the config file. Still, might be useful to go through this step to make sure the script executes the browser from the correct path.

   ### Chrome or Chromium

   Navigate to `chrome://version/` and check the **Profile Path.** It should say something along the lines of:

   `/home/your-user/.config/chromium/Default`.

   Drop the `Default` and copy the parent folder, in this case it would be `/home/your-user/.config/chromium/`. That path goes in your `BROWSER_PROFILE_PATH=` config.

   Next, look for **Command Line** in `chrome://version/` and copy the executable path without the `--flags`. For instance:
   `/usr/lib/chromium/chromium` or `/usr/bin/google-chrome-stable` and paste it next to `BROWSER_BINARY=`.

   ### Firefox

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

6. **Test and Run**

   ```bash
   viewport -h
   ```

   Expected Output:

   <img width="550" alt="viewport -h output" src="https://github.com/user-attachments/assets/21d97cc2-96d0-405c-8961-8f2301c96f0c" />

   This command will validate the variables you have in your `.env` and `config.ini` files.

   ```bash
   viewport -d
   ```

   Start the script using the following command:

   ```bash
   viewport
   ```

---

## <a name="usage"></a>Usage

- Run in background:

   ```bash
   viewport -b
   ```

- Show status:

   ```bash
   viewport -s
   ```

- Stop script:

   ```bash
   viewport -q
   ```

- Pause health checks:

   ```bash
   viewport -p
   ```

- View logs:

   ```bash
   viewport -l 10
   ```

- If alias doesn't work, run:

   ```bash
   venv/bin/python3 viewport.py
   ```

---

## Update

If you're running an older version of the script, the easiest way to update is through the Dashboard. An `Update` button will appear (see <a href="#API">API</a>), read the Changelog for any possible breaking changes, and click the Update button.

Note that updating through the Dashboard will also run the `minimize.sh` script and remove all the developmental/test files.

Updating manually takes opening a console, or using ssh to the machine and running `git pull` inside the `fakeViewport` directory. If you downloaded a release manually, you can grab the latest version and unzip it over your current directory.

Any breaking changes will be clearly marked with a 💥 in the release notes and changelog, along with instructions on how to transition from the old version.

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

- Enable in `config.ini` with `USE_API=True`.
- Start API:

   ```bash
   viewport -a
   ```

- Access via browser: `http://[device IP]:5000`
- Set `SECRET` in `.env` for authentication.

Generate a `SECRET` key using this:

```python
python3 - <<EOF
import secrets
print(secrets.token_urlsafe(32))
EOF
```

**Dashboard:**

<img width="678" alt="Dashboard with Update button" src="https://github.com/user-attachments/assets/f09defc5-ec47-41a0-8d97-ddd8c84df68f" />

<sup>Button will flash blue and yellow when there's an update available</sup>

### <a name="endpoints"></a>Endpoints

These endpoints display raw data, meant to be integrated into a third party tool like HomeAssistant or Rainmeter.

```pgsql
-- ======================================================================
--  Viewport REST API – route catalogue
--  Conventions
--      • All routes answer with JSON: {"status": <"ok" | "error">, ...}
--      • 200 on success, 4xx/5xx on error unless noted.
--      • Timestamps are ISO-8601 local time.
--      • Uptimes are seconds. Data is shown in Bytes. 
-- ======================================================================

-- ----------------------------------------------------------------------
-- GET /api
-- Description   List every available endpoint.
-- Response
-- {
--   "status": "ok",
--   "data": [
--     "/api/config",
--     "/api/logs",
--     ...
--   ]
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/config
-- Description   Current runtime configuration.
-- Response
-- {
--   "status": "ok",
--   "data": {
--     "browser": {
--       "binary_path": "/usr/bin/google-chrome",
--       "profile_path": "/home/user/.config/chrome",
--       "headless": false
--     },
--     "general": {
--       "health_interval_sec": 30,
--       "max_retries": 3,
--       "next_restart": "2025-06-06 03:00:00" | null,
--       "restart_times": [ "03:00", "15:00" ] | null,
--       "wait_time_sec": 10,
--     },
--     "logging": {
--       "ERROR_PRTSCR": false,
--       "debug_logging": false,
--       "error_logging": true,
--       "log_console_flag": true,
--       "log_days": 7,
--       "log_file_flag": true,
--       "log_interval_min": 60,
--     }
--   }
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/logs
-- GET /api/logs?limit=<N>
-- Description   Tail the script log (default N = 100).
-- Response
-- {
--   "status": "ok",
--   "data": {
--     "logs": [
--       "[2025-06-05 17:52:48] API started successfully",
--       ...
--     ]
--   }
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/status
-- Description   One-shot health snapshot produced by the script.
-- Response
-- {
--   "status": "ok",
--   "data": {
--     "status":       "Feed Healthy"
--   }
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/system_info
-- Description   Host statistics.
-- Response
-- {
--   "status": "ok",
--   "data": {
--     "cpu": {  
--             "cores": 8, 
--             "percent": 12.5, 
--             "threads": 16
--            },
--     "disk_available":  "123.4G",
--     "hardware_model":  "NUC12WSKi7",
--     "memory": { 
--             "percent": 19.3, 
--             "total": 16618045440, 
--             "used": 2780758016 
--             },
--     "network": {
--       "eth0": {
--         "download":    1234.18471531050941,
--         "upload":      3537.10995406011205,
--         "total_download": 67134056,
--         "total_upload": 15068848,
--         "interface": "eth0"
--       },
--       "primary_interface": {
--         "download":    1234.18471531050941,
--         "upload":      3537.10995406011205,
--         "total_download": 67134056,
--         "total_upload": 15068848,
--         "interface": "eth0"
--       },
--     },
--     "os_name":   "Debian 12 (bookworm)",
--     "system_uptime": 86400.388867378235
--   }
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/update
-- Description   Version comparison.
-- Response
-- {
--   "status": "ok",
--   "data": {
--     "current": "1.3.2",
--     "latest":  "1.4.0"
--   }
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/update/changelog
-- Description   Raw markdown changelog of the latest release.
-- Response
-- {
--   "status": "ok",
--   "data": {
--     "changelog": "# 1.4.0\n\n* Added feature X\n* Fixed bug Y\n..."
--     "release_url": "https://github.com.../releases/latest"
--   }
-- }
-- ----------------------------------------------------------------------

-- ----------------------------------------------------------------------
-- GET /api/script_uptime
-- Description   Script-level uptime in seconds.
-- Response (running)
-- {
--   "status": "ok",
--   "data": {
--     "running": true,
--     "uptime": 345.67 | null
--   }
-- }
-- ----------------------------------------------------------------------

-- End of route catalogue
```

---

## <a name="why"></a>Why Choose This?

Because this script simply displays the live view on a webpage, it has several advantages to running it over a TV App or even a real Viewport. Below is a comparison of it's advantages and disadvantages:

### Advantages

- **Vintage Point Support** - Display several consoles' cameras in a single view.
- **Enhanced Encoding** - Native TV Apps are slow to adapt enhanced encoding, but firefox supports it on Linux.
- **Cost Effective** - Less than $50 **total** as opposed to $100-$200+
- **4K Streaming** - Some native TV Apps cannot display 4K cameras.
- **WiFi Compatible** - Viewport requires wired connection.
- **No Vendor Lock-in** - AppleTV requires an AppleID to use.
- **Local & Private** - No cloud dependency; runs entirely on your local network.
- **360 Camera Support** - Protect Viewport does not support de-warping 360 camera feeds into separate views.

### Limitations

- **Initial Setup Required** – More configuration than plug-and-play alternatives
- **Larger Footprint** – Slightly bulkier than some devices (but easily hidden behind a TV/monitor)
- **Requires internet access at least once** - If you want to run it locally you must have internet access once when running the script to download the drivers to control the browser.

---

## <a name="show"></a>Showcase

<img width="550" alt="Console showing viewport -s output" src="https://github.com/user-attachments/assets/f80ae222-874c-4ffe-8327-67134a5c97a4" />

<sup>`viewport -s` output</sup>

<img width="550" alt="thin client" src="https://github.com/user-attachments/assets/cc81774c-303d-4501-991b-0365496e66b8" />

<sup>Initial install behind TV</sup>

<img width="550" alt="Full Setup" src="https://github.com/user-attachments/assets/fc5dc452-bed7-4399-9604-538c25436fa5" />

<sup>Setup at my parent's house—blurred for privacy</sup>

<img width="678" alt="Login Page" src="https://github.com/user-attachments/assets/149bd036-1bbc-4ceb-9e4f-204e66471859" />

<sup>Dashboard Login Page | Light Theme</sup>

<img width="678" alt="Status Tab" src="https://github.com/user-attachments/assets/9cdfe8f5-a62b-4d20-ab10-08452e6f2602" />

<sup>Control Panel | Status Tab | Dark Theme</sup>

<img width="678" alt="Device Tab" src="https://github.com/user-attachments/assets/7bdb2cd4-40a0-4da0-b86e-1c59491ea506" />

<sup>Control Panel | Device Tab | Light Theme</sup>

<img width="678" alt="Config Tab" src="https://github.com/user-attachments/assets/1f1167c4-5682-471e-b65b-678eaba77ad9" />

<sup>Control Panel | Config Tab | Light Theme</sup>

<img width="678" alt="Logs Tab" src="https://github.com/user-attachments/assets/cde75dd5-0428-4e25-b907-47f28a5ad771" />

<sup>Control Panel | Logs Tab | Dark Theme</sup>

---

## Notes

- The thin clients used in this setup only have DisplayPort outputs. Ensure your monitor or TV supports DisplayPort, or use a compatible adapter.
- The tested Thin Clients do not include built-in WiFi antennas. However, you can use a USB WiFi adapter to connect wirelessly. Some thin clients do include wifi.
- If you use the machine for things other than just a viewport display, make sure you do your other internet browsing in a different browser than the script uses. The browser window it launches is very limited and stripped of functionality (for better resource management), and the script will kill all other instances of the same browser when resurrecting itself.

---
