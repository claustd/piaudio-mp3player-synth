# Pirate Audio Player & Synth

**Category:** Raspberry Pi / Audio Projects
**Tags:** Pirate Audio, FluidSynth, MIDI, ST7789, Python, Systemd, GPIO, Bookworm

This project creates a multi-app device for the Raspberry Pi using the Pirate Audio HAT. It features a startup menu to launch one of two applications:
1.  A **Music Player** for listening to MP3s.
2.  A **MIDI Synthesizer** that uses SoundFonts (`.sf2`) and an external MIDI keyboard.

This guide covers setup on Raspberry Pi OS (Bookworm) and includes scripts to automate the installation.

## Project Structure

```
.
├── install/
│   ├── install_1.sh
│   └── install_2.sh
├── player/
│   ├── config.json
│   └── player.py
├── synth/
│   ├── config.json
│   └── synth.py
├── Start.py
├── midi_test.py
├── PixelifySans-Regular.ttf
├── README.md
└── requirements.txt
```

---

# Automated Installation (Recommended)

These scripts automate the entire setup process.

1.  **Make the scripts executable:**
    On your Raspberry Pi, open a terminal in the project directory and run:
    ```bash
    chmod +x install/install_1.sh install/install_2.sh
    ```

2.  **Run Part 1 (System Setup):**
    This installs system packages (including `fluidsynth`), configures `config.txt`, and sets up audio. A reboot is required.
    ```bash
    ./install/install_1.sh
    ```
    Your Raspberry Pi will ask to reboot. After it restarts, open a terminal in this directory again.

3.  **Run Part 2 (Project Setup):**
    This sets up the Python environment and the autostart service.
    ```bash
    ./install/install_2.sh
    ```

The installation is now complete. The application menu should launch automatically on boot.

---

# Manual Installation

## Part 1: System Setup

Start with a fresh installation of Raspberry Pi OS (Bookworm 64-bit).

### 1. Configure `/boot/firmware/config.txt`
Edit the Raspberry Pi's configuration file to enable SPI and configure the audio HAT.
```bash
sudo nano /boot/firmware/config.txt
```
Add or uncomment these lines:
```
dtparam=spi=on
dtoverlay=hifiberry-dac
dtparam=audio=off
```

### 2. Install System Dependencies
This includes `fluidsynth` for the synthesizer.
```bash
sudo apt update
sudo apt install -y python3-venv python3-pip python3-pygame fluidsynth libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libjpeg-dev libpng-dev
```

### 3. Configure Audio (`asound.conf`)
This is critical to force audio to the HAT instead of HDMI. Create/Edit the config file:
```bash
sudo nano /etc/asound.conf
```
Paste this exact text:
```
pcm.softvol {
    type softvol
    slave { pcm "dmix" }
    control { name "Amp"; card 0; }
    min_dB -5.0;
    max_dB 20.0;
    resolution 6;
}
pcm.!default { type plug; slave.pcm "softvol"; }
ctl.!default { type hw; card 0; }
```
Save (`Ctrl+O`), Exit (`Ctrl+X`), and **reboot your Raspberry Pi**.

## Part 2: Project & Service Setup

### 1. Create Virtual Environment
From the project's root directory:
```bash
python3 -m venv .venv --system-site-packages
```

### 2. Install Python Libraries
```bash
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Autostart Service
Create the service file:
```bash
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/pirate-player.service
```
Paste the configuration below. **You must change `/home/clau/pirate-synth-player`** to the actual, full path of your project directory.
```ini
[Unit]
Description=Pirate Audio Player & Synth
After=default.target

[Service]
Environment="SDL_AUDIODRIVER=alsa"
Environment="SDL_VIDEODRIVER=dummy"
Environment="PYTHONUNBUFFERED=1"

# --- IMPORTANT: UPDATE THIS PATH ---
ExecStart=/home/clau/pirate-synth-player/.venv/bin/python3 /home/clau/pirate-synth-player/Start.py
WorkingDirectory=/home/clau/pirate-synth-player

StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

### 4. Enable and Start the Service
```bash
sudo loginctl enable-linger $USER
systemctl --user daemon-reload
systemctl --user enable pirate-player.service
systemctl --user start pirate-player.service
```

# How to Use

## Main Menu
On boot, a menu will appear. Use buttons **A** (Up) and **X** (Down) to select an application, and **B** to launch it. The menu also includes options to Reboot or Shutdown the device.

## Music Player
*   **Add Music:** Add your music folders to the directory specified in `player/config.json` (default is `~/Music`).
*   **Controls:**
    *   **A / X:** Previous / Next Song. Hold for Volume Down / Up.
    *   **B:** Play / Pause. In menus, this is the "Select" button.
    *   **Y:** Cycle through Player -> Album Browser -> Song Browser. Hold for System Menu.

## MIDI Synthesizer
*   **Connect Keyboard:** Connect a USB MIDI keyboard before or during application use.
*   **Add SoundFonts:** Place your `.sf2` SoundFont files in the directory specified in `synth/config.json` (default is `~/SoundFonts`). The app will scan this directory on first launch.
*   **Controls:**
    *   **A / X:** Browse up/down the list of SoundFonts. Hold for Volume Down / Up.
    *   **B:** Load the selected SoundFont.
    *   **Y:** Exit back to the main menu.

### Synthesizer Configuration
You can customize the synthesizer by editing `synth/config.json`.

#### MIDI Device
If you have multiple MIDI devices, specify your keyboard's ID.
1.  Run the `midi_test.py` script to find your device's ID: `python3 midi_test.py`
2.  Set the `device_id` in the `midi` section.
    ```json
    "midi": {
      "device_id": 3
    }
    ```

#### Maximum Volume (Gain)
If the synthesizer volume is too low, you can increase the maximum gain. The default is `3.0`. Increase this value carefully to avoid distortion.
```json
"audio": {
    "gain": 0.7,
    "max_gain": 3.0
}
```