#!/usr/bin/env bash
# Run this on the Raspberry Pi (Raspberry Pi OS Lite) as the user that should
# run the display, e.g.:
#   bash setup/install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SUDO_USER:-$(whoami)}"

echo "==> Installing system packages..."
sudo apt-get update
sudo apt-get install -y python3-pip python3-venv

echo "==> Installing Python dependencies (pygame/numpy come from piwheels prebuilt for the Pi)..."
pip3 install --user -r "$REPO_DIR/requirements.txt"

echo "==> Adding $SERVICE_USER to video/input/render groups for DRM + touch access..."
sudo usermod -aG video,input,render "$SERVICE_USER"

echo "==> Installing systemd service..."
sudo sed "s#__REPO_DIR__#$REPO_DIR#g; s#__SERVICE_USER__#$SERVICE_USER#g" \
    "$REPO_DIR/setup/pi-display.service" | sudo tee /etc/systemd/system/pi-display.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now pi-display

echo "==> Done."
echo "Check status with: systemctl status pi-display"
echo "Follow logs with:  journalctl -u pi-display -f"
echo "You may need to log out/in (or reboot) for the new group membership to take effect."
