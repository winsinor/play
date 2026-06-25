import numpy as np
import pygame
import pygame.surfarray

from display.demos.base import Demo

CELL_SIZE = 4
# How many ant steps to simulate per rendered frame. Langton's ant needs
# thousands of steps before its chaotic phase resolves into the famous
# diagonal "highway", so stepping once per frame would make that take
# minutes to even start -- this trades a bit of single-step granularity
# for the pattern actually being visible to watch develop.
STEPS_PER_FRAME = 40
PAUSE_SECONDS = 2.0

BLACK_CELL_COLOR = np.array([235, 235, 245], dtype=np.uint8)
ANT_COLOR = np.array([220, 70, 70], dtype=np.uint8)
BG_COLOR = (10, 10, 16)
BG_COLOR_ARR = np.array(BG_COLOR, dtype=np.uint8)

# Index order matches a 90-degree-right turn cycle: up -> right -> down -> left.
DIRECTIONS = [(0, -1), (1, 0), (0, 1), (-1, 0)]


class LangtonDemo(Demo):
    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.cols = max(10, self.width // CELL_SIZE)
        self.rows = max(10, self.height // CELL_SIZE)
        self.offset_x = (self.width - self.cols * CELL_SIZE) // 2
        self.offset_y = (self.height - self.rows * CELL_SIZE) // 2
        self._start_new_ant()

    def _start_new_ant(self):
        self.grid = np.zeros((self.rows, self.cols), dtype=bool)
        self.pos = (self.cols // 2, self.rows // 2)
        self.direction = 0
        self.phase = "running"
        self.pause_timer = 0.0

    def handle_event(self, event):
        pass

    def update(self, dt):
        if self.phase == "paused":
            self.pause_timer += dt
            if self.pause_timer >= PAUSE_SECONDS:
                self._start_new_ant()
            return

        for _ in range(STEPS_PER_FRAME):
            self.pos, self.direction = step_ant(self.grid, self.pos, self.direction)
            x, y = self.pos
            if not (0 <= x < self.cols and 0 <= y < self.rows):
                self.phase = "paused"
                self.pause_timer = 0.0
                break

    def draw(self, surface):
        surface.fill(BG_COLOR)
        colors = np.where(self.grid[..., None], BLACK_CELL_COLOR, BG_COLOR_ARR)
        x, y = self.pos
        if 0 <= x < self.cols and 0 <= y < self.rows:
            colors[y, x] = ANT_COLOR
        small_surface = pygame.surfarray.make_surface(colors.swapaxes(0, 1))
        scaled = pygame.transform.scale(small_surface, (self.cols * CELL_SIZE, self.rows * CELL_SIZE))
        surface.blit(scaled, (self.offset_x, self.offset_y))


def step_ant(grid, pos, direction):
    """One step of Langton's ant: on a white (False) cell, turn right and
    paint it black; on a black (True) cell, turn left and paint it white;
    then move forward one cell in the new direction. Mutates grid in place
    (flips a single cell) rather than returning a copy -- a full-grid copy
    per step would be far too slow across the thousands of steps needed for
    the ant's chaotic phase to resolve into its "highway" pattern. Returns
    (new_pos, new_direction); does not bounds-check the new position."""
    x, y = pos
    if grid[y, x]:
        grid[y, x] = False
        new_direction = (direction - 1) % 4
    else:
        grid[y, x] = True
        new_direction = (direction + 1) % 4
    dx, dy = DIRECTIONS[new_direction]
    return (x + dx, y + dy), new_direction
