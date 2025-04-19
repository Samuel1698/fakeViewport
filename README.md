# Fake Viewport

Tired of refreshing the Unifi store only to see the Viewport out of stock? Me too. So I created a $30 alternative using a **Dell Wyse Thin Client** and this script. With this setup, you can automatically and remotely launch the Protect Live View website, handle login if the session expires, recover from temporary connection issues, and resolve random webpage hiccups.

---

## Features

- Automatically launches the Protect Live View website with your desired url.
- Handles login expiration and reconnects automatically.
- Detects and resolves temporary connection issues or webpage errors.
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

3. **Configure the `.env` File**  
   The `setup.sh` script will rename the `.env.example` file to `.env`. 
   
   Open the `.env` file and update it with your credentials and the URL of your Protect Live View. You can use vim or nano for this.

   **I strongly recommend to use a local account for this.**

4. **Run the Script**  
   Start the virtual environment:
   ```bash
    source venv/bin/activate
   ```
   Start the script using the following command:
   ```bash
    python3 viewport.py
   ```

   If running remotely or in a detached session, use:
   ```bash
    nohup python3 viewport.py > nohup.out 2>&1 &
   ```

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