# Updated!
I'm happy to announce that the basic functionality is once again working. I cannot test the entire script's functionality at the moment, but will do so with time. Go to the Releases for the stable versions of this code while I iron out all the kinks and try to bring back functionality through trial and error.  

# Fake Viewport

Tired of refreshing the Unifi store to constantly see the Viewport out of stock? Me too. So I made a 30$ alternative.
Using a used **Dell Wyse Thin Client** with your favorite lightweight Linux distro installed on it (~30$ on [ebay](https://www.ebay.com/sch/i.html?_nkw=wyse%20thin%20client&_sacat=0&_odkw=dell%20wyse%20thin%20client&_osacat=0)) (I've found a few for 20$ in Facebook Marketplace), and this script I made.
I can automatically, and remotely, launch the Protect Live View website with the desired Live View, automatically handle login if the session expires, handle temporary loss of connection to the console, or any random hiccups of the webpage.

## Technical Information

The API file is optional. I made a simple API to gather some data for me to display on my main computer, since the fake viewport is in another location.

You'll need a .env file in the same location as your protect.py file, with your login information as well as the live view link you want to see. **You must use a local account for this.** I recommend making one just for use in this device with view-only permissions.

I've included an example DOTenv for you to modify and rename to '.env'

I chose to put this script in /usr/local/bin but you can put it anywhere you want (that doesn't require root permission).
Execute it with `python3 protect.py`, `python3 /usr/local/bin/protect.py` or `nohup python3 protect.py` if you're remotely executing it.

Note that the Thin Client I'm using only has DisplayPort outputs.

## Requirements 

When selecting the Thing Client, make sure it meets the requirements for your linux distro of choice. I've gotten away with Mint installed on a 5070 with 16GB of storage. You could even dedicate a flash drive just for booting up and launching the script, or buy a thin client with upgradable storage.

For this code to work you need to have python3, selenium, webdriver_manager and dotenv installed. You can download the requirements.txt file in the same folder as the script and run `pip install -r requirements.txt` or manually install them yourself. I've included some code to check for webdriver_manager since it tends to be finnicky with the different environments.
