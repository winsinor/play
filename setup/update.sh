#!/usr/bin/env bash
# Pull the latest code from main and restart the display service to pick it
# up. Run this on the Pi:
#   bash setup/update.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

#BRANCH="main"
BRANCH="fix/touch-calibration-rescaling"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    echo "==> Switching from $CURRENT_BRANCH to $BRANCH..."
    git fetch origin "$BRANCH"
    git checkout "$BRANCH"
fi

echo "==> Pulling origin/$BRANCH..."
git pull origin "$BRANCH"

echo "==> Restarting pi-display service..."
sudo systemctl restart pi-display

echo "==> Done. Tail logs with: journalctl -u pi-display -f"
