import random

import numpy as np
import pygame

from display.demos.base import Demo
from display.manager import LongPressEvent, TapEvent

BG_COLOR = (9, 10, 18)
PEG_COLOR = (150, 165, 190)
BALL_COLOR = (235, 195, 60)
BAR_COLOR = (70, 130, 230)
BIN_DIVIDER_COLOR = (40, 46, 60)
LABEL_COLOR = (200, 205, 215)


class PlinkoDemo(Demo):
    ROWS = 8
    PEG_SPACING_X = 52
    # Taller/wider than a non-rotated board would need -- the demo is drawn
    # on a portrait virtual canvas (screen height x screen width) and then
    # rotated 90 degrees clockwise onto the real landscape screen, so these
    # are tuned against the swapped dimensions (see setup()/draw()).
    PEG_SPACING_Y = 70
    PEG_RADIUS = 5
    TOP_MARGIN = 60
    N_BINS = ROWS + 1  # one more bin than the bottom peg row -- real binomial outcome count

    GRAVITY = 480.0
    # Capped well under PEG_SPACING_Y (in px/frame @60fps) so a ball can never
    # fall fast enough to skip past a peg row without triggering its kick.
    MAX_FALL_SPEED = 260.0
    KICK_SPEED = 70.0
    KICK_DECAY = 6.0  # exponential decay rate (/s) pulling vx back to 0 between kicks
    BALL_RADIUS = 8

    DROP_STAGGER_SECONDS = 0.05
    PAUSE_SECONDS = 3.0

    BAR_AREA_HEIGHT = 110

    def setup(self, screen_size):
        self.width, self.height = screen_size
        # Layout/physics happen on a virtual canvas with width and height
        # swapped relative to the real screen; draw() renders to this canvas
        # and then rotates it 90 degrees clockwise onto the real surface.
        self.sim_width, self.sim_height = self.height, self.width
        self._scene_surface = pygame.Surface((self.sim_width, self.sim_height))
        self.rng = np.random.default_rng()
        self.font = pygame.font.SysFont(None, 18)

        self.center_x = self.sim_width / 2
        self.peg_rows = [
            [
                (self.center_x + (c - r / 2) * self.PEG_SPACING_X, self.TOP_MARGIN + r * self.PEG_SPACING_Y)
                for c in range(r + 1)
            ]
            for r in range(self.ROWS)
        ]
        self.peg_row_ys = np.array(
            [self.TOP_MARGIN + r * self.PEG_SPACING_Y for r in range(self.ROWS)]
        )

        # Bin area starts one row-spacing below the last peg row (an open
        # gap with no pegs, like a real board) and the bins span a bit wider
        # than the last peg row so a ball that drifted far still lands in a
        # real bin instead of clamping at the very edge one every time.
        self.bin_area_top = self.peg_row_ys[-1] + self.PEG_SPACING_Y
        self.bin_area_bottom = min(self.sim_height - 14, self.bin_area_top + self.BAR_AREA_HEIGHT)
        board_half_width = self.ROWS * self.PEG_SPACING_X / 2
        self.bins_left = self.center_x - board_half_width
        self.bin_width = (2 * board_half_width) / self.N_BINS

        self._start_new_round()

    def _start_new_round(self):
        self.ball_count = random.randint(50, 200)
        self.bin_counts = np.zeros(self.N_BINS, dtype=int)
        self.released = 0
        self.drop_timer = 0.0
        self.positions = np.zeros((0, 2))
        self.velocities = np.zeros((0, 2))
        self.next_row_index = np.zeros((0,), dtype=int)
        self.phase = "dropping"
        self.pause_timer = 0.0

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            if self.phase == "settled":
                self._start_new_round()
        elif isinstance(event, LongPressEvent):
            self._start_new_round()

    def update(self, dt):
        if self.phase == "dropping":
            self._release_balls(dt)
            self._step_balls(dt)
            if self.released >= self.ball_count and len(self.positions) == 0:
                self.phase = "settled"
                self.pause_timer = 0.0
        elif self.phase == "settled":
            self.pause_timer += dt
            if self.pause_timer >= self.PAUSE_SECONDS:
                self._start_new_round()

    def _release_balls(self, dt):
        self.drop_timer += dt
        while self.released < self.ball_count and self.drop_timer >= self.DROP_STAGGER_SECONDS:
            self.drop_timer -= self.DROP_STAGGER_SECONDS
            self._spawn_ball()

    def _spawn_ball(self):
        jitter = self.rng.uniform(-2.0, 2.0)
        pos = [[self.center_x + jitter, self.TOP_MARGIN - self.PEG_SPACING_Y]]
        self.positions = np.vstack([self.positions, pos])
        self.velocities = np.vstack([self.velocities, [[0.0, 0.0]]])
        self.next_row_index = np.append(self.next_row_index, 0)
        self.released += 1

    def _step_balls(self, dt):
        if len(self.positions) == 0:
            return
        self.positions, self.velocities, self.next_row_index, _ = step_balls(
            self.positions,
            self.velocities,
            self.next_row_index,
            self.peg_row_ys,
            dt,
            gravity=self.GRAVITY,
            max_fall_speed=self.MAX_FALL_SPEED,
            kick_speed=self.KICK_SPEED,
            kick_decay=self.KICK_DECAY,
            peg_spacing_x=self.PEG_SPACING_X,
            rng=self.rng,
        )

        settled = self.positions[:, 1] >= self.bin_area_top
        if settled.any():
            idxs = bin_index_for_x(
                self.positions[settled, 0], self.bins_left, self.bin_width, self.N_BINS
            )
            for idx in np.atleast_1d(idxs):
                self.bin_counts[idx] += 1
            keep = ~settled
            self.positions = self.positions[keep]
            self.velocities = self.velocities[keep]
            self.next_row_index = self.next_row_index[keep]

    def draw(self, surface):
        scene = self._scene_surface
        scene.fill(BG_COLOR)
        self._draw_pegs(scene)
        self._draw_balls(scene)
        self._draw_bins(scene)
        surface.blit(pygame.transform.rotate(scene, -90), (0, 0))

    def _draw_pegs(self, surface):
        for row in self.peg_rows:
            for x, y in row:
                pygame.draw.circle(surface, PEG_COLOR, (int(x), int(y)), self.PEG_RADIUS)

    def _draw_balls(self, surface):
        for x, y in self.positions:
            pygame.draw.circle(surface, BALL_COLOR, (int(x), int(y)), self.BALL_RADIUS)

    def _draw_bins(self, surface):
        max_count = max(1, int(self.bin_counts.max())) if len(self.bin_counts) else 1
        area_height = self.bin_area_bottom - self.bin_area_top
        for i in range(self.N_BINS):
            x0 = self.bins_left + i * self.bin_width
            count = int(self.bin_counts[i])
            bar_height = (count / max_count) * area_height
            rect = (
                int(x0) + 1,
                int(self.bin_area_bottom - bar_height),
                int(self.bin_width) - 2,
                int(bar_height),
            )
            pygame.draw.rect(surface, BAR_COLOR, rect)
            pygame.draw.line(
                surface,
                BIN_DIVIDER_COLOR,
                (int(x0), int(self.bin_area_top)),
                (int(x0), int(self.bin_area_bottom)),
            )
            label = self.font.render(str(count), True, LABEL_COLOR)
            label_rect = label.get_rect(
                centerx=int(x0 + self.bin_width / 2), top=int(self.bin_area_bottom) + 2
            )
            surface.blit(label, label_rect)


