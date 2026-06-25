import math

import numpy as np
import pygame

from display.demos.base import Demo
from display.manager import LongPressEvent, TapEvent

BG_COLOR = (8, 8, 16)
STAR_COLOR = (255, 225, 140)
ORBITER_COLOR = (120, 175, 255)


class NBodyDemo(Demo):
    # Tuned so an orbiter at the inner edge of the spawn ring (~0.15 of the
    # screen's shorter side) completes an orbit in a handful of seconds, and
    # one at the outer edge (~0.35) takes proportionally longer (r^1.5) --
    # visibly Keplerian without being too fast to read or too slow to notice.
    G = 300.0
    # Softens the 1/r^2 force so it stays finite as bodies pass close to each
    # other, instead of flinging them out at near-infinite speed.
    SOFTENING = 15.0
    STAR_MASS = 4000.0
    ORBITER_MASS = 30.0
    TAP_BODY_MASS = 50.0
    NUM_INITIAL_ORBITERS = 4
    MIN_ORBIT_RADIUS = 12.0
    # Bodies more than this many screen-widths/heights from the screen center
    # stop being tracked, so a long session of tapping doesn't slowly grow an
    # ever-larger O(n^2) force computation from bodies that have long since
    # flown off past any visible area.
    TRACKING_AREA_MULTIPLIER = 10
    RADIUS_SCALE = 2.2
    MIN_DRAW_RADIUS = 3
    MAX_DRAW_RADIUS = 18

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self._spawn_initial_system()

    def _spawn_initial_system(self):
        cx, cy = self.width / 2, self.height / 2
        self.positions = np.array([[cx, cy]], dtype=float)
        self.velocities = np.array([[0.0, 0.0]])
        self.masses = np.array([self.STAR_MASS])

        rng = np.random.default_rng()
        min_dim = min(self.width, self.height)
        for _ in range(self.NUM_INITIAL_ORBITERS):
            radius = rng.uniform(0.15, 0.35) * min_dim
            angle = rng.uniform(0, 2 * np.pi)
            pos = [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
            speed = math.sqrt(self.G * self.STAR_MASS / radius)
            # Tangential direction (perpendicular to the radius vector),
            # consistently rotated the same way for every orbiter so they all
            # circle in the same direction rather than colliding head-on.
            direction = (-math.sin(angle), math.cos(angle))
            velocity = [direction[0] * speed, direction[1] * speed]
            self.positions = np.vstack([self.positions, pos])
            self.velocities = np.vstack([self.velocities, velocity])
            self.masses = np.append(self.masses, self.ORBITER_MASS)

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._add_body(event.x, event.y)
        elif isinstance(event, LongPressEvent):
            self._spawn_initial_system()

    def _add_body(self, x, y):
        # New bodies are launched into a circular orbit around the current
        # heaviest body (the "star"), rather than dropped in with zero
        # velocity, so tapping anywhere near it adds a body that swings
        # around instead of just falling straight in.
        star_idx = int(np.argmax(self.masses))
        star_pos = self.positions[star_idx]
        star_mass = self.masses[star_idx]

        offset = np.array([float(x), float(y)]) - star_pos
        r = max(float(np.linalg.norm(offset)), self.MIN_ORBIT_RADIUS)
        direction = offset / r
        tangential = np.array([-direction[1], direction[0]])
        speed = math.sqrt(self.G * star_mass / r)

        self.positions = np.vstack([self.positions, [float(x), float(y)]])
        self.velocities = np.vstack([self.velocities, tangential * speed])
        self.masses = np.append(self.masses, self.TAP_BODY_MASS)

    def update(self, dt):
        if len(self.masses) == 0:
            self._spawn_initial_system()
            return

        accel = compute_gravitational_acceleration(
            self.positions, self.masses, g=self.G, softening=self.SOFTENING
        )
        self.velocities = self.velocities + accel * dt
        self.positions = self.positions + self.velocities * dt
        self._cull_escaped_bodies()

    def _cull_escaped_bodies(self):
        cx, cy = self.width / 2, self.height / 2
        bound_x = self.width * self.TRACKING_AREA_MULTIPLIER / 2
        bound_y = self.height * self.TRACKING_AREA_MULTIPLIER / 2
        within = (np.abs(self.positions[:, 0] - cx) <= bound_x) & (
            np.abs(self.positions[:, 1] - cy) <= bound_y
        )
        if not within.all():
            self.positions = self.positions[within]
            self.velocities = self.velocities[within]
            self.masses = self.masses[within]

    def draw(self, surface):
        surface.fill(BG_COLOR)
        star_mass = self.masses.max() if len(self.masses) else 0.0
        for pos, mass in zip(self.positions, self.masses):
            radius = int(
                np.clip(mass ** (1 / 3) * self.RADIUS_SCALE, self.MIN_DRAW_RADIUS, self.MAX_DRAW_RADIUS)
            )
            color = STAR_COLOR if mass >= star_mass * 0.5 else ORBITER_COLOR
            pygame.draw.circle(surface, color, (int(pos[0]), int(pos[1])), radius)


def compute_gravitational_acceleration(positions, masses, *, g, softening):
    """Pure numpy pairwise gravity, independent of pygame, so it's testable
    without a display. acc[i] = G * sum_j masses[j] * (pos[j] - pos[i]) /
    (dist_ij^2 + softening^2)^1.5 -- the softening term keeps this finite as
    dist_ij -> 0 instead of diverging. The diagonal (j == i) is zeroed
    explicitly: with softening == 0 it would otherwise be 0 * inf (nan)
    rather than the 0 it should contribute.
    """
    n = len(positions)
    if n == 0:
        return np.zeros_like(positions)

    diffs = positions[None, :, :] - positions[:, None, :]  # diffs[i, j] = pos[j] - pos[i]
    dist_sq = np.sum(diffs * diffs, axis=2)
    np.fill_diagonal(dist_sq, 1.0)  # avoid a 0**-1.5 div-by-zero warning; zeroed out below anyway
    inv_dist_cubed = (dist_sq + softening**2) ** -1.5
    np.fill_diagonal(inv_dist_cubed, 0.0)
    return g * np.sum(diffs * (masses[None, :, None] * inv_dist_cubed[:, :, None]), axis=1)
