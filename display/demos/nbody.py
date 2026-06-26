import colorsys
import math
from collections import deque

import numpy as np
import pygame

from display.demos.base import Demo
from display.manager import LongPressEvent, TapEvent

BG_COLOR = (8, 8, 16)
STAR_COLOR = (255, 225, 140)
# Trails fade from this fraction of a planet's own color (near-black but not
# quite, so they stay visible against BG_COLOR) up to its full color.
TRAIL_DARK_FRACTION = 0.15


class NBodyDemo(Demo):
    # Tuned so an orbiter at the inner edge of the spawn ring (~0.15 of the
    # screen's shorter side) completes an orbit in a handful of seconds, and
    # one at the outer edge (~0.35) takes proportionally longer (r^1.5) --
    # visibly Keplerian without being too fast to read or too slow to notice.
    G = 300.0
    # Softens the 1/r^2 force so it stays finite as bodies pass close to each
    # other, instead of flinging them out at near-infinite speed.
    SOFTENING = 15.0
    # Heavy enough that the momentum a tapped-in body imparts barely moves it
    # even before the momentum-conserving kick in _add_body is applied.
    STAR_MASS = 8000.0
    PLANET_MASS_MIN = 20.0
    PLANET_MASS_MAX = 80.0
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
    TRAIL_LENGTH = 90  # ~1.5s at 60fps
    RECENTER_INTERVAL = 5.0  # seconds between recentering the star
    COLLISION_RADIUS_FRACTION = 0.5  # 50% of star's visual radius

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self._spawn_initial_system()

    def _spawn_initial_system(self):
        cx, cy = self.width / 2, self.height / 2
        self.positions = np.array([[cx, cy]], dtype=float)
        self.velocities = np.array([[0.0, 0.0]])
        self.masses = np.array([self.STAR_MASS])
        self.colors = [STAR_COLOR]
        self.trails = [deque(maxlen=self.TRAIL_LENGTH)]
        self._next_color_index = 0
        self._time_since_recenter = 0.0

        rng = np.random.default_rng()
        min_dim = min(self.width, self.height)
        for _ in range(self.NUM_INITIAL_ORBITERS):
            radius = rng.uniform(0.15, 0.35) * min_dim
            angle = rng.uniform(0, 2 * np.pi)
            pos = [cx + radius * math.cos(angle), cy + radius * math.sin(angle)]
            
            # Random mass between PLANET_MASS_MIN and PLANET_MASS_MAX
            planet_mass = rng.uniform(self.PLANET_MASS_MIN, self.PLANET_MASS_MAX)
            speed = math.sqrt(self.G * self.STAR_MASS / radius)
            # Tangential direction (perpendicular to the radius vector),
            # consistently rotated the same way for every orbiter so they all
            # circle in the same direction rather than colliding head-on.
            direction = (-math.sin(angle), math.cos(angle))
            velocity = [direction[0] * speed, direction[1] * speed]
            self.positions = np.vstack([self.positions, pos])
            self.velocities = np.vstack([self.velocities, velocity])
            self.masses = np.append(self.masses, planet_mass)
            self._add_color_and_trail()

    def _add_color_and_trail(self):
        self.colors.append(_planet_color(self._next_color_index))
        self.trails.append(deque(maxlen=self.TRAIL_LENGTH))
        self._next_color_index += 1

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
        new_velocity = tangential * speed

        # Random mass between PLANET_MASS_MIN and PLANET_MASS_MAX
        planet_mass = np.random.uniform(self.PLANET_MASS_MIN, self.PLANET_MASS_MAX)

        # Conserve momentum: the new body's momentum must be balanced by an
        # equal-and-opposite kick to the star, otherwise every tap injects
        # net momentum into the system and the star (which dominates the
        # system's center of mass) drifts further off-screen with every tap.
        self.velocities[star_idx] = (
            self.velocities[star_idx] - (planet_mass * new_velocity) / star_mass
        )

        self.positions = np.vstack([self.positions, [float(x), float(y)]])
        self.velocities = np.vstack([self.velocities, new_velocity])
        self.masses = np.append(self.masses, planet_mass)
        self._add_color_and_trail()

    def update(self, dt):
        if len(self.masses) == 0:
            self._spawn_initial_system()
            return

        accel = compute_gravitational_acceleration(
            self.positions, self.masses, g=self.G, softening=self.SOFTENING
        )
        self.velocities = self.velocities + accel * dt
        self.positions = self.positions + self.velocities * dt
        self._update_trails()
        self._check_collisions()
        self._cull_escaped_bodies()
        self._recenter_star_if_needed(dt)

    def _check_collisions(self):
        """Check if any planets have passed too close to the star and absorb them.
        Planets within COLLISION_RADIUS_FRACTION of the star's visual radius are absorbed."""
        if len(self.masses) < 2:
            return
        
        star_pos = self.positions[0]
        star_mass = self.masses[0]
        star_radius = np.clip(
            star_mass ** (1 / 3) * self.RADIUS_SCALE, 
            self.MIN_DRAW_RADIUS, 
            self.MAX_DRAW_RADIUS
        )
        collision_radius = star_radius * self.COLLISION_RADIUS_FRACTION
        
        # Find planets to absorb (indices > 0, since star is at index 0)
        to_absorb = []
        for i in range(1, len(self.masses)):
            dist = float(np.linalg.norm(self.positions[i] - star_pos))
            if dist <= collision_radius:
                to_absorb.append(i)
        
        # Absorb planets (iterate in reverse to avoid index shifting)
        for i in reversed(to_absorb):
            star_mass += self.masses[i]
            self.positions = np.delete(self.positions, i, axis=0)
            self.velocities = np.delete(self.velocities, i, axis=0)
            self.masses = np.delete(self.masses, i, axis=0)
            self.colors.pop(i)
            self.trails.pop(i)
        
        # Update star mass
        if len(to_absorb) > 0:
            self.masses[0] = star_mass

    def _recenter_star_if_needed(self, dt):
        """Every RECENTER_INTERVAL seconds, snap the star back to the center
        of the screen. This prevents long-term drift from accumulated momentum
        kicks without affecting the physics of the orbits themselves."""
        self._time_since_recenter += dt
        if self._time_since_recenter >= self.RECENTER_INTERVAL:
            cx, cy = self.width / 2, self.height / 2
            star_pos = self.positions[0]
            offset = np.array([cx, cy]) - star_pos
            # Move all bodies by the same offset so relative positions stay the same
            self.positions += offset
            self._time_since_recenter = 0.0

    def _update_trails(self):
        star_mass = self.masses.max() if len(self.masses) else 0.0
        for i, (pos, mass) in enumerate(zip(self.positions, self.masses)):
            if mass < star_mass * 0.5:
                self.trails[i].append((float(pos[0]), float(pos[1])))

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
            self.colors = [c for c, keep in zip(self.colors, within) if keep]
            self.trails = [t for t, keep in zip(self.trails, within) if keep]

    def draw(self, surface):
        surface.fill(BG_COLOR)
        star_mass = self.masses.max() if len(self.masses) else 0.0
        for i, (pos, mass) in enumerate(zip(self.positions, self.masses)):
            is_star = mass >= star_mass * 0.5
            color = STAR_COLOR if is_star else self.colors[i]
            if not is_star:
                _draw_trail(surface, self.trails[i], color)
            radius = int(
                np.clip(mass ** (1 / 3) * self.RADIUS_SCALE, self.MIN_DRAW_RADIUS, self.MAX_DRAW_RADIUS)
            )
            pygame.draw.circle(surface, color, (int(pos[0]), int(pos[1])), radius)


def _planet_color(seed_index):
    """Deterministic, well-separated hue per index via golden-ratio stepping
    -- stays visually distinct from its neighbors even as the number of
    simultaneously-visible planets changes from adds/culls."""
    hue = (seed_index * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.65, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def _draw_trail(surface, trail, color):
    pts = list(trail)
    n = len(pts)
    if n < 2:
        return
    dark = tuple(int(c * TRAIL_DARK_FRACTION) for c in color)
    step = max(1.0, n - 1)
    for i in range(1, n):
        line_color = _lerp_color(dark, color, i / step)
        pygame.draw.line(surface, line_color, pts[i - 1], pts[i], 2)


def _lerp_color(c0, c1, t):
    return (
        int(c0[0] + (c1[0] - c0[0]) * t),
        int(c0[1] + (c1[1] - c0[1]) * t),
        int(c0[2] + (c1[2] - c0[2]) * t),
    )


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
