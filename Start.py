#!/usr/bin/env python3

import os
import sys
import time
import st7789
from gpiozero import Button
from PIL import Image, ImageDraw, ImageFont

# --- HARDWARE & CONFIG ---
# This script uses a minimal, hardcoded config for simplicity.
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'
BTN_A_PIN = 5
BTN_B_PIN = 6
BTN_X_PIN = 16
BTN_Y_PIN = 24
BOUNCE_TIME = 0.05

class MainMenu:
    def __init__(self):
        try:
            self.display = st7789.ST7789(
                port=0, cs=1, dc=9, backlight=13, rst=27,
                width=240, height=240, rotation=90, spi_speed_hz=80000000
            )
            self.display.begin()
            self.width, self.height = self.display.width, self.display.height
        except Exception as e:
            print(f"Display Init Error: {e}")
            sys.exit(1)
            
        try:
            self.btn_a = Button(BTN_A_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
            self.btn_b = Button(BTN_B_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
            self.btn_x = Button(BTN_X_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
        except Exception as e:
            print(f"GPIO Error: {e}")
            sys.exit(1)

        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        
        try:
            font_path = os.path.join(self.script_dir, "PixelifySans-Regular.ttf")
            self.font_lg = ImageFont.truetype(font_path, 30)
            self.font_md = ImageFont.truetype(font_path, 22)
            self.font_sm = ImageFont.truetype(font_path, 18)
        except OSError:
            print("Warning: Custom font 'PixelifySans-Regular.ttf' not found.")
            print("Falling back to default font.")
            self.font_lg = ImageFont.load_default()
            self.font_md = ImageFont.load_default()
            self.font_sm = ImageFont.load_default()

        self.options = ["Music Player", "Synthesizer", "Reboot", "Shutdown"]
        self.selection = 0

    def draw_menu(self):
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        
        draw.text((30, 20), "PIRATE OS", font=self.font_lg, fill=(255, 0, 255))
        draw.line((30, 60, self.width - 30, 60), fill=(255, 0, 255), width=2)
        
        y = 80
        for i, option in enumerate(self.options):
            fill_color = "black"
            text_color = (255, 0, 255)
            
            if i == self.selection:
                # Invert colors for selection
                fill_color = (255, 0, 255)
                text_color = "black"
                
            draw.rectangle((15, y - 5, self.width - 15, y + 30), fill=fill_color)
            draw.text((30, y), f"> {option}", font=self.font_md, fill=text_color)
            y += 45
            
        self.display.display(img)

    def handle_selection(self):
        """Handles the selected menu option."""
        selection_name = self.options[self.selection]
        print(f"Selected: {selection_name}")

        # Cleanup GPIO before launching anything
        try:
            self.btn_a.close()
            self.btn_b.close()
            self.btn_x.close()
        except Exception as e:
            print(f"Cleanup error: {e}")

        if selection_name == "Music Player":
            script_path = os.path.abspath(os.path.join(self.script_dir, 'player', 'player.py'))
            os.execv(sys.executable, [sys.executable, script_path])
        
        elif selection_name == "Synthesizer":
            script_path = os.path.abspath(os.path.join(self.script_dir, 'synth', 'synth.py'))
            os.execv(sys.executable, [sys.executable, script_path])

        elif selection_name == "Reboot":
            img = Image.new("RGB", (self.width, self.height), "black")
            draw = ImageDraw.Draw(img)
            draw.text((30, 100), "Rebooting...", font=self.font_md, fill="orange")
            self.display.display(img)
            time.sleep(1)
            os.system("sudo reboot")
            sys.exit()

        elif selection_name == "Shutdown":
            img = Image.new("RGB", (self.width, self.height), "black")
            draw = ImageDraw.Draw(img)
            draw.text((30, 100), "Shutting Down...", font=self.font_md, fill="red")
            self.display.display(img)
            time.sleep(1)
            self.display.set_backlight(0)
            os.system("sudo poweroff")
            sys.exit()

    def run(self):
        self.draw_menu()
        
        def handle_up():
            self.selection = (self.selection - 1) % len(self.options)
            self.draw_menu()

        def handle_down():
            self.selection = (self.selection + 1) % len(self.options)
            self.draw_menu()

        self.btn_a.when_pressed = handle_up
        self.btn_x.when_pressed = handle_down
        self.btn_b.when_pressed = self.handle_selection

        # Keep the script running
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Exiting Start Menu.")
            self.display.set_backlight(0)

if __name__ == "__main__":
    menu = MainMenu()
    menu.run()
