# Setting up the HyperPixel 4 idle display on a Raspberry Pi 3

This targets **Raspberry Pi OS Lite** (no desktop/X11) with a **Pimoroni
HyperPixel 4 Rectangular** display, mounted physically rotated to landscape.
The app renders straight to the framebuffer/DRM (SDL's `kmsdrm` driver) and
runs as a systemd service, so it comes up automatically on boot with no login
required.

## 1. Enable the display + touch overlay, with rotation

On current Raspberry Pi OS (kernel 5.15+, images from 2022-04-04 or later —
this is what ships today), HyperPixel4 is driven by the standard VC4 **KMS**
panel driver, *not* the legacy `dtoverlay=hyperpixel4` overlay. The legacy
overlay doesn't create a `/dev/dri` device at all, so SDL's `kmsdrm` driver
will fail with `pygame.error: kmsdrm not available` if that's all you have.

Edit `/boot/firmware/config.txt` (older OS images: `/boot/config.txt`) and add:

```
dtoverlay=vc4-kms-dpi-hyperpixel4
```

The default orientation is portrait with the USB/power ports on the right.
For landscape, add one of these `dtparam` lines directly underneath (these
rotate the touch input to match, so the app never needs its own coordinate
transform):

```
dtparam=rotate=90,touchscreen-swapped-x-y,touchscreen-inverted-y
```
— landscape, ports on the bottom — or:
```
dtparam=rotate=270,touchscreen-swapped-x-y,touchscreen-inverted-x
```
— landscape, ports on the top. Pick whichever matches your physical mount.

Reboot, and confirm the display is alive:

```
sudo reboot
# after it comes back up:
ls /dev/dri              # should list card0/card1 + renderD128 -- if empty, the KMS overlay isn't loading
fbset                     # should show an 800x480 (or 480x800, depending on rotate) framebuffer
```

## 2. Install the app

```
git clone <this repo's URL> ~/play
cd ~/play
bash setup/install.sh
```

`setup/install.sh`:
- installs `python3-pip`
- `pip3 install`s `requirements.txt` (pygame/numpy come down as prebuilt
  wheels from piwheels on a Pi — no slow source compiles)
- adds your user to the `video`, `input`, `render` groups (needed for
  DRM + raw touch device access without root)
- installs and enables `setup/pi-display.service` as a systemd service

If this is the first time your user was added to those groups, reboot once
more (or fully log out/in) before relying on the service.

## 3. Check it's running

```
systemctl status pi-display
journalctl -u pi-display -f
```

You should see boids/maze/fractal cycling on the screen. The log line
`[input_touch] reading touch events from /dev/input/eventN (...)` confirms the
touchscreen was found; `[input_touch] no touchscreen device found` means the
auto-detection didn't find it (see Troubleshooting below) — keyboard nav still
works either way if you have one plugged in.

## 4. Controls

| Input | Action |
|---|---|
| Swipe left / right on screen | Next / previous demo |
| Tap | Pause / resume the auto-advance timer |
| Right / Left arrow key | Next / previous demo |
| Space | Pause / resume the auto-advance timer |
| Esc / q | Quit (mainly useful when running by hand over SSH) |
| (nothing) | Auto-advances to the next demo every `AUTO_ADVANCE_SECONDS` (see `display/config.py`) |

## 5. Manual / interactive debugging

To iterate without waiting on the service:

```
sudo systemctl stop pi-display
cd ~/play
SDL_VIDEODRIVER=kmsdrm SDL_AUDIODRIVER=dummy .venv/bin/python main.py
```

(`setup/install.sh` creates `.venv` for you, since modern Raspberry Pi OS
blocks system-wide `pip install`. If you're not using the venv, activate it
first with `source .venv/bin/activate`.)

Ctrl-C to stop, then `sudo systemctl start pi-display` when you're done.

To test logic changes without the Pi at all, run windowed on any machine with
pygame installed (use a venv there too if your OS enforces PEP 668):

```
python3 main.py --windowed
```

## 6. Touch device troubleshooting

If `[input_touch] no touchscreen device found` shows up but the touchscreen
otherwise works (e.g. under a desktop session), the auto-detect heuristic in
`display/input_touch.py` (looks for a device exposing `ABS_MT_POSITION_X` or
`ABS_X`) didn't match it. List input devices and pin it manually:

```
python3 -c "import evdev; [print(d.path, d.name, d.capabilities(verbose=True).keys()) for d in map(evdev.InputDevice, evdev.list_devices())]"
```

Then set the path explicitly as an environment override, e.g. add to the
service file (or `setup/pi-display.service` before installing):

```
Environment=EVDEV_TOUCH_DEVICE=/dev/input/event2
```

## 7. Tuning

All the knobs live in `display/config.py`:

- `AUTO_ADVANCE_SECONDS` — how long each demo stays up before auto-advancing
- `SWIPE_THRESHOLD_PX` — how far (in raw touch units) a swipe needs to travel
- `TAP_MAX_DURATION` / `TAP_MAX_DISTANCE_PX` — what counts as a "tap" vs a drag

Per-demo parameters (boid count/speed, maze cell size/animation speed,
fractal zoom targets/rate) are constants at the top of each file in
`display/demos/`.

## 8. Adding a new demo

1. Create `display/demos/your_thing.py` with a class implementing the `Demo`
   interface from `display/demos/base.py` (`setup`, `handle_event`, `update`,
   `draw`).
2. Add it to `ALL_DEMOS` in `display/demos/__init__.py`.

That's it — it's now part of the auto-advance/swipe/keyboard cycle.
