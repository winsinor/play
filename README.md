# play

A fun idle-art display for a Raspberry Pi + Pimoroni HyperPixel 4 screen. It
cycles between generative-art demos — boids flocking, a maze generator/solver,
a Julia set zoom, a DVD-logo bounce, and a self-playing Snake AI — switching
only on demand via keyboard or touchscreen swipe (it never auto-advances).

## Demos

- **Boids** — separation/alignment/cohesion flocking, vectorized with numpy,
  with hard reflective walls. Tap to add a boid, long-press to reset the
  flock.
- **Maze** — animated recursive-backtracker generation (start/goal marked
  green/red), then a BFS solve traced across the screen, then it regenerates.
- **Fractal** — Julia set escape-time zoom that steers toward the boundary
  (the area with the most detail) instead of zooming into a flat interior or
  exterior region, with a cycling color palette.
- **DVD** — the bouncing-logo screensaver, engineered so it hits a corner
  exactly once per cycle (not by chance) with a special flash animation, and
  changes color on every wall touch.
- **Snake** — an AI that always follows a precomputed Hamiltonian cycle
  through the whole board as a safety net (so it can never trap or crash
  itself), taking greedy shortcuts toward the food whenever there's enough
  free space to do so safely.

## Controls

| Input | Action |
|---|---|
| Swipe left / right (touchscreen) | Next / previous demo |
| Tap / long-press (touchscreen) | Demo-specific (see above) |
| Left / Right arrow | Previous / next demo |
| Esc / q | Quit |

## Running it

On a dev machine (any OS with Python + pygame):

```
pip install -r requirements.txt
python3 main.py --windowed
```

On a Raspberry Pi with a HyperPixel 4 display, see
[`docs/pi-setup.md`](docs/pi-setup.md) for full hardware setup, rotation
config, and installing it as an auto-starting systemd service.

## Remote preview

By default the app also serves an MJPEG preview of whatever's on screen at
`http://<device-ip>:8000/`, with a slider on that page to adjust the stream
rate live (no restart needed) -- handy for checking a headless Pi from a
laptop or phone on the same network. Pass `--no-stream` to disable it.

The page also has prev/next buttons that enqueue real navigation events into
the running app (the same path a touchscreen swipe takes), so you can drive
the demo rotation remotely too, not just watch it.

There's also an "Update from GitHub" button that runs `git pull` on the
branch currently checked out and restarts. It never needs sudo: it just
exits, and relies on the systemd service's `Restart=always` to bring it back
up with the new code (see `setup/pi-display.service`). Outside the service —
e.g. running `python3 main.py` by hand — the pull still happens but nothing
restarts it afterwards.

## Adding a new demo

1. Add `display/demos/your_thing.py` implementing the `Demo` interface in
   `display/demos/base.py` (`setup`, `handle_event`, `update`, `draw`).
2. Register the class in `ALL_DEMOS` in `display/demos/__init__.py`.

## Tests

```
pip install pytest
pytest
```

Covers the maze generator/solver correctness and the boids steering math —
pure logic, no display required.
