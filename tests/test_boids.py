import numpy as np

from display.demos.boids import compute_flock_acceleration


def _accel(positions, velocities, **overrides):
    params = dict(
        perception_radius=10.0,
        weight_separation=1.0,
        weight_alignment=0.0,
        weight_cohesion=0.0,
        max_force=1000.0,
    )
    params.update(overrides)
    return compute_flock_acceleration(
        np.array(positions, dtype=float), np.array(velocities, dtype=float), **params
    )


def test_separation_pushes_close_boids_apart():
    positions = [[0.0, 0.0], [1.0, 0.0]]
    velocities = [[0.0, 0.0], [0.0, 0.0]]
    accel = _accel(positions, velocities)
    assert accel[0][0] < 0  # boid 0 steers away (left) from boid 1
    assert accel[1][0] > 0  # boid 1 steers away (right) from boid 0


def test_alignment_steers_towards_neighbor_velocity():
    positions = [[0.0, 0.0], [5.0, 0.0]]
    velocities = [[0.0, 0.0], [10.0, 0.0]]
    accel = _accel(
        positions,
        velocities,
        weight_separation=0.0,
        weight_alignment=1.0,
    )
    assert accel[0][0] > 0  # stationary boid steers towards the moving neighbor's heading


def test_cohesion_steers_towards_neighbor_position():
    positions = [[0.0, 0.0], [5.0, 0.0]]
    velocities = [[0.0, 0.0], [0.0, 0.0]]
    accel = _accel(
        positions,
        velocities,
        weight_separation=0.0,
        weight_cohesion=1.0,
    )
    assert accel[0][0] > 0  # boid 0 steers towards boid 1's position


def test_no_neighbors_means_no_acceleration():
    positions = [[0.0, 0.0], [1000.0, 1000.0]]
    velocities = [[0.0, 0.0], [0.0, 0.0]]
    accel = _accel(
        positions,
        velocities,
        weight_separation=1.0,
        weight_alignment=1.0,
        weight_cohesion=1.0,
    )
    assert np.allclose(accel, 0.0)


def test_max_force_clamps_each_behavior_before_weighting():
    # Four close boids -> a large raw separation vector for the boid at the
    # origin. With weight_separation > 1, the *weighted* result can exceed
    # max_force -- only the raw per-behavior vector is clamped to it, not
    # the final weighted sum.
    positions = [[0.0, 0.0], [0.5, 0.0], [0.0, 0.5], [-0.5, 0.0]]
    velocities = [[0.0, 0.0]] * 4
    max_force = 0.5
    weight_separation = 5.0
    accel = _accel(
        positions,
        velocities,
        max_force=max_force,
        weight_separation=weight_separation,
    )
    mags = np.linalg.norm(accel, axis=1)
    assert np.all(mags <= weight_separation * max_force + 1e-9)
    assert np.any(mags > max_force)  # confirms the weight did push past max_force
