#!/bin/bash
# Installer Part 2: Python Environment & Autostart Service

set -e

echo "--- Part 2: Setting up Python environment ---"

if [ -d ".venv" ]; then
    echo "Virtual environment already exists. Skipping creation."
else
    python3 -m venv .venv --system-site-packages
fi

echo "--- Installing Python dependencies ---"
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "--- Configuring autostart service (systemd) ---"

# Attempt to get username and project path automatically
PLAYER_USER=$(whoami)
PLAYER_DIR=$(pwd)
SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/pirate-player.service"

echo "Detected User: $PLAYER_USER"
echo "Detected Project Directory: $PLAYER_DIR"
echo "Service file will be created at: $SERVICE_FILE"

read -p "Is this correct? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Aborted. Please create the systemd service file manually as described in README.md."
    exit 1
fi

# Create the service file content
SERVICE_CONFIG="[Unit]
Description=Pirate Audio Player
After=default.target

[Service]
Environment=\"SDL_AUDIODRIVER=alsa\"
Environment=\"SDL_VIDEODRIVER=dummy\"
Environment=\"PYTHONUNBUFFERED=1\"
ExecStart=$PLAYER_DIR/.venv/bin/python3 $PLAYER_DIR/Start.py
WorkingDirectory=$PLAYER_DIR
StandardOutput=journal
StandardError=journal
Restart=always
RestartSec=5

[Install]
WantedBy=default.target"

mkdir -p "$SERVICE_DIR"
echo "$SERVICE_CONFIG" > "$SERVICE_FILE"

echo "--- Enabling and starting the service ---"
sudo loginctl enable-linger "$PLAYER_USER"
systemctl --user daemon-reload
systemctl --user enable pirate-player.service
systemctl --user start pirate-player.service

echo ""
echo "--- Installation Complete! ---"
echo "The player service has been started."
echo "To check its status, run: systemctl --user status pirate-player.service"
echo "REMINDER: Make sure you have downloaded the font file specified in config.json."
