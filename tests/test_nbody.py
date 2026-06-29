import numpy as np
import pygame
import pytest

from display.demos.nbody import NBodyDemo, compute_gravitational_acceleration
from display.manager import PinchZoomEvent


@pytest.fixture
def demo():
    pygame.init()
    d = NBodyDemo()
    d.setup((800, 480))
    return d


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


def test_rapid_taps_at_the_same_spot_do_not_cause_a_population_crash(demo):
    # Regression guard: spawning many bodies right on top of each other (a
    # burst of taps landing near the same point, the realistic version of
    # "adding a lot of planets quickly") must not have them spawn already
    # overlapping -- that made the very next physics step read it as
    # simultaneous collisions and merge/shatter away most of what was just
    # added, crashing the population in well under a second and looking
    # exactly like a silent reset even though no state was actually lost.
    for _ in range(120):
        demo._add_body(420, 250)  # same point every time, no jitter
    spawned = len(demo.masses)
    for _ in range(120):
        demo.update(1 / 60)
    # losing a handful to legitimate collisions among bodies that drift back
    # together is fine; losing the bulk of them in one cascade is the bug.
    assert len(demo.masses) >= spawned * 0.7


def test_spawning_past_max_bodies_is_a_silent_no_op(demo):
    # Regression guard: rapid tapping/launching must never be able to grow
    # the body count past MAX_BODIES -- that's what let close encounters
    # get frequent enough to blow positions up to inf/nan and wipe the sim
    # (see MAX_BODIES's docstring).
    for i in range(demo.MAX_BODIES + 50):
        demo._add_body(400 + i * 0.01, 240 + i * 0.01)
    assert len(demo.masses) == demo.MAX_BODIES


def test_physics_never_goes_non_finite_with_many_close_bodies(demo):
    for i in range(demo.MAX_BODIES):
        demo._add_body(400 + i * 0.01, 240 + i * 0.01)
    for _ in range(500):
        demo.update(1 / 60)
        assert len(demo.masses) > 0, "simulation reset (array went empty)"
        assert np.isfinite(demo.positions).all()
        assert np.isfinite(demo.velocities).all()


def test_large_dt_spike_does_not_blow_up_positions(demo):
    # A stalled frame (GC pause, slow draw call) must not translate into one
    # huge Euler step -- update() should clamp it internally.
    demo.update(5.0)
    assert np.isfinite(demo.positions).all()
    assert np.isfinite(demo.velocities).all()


def test_pinch_zoom_eases_toward_target_instead_of_snapping(demo):
    demo.handle_touch(PinchZoomEvent(0.1))
    assert demo.zoom == pytest.approx(1.0)  # not yet applied -- only the target moved
    assert demo._zoom_target == pytest.approx(0.1)
    demo.update(1 / 60)
    assert 0.1 < demo.zoom < 1.0  # eased partway, not snapped all the way


def test_pinch_zoom_eventually_reaches_target(demo):
    demo.handle_touch(PinchZoomEvent(0.1))
    for _ in range(300):
        demo.update(1 / 60)
    assert demo.zoom == pytest.approx(0.1, abs=1e-3)


def test_pinch_can_zoom_in_past_the_default_view(demo):
    # The default view used to sit exactly on ZOOM_MAX, so spreading two
    # fingers to zoom *in* (scale > 1) was a clamped no-op -- half of every
    # pinch did nothing, which is most of why zoom felt unresponsive. Zooming
    # in from the default must now actually magnify, up to ZOOM_MAX.
    assert demo.zoom == pytest.approx(demo.ZOOM_DEFAULT)
    for _ in range(60):
        demo.handle_touch(PinchZoomEvent(1.2))
    assert demo._zoom_target > demo.ZOOM_DEFAULT
    assert demo._zoom_target <= demo.ZOOM_MAX
    for _ in range(300):
        demo.update(1 / 60)
    assert demo.zoom > demo.ZOOM_DEFAULT
