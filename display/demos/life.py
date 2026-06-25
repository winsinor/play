from collections import deque

import numpy as np
import pygame
import pygame.surfarray

from display.demos.base import Demo
from display.manager import LongPressEvent, TapEvent

CELL_SIZE = 8
SEED_ALIVE_PROBABILITY = 0.25
GENERATIONS_PER_SECOND = 8
PAUSE_SECONDS = 2.0
# How many past generations to remember when checking for a repeat -- catches
# a die-out (all dead) as well as still lifes and the common low-period
# oscillators (blinkers, toads, pulsars, ...). A long-period oscillator or a
# spaceship that never returns to a remembered state just keeps running,
# which is fine -- restarting is only meant to recover from a boring/stuck
# board, not to force a fixed lifetime.
HISTORY_LENGTH = 16

ALIVE_COLOR = np.array([240, 220, 80], dtype=np.uint8)
BG_COLOR = (10, 10, 18)
BG_COLOR_ARR = np.array(BG_COLOR, dtype=np.uint8)


class LifeDemo(Demo):
    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.cols = max(10, self.width // CELL_SIZE)
        self.rows = max(10, self.height // CELL_SIZE)
        self.offset_x = (self.width - self.cols * CELL_SIZE) // 2
        self.offset_y = (self.height - self.rows * CELL_SIZE) // 2
        self._start_new_generation()

    def _start_new_generation(self):
        rng = np.random.default_rng()
        self.grid = rng.random((self.rows, self.cols)) < SEED_ALIVE_PROBABILITY
        self.history = deque(maxlen=HISTORY_LENGTH)
        self.tick_timer = 0.0
        self.phase = "running"
        self.pause_timer = 0.0

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._toggle_cell(event.x, event.y)
        elif isinstance(event, LongPressEvent):
            self._start_new_generation()

    def _toggle_cell(self, x, y):
        col = (x - self.offset_x) // CELL_SIZE
        row = (y - self.offset_y) // CELL_SIZE
        if 0 <= col < self.cols and 0 <= row < self.rows:
            self.grid[row, col] = not self.grid[row, col]
            # A manual edit makes a paused (dead/repeating) board interesting
            # again -- and resets the repeat-history, since we just changed
            # the state out from under it.
            self.phase = "running"
            self.history.clear()

    def update(self, dt):
        if self.phase == "paused":
            self.pause_timer += dt
            if self.pause_timer >= PAUSE_SECONDS:
                self._start_new_generation()
            return

        self.tick_timer += dt
        tick_interval = 1.0 / GENERATIONS_PER_SECOND
        while self.tick_timer >= tick_interval and self.phase == "running":
            self.tick_timer -= tick_interval
            self._step()

    def _step(self):
        if not self.grid.any():
            self.phase = "paused"
            self.pause_timer = 0.0
            return
        grid_bytes = self.grid.tobytes()
        if grid_bytes in self.history:
            self.phase = "paused"
            self.pause_timer = 0.0
            return
        self.history.append(grid_bytes)
        self.grid = step_life(self.grid)

    def draw(self, surface):
        surface.fill(BG_COLOR)
        colors = np.where(self.grid[..., None], ALIVE_COLOR, BG_COLOR_ARR)
        small_surface = pygame.surfarray.make_surface(colors.swapaxes(0, 1))
        scaled = pygame.transform.scale(small_surface, (self.cols * CELL_SIZE, self.rows * CELL_SIZE))
        surface.blit(scaled, (self.offset_x, self.offset_y))


def step_life(grid):
    """One generation of Conway's Game of Life on a toroidal (wrapping)
    boolean grid: a cell is alive next generation iff it has exactly 3 live
    neighbors, or exactly 2 and is already alive. Vectorized via np.roll
    (one shifted view per neighbor offset, summed) rather than a per-cell
    Python loop -- the whole point of running this on a Pi 3 is to keep the
    per-frame cost low."""
    neighbor_count = sum(
        np.roll(np.roll(grid, dy, axis=0), dx, axis=1)
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
        if not (dx == 0 and dy == 0)
    )
    return (neighbor_count == 3) | (grid & (neighbor_count == 2))
