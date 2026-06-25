import numpy as np
import pygame

from display.demos.base import Demo
from display.manager import LongPressEvent, TapEvent

# See compute_flock_acceleration's docstring/comments for why separation needs
# its own pixel-scale factor (distinct from perception_radius itself).
SEPARATION_RANGE_SCALE = 0.5


class BoidsDemo(Demo):
    NUM_BOIDS = 120
    # Tapping repeatedly grows the flock via _add_boid; this caps how large it
    # can get so the O(n^2) flocking computation (compute_flock_acceleration)
    # never grows unbounded with tap count.
    MAX_BOIDS = 220
    MAX_SPEED = 190.0
    MAX_FORCE = 400.0
    # Perception scales with screen size rather than being a fixed pixel
    # radius. With this large a fraction, most boids can see most of the
    # flock most of the time, which is what makes the flock move as one
    # coherent body instead of splintering into separate circling cliques.
    PERCEPTION_RATIO = 0.4
    WEIGHT_SEPARATION = 1.6
    WEIGHT_ALIGNMENT = 1.0
    WEIGHT_COHESION = 1.5
    BG_COLOR = (10, 12, 24)

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.perception_radius = max(self.width, self.height) * self.PERCEPTION_RATIO
        self._spawn_random(self.NUM_BOIDS)

    def _spawn_random(self, count):
        rng = np.random.default_rng()
        # Spawn clustered near the center (40% of the screen) so boids start
        # within sight of each other instead of scattered too thin.
        cx, cy = self.width / 2, self.height / 2
        spawn_w, spawn_h = self.width * 0.4, self.height * 0.4
        self.positions = rng.uniform(
            [cx - spawn_w / 2, cy - spawn_h / 2],
            [cx + spawn_w / 2, cy + spawn_h / 2],
            size=(count, 2),
        )
        angles = rng.uniform(0, 2 * np.pi, size=count)
        self.velocities = (
            np.column_stack([np.cos(angles), np.sin(angles)]) * self.MAX_SPEED * 0.5
        )

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._add_boid(event.x, event.y)
        elif isinstance(event, LongPressEvent):
            self._spawn_random(self.NUM_BOIDS)

    def _add_boid(self, x, y):
        if len(self.positions) >= self.MAX_BOIDS:
            return
        rng = np.random.default_rng()
        angle = rng.uniform(0, 2 * np.pi)
        velocity = np.array([np.cos(angle), np.sin(angle)]) * self.MAX_SPEED * 0.5
        self.positions = np.vstack([self.positions, [float(x), float(y)]])
        self.velocities = np.vstack([self.velocities, velocity])

    def update(self, dt):
        accel = compute_flock_acceleration(
            self.positions,
            self.velocities,
            perception_radius=self.perception_radius,
            weight_separation=self.WEIGHT_SEPARATION,
            weight_alignment=self.WEIGHT_ALIGNMENT,
            weight_cohesion=self.WEIGHT_COHESION,
            max_force=self.MAX_FORCE,
        )
        self.velocities = self.velocities + accel * dt

        speeds = np.linalg.norm(self.velocities, axis=1)
        too_fast = speeds > self.MAX_SPEED
        if np.any(too_fast):
            self.velocities[too_fast] *= (self.MAX_SPEED / speeds[too_fast])[:, None]

        self.positions = self.positions + self.velocities * dt
        self._bounce_off_walls()

    def _bounce_off_walls(self):
        # Hard boundaries: mirror any overshoot back into bounds and flip the
        # corresponding velocity component, rather than wrapping around.
        for axis, bound in ((0, self.width), (1, self.height)):
            too_low = self.positions[:, axis] < 0
            self.positions[too_low, axis] = -self.positions[too_low, axis]
            self.velocities[too_low, axis] *= -1

            too_high = self.positions[:, axis] > bound
            self.positions[too_high, axis] = 2 * bound - self.positions[too_high, axis]
            self.velocities[too_high, axis] *= -1

    def draw(self, surface):
        surface.fill(self.BG_COLOR)
        for pos, vel in zip(self.positions, self.velocities):
            _draw_boid(surface, pos, vel)


