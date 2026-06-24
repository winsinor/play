# Pi 3 + HyperPixel 4 bring-up: status

**Resolved.** The `EGL not initialized` blocker below was fixed by forcing
`EGL_PLATFORM=gbm` (Mesa's EGL platform auto-detection was failing in this
headless setup). Confirmed end-to-end on hardware: `kmscube` and `main.py`
(via `setup/diagnose-egl.sh`) both ran cleanly, including touchscreen
auto-detection (`Goodix Capacitive TouchScreen`). The fix is now wired into
`setup/pi-display.service` (`Environment=EGL_PLATFORM=gbm`, `ExecStart`
pointed at system `python3`) and `setup/install.sh` (apt-installs
`python3-pygame`/`numpy`/`evdev` instead of a venv). The history below is
kept for reference.

## Goal

Pi 3 + Pimoroni HyperPixel 4 Rectangular, mounted landscape, running
Raspberry Pi OS Lite (headless, no X11). App cycles boids/maze/fractal demos
via pygame, rendering through SDL's `kmsdrm` driver, run as the `pi-display`
systemd service (see `setup/pi-display.service`, `setup/install.sh`,
`docs/pi-setup.md`).

## Confirmed working

- `/boot/firmware/config.txt` has both overlays correctly enabled:
  ```
  dtoverlay=vc4-kms-v3d
  dtoverlay=vc4-kms-dpi-hyperpixel4
  ```
  plus a `dtparam=rotate=...` line per `docs/pi-setup.md`.
- `cat /sys/class/drm/*/status` shows `card0-DPI-1: connected` — the panel
  is correctly detected at the kernel/DRM level. (`card0-HDMI-A-1` is
  `disconnected`, expected — nothing's plugged into HDMI.)
- `/dev/dri/card0` and `renderD128` have correct group ownership
  (`video`/`render`); user `win` is in `video`, `render`, `input` groups;
  the systemd service also runs as `win`. Permissions are not the issue.
- The original pip-installed pygame (in `.venv`, from piwheels) gave
  `pygame.error: kmsdrm not available` — its bundled SDL2 doesn't have
  KMSDRM driver support compiled in.
- Switching to **apt's `python3-pygame`** (system package, run with plain
  `python3`, not `.venv/bin/python`) got further: SDL now recognizes the
  kmsdrm driver, but fails one layer deeper (see below).

## Current blocker

Every attempt now fails identically with:

```
pygame.error: EGL not initialized
```

on `pygame.display.set_mode(config.SCREEN_SIZE)` in `main.py`. Already ruled
out as causes:

- **Missing Mesa packages** — installed `libgbm1 libegl1 libgl1-mesa-dri`
  (which pulled in `libegl-mesa0`, `libglvnd0`, `mesa-vulkan-drivers`,
  `libvulkan1`, etc.) — no change.
- **Console/getty DRM-master conflict** — stopped `getty@tty1` (the
  HyperPixel was showing a login prompt, a plausible DRM-master holder) —
  no change.

## Not yet tried — next steps

`setup/diagnose-egl.sh` runs all three of the steps below in order against a
single timestamped log file (`egl-diagnosis-*.log` in the repo root, gitignored)
— run it on the Pi with `bash setup/diagnose-egl.sh` and paste back the log if
it's still stuck after that.

1. Force Mesa's EGL platform instead of relying on auto-detection (a known
   fix for headless EGL failures where probing fails to pick a backend):
   ```bash
   EGL_PLATFORM=gbm SDL_VIDEODRIVER=kmsdrm SDL_AUDIODRIVER=dummy python3 main.py
   ```
2. Check whether the V3D GPU driver actually bound to hardware at boot, or
   logged a real kernel-level failure we haven't seen yet:
   ```bash
   dmesg | grep -iE 'v3d|vc4|drm'
   ```
3. If both of the above are clean/unhelpful, isolate whether this is a
   pygame/SDL-specific issue or a system Mesa/kernel issue using a minimal
   standalone EGL/GBM test tool:
   ```bash
   sudo apt install -y kmscube
   kmscube
   ```
   If `kmscube` *also* fails to get an EGL context, the problem is below the
   app entirely (kernel/Mesa/firmware), not pygame-specific, and the fix
   target shifts to the OS/driver layer rather than anything in this repo.

## Repo follow-up (done)

`setup/install.sh` now apt-installs `python3-pygame python3-numpy
python3-evdev` instead of creating a venv (the venv-installed pygame is the
one that doesn't support kmsdrm). `setup/pi-display.service`'s `ExecStart`
points at system `python3`, with `Environment=EGL_PLATFORM=gbm` added
alongside the existing `SDL_VIDEODRIVER=kmsdrm`/`SDL_AUDIODRIVER=dummy`.
`docs/pi-setup.md` is updated to match. `requirements.txt` is unchanged —
it's still used for the windowed dev workflow (`python3 main.py --windowed`
off-Pi), which is unaffected.

If you're re-running setup on a Pi that already went through the old
venv-based `install.sh`, the stale `.venv/` directory is harmless (unused,
gitignored) but can be deleted: `rm -rf .venv`.
