#!/bin/bash
# Installer Part 1: System Dependencies & Audio Configuration

set -e

echo "--- Part 1: Installing system dependencies ---"
sudo apt update
sudo apt install -y python3-venv python3-pip python3-pygame fluidsynth libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libjpeg-dev libpng-dev

echo "--- Configuring /boot/firmware/config.txt for Pirate Audio HAT ---"

# Enable SPI
sudo sed -i -e 's/^#dtparam=spi=on/dtparam=spi=on/' /boot/firmware/config.txt
if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt; then
  echo "dtparam=spi=on" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

# Enable Hifiberry DAC overlay
sudo sed -i -e 's/^#dtoverlay=hifiberry-dac/dtoverlay=hifiberry-dac/' /boot/firmware/config.txt
if ! grep -q "^dtoverlay=hifiberry-dac" /boot/firmware/config.txt; then
  echo "dtoverlay=hifiberry-dac" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

# Disable onboard audio (optional, but good practice for HATs)
sudo sed -i -e 's/^#dtparam=audio=off/dtparam=audio=off/' /boot/firmware/config.txt
if ! grep -q "^dtparam=audio=off" /boot/firmware/config.txt; then
  echo "dtparam=audio=off" | sudo tee -a /boot/firmware/config.txt > /dev/null
fi

echo ""
echo "--- Configuring audio to use the Pirate Audio HAT ---"
ASOUND_CONFIG="pcm.softvol {
    type softvol
    slave {
        pcm \"dmix\"
    }
    control {
        name \"Amp\"
        card 0
    }
    min_dB -5.0
    max_dB 20.0
    resolution 6
}

pcm.!default {
    type plug
    slave.pcm \"softvol\"
}

ctl.!default {
    type hw
    card 0
}"

echo "$ASOUND_CONFIG" | sudo tee /etc/asound.conf > /dev/null

echo ""
echo "--- Part 1 complete! ---"
echo "A reboot is required to apply audio changes."
read -p "Reboot now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]
then
    echo "Rebooting..."
    sudo reboot
fi
