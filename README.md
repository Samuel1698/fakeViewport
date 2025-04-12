# Important!

This code is out of date and will not receive any update until June 2025. It has not received any update since Ubiquiti started mandating 2FA on all accounts, which currently break the login proccess of this code.  

# Fake Viewport

Tired of refreshing the unifi store to constantly see the Viewport out of stock? Me too. So I made a 40$ alternative.
Using a used **Dell Wyse 5070 Thin Client** with Mint installed on it (40$ on [ebay](https://www.ebay.com/itm/115791180422)), and this script I made
I can automatically, and remotely, launch the Protect Live View website with the desired Live View, automatically handle login if the session expires, handle temporary loss of connection to the console, or any random hiccups of the webpage.

The API file is optional. I made a simple API to gather some data for me to display on my main computer, since the fake viewport is in another location.
You'll need a .env file in the same location as your protect.py file, with your login information as well as the live view link you want to see.
I've included an example .env for you to modify and rename.

I chose to put this script in /usr/local/bin but you can put it anywhere you want (That doesnt require root permission).
Execute it with `python3 protect.py`, `python3 /usr/local/bin/protect.py` or `nohup python3 protect.py` if you're remotely executing it.

Note that the Thin Client I'm using only has DisplayPort outputs.

## Requirements

For this code to work you need to have selenium, webdriver_manager and dotenv installed. You can download the requirements.txt file in the same folder as the script and run `pip install -r requirements.txt` or manually install them yourself. I've included some code to check for webdriver_manager since it tends to be finnicky with the different environments.
