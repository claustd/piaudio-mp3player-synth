#!/usr/bin/env python3

import os
import sys
import subprocess
import json
import st7789
from gpiozero import Button
from PIL import Image, ImageDraw, ImageFont
import pygame
import glob
import time
import random

# --- CRITICAL FIX FOR PI 4 / BOOKWORM ---
os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'
# ----------------------------------------

class PiratePlayer:
    def __init__(self, config):
        self.config = config
        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        
        # --- Views ---
        self.VIEW_PLAYER = 0
        self.VIEW_ALBUM_BROWSER = 1
        self.VIEW_SONG_BROWSER = 2
        self.VIEW_SYSTEM_MENU = 3

        # --- State ---
        self.current_view = self.VIEW_PLAYER
        self.music_database = []
        self.album_browser_index = 0
        self.song_browser_index = 0
        self.system_menu_index = 0
        self.system_menu_options = ["Synthesizer", "Rebuild Library", "Reboot", "Shutdown", "Exit to Menu"]
        self.current_playlist = []
        self.current_playlist_index = 0
        self.current_album_index = 0
        self.is_playing = False
        self.playback_time = 0.0
        self.last_tick = 0.0
        self.current_song_duration = 1.0
        self.current_volume = 1.0
        self.current_random_bg = (50, 50, 50)
        self.press_times = {'a': 0, 'b': 0, 'x': 0, 'y': 0}
        self.needs_redraw = True
        self.player_bg_buffer = None
        self.requested_action = None

        self._init_hardware()
        self._init_visuals()

    def _init_hardware(self):
        """Initializes the display and buttons based on the config."""
        display_conf = self.config["hardware"]["display"]
        self.display = st7789.ST7789(
            port=display_conf["port"], cs=display_conf["cs"], dc=display_conf["dc"],
            backlight=display_conf["backlight"], rst=display_conf["rst"],
            width=display_conf["width"], height=display_conf["height"],
            rotation=display_conf["rotation"], spi_speed_hz=display_conf["spi_speed_hz"]
        )
        self.display.begin()
        self.width, self.height = self.display.width, self.display.height

        btn_conf = self.config["hardware"]["buttons"]
        self.btn_a = Button(btn_conf["a"], pull_up=True, bounce_time=btn_conf["bounce_time"])
        self.btn_b = Button(btn_conf["b"], pull_up=True, bounce_time=btn_conf["bounce_time"])
        self.btn_x = Button(btn_conf["x"], pull_up=True, bounce_time=btn_conf["bounce_time"])
        self.btn_y = Button(btn_conf["y"], pull_up=True, bounce_time=btn_conf["bounce_time"])

        self.btn_a.when_pressed = lambda: self.record_press('a')
        self.btn_a.when_released = lambda: self.handle_release('a')
        self.btn_x.when_pressed = lambda: self.record_press('x')
        self.btn_x.when_released = lambda: self.handle_release('x')
        self.btn_b.when_pressed = lambda: self.record_press('b')
        self.btn_b.when_released = lambda: self.handle_release('b')
        self.btn_y.when_pressed = lambda: self.record_press('y')
        self.btn_y.when_released = lambda: self.handle_release('y')

    def _init_visuals(self):
        """Initializes colors and fonts based on the config."""
        colors_conf = self.config["visuals"]["colors"]
        self.HIGHLIGHT_COLOR = tuple(colors_conf["highlight"])
        self.TEXT_COLOR = tuple(colors_conf["text"])
        self.DIM_TEXT_COLOR = tuple(colors_conf["dim_text"])
        self.ALERT_COLOR = tuple(colors_conf["alert"])

        try:
            font_conf = self.config["visuals"]["font"]
            font_path = os.path.abspath(os.path.join(self.script_dir, '..', font_conf["file"]))
            self.font_lg = ImageFont.truetype(font_path, font_conf["large_size"])
            self.font_md = ImageFont.truetype(font_path, font_conf["medium_size"])
            self.font_sm = ImageFont.truetype(font_path, font_conf["small_size"])
            self.font_mono = ImageFont.truetype(font_path, font_conf["mono_size"])
        except (OSError, IOError) as e:
            print(f"Warning: Could not load custom font. {e}")
            print("Falling back to default font.")
            self.font_lg = ImageFont.load_default()
            self.font_md = ImageFont.load_default()
            self.font_sm = ImageFont.load_default()
            self.font_mono = ImageFont.load_default()

    def get_text_center(self, draw, text, font):
        return (self.width - draw.textlength(text, font=font)) // 2

    def generate_random_color(self):
        return (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))

    def save_library(self):
        data = {
            "database": self.music_database,
            "last_state": {
                "album_index": self.current_album_index,
                "song_index": self.current_playlist_index,
                "volume": self.current_volume
            }
        }
        try:
            library_path = os.path.abspath(os.path.join(self.script_dir, '..', self.config["paths"]["library_file"]))
            with open(library_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving library: {e}")

    def load_library(self):
        library_path = os.path.join(self.script_dir, self.config["paths"]["library_file"])
        if not os.path.exists(library_path):
            return False
        try:
            with open(library_path, 'r') as f:
                data = json.load(f)
            self.music_database = data.get("database", [])
            state = data.get("last_state", {})
            self.current_album_index = state.get("album_index", 0)
            self.current_playlist_index = state.get("song_index", 0)
            self.current_volume = state.get("volume", 1.0)
            return bool(self.music_database)
        except Exception as e:
            print(f"Error loading library: {e}")
            return False

    def scan_music_directory(self):
        self.music_database = []
        music_dir = os.path.expanduser(self.config["paths"]["music_directory"])
        print(f"Scanning {music_dir}...")
        
        img = Image.new("RGB", (self.width, self.height), "black")
        d = ImageDraw.Draw(img)
        d.text((20, 100), "Scanning Music...", font=self.font_md, fill="cyan")
        d.text((20, 130), "Please Wait", font=self.font_sm, fill="white")
        self.display.display(img)
        
        try:
            entries = sorted([f.path for f in os.scandir(music_dir) if f.is_dir()])
        except FileNotFoundError:
            print("Music dir not found.")
            return

        for album_path in entries:
            album_name = os.path.basename(album_path)
            songs = sorted(glob.glob(os.path.join(album_path, "*.mp3")))
            if not songs: continue

            art_path = None
            for ext in ["art.jpg", "art.png", "folder.jpg", "folder.png"]:
                matches = glob.glob(os.path.join(album_path, "*"))
                for f in matches:
                    if f.lower().endswith(ext):
                        art_path = f
                        break
                if art_path: break
            
            self.music_database.append({
                "album": album_name, "artist": "Unknown Artist",
                "art_path": art_path, "songs": songs
            })
        
        print(f"Found {len(self.music_database)} albums.")
        self.save_library()

    def launch_synth(self):
        print("Launching Synthesizer...")
        self.save_library()
        img = Image.new("RGB", (self.width, self.height), "black")
        d = ImageDraw.Draw(img)
        d.text((40, 100), "Loading Synth...", font=self.font_md, fill="cyan")
        self.display.display(img)
        try:
            pygame.mixer.quit()
            self.btn_a.close()
            self.btn_b.close()
            self.btn_x.close()
            self.btn_y.close()
        except Exception as e:
            print(f"Cleanup Error: {e}")
        
        synth_script_path = os.path.abspath(os.path.join(self.script_dir, '..', 'synth', 'synth.py'))
        os.execv(sys.executable, [sys.executable, synth_script_path])

    def launch_menu(self):
        print("Returning to Main Menu...")
        self.save_library()
        try:
            pygame.mixer.quit()
            self.btn_a.close()
            self.btn_b.close()
            self.btn_x.close()
            self.btn_y.close()
        except Exception as e:
            print(f"Cleanup Error: {e}")
        
        menu_script_path = os.path.abspath(os.path.join(self.script_dir, '..', 'Start.py'))
        os.execv(sys.executable, [sys.executable, menu_script_path])

    def record_press(self, btn_char):
        self.press_times[btn_char] = time.time()

    def handle_release(self, btn_char):
        duration = time.time() - self.press_times[btn_char]
        
        long_press = self.config["behavior"]["long_press_s"]
        if btn_char == 'y' and duration > long_press["menu"]: return
        if (btn_char == 'a' or btn_char == 'x') and duration > long_press["volume"]: return

        if btn_char == 'a': # UP
            if self.current_view == self.VIEW_PLAYER:
                self.change_song(-1)
            elif self.current_view == self.VIEW_ALBUM_BROWSER:
                if self.music_database: self.album_browser_index = (self.album_browser_index - 1) % len(self.music_database)
            elif self.current_view == self.VIEW_SONG_BROWSER:
                count = len(self.music_database[self.album_browser_index]["songs"])
                if count: self.song_browser_index = (self.song_browser_index - 1) % count
            elif self.current_view == self.VIEW_SYSTEM_MENU:
                self.system_menu_index = (self.system_menu_index - 1) % len(self.system_menu_options)

        elif btn_char == 'x': # DOWN
            if self.current_view == self.VIEW_PLAYER:
                self.change_song(1)
            elif self.current_view == self.VIEW_ALBUM_BROWSER:
                if self.music_database: self.album_browser_index = (self.album_browser_index + 1) % len(self.music_database)
            elif self.current_view == self.VIEW_SONG_BROWSER:
                count = len(self.music_database[self.album_browser_index]["songs"])
                if count: self.song_browser_index = (self.song_browser_index + 1) % count
            elif self.current_view == self.VIEW_SYSTEM_MENU:
                self.system_menu_index = (self.system_menu_index + 1) % len(self.system_menu_options)

        elif btn_char == 'b': # PLAY/OK
            if self.current_view == self.VIEW_SYSTEM_MENU:
                self.handle_system_menu_selection()
            elif self.current_view == self.VIEW_PLAYER:
                self.toggle_play()
            elif self.current_view == self.VIEW_ALBUM_BROWSER:
                self.start_album_playback(self.album_browser_index, 0)
                self.current_view = self.VIEW_PLAYER
            elif self.current_view == self.VIEW_SONG_BROWSER:
                self.start_album_playback(self.album_browser_index, self.song_browser_index)
                self.current_view = self.VIEW_PLAYER

        elif btn_char == 'y': # MENU
            if self.current_view == self.VIEW_SYSTEM_MENU:
                self.current_view = self.VIEW_PLAYER
            elif self.current_view == self.VIEW_PLAYER:
                self.album_browser_index = self.current_album_index
                self.current_view = self.VIEW_ALBUM_BROWSER
            elif self.current_view == self.VIEW_ALBUM_BROWSER:
                self.song_browser_index = self.current_playlist_index if self.album_browser_index == self.current_album_index else 0
                self.current_view = self.VIEW_SONG_BROWSER
            elif self.current_view == self.VIEW_SONG_BROWSER:
                self.current_view = self.VIEW_PLAYER
            
        self.needs_redraw = True

    def handle_system_menu_selection(self):
        selection = self.system_menu_options[self.system_menu_index]
        if selection == "Synthesizer": self.requested_action = "synth"
        elif selection == "Rebuild Library": self.requested_action = "rebuild"
        elif selection == "Reboot": self.requested_action = "reboot"
        elif selection == "Shutdown": self.requested_action = "shutdown"
        elif selection == "Exit to Menu": self.requested_action = "menu"

    def run(self):
        print("Final Player Starting...")
        try:
            pygame.mixer.init()
            time.sleep(0.5) 
        except Exception as e:
            print(f"Audio Init Error: {e}")

        try:
            os.system("amixer -D default sset Amp 100% > /dev/null 2>&1")
        except:
            pass

        if not self.load_library():
            self.scan_music_directory()

        if not self.music_database:
            img = Image.new("RGB", (self.width, self.height), "black")
            d = ImageDraw.Draw(img)
            d.text((10, 50), "No Music Found", font=self.font_md, fill=self.ALERT_COLOR)
            self.display.display(img)
        else:
            self.current_playlist = self.music_database[self.current_album_index]["songs"]
            if self.current_playlist_index >= len(self.current_playlist): self.current_playlist_index = 0
            self.start_album_playback(self.current_album_index, self.current_playlist_index)
            self.toggle_play() # Pause on start

        try:
            while True:
                self.main_loop_tick()
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            self.cleanup()
            
    def main_loop_tick(self):
        current_time = time.time()
        long_press = self.config["behavior"]["long_press_s"]

        if self.requested_action: self.handle_requested_action()

        if self.btn_a.is_active and (current_time - self.press_times['a'] > long_press["volume"]):
             if int(current_time * 10) % 2 == 0: self.change_volume(-0.02)
        if self.btn_x.is_active and (current_time - self.press_times['x'] > long_press["volume"]):
             if int(current_time * 10) % 2 == 0: self.change_volume(0.02)
        if self.btn_y.is_active and (current_time - self.press_times['y'] > long_press["menu"]):
            if self.current_view != self.VIEW_SYSTEM_MENU:
                self.current_view = self.VIEW_SYSTEM_MENU
                self.system_menu_index = 0
                self.needs_redraw = True

        if self.is_playing:
            self.playback_time += (current_time - self.last_tick)
            self.last_tick = current_time
            if not pygame.mixer.music.get_busy():
                self.change_song(1)
            if self.current_view == self.VIEW_PLAYER:
                self.needs_redraw = True

        if self.needs_redraw:
            self.update_display()
            self.needs_redraw = False

    def handle_requested_action(self):
        act = self.requested_action
        self.requested_action = None 
        if act == "synth": self.launch_synth()
        elif act == "menu": self.launch_menu()
        elif act == "rebuild":
            self.perform_rebuild()
            self.current_view = self.VIEW_PLAYER
        elif act == "reboot":
            self.save_library()
            os.system("sudo reboot")
            sys.exit()
        elif act == "shutdown":
            self.save_library()
            
            # Display shutdown message and turn off backlight
            img = Image.new("RGB", (self.width, self.height), "black")
            draw = ImageDraw.Draw(img)
            draw.text((self.get_text_center(draw, "Shutting Down...", self.font_md), 110), "Shutting Down...", font=self.font_md, fill=self.ALERT_COLOR)
            self.display.display(img)
            time.sleep(1) # Give user a moment to see the message
            self.display.set_backlight(0)
            
            os.system("sudo poweroff")
            sys.exit()

    def cleanup(self):
        try:
            self.save_library()
            pygame.mixer.music.stop()
            self.display.set_backlight(0)
        except:
            pass

    def perform_rebuild(self):
        self.scan_music_directory()
        self.current_album_index = 0
        self.current_playlist_index = 0
        self.start_album_playback(0, 0)
        self.needs_redraw = True

    def update_display(self):
        if self.current_view == self.VIEW_PLAYER: self.draw_player_screen()
        elif self.current_view == self.VIEW_ALBUM_BROWSER: self.draw_album_browser()
        elif self.current_view == self.VIEW_SONG_BROWSER: self.draw_song_browser()
        elif self.current_view == self.VIEW_SYSTEM_MENU: self.draw_system_menu()

    def draw_player_screen(self, full_redraw=True):
        if full_redraw or self.player_bg_buffer is None:
            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img, "RGBA")
            
            if not self.music_database or self.current_album_index >= len(self.music_database): return
            
            album = self.music_database[self.current_album_index]
            song_title = "No Songs"
            if self.current_playlist and self.current_playlist_index < len(self.current_playlist):
                song_title = os.path.basename(self.current_playlist[self.current_playlist_index]).replace(".mp3", "")

            if album["art_path"] and os.path.exists(album["art_path"]):
                try:
                    art_img = Image.open(album["art_path"]).resize((self.width, self.height))
                    img.paste(art_img, (0, 0))
                except:
                    draw.rectangle((0, 0, self.width, self.height), fill=self.current_random_bg)
            else:
                draw.rectangle((0, 0, self.width, self.height), fill=self.current_random_bg)

            draw.rectangle((0, 0, self.width, self.height), fill=(0, 0, 0, 150))
            draw.text((self.get_text_center(draw, song_title, self.font_lg), 80), song_title, font=self.font_lg, fill=self.TEXT_COLOR)
            draw.text((self.get_text_center(draw, album["artist"], self.font_md), 110), album["artist"], font=self.font_md, fill=self.DIM_TEXT_COLOR)
            draw.rectangle((20, self.height - 30, self.width - 20, self.height - 28), fill=(80, 80, 80))
            self.player_bg_buffer = img.copy().convert("RGB")

        final_img = self.player_bg_buffer.copy()
        draw = ImageDraw.Draw(final_img)

        cur_s, dur_s = int(self.playback_time), int(self.current_song_duration)
        time_str = f"{cur_s // 60}:{cur_s % 60:02d} / {dur_s // 60}:{dur_s % 60:02d}"
        draw.text((self.get_text_center(draw, time_str, self.font_sm), 140), time_str, font=self.font_sm, fill=self.DIM_TEXT_COLOR)

        pct = self.playback_time / self.current_song_duration if self.current_song_duration > 0 else 0
        bar_w = int((self.width - 40) * min(pct, 1.0))
        draw.rectangle((20, self.height - 30, 20 + bar_w, self.height - 28), fill="cyan")

        cx = self.width // 2
        if self.is_playing:
            draw.rectangle((cx - 10, 170, cx - 5, 190), fill=self.TEXT_COLOR)
            draw.rectangle((cx + 5, 170, cx + 10, 190), fill=self.TEXT_COLOR)
        else:
            draw.polygon([(cx - 5, 170), (cx - 5, 190), (cx + 10, 180)], fill=self.TEXT_COLOR)
        
        vol_txt = f"Vol: {int(self.current_volume * 100)}%"
        draw.text((self.width - 70, 5), vol_txt, font=self.font_sm, fill=self.DIM_TEXT_COLOR)
        self.display.display(final_img)

    def draw_album_browser(self):
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        draw.text((10, 5), "Albums", font=self.font_lg, fill=self.HIGHLIGHT_COLOR)
        draw.line((10, 30, self.width - 10, 30), fill=self.HIGHLIGHT_COLOR, width=1)
        
        y, h = 40, 24
        start_idx = max(0, self.album_browser_index - 3)
        visible_albums = self.music_database[start_idx:start_idx + 6]
        
        for i, album in enumerate(visible_albums):
            real_idx = start_idx + i
            name = album['album'];
            if len(name) > 18: name = name[:17] + ".."
            color = self.TEXT_COLOR if real_idx == self.album_browser_index else self.DIM_TEXT_COLOR
            if real_idx == self.album_browser_index:
                draw.rectangle((0, y, self.width, y + h), fill=self.HIGHLIGHT_COLOR)
            draw.text((10, y), f"{'> ' if real_idx == self.album_browser_index else '  '}{name}", font=self.font_mono, fill=color)
            y += h + 2
        self.display.display(img)

    def draw_song_browser(self):
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        
        album = self.music_database[self.album_browser_index]
        header = album['album'];
        if len(header) > 15: header = header[:14] + ".."
        draw.text((10, 5), header, font=self.font_md, fill=self.HIGHLIGHT_COLOR)
        draw.line((10, 30, self.width - 10, 30), fill=self.HIGHLIGHT_COLOR, width=1)

        y, h = 40, 24
        songs = album['songs']
        start_idx = max(0, self.song_browser_index - 3)
        visible_songs = songs[start_idx:start_idx + 6]

        for i, song_path in enumerate(visible_songs):
            real_idx = start_idx + i
            title = os.path.basename(song_path).replace(".mp3", "")
            if len(title) > 18: title = title[:17] + ".."
            color = self.TEXT_COLOR if real_idx == self.song_browser_index else self.DIM_TEXT_COLOR
            if real_idx == self.song_browser_index:
                draw.rectangle((0, y, self.width, y + h), fill=self.HIGHLIGHT_COLOR)
            draw.text((10, y), f"{'> ' if real_idx == self.song_browser_index else '  '}{title}", font=self.font_mono, fill=color)
            y += h + 2
        self.display.display(img)

    def draw_system_menu(self):
        img = Image.new("RGB", (self.width, self.height), "black")
        draw = ImageDraw.Draw(img)
        
        draw.rectangle((0, 0, self.width, self.height), fill=(40, 10, 10))
        draw.text((10, 5), "System Menu", font=self.font_lg, fill=self.ALERT_COLOR)
        draw.line((10, 30, self.width - 10, 30), fill=self.ALERT_COLOR, width=1)
        
        y, h = 50, 30
        for i, option in enumerate(self.system_menu_options):
            if i == self.system_menu_index:
                draw.rectangle((0, y, self.width, y + h), fill=self.ALERT_COLOR)
                draw.text((20, y + 5), f"> {option}", font=self.font_md, fill=self.TEXT_COLOR)
            else:
                draw.text((20, y + 5), f"  {option}", font=self.font_md, fill=self.DIM_TEXT_COLOR)
            y += h + 5
        self.display.display(img)

    def load_song_data(self):
        self.playback_time = 0.0
        self.last_tick = time.time()
        self.current_random_bg = self.generate_random_color()

        if not self.current_playlist: return
        path = self.current_playlist[self.current_playlist_index]
        print(f"Loading: {path}")
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(self.current_volume)
            try: self.current_song_duration = pygame.mixer.Sound(path).get_length()
            except: self.current_song_duration = 1.0
        except Exception as e: print(f"Load Failed: {e}")

    def start_album_playback(self, alb_idx, song_idx=0):
        self.current_album_index = alb_idx
        if not self.music_database: return
        self.current_playlist = self.music_database[alb_idx]["songs"]
        self.current_playlist_index = song_idx
        self.load_song_data()
        pygame.mixer.music.play()
        self.is_playing = True
        self.needs_redraw = True
        self.player_bg_buffer = None 
        self.save_library()

    def toggle_play(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
        else:
            if not pygame.mixer.music.get_busy() and self.playback_time > 1.0:
                pygame.mixer.music.play()
            else:
                pygame.mixer.music.unpause()
            self.is_playing = True
        self.needs_redraw = True

    def change_volume(self, amount):
        self.current_volume = max(0.0, min(1.0, self.current_volume + amount))
        pygame.mixer.music.set_volume(self.current_volume)
        self.needs_redraw = True
        
    def change_song(self, direction):
        if not self.current_playlist: return
        was_playing = self.is_playing
        self.is_playing = False # Prevent race conditions
        
        self.current_playlist_index = (self.current_playlist_index + direction) % len(self.current_playlist)
        self.load_song_data()
        if was_playing:
            pygame.mixer.music.play()
        self.player_bg_buffer = None
        self.save_library()
        
        self.is_playing = was_playing
        self.needs_redraw = True


def main():
    """Main execution function."""
    def load_config():
        """Loads configuration from config.json."""
        try:
            script_dir = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(script_dir, "config.json"), 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Error: config.json not found. Please create it.")
            sys.exit(1)
        except json.JSONDecodeError:
            print("Error: Could not decode config.json. Please check for syntax errors.")
            sys.exit(1)

    config = load_config()
    player = PiratePlayer(config)
    player.run()

if __name__ == "__main__":
    main()
