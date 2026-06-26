import colorsys
import math
from collections import deque

import numpy as np
import pygame

from display.demos.base import Demo
from display.demos.nbody import compute_gravitational_acceleration
from display.manager import TapEvent

BG_COLOR = (6, 6, 14)
# Each system's planets are colored as hue variations of their own star, so
# it stays visually obvious which system a planet (or a chunk of debris)
# originally belonged to even after they've mixed together.
STAR_HUE_A = 0.08  # warm (orange)
STAR_HUE_B = 0.58  # cool (blue)
TRAIL_DARK_FRACTION = 0.25
TRAIL_LENGTH = 140


class StellarCollisionDemo(Demo):
    """Two dense, compact planetary systems drift toward each other and
    collide under gravity -- depending on the (randomized) impact parameter
    and how the planets happen to interact along the way, the two stars
    merge into one, get flung apart again after a slingshot, or settle into
    a mutually orbiting binary, with their planets scattered, captured, or
    absorbed in the process. This is a self-contained show, not an
    interactive toy: it restarts with a freshly randomized approach every
    MAX_RUN_SECONDS (or sooner, once only one body is left), so the cycle
    keeps producing different outcomes if you leave it running. A tap
    restarts it immediately, to preview a different roll without waiting."""

    G = 80.0
    SOFTENING = 6.0

    STAR_MASS_MIN = 9000.0
    STAR_MASS_MAX = 14000.0
    PLANETS_PER_SYSTEM = 5
    PLANET_MASS_MIN = 15.0
    PLANET_MASS_MAX = 45.0
    # Tightly packed -- "very dense" systems, much closer-orbiting than the
    # interactive nbody demo's planets.
    ORBIT_RADIUS_MIN = 16.0
    ORBIT_RADIUS_MAX = 42.0

    RADIUS_SCALE = 2.0
    MIN_DRAW_RADIUS = 3
    MAX_DRAW_RADIUS = 22

    # Each star starts this far from its edge of the screen (as a fraction
    # of width) and they close at a speed tuned so the encounter lands
    # mid-show rather than in the first second or right at the very end.
    SYSTEM_START_FRACTION = 0.12
    APPROACH_SECONDS = 9.0
    # Vertical offset between the two stars' approach paths, randomized each
    # run (as a fraction of screen height) so outcomes vary: near 0 is a
    # head-on hit (merge or, if fast enough, a shattering impact); larger
    # offsets are more likely to produce a slingshot flyby or a captured
    # binary instead. Empirically (see headless multi-seed trials), infall
    # from rest dominates the approach speed by the time the stars are close,
    # so the impact parameter needs to range up to a large fraction of the
    # screen height for flyby/binary outcomes to actually show up at all --
    # anything much smaller and gravitational focusing pulls almost every
    # encounter into a head-on merge.
    IMPACT_PARAMETER_MAX_FRACTION = 0.8

    COLLISION_RADIUS_FRACTION = 1.0
    # Only collisions where *both* bodies are at least this massive are
    # eligible to shatter -- a planet hitting a star (or another planet)
    # always just merges cleanly; only a fast star-on-star hit can produce
    # a debris field.
    STELLAR_MASS_THRESHOLD = 1000.0
    # Two stars falling together from rest collide right around their own
    # mutual escape velocity (that's just energy conservation), so a factor
    # of 1.0 here almost never shatters in practice -- dropped below 1 so a
    # meaningful fraction of head-on hits produce debris instead of always
    # cleanly merging.
    FRAGMENTATION_SPEED_FACTOR = 0.75
    EJECTA_SPEED_FACTOR = 0.35
    MIN_FRAGMENT_MASS = 200.0
    MAX_FRAGMENTS = 4

    # Safety nets (see docs/pi-setup.md and the nbody demo for why these
    # matter): a hard body cap, a per-frame speed clamp, and a clamp on the
    # physics dt itself, so a stalled frame or a chaotic close encounter
    # can never blow a position up to inf/nan.
    MAX_BODIES = 60
    MAX_SPEED = 3000.0
    MAX_PHYSICS_DT = 1.0 / 30.0

    TRACKING_AREA_MULTIPLIER = 2.5  # cull bodies this many screens from center
    MAX_RUN_SECONDS = 32.0
    END_PAUSE_SECONDS = 2.5

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self._start_new_encounter()

    def _start_new_encounter(self):
        rng = np.random.default_rng()
        cy = self.height / 2
        gap = self.width * (1 - 2 * self.SYSTEM_START_FRACTION)
        approach_speed = (gap / 2) / self.APPROACH_SECONDS
        impact_offset = rng.uniform(-1, 1) * self.IMPACT_PARAMETER_MAX_FRACTION * self.height

        positions, velocities, masses, colors = [], [], [], []
        star_a_pos = (self.width * self.SYSTEM_START_FRACTION, cy - impact_offset / 2)
        star_b_pos = (self.width * (1 - self.SYSTEM_START_FRACTION), cy + impact_offset / 2)
        self._add_system(
            positions, velocities, masses, colors, rng,
            star_pos=star_a_pos, star_velocity=(approach_speed, 0.0),
            star_mass=rng.uniform(self.STAR_MASS_MIN, self.STAR_MASS_MAX), hue=STAR_HUE_A,
        )
        self._add_system(
            positions, velocities, masses, colors, rng,
            star_pos=star_b_pos, star_velocity=(-approach_speed, 0.0),
            star_mass=rng.uniform(self.STAR_MASS_MIN, self.STAR_MASS_MAX), hue=STAR_HUE_B,
        )

        self.positions = np.array(positions, dtype=float)
        self.velocities = np.array(velocities, dtype=float)
        self.masses = np.array(masses, dtype=float)
        self.colors = colors
        self.trails = [deque(maxlen=TRAIL_LENGTH) for _ in masses]
        self.elapsed = 0.0
        self.phase = "running"
        self.pause_timer = 0.0

    def _add_system(self, positions, velocities, masses, colors, rng, *, star_pos, star_velocity, star_mass, hue):
        positions.append(list(star_pos))
        velocities.append(list(star_velocity))
        masses.append(star_mass)
        colors.append(_hue_color(hue, 1.0, 0.85))

        for i in range(self.PLANETS_PER_SYSTEM):
            radius = rng.uniform(self.ORBIT_RADIUS_MIN, self.ORBIT_RADIUS_MAX)
            angle = rng.uniform(0, 2 * np.pi)
            planet_mass = rng.uniform(self.PLANET_MASS_MIN, self.PLANET_MASS_MAX)
            speed = math.sqrt(self.G * star_mass / radius)
            direction = (-math.sin(angle), math.cos(angle))
            positions.append([star_pos[0] + radius * math.cos(angle), star_pos[1] + radius * math.sin(angle)])
            velocities.append([
                star_velocity[0] + direction[0] * speed,
                star_velocity[1] + direction[1] * speed,
            ])
            masses.append(planet_mass)
            colors.append(_hue_color(hue, 0.55 + 0.08 * i, 1.0))

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._start_new_encounter()

    def update(self, dt):
        if self.phase == "paused":
            self.pause_timer += dt
            if self.pause_timer >= self.END_PAUSE_SECONDS:
                self._start_new_encounter()
            return

        self.elapsed += dt
        if len(self.masses) <= 1 or self.elapsed >= self.MAX_RUN_SECONDS:
            self.phase = "paused"
            self.pause_timer = 0.0
            return

        dt = min(dt, self.MAX_PHYSICS_DT)
        accel = compute_gravitational_acceleration(self.positions, self.masses, g=self.G, softening=self.SOFTENING)
        self.velocities = self.velocities + accel * dt
        speed = np.sqrt(np.sum(self.velocities * self.velocities, axis=1))
        too_fast = speed > self.MAX_SPEED
        if too_fast.any():
            self.velocities[too_fast] *= (self.MAX_SPEED / speed[too_fast])[:, None]
        self.positions = self.positions + self.velocities * dt
        self._update_trails()
        self._check_collisions()
        self._cull_escaped_bodies()

    def _radius_for_mass(self, mass):
        return np.clip(mass ** (1 / 3) * self.RADIUS_SCALE, self.MIN_DRAW_RADIUS, self.MAX_DRAW_RADIUS)

    def _update_trails(self):
        for i in range(len(self.positions)):
            self.trails[i].append((float(self.positions[i, 0]), float(self.positions[i, 1])))

    def _check_collisions(self):
        """Pairwise collision-merge over *every* body (unlike the nbody demo,
        there's no single privileged star index here -- either star can be
        on either side of a collision). The full pairwise distance matrix is
        computed in one vectorized batch; only candidate colliding pairs
        (almost always zero) go through the Python greedy-claim loop."""
        n = len(self.masses)
        if n < 2:
            return

        radii = self._radius_for_mass(self.masses)
        diffs = self.positions[:, None, :] - self.positions[None, :, :]
        dist = np.sqrt(np.sum(diffs * diffs, axis=2))
        threshold = (radii[:, None] + radii[None, :]) * self.COLLISION_RADIUS_FRACTION
        colliding = np.triu(dist <= threshold, k=1)
        idx_i, idx_j = np.nonzero(colliding)

        claimed = np.zeros(n, dtype=bool)
        pairs = []
        for i, j in zip(idx_i, idx_j):
            i, j = int(i), int(j)
            if claimed[i] or claimed[j]:
                continue
            pairs.append((i, j))
            claimed[i] = True
            claimed[j] = True
        if not pairs:
            return

        new_bodies = [self._resolve_collision(i, j) for i, j in pairs]

        keep = ~claimed
        self.positions = self.positions[keep]
        self.velocities = self.velocities[keep]
        self.masses = self.masses[keep]
        self.colors = [c for c, k in zip(self.colors, keep) if k]
        self.trails = [t for t, k in zip(self.trails, keep) if k]

        for bodies in new_bodies:
            for pos, vel, mass, color in bodies:
                if len(self.masses) >= self.MAX_BODIES:
                    break
                self.positions = np.vstack([self.positions, pos])
                self.velocities = np.vstack([self.velocities, vel])
                self.masses = np.append(self.masses, mass)
                self.colors.append(color)
                self.trails.append(deque(maxlen=TRAIL_LENGTH))

    def _resolve_collision(self, i, j):
        """Resolve a collision between bodies i and j, returning a list of
        (position, velocity, mass, color) tuples for the body/bodies it
        becomes. A slow merge (or any collision involving a sub-stellar
        body) combines into one; a fast star-on-star impact shatters into
        capped, momentum-conserving fragments -- same rule of thumb as the
        nbody demo's planet collisions (shatter iff impact speed exceeds the
        pair's mutual escape velocity), just gated additionally on both
        bodies being star-sized so a star swallowing a tiny planet always
        reads as a clean absorption, never an explosion."""
        m1, m2 = self.masses[i], self.masses[j]
        total_mass = m1 + m2
        pos1, pos2 = self.positions[i], self.positions[j]
        vel1, vel2 = self.velocities[i], self.velocities[j]
        color = self.colors[i] if m1 >= m2 else self.colors[j]

        v_com = (m1 * vel1 + m2 * vel2) / total_mass
        collision_point = (m1 * pos1 + m2 * pos2) / total_mass
        relative_speed = float(np.linalg.norm(vel1 - vel2))

        contact_dist = float(self._radius_for_mass(m1) + self._radius_for_mass(m2))
        mutual_escape_speed = math.sqrt(2 * self.G * total_mass / contact_dist)
        max_fragments = int(total_mass // self.MIN_FRAGMENT_MASS)
        both_stellar = min(m1, m2) >= self.STELLAR_MASS_THRESHOLD
        shatters = (
            both_stellar
            and relative_speed > mutual_escape_speed * self.FRAGMENTATION_SPEED_FACTOR
            and max_fragments >= 2
        )
        fragment_count = min(self.MAX_FRAGMENTS, max_fragments) if shatters else 1

        if fragment_count == 1:
            return [(collision_point, v_com, total_mass, color)]

        rng = np.random.default_rng()
        leftover = total_mass - fragment_count * self.MIN_FRAGMENT_MASS
        frag_masses = self.MIN_FRAGMENT_MASS + leftover * rng.dirichlet(np.ones(fragment_count))

        ejecta_speed = relative_speed * self.EJECTA_SPEED_FACTOR
        base_angle = rng.uniform(0, 2 * np.pi)
        angles = (
            base_angle
            + np.arange(fragment_count) * (2 * np.pi / fragment_count)
            + rng.uniform(-0.3, 0.3, fragment_count)
        )
        directions = np.stack([np.cos(angles), np.sin(angles)], axis=1)
        kicks_raw = directions * ejecta_speed
        net_bias = np.sum(frag_masses[:, None] * kicks_raw, axis=0) / total_mass
        kicks = kicks_raw - net_bias

        bodies = []
        for k in range(fragment_count):
            separation = contact_dist * 0.5 + float(self._radius_for_mass(frag_masses[k]))
            frag_pos = collision_point + directions[k] * separation
            frag_vel = v_com + kicks[k]
            bodies.append((frag_pos, frag_vel, frag_masses[k], color))
        return bodies

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
        n = len(self.masses)
        if n == 0:
            return
        radii = np.maximum(1, self._radius_for_mass(self.masses)).astype(int)
        for i in range(n):
            _draw_trail(surface, self.trails[i], self.colors[i])
            pygame.draw.circle(
                surface, self.colors[i], (int(self.positions[i, 0]), int(self.positions[i, 1])), int(radii[i])
            )


def _hue_color(hue, sat, val):
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, sat, val)
    return (int(r * 255), int(g * 255), int(b * 255))


def _draw_trail(surface, trail, color):
    if len(trail) < 2:
        return
    dark = tuple(int(c * TRAIL_DARK_FRACTION) for c in color)
    pygame.draw.lines(surface, dark, False, list(trail), 2)
