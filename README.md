# Fake Viewport

Tired of refreshing the Unifi store only to see the Viewport out of stock? Me too. So I created a $30 alternative using a **Dell Wyse Thin Client** and this script. With this setup, you can automatically and remotely launch the Protect Live View of your choosing, handle login if the session expires, recover from temporary connection issues, and resolve random webpage hiccups.

---

## Features

- Automatically launches the Protect LiveView of your choosing.
- Handles login expiration and reconnects automatically.
- Detects and resolves temporary connection issues or webpage errors.
- Detects if the console or application are offline and waits before reloading.
- Detects if chrome is running too slow and restarts it.
- Logs output of the terminal to logs/viewport.log for troubleshooting or checking status remotely.
- Optional API integration for remote monitoring (e.g., with [Rainmeter](https://www.rainmeter.net/)).

---

## Requirements

### Hardware
- A **Dell Wyse Thin Client** or similar device.
- Tested on:
  - Dell Wyse 5070 with Linux Mint. 
  - Dell Wyse Dx0Q with antiX Linux.

### Software
- A lightweight Linux distribution of your choice (Preferably Debian based).
- Chrome installed.
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
   *I strongly recommend to use a local ubiquiti account for this.
   ```
4. **Run the Script**  
   Start the script using the following command:
   ```bash
    python3 viewport.py
   ```

   If running remotely or in a detached session, use:
   ```bash
    nohup python3 viewport.py > nohup.out 2>&1 &
   ```

   If you chose to install the desktop shortcut during setup, simply click on it.
---

## Usage

### Stopping the Script
If the script is running and you cannot use `CTRL+C` to stop it, you can manually kill the process: 
```bash
ps aux | grep viewport.py
kill <pid>
```

### API Integration (Optional)
The script includes an optional API for remote monitoring. It is disabled by default. Enable it in the `config.ini` file by setting `USE_API=True` under the `[API]` section. Once enabled, you can access the script's status remotely (with appropriate network permissions) by navigating to the Thin Client's IP address in your browser. For example: `http://[machine's IP]:5000/admin.`

---

## Notes

- The thin clients used in this setup only have DisplayPort outputs. Ensure your monitor or TV supports DisplayPort, or use a compatible adapter.
- The tested Thin Clients do not include built-in WiFi antennas. However, you can use a USB WiFi adapter to connect wirelessly, provided your network has sufficient bandwidth for the video streams.

---