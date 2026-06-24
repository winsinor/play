# play

A fun idle-art display for a Raspberry Pi + Pimoroni HyperPixel 4 screen. It
cycles between generative-art demos — boids flocking, a maze generator/solver,
and a Mandelbrot zoom — on a timer, or on demand via keyboard or touchscreen
swipe/tap.

## Demos

- **Boids** — classic separation/alignment/cohesion flocking, vectorized with
  numpy.
- **Maze** — animated recursive-backtracker generation, then a BFS solve
  traced across the screen, then it regenerates.
- **Fractal** — Mandelbrot escape-time zoom into a few curated coordinates,
  with a cycling color palette.

## Controls

| Input | Action |
|---|---|
| Swipe left / right (touchscreen) | Next / previous demo |
| Tap (touchscreen) | Pause / resume auto-advance |
| Left / Right arrow | Previous / next demo |
| Space | Pause / resume auto-advance |
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
