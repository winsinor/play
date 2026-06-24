import numpy as np

from display.demos.boids import compute_flock_acceleration


def _accel(positions, velocities, **overrides):
    params = dict(
        perception_radius=10.0,
        separation_radius=10.0,
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
        separation_radius=0.0,
        weight_alignment=1.0,
    )
    assert accel[0][0] > 0  # stationary boid steers towards the moving neighbor's heading


def test_cohesion_steers_towards_neighbor_position():
    positions = [[0.0, 0.0], [5.0, 0.0]]
    velocities = [[0.0, 0.0], [0.0, 0.0]]
    accel = _accel(
        positions,
        velocities,
        separation_radius=0.0,
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


def test_max_force_clamps_large_acceleration():
    positions = [[0.0, 0.0], [0.5, 0.0], [0.0, 0.5], [-0.5, 0.0]]
    velocities = [[0.0, 0.0]] * 4
    accel = _accel(positions, velocities, max_force=0.5, weight_separation=5.0)
    mags = np.linalg.norm(accel, axis=1)
    assert np.all(mags <= 0.5 + 1e-9)
