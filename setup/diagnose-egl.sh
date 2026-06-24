#!/usr/bin/env bash
# Diagnose the "pygame.error: EGL not initialized" blocker on the Pi 3 +
# HyperPixel4 kmsdrm bring-up. Background/history: docs/pi-bringup-status.md.
#
# Run this ON THE PI itself (not in a dev sandbox):
#   bash setup/diagnose-egl.sh
#
# It installs a couple of small diagnostic/runtime packages, then walks
# through the "not yet tried" steps from the status doc in order, logging
# everything to a timestamped file so the results can be pasted back.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="$REPO_DIR/egl-diagnosis-$(date +%Y%m%d-%H%M%S).log"

log() { echo "$@" | tee -a "$LOG"; }
section() { log ""; log "===== $* ====="; }
run_logged() { "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"; }

section "1. Installing kmscube (isolation test), eglinfo, and apt's pygame/numpy/evdev"
# kmscube/eglinfo are the new diagnostic tools. python3-pygame/numpy/evdev are
# the apt packages already confirmed (per the status doc) to get further than
# the venv-installed pygame -- installing them here so step 6 can use them.
run_logged sudo apt-get update
run_logged sudo apt-get install -y kmscube mesa-utils-extra libgles2 \
    python3-pygame python3-numpy python3-evdev

section "2. Kernel/DRM driver log lines (dmesg)"
dmesg | grep -iE 'v3d|vc4|drm' | tee -a "$LOG"
[ "${PIPESTATUS[0]}" -eq 0 ] || log "(no matching dmesg lines -- on a Pi 3 this overlay drives the GPU through 'vc4', not 'v3d'; vc4/drm lines are what to look for)"

section "3. DRM connector status (sanity recheck)"
for f in /sys/class/drm/*/status; do
    log "$f: $(cat "$f" 2>/dev/null)"
done

section "4. Who currently holds DRM master on /dev/dri/card0"
sudo fuser -v /dev/dri/card0 2>&1 | tee -a "$LOG"
log "(empty output means nothing is holding it open right now)"

section "5. Minimal EGL/GBM smoke test: kmscube"
log "Running kmscube for ~3s. This bypasses pygame/SDL entirely -- if THIS"
log "also fails to get an EGL context, the bug is in the kernel/Mesa/firmware"
log "stack below this repo, and step 6 won't help."
timeout 3 kmscube > >(tee -a "$LOG") 2>&1
rc=$?
if [ "$rc" -eq 124 ]; then
    log "kmscube ran without erroring (killed by timeout after 3s) -- GOOD"
else
    log "kmscube exited early with code $rc -- BAD, see output above"
fi

section "6. Retrying main.py with EGL_PLATFORM forced to gbm (apt's pygame, not the venv)"
sudo systemctl stop pi-display 2>/dev/null || true
cd "$REPO_DIR"
EGL_PLATFORM=gbm SDL_VIDEODRIVER=kmsdrm SDL_AUDIODRIVER=dummy \
    timeout 5 python3 main.py --max-frames 30 > >(tee -a "$LOG") 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
    log "main.py exited cleanly with EGL_PLATFORM=gbm -- THIS LOOKS LIKE THE FIX"
    log "Next: add Environment=EGL_PLATFORM=gbm to setup/pi-display.service,"
    log "then re-run setup/install.sh, then 'sudo systemctl start pi-display'."
else
    log "main.py still failed (exit $rc) even with EGL_PLATFORM=gbm forced"
fi

section "Done"
log "Full log: $LOG"
log "If steps 5 and 6 both still fail, paste $LOG back for the next round --"
log "at that point the fix target is the OS/Mesa/kernel layer (firmware"
log "update, GPU memory/CMA sizing, or a Mesa version issue), not this app."
