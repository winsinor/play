import math

import numpy as np

from display.demos.pendulum import double_pendulum_derivatives, rk4_step

PARAMS = dict(l1=1.0, l2=1.0, m1=1.0, m2=1.0, g=9.8)


def total_energy(state, *, l1, l2, m1, m2, g):
    """Total mechanical energy (kinetic + potential), the quantity the true
    dynamics conserve -- used to check the integrator doesn't pump or bleed
    energy. Heights measured upward from the pivot."""
    t1, w1, t2, w2 = state
    y1 = -l1 * math.cos(t1)
    y2 = y1 - l2 * math.cos(t2)
    potential = m1 * g * y1 + m2 * g * y2
    v1_sq = (l1 * w1) ** 2
    v2_sq = (
        l1**2 * w1**2
        + l2**2 * w2**2
        + 2 * l1 * l2 * w1 * w2 * math.cos(t1 - t2)
    )
    kinetic = 0.5 * m1 * v1_sq + 0.5 * m2 * v2_sq
    return kinetic + potential


def test_equilibrium_at_rest_has_zero_derivatives():
    # Hanging straight down, motionless -> nothing accelerates.
    d = double_pendulum_derivatives(np.array([0.0, 0.0, 0.0, 0.0]), **PARAMS)
    assert np.allclose(d, 0.0)


def test_first_components_are_the_angular_velocities():
    state = np.array([0.3, 1.1, -0.4, -0.7])
    d = double_pendulum_derivatives(state, **PARAMS)
    assert d[0] == 1.1
    assert d[2] == -0.7


def test_small_displacement_is_restoring():
    # Each arm nudged off vertical (the other left at rest) should feel a
    # torque pulling it back toward straight-down -> negative angular accel.
    d1 = double_pendulum_derivatives(np.array([0.05, 0.0, 0.0, 0.0]), **PARAMS)
    assert d1[1] < 0
    d2 = double_pendulum_derivatives(np.array([0.0, 0.0, 0.05, 0.0]), **PARAMS)
    assert d2[3] < 0


def test_rk4_conserves_energy_approximately():
    state = np.array([math.pi / 2, 0.0, math.pi / 2, 0.0])
    e0 = total_energy(state, **PARAMS)
    dt = 1.0 / 480.0
    for _ in range(int(4.0 / dt)):  # 4 seconds of chaotic motion
        state = rk4_step(state, dt, **PARAMS)
    e1 = total_energy(state, **PARAMS)
    assert abs(e1 - e0) <= 1e-2 * abs(e0) + 1e-3


def test_rk4_stays_finite_from_horizontal_release():
    state = np.array([math.pi / 2, 0.0, math.pi / 2, 0.0])
    dt = 1.0 / 240.0
    for _ in range(int(20.0 / dt)):  # 20 seconds -- must never blow up to inf/nan
        state = rk4_step(state, dt, **PARAMS)
    assert np.all(np.isfinite(state))
