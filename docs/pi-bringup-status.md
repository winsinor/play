# Pi 3 + HyperPixel 4 bring-up: current status

This is a handoff doc for debugging the physical Raspberry Pi 3 + HyperPixel 4
hardware bring-up. The app itself (`main.py`, `display/`, `tests/`) is done
and tested — windowed/dummy-driver smoke tests pass, `pytest` passes. What's
left is purely getting `kmsdrm` rendering working on the real Pi.

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

## Repo follow-up once the real fix is found

`setup/install.sh` currently creates a venv and `pip install`s
`requirements.txt` (pygame/numpy). Since the venv-installed pygame is the
one that *doesn't* support kmsdrm, and apt's `python3-pygame` got further,
the install script likely needs to switch to apt-installing
`python3-pygame python3-numpy` instead (or use
`python3 -m venv --system-site-packages` so the venv can see the apt
packages while still using a venv for `evdev`). `setup/pi-display.service`'s
`ExecStart` would need to point at system `python3` instead of
`.venv/bin/python` accordingly. Hold off on editing these until the EGL
issue above is actually resolved and confirmed working end-to-end.
