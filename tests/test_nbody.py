import numpy as np
import pytest

from display.demos.nbody import compute_gravitational_acceleration


def test_single_body_has_zero_acceleration():
    positions = np.array([[100.0, 100.0]])
    masses = np.array([50.0])
    acc = compute_gravitational_acceleration(positions, masses, g=1.0, softening=1.0)
    assert np.allclose(acc, [[0.0, 0.0]])


def test_no_bodies_returns_empty_array():
    positions = np.zeros((0, 2))
    masses = np.zeros(0)
    acc = compute_gravitational_acceleration(positions, masses, g=1.0, softening=1.0)
    assert acc.shape == (0, 2)


def test_two_bodies_accelerate_toward_each_other():
    positions = np.array([[0.0, 0.0], [100.0, 0.0]])
    masses = np.array([10.0, 10.0])
    acc = compute_gravitational_acceleration(positions, masses, g=1.0, softening=0.0)
    assert acc[0, 0] > 0  # body 0 pulled toward body 1 (+x)
    assert acc[0, 1] == 0
    assert acc[1, 0] < 0  # body 1 pulled toward body 0 (-x)
    assert acc[1, 1] == 0


def test_two_body_acceleration_matches_newtons_law_of_gravitation():
    g, softening = 2.0, 0.0
    positions = np.array([[0.0, 0.0], [10.0, 0.0]])
    masses = np.array([5.0, 7.0])
    acc = compute_gravitational_acceleration(positions, masses, g=g, softening=softening)
    expected_magnitude = g * masses[1] / 10.0**2
    assert acc[0, 0] == pytest.approx(expected_magnitude)


def test_forces_are_equal_and_opposite_newtons_third_law():
    positions = np.array([[0.0, 0.0], [30.0, 40.0]])
    masses = np.array([6.0, 9.0])
    acc = compute_gravitational_acceleration(positions, masses, g=1.0, softening=2.0)
    force_0 = masses[0] * acc[0]
    force_1 = masses[1] * acc[1]
    assert np.allclose(force_0, -force_1)


def test_softening_keeps_acceleration_finite_at_zero_distance():
    positions = np.array([[50.0, 50.0], [50.0, 50.0]])
    masses = np.array([100.0, 100.0])
    acc = compute_gravitational_acceleration(positions, masses, g=1.0, softening=5.0)
    assert np.all(np.isfinite(acc))
    assert np.allclose(acc, [[0.0, 0.0], [0.0, 0.0]])


def test_zero_mass_body_exerts_no_force():
    positions = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
    masses = np.array([5.0, 0.0, 5.0])
    acc = compute_gravitational_acceleration(positions, masses, g=1.0, softening=0.0)
    # Body 0 only feels body 2 (the massless body 1 contributes nothing).
    expected = 1.0 * 5.0 / 20.0**2
    assert acc[0, 0] == pytest.approx(expected)
