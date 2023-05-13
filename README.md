# Fake Viewport

Tired of refreshing the unifi store to constantly see the Viewport out of stock? Me too. I made a 40$ alternative.
Using a used Dell Wyse 5070 Thin Client with Mint installed on it (40$ on ebay https://www.ebay.com/itm/115730201228), and this script I made
I can automatically, and remotely, launch the Protect Live View website with the desired Live View, automatically handle logging in, if the session expires, handle temporary loss of connection of the console, or any random hiccups of the webpage.

The API file is optional, as well as any code with the #api comment inside 'protect.py'. I made a simple API to gather some data for me to display on my main computer, since the fake viewport is in another location.
You'll need a .env file in the same location as your protect.py file, with your login information as well as the live view link you want to see.
I've included an example .env for you to modify.