def step_balls(
    positions, velocities, next_row_index, peg_row_ys, dt, *, gravity, max_fall_speed, kick_speed,
    kick_decay, peg_spacing_x, rng,
):
    """Pure numpy step for every ball at once. Gravity accelerates vy (capped
    at max_fall_speed). A ball "crosses" a peg row once its new y reaches
    that row's y, at which point it gets an unbiased left/right deflection
    and advances to the next row -- once next_row_index has passed every
    row, no further deflections apply and the ball just falls straight down.

    The deflection has two parts: a deterministic horizontal jump of exactly
    half a peg-spacing (matching a real Galton board, where landing position
    after `rows` deflections is `center +/- k*peg_spacing_x` for k rightward
    kicks -- this is what actually determines the bin a ball lands in,
    independent of fall-speed/timing). `vx`/kick_speed/kick_decay only add a
    bit of cosmetic sideways motion between rows and have no bearing on the
    final landing column. Returns the updated (positions, velocities,
    next_row_index) plus a bool mask of which balls were kicked this step."""
    vx = velocities[:, 0] * np.exp(-kick_decay * dt)
    vy = np.minimum(velocities[:, 1] + gravity * dt, max_fall_speed)
    new_y = positions[:, 1] + vy * dt
    new_x = positions[:, 0] + vx * dt

    n_rows = len(peg_row_ys)
    extended_row_ys = np.append(peg_row_ys, np.inf)
    row_y = extended_row_ys[np.clip(next_row_index, 0, n_rows)]
    crossed = (next_row_index < n_rows) & (new_y >= row_y)

    new_next_row_index = next_row_index
    if crossed.any():
        signs = rng.integers(0, 2, size=int(crossed.sum())) * 2 - 1
        vx[crossed] = kick_speed * signs
        new_x[crossed] += signs * (peg_spacing_x / 2)
        new_next_row_index = next_row_index.copy()
        new_next_row_index[crossed] += 1

    new_positions = np.stack([new_x, new_y], axis=1)
    new_velocities = np.stack([vx, vy], axis=1)
    return new_positions, new_velocities, new_next_row_index, crossed


def bin_index_for_x(x, bins_left, bin_width, n_bins):
    """Clamp an x coordinate (scalar or array) to a bin index in [0, n_bins)."""
    idx = np.floor((np.asarray(x, dtype=float) - bins_left) / bin_width).astype(int)
    idx = np.clip(idx, 0, n_bins - 1)
    return idx.item() if np.ndim(x) == 0 else idx
