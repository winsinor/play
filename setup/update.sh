#!/usr/bin/env bash
# Pull the latest code for whatever branch is currently checked out and
# restart the display service to pick it up. Run this on the Pi:
#   bash setup/update.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "==> Pulling origin/$BRANCH..."
git pull origin "$BRANCH"

echo "==> Restarting pi-display service..."
sudo systemctl restart pi-display

echo "==> Done. Tail logs with: journalctl -u pi-display -f"
