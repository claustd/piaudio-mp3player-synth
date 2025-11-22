#!/usr/bin/env python3

import os
import sys
import time
import glob
import json
import pygame
import pygame.midi
import fluidsynth
import st7789
from gpiozero import Button
from PIL import Image, ImageDraw, ImageFont

# --- HARDWARE & CONFIG ---
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'
BTN_A_PIN, BTN_B_PIN, BTN_X_PIN, BTN_Y_PIN = 5, 6, 16, 24
BOUNCE_TIME = 0.05

class FluidSynthApp:
    def __init__(self):
        print("FluidSynthApp: Initializing...")
        # --- Paths & Config ---
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        self.root_dir = os.path.abspath(os.path.join(self.script_dir, '..'))
        self.load_config()
        print("FluidSynthApp: Config loaded.")

        # --- Display & UI ---
        self._init_display()
        self._init_fonts()
        self.soundfonts = []
        self.sf_selection = 0
        self.needs_redraw = True
        print("FluidSynthApp: Display & Fonts initialized.")

        # --- Audio & MIDI ---
        self._init_audio()
        self._init_midi()
        print("FluidSynthApp: Audio & MIDI initialized.")

        # --- Buttons ---
        self._init_buttons()
        self.press_times = {'a': 0, 'b': 0, 'x': 0, 'y': 0}
        print("FluidSynthApp: Buttons initialized.")
        
        # --- Load Library ---
        if not self.load_library():
            print("FluidSynthApp: Library not found or empty, scanning for soundfonts.")
            self.scan_for_soundfonts()
        else:
            print("FluidSynthApp: Library loaded.")
        
        if self.soundfonts:
            print(f"FluidSynthApp: Loading initial soundfont: {self.soundfonts[self.sf_selection]}")
            self.load_soundfont(self.soundfonts[self.sf_selection])
        else:
            print("FluidSynthApp: No SoundFonts available.")
            self.draw_message("No SoundFonts found!", "Check your config or add .sf2 files.")
        
        print("FluidSynthApp: Initialization complete.")

    def load_config(self):
        try:
            with open(os.path.join(self.script_dir, "config.json"), 'r') as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"ERROR: Failed to load synth config.json: {e}")
            sys.exit(1)

    def _init_display(self):
        try:
            self.display = st7789.ST7789(port=0, cs=1, dc=9, backlight=13, rst=27, width=240, height=240, rotation=90, spi_speed_hz=80000000)
            self.display.begin()
            self.width, self.height = self.display.width, self.display.height
        except Exception as e:
            print(f"ERROR: Display Init Error: {e}")
            sys.exit(1)

    def _init_fonts(self):
        try:
            font_path = os.path.join(self.root_dir, "PixelifySans-Regular.ttf")
            self.font_lg = ImageFont.truetype(font_path, 24)
            self.font_md = ImageFont.truetype(font_path, 18)
        except (OSError, IOError) as e:
            print(f"Warning: Could not load custom font. {e}")
            print("Falling back to default font.")
            self.font_lg = ImageFont.load_default()
            self.font_md = ImageFont.load_default()

    def _init_audio(self):
        try:
            pygame.init()
            self.fs = fluidsynth.Synth()
            self.fs.start()
            # Set ALSA 'Amp' control to 100% to ensure max system volume headroom
            os.system("amixer -D default sset Amp 100% > /dev/null 2>&1")
            self.gain = self.config["audio"]["gain"]
            self.fs.setting("synth.gain", self.gain)
            print("FluidSynth: Audio initialized successfully.")
        except Exception as e:
            print(f"ERROR: FluidSynth Audio Init Error: {e}")
            sys.exit(1)

    def _init_midi(self):
        print("FluidSynth: Initializing MIDI...")
        pygame.midi.init()
        self.midi_in = None
        self.check_midi_connection()
        if self.midi_in:
            print("FluidSynth: MIDI device connected at init.")
        else:
            print("FluidSynth: No MIDI device found at init, will check periodically.")

    def _init_buttons(self):
        try:
            self.btn_a = Button(BTN_A_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
            self.btn_b = Button(BTN_B_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
            self.btn_x = Button(BTN_X_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
            self.btn_y = Button(BTN_Y_PIN, pull_up=True, bounce_time=BOUNCE_TIME)
            
            self.btn_a.when_pressed = lambda: self.record_press('a')
            self.btn_a.when_released = lambda: self.handle_release('a')
            self.btn_x.when_pressed = lambda: self.record_press('x')
            self.btn_x.when_released = lambda: self.handle_release('x')
            
            self.btn_b.when_pressed = self.load_selected_soundfont
            self.btn_y.when_pressed = self.return_to_menu
        except Exception as e:
            print(f"ERROR: Button Init Error: {e}")
            sys.exit(1)

    def record_press(self, btn_char):
        self.press_times[btn_char] = time.time()

    def handle_release(self, btn_char):
        LONG_PRESS_THRESHOLD = 0.3 
        duration = time.time() - self.press_times.get(btn_char, time.time())
        
        if duration < LONG_PRESS_THRESHOLD:
            if btn_char == 'a':
                self.navigate_sf(-1)
            elif btn_char == 'x':
                self.navigate_sf(1)
        
    def load_selected_soundfont(self):
        if self.soundfonts:
            self.load_soundfont(self.soundfonts[self.sf_selection])

    def check_midi_connection(self):
        """Checks for new MIDI devices or disconnections."""
        # Check for disconnection first
        if self.midi_in:
            try:
                self.midi_in.poll()
            except pygame.midi.MidiException:
                print("MIDI keyboard disconnected.")
                self.midi_in.close()
                self.midi_in = None
                self.needs_redraw = True

        # If not connected, try to connect
        if self.midi_in is None:
            pygame.midi.quit()
            pygame.midi.init()
            if pygame.midi.get_count() > 0:
                device_id = self.config.get("midi", {}).get("device_id")

                # If no ID is specified in config, use the default. Otherwise, use the specified one.
                if device_id is None:
                    device_id = pygame.midi.get_default_input_id()
                    print(f"No MIDI device ID specified in config, using default ID: {device_id}")
                else:
                    print(f"Using MIDI device ID from config: {device_id}")

                if device_id != -1:
                    try:
                        self.midi_in = pygame.midi.Input(device_id)
                        print(f"Successfully connected to MIDI device ID: {device_id}")
                        self.needs_redraw = True
                    except Exception as e:
                        print(f"ERROR: Failed to open specified MIDI port {device_id}: {e}")
                        if self.midi_in:
                            self.midi_in.close()
                        self.midi_in = None
                        self.draw_message("MIDI Error!", f"Can't open ID {device_id}", "red")
                        time.sleep(3) # Show error for a moment
                        self.needs_redraw = True
    
    def get_library_path(self):
        return os.path.join(self.root_dir, self.config["paths"]["library_file"])

    def load_library(self):
        path = self.get_library_path()
        if not os.path.exists(path): return False
        try:
            with open(path, 'r') as f: data = json.load(f)
            self.soundfonts = data.get("soundfonts", [])
            self.sf_selection = data.get("last_selection", 0)
            self.gain = data.get("last_gain", self.config["audio"]["gain"])
            self.fs.setting("synth.gain", self.gain)
            return bool(self.soundfonts)
        except Exception as e:
            print(f"Error loading synth library: {e}")
            return False

    def save_library(self):
        path = self.get_library_path()
        data = {
            "soundfonts": self.soundfonts,
            "last_selection": self.sf_selection,
            "last_gain": self.gain
        }
        try:
            with open(path, 'w') as f: json.dump(data, f)
        except Exception as e: print(f"Error saving synth library: {e}")
        
    def scan_for_soundfonts(self):
        sf_dir = os.path.expanduser(self.config["paths"]["soundfont_dir"])
        print(f"Scanning for SoundFonts in {sf_dir}...")
        self.soundfonts = sorted(glob.glob(os.path.join(sf_dir, "*.sf2")))
        self.sf_selection = 0
        self.save_library()
        self.needs_redraw = True

    def load_soundfont(self, path):
        if not os.path.exists(path):
            print(f"SoundFont not found: {path}")
            self.draw_message("SoundFont not found!", os.path.basename(path), "red")
            return
        
        print(f"Loading {os.path.basename(path)}")
        self.draw_message("Loading...", os.path.basename(path))
        
        if hasattr(self, 'sfid'):
            self.fs.sfunload(self.sfid)

        self.sfid = self.fs.sfload(path)
        self.fs.program_select(0, self.sfid, 0, 0)
        self.needs_redraw = True

    def navigate_sf(self, direction):
        if not self.soundfonts: return
        self.sf_selection = (self.sf_selection + direction) % len(self.soundfonts)
        self.needs_redraw = True

    def change_gain(self, amount):
        """Changes the synthesizer gain and redraws the UI."""
        self.gain += amount
        max_gain = self.config.get("audio", {}).get("max_gain", 1.5)
        self.gain = max(0.0, min(max_gain, self.gain))
        self.fs.setting("synth.gain", self.gain)
        self.needs_redraw = True

    def draw_ui(self):
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        
        draw.text((10, 5), "MIDI SYNTH", font=self.font_lg, fill="cyan")
        draw.line((10, 35, self.width - 10, 35), fill="cyan", width=1)

        if self.midi_in is None:
            message_line1 = "Waiting for"
            message_line2 = "MIDI Keyboard..."
            
            w1 = draw.textlength(message_line1, font=self.font_lg)
            w2 = draw.textlength(message_line2, font=self.font_lg)
            
            x1 = (self.width - w1) // 2
            x2 = (self.width - w2) // 2
            
            draw.text((x1, 100), message_line1, font=self.font_lg, fill="yellow")
            draw.text((x2, 130), message_line2, font=self.font_lg, fill="yellow")

        elif not self.soundfonts:
            draw.text((20, 100), "No SoundFonts found!", font=self.font_md, fill="red")

        else:
            y, h = 45, 22
            start_idx = max(0, self.sf_selection - 3)
            visible_sfs = self.soundfonts[start_idx:start_idx + 7]

            for i, sf_path in enumerate(visible_sfs):
                real_idx = start_idx + i
                name = os.path.basename(sf_path)
                if len(name) > 22: name = name[:21] + ".."
                
                color = "white"
                if real_idx == self.sf_selection:
                    draw.rectangle((0, y, self.width, y + h), fill="cyan")
                    color = "black"

                draw.text((10, y), f"{'> ' if real_idx == self.sf_selection else '  '}{name}", font=self.font_md, fill=color)
                y += h + 2
        
        midi_status = "MIDI: CONNECTED" if self.midi_in else "MIDI: NOT FOUND"
        midi_color = "lime" if self.midi_in else "orange"
        draw.text((10, self.height - 25), midi_status, font=self.font_md, fill=midi_color)
        
        gain_text = f"Gain: {int(self.gain * 100)}%"
        w = draw.textlength(gain_text, font=self.font_md)
        draw.text((self.width - w - 10, self.height - 25), gain_text, font=self.font_md, fill="white")
        
        self.display.display(img)

    def draw_message(self, line1, line2, color="cyan"):
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        draw.text((20, 90), line1, font=self.font_lg, fill=color)
        draw.text((20, 120), line2, font=self.font_md, fill="white")
        self.display.display(img)

    def return_to_menu(self):
        print("Returning to Main Menu...")
        self.save_library()
        self.fs.delete()
        pygame.midi.quit()
        self.display.set_backlight(0)
        
        menu_script = os.path.abspath(os.path.join(self.script_dir, '..', 'Start.py'))
        os.execv(sys.executable, [sys.executable, menu_script])

    def run(self):
        print("FluidSynth App Running...")
        last_midi_check_time = time.time()
        LONG_PRESS_THRESHOLD = 0.3 

        try:
            while True:
                try:
                    current_time = time.time()

                    # Handle continuous long press for volume
                    if self.btn_a.is_active and (current_time - self.press_times.get('a', current_time) > LONG_PRESS_THRESHOLD):
                        if int(current_time * 10) % 2 == 0: self.change_gain(-0.02)
                    if self.btn_x.is_active and (current_time - self.press_times.get('x', current_time) > LONG_PRESS_THRESHOLD):
                        if int(current_time * 10) % 2 == 0: self.change_gain(0.02)

                    # Periodically check for MIDI connection changes
                    if current_time - last_midi_check_time > 1.0:
                        self.check_midi_connection()
                        last_midi_check_time = current_time

                    # Process MIDI events if a device is connected
                    if self.midi_in and self.midi_in.poll():
                        for event in self.midi_in.read(16):
                            (status, note, vel, _), _ = event
                            if status == 0x90 and vel > 0: # Note On
                                self.fs.noteon(0, note, vel)
                            elif status == 0x80 or (status == 0x90 and vel == 0): # Note Off
                                self.fs.noteoff(0, note)

                    if self.needs_redraw:
                        self.draw_ui()
                        self.needs_redraw = False
                    
                    time.sleep(0.01)

                except Exception as e:
                    print(f"---!!! UNEXPECTED RUNTIME ERROR !!!---")
                    print(f"ERROR: {e}")
                    print(f"--------------------------------------")
                    # Display error on screen as well
                    self.draw_message("Runtime Error:", str(e), "red")
                    time.sleep(5) # Pause on error to allow reading it
                    self.needs_redraw = True # Redraw the normal UI after pause
        
        except KeyboardInterrupt:
            print("Exiting Synth...")
        finally:
            print("Executing finally block, returning to menu.")
            self.return_to_menu()


if __name__ == "__main__":
    app = FluidSynthApp()
    app.run()