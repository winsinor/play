import numpy as np
import pygame

from display.demos.base import Demo


class BoidsDemo(Demo):
    NUM_BOIDS = 120
    MAX_SPEED = 140.0
    MAX_FORCE = 250.0
    PERCEPTION_RADIUS = 60.0
    SEPARATION_RADIUS = 24.0
    WEIGHT_SEPARATION = 1.6
    WEIGHT_ALIGNMENT = 1.0
    WEIGHT_COHESION = 0.9
    BG_COLOR = (10, 12, 24)

    def setup(self, screen_size):
        self.width, self.height = screen_size
        rng = np.random.default_rng()
        self.positions = rng.uniform(
            [0, 0], [self.width, self.height], size=(self.NUM_BOIDS, 2)
        )
        angles = rng.uniform(0, 2 * np.pi, size=self.NUM_BOIDS)
        self.velocities = (
            np.column_stack([np.cos(angles), np.sin(angles)]) * self.MAX_SPEED * 0.5
        )

    def handle_event(self, event):
        pass

    def update(self, dt):
        accel = compute_flock_acceleration(
            self.positions,
            self.velocities,
            perception_radius=self.PERCEPTION_RADIUS,
            separation_radius=self.SEPARATION_RADIUS,
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
        self.positions[:, 0] %= self.width
        self.positions[:, 1] %= self.height

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
    separation_radius,
    weight_separation,
    weight_alignment,
    weight_cohesion,
    max_force,
):
    """Pure numpy steering computation, independent of pygame, so it's testable
    without a display."""
    n = len(positions)
    if n == 0:
        return np.zeros_like(positions)

    diffs = positions[:, None, :] - positions[None, :, :]  # diffs[i, j] = pos[i] - pos[j]
    dist = np.linalg.norm(diffs, axis=2)
    np.fill_diagonal(dist, np.inf)

    perception_mask = dist < perception_radius
    separation_mask = dist < separation_radius

    safe_dist = np.where(separation_mask, dist, np.inf)
    sep_vectors = diffs / safe_dist[:, :, None]
    sep_vectors = np.where(separation_mask[:, :, None], sep_vectors, 0.0)
    separation = sep_vectors.sum(axis=1)

    counts = perception_mask.sum(axis=1)
    safe_counts = np.where(counts > 0, counts, 1)

    neighbor_vel_sum = np.where(
        perception_mask[:, :, None], velocities[None, :, :], 0.0
    ).sum(axis=1)
    avg_vel = neighbor_vel_sum / safe_counts[:, None]
    alignment = np.where(counts[:, None] > 0, avg_vel - velocities, 0.0)

    neighbor_pos_sum = np.where(
        perception_mask[:, :, None], positions[None, :, :], 0.0
    ).sum(axis=1)
    avg_pos = neighbor_pos_sum / safe_counts[:, None]
    cohesion = np.where(counts[:, None] > 0, avg_pos - positions, 0.0)

    accel = (
        separation * weight_separation
        + alignment * weight_alignment
        + cohesion * weight_cohesion
    )

    mags = np.linalg.norm(accel, axis=1)
    too_strong = mags > max_force
    if np.any(too_strong):
        accel[too_strong] *= (max_force / mags[too_strong])[:, None]
    return accel