def _draw_boid(surface, pos, vel):
    speed = float(np.hypot(vel[0], vel[1]))
    direction = vel / speed if speed > 1e-6 else np.array([1.0, 0.0])
    perp = np.array([-direction[1], direction[0]])

    size = 7.0
    tip = pos + direction * size
    left = pos - direction * size * 0.6 + perp * size * 0.5
    right = pos - direction * size * 0.6 - perp * size * 0.5

    color = (
        120 + int(80 * direction[0]),
        160 + int(60 * direction[1]),
        220,
    )
    pygame.draw.polygon(surface, color, [tuple(tip), tuple(left), tuple(right)])


def compute_flock_acceleration(
    positions,
    velocities,
    *,
    perception_radius,
    weight_separation,
    weight_alignment,
    weight_cohesion,
    max_force,
    min_separation_fraction=0.05,
):
    """Pure numpy steering computation, independent of pygame, so it's
    testable without a display.

    All three classic boid behaviors (separation, alignment, cohesion) look
    at the *same* perception radius, and each is clamped to max_force
    individually before being weighted and summed -- so a high weight can
    still push a behavior's contribution past max_force overall. This
    mirrors a hand-tuned terminal boids sketch whose flocking felt notably
    better than clamping the combined total: separation in particular decays
    smoothly with distance (~1/d, via a diff/dist^2 vector) across the whole
    perception radius rather than only kicking in within a small separate
    separation radius, which avoids boids packing into tight, sharp-edged
    orbiting clusters. Alignment uses the raw average neighbor velocity
    (not relative to the boid's own velocity), again matching that sketch.
    """
    n = len(positions)
    if n == 0:
        return np.zeros_like(positions)

    diffs = positions[:, None, :] - positions[None, :, :]  # diffs[i, j] = pos[i] - pos[j]
    dist_sq = np.sum(diffs * diffs, axis=2)
    np.fill_diagonal(dist_sq, np.inf)

    perception_mask = dist_sq < perception_radius**2
    counts = perception_mask.sum(axis=1)
    safe_counts = np.where(counts > 0, counts, 1)
    has_neighbors = counts > 0

    # Unit direction away from each neighbor, scaled by ~perception_radius/distance
    # -- clamped to a minimum distance so it caps at a strong-but-finite push
    # instead of blowing up (or, if the *unclamped* raw diff vector were
    # divided by dist_sq instead, actually weakening back toward zero) as
    # boids approach full overlap. The perception_radius factor matters:
    # cohesion and alignment both operate directly in pixel-distance units, so
    # a bare 1/distance separation (fractions well under 1) is utterly
    # dwarfed by them regardless of weight. SEPARATION_RANGE_SCALE further
    # tones that down -- the full perception_radius scale spreads the flock
    # out too loosely (~100px of slack between neighbors); half of it keeps
    # a visibly tighter flock without re-collapsing it.
    dist = np.sqrt(dist_sq)
    unit_diffs = diffs / np.maximum(dist, 1e-6)[:, :, None]
    min_dist = perception_radius * min_separation_fraction
    effective_dist = np.maximum(dist, min_dist)
    separation_range = perception_radius * SEPARATION_RANGE_SCALE
    sep_vectors = np.where(
        perception_mask[:, :, None],
        unit_diffs * (separation_range / effective_dist)[:, :, None],
        0.0,
    )
    separation = sep_vectors.sum(axis=1)

    neighbor_vel_sum = np.where(
        perception_mask[:, :, None], velocities[None, :, :], 0.0
    ).sum(axis=1)
    alignment = np.where(has_neighbors[:, None], neighbor_vel_sum / safe_counts[:, None], 0.0)

    neighbor_pos_sum = np.where(
        perception_mask[:, :, None], positions[None, :, :], 0.0
    ).sum(axis=1)
    avg_pos = neighbor_pos_sum / safe_counts[:, None]
    cohesion = np.where(has_neighbors[:, None], avg_pos - positions, 0.0)

    separation = _limit(separation, max_force)
    alignment = _limit(alignment, max_force)
    cohesion = _limit(cohesion, max_force)

    return (
        separation * weight_separation
        + alignment * weight_alignment
        + cohesion * weight_cohesion
    )


def _limit(vectors, max_magnitude):
    mags = np.linalg.norm(vectors, axis=1)
    too_strong = mags > max_magnitude
    if np.any(too_strong):
        vectors[too_strong] *= (max_magnitude / mags[too_strong])[:, None]
    return vectors
