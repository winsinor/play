import numpy as np
import pygame
import pytest

from display.demos.nbody import NBodyDemo, compute_gravitational_acceleration
from display.manager import PressDragEvent, PressReleaseEvent, TapEvent


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


def _slider_y(demo, frac):
    """Screen y for a fraction up a slider track (0 bottom, 1 top)."""
    top_y, bottom_y = demo._slider_track_y()
    return bottom_y - frac * (bottom_y - top_y)


def test_zoom_slider_sets_target_and_eases_toward_it(demo):
    # Tapping near the bottom of the right-edge slider asks for the most
    # zoomed-out view; zoom should ease toward it rather than snap.
    assert demo.zoom == pytest.approx(demo.ZOOM_DEFAULT)
    demo.handle_touch(TapEvent(demo.width - 8, _slider_y(demo, 0.0)))
    assert demo._zoom_target == pytest.approx(demo.ZOOM_MIN, rel=1e-6)
    assert demo.zoom == pytest.approx(demo.ZOOM_DEFAULT)  # target moved, not yet applied
    demo.update(1 / 60)
    assert demo.ZOOM_MIN < demo.zoom < demo.ZOOM_DEFAULT  # eased partway
    for _ in range(600):
        demo.update(1 / 60)
    assert demo.zoom == pytest.approx(demo.ZOOM_MIN, abs=1e-3)


def test_zoom_slider_can_zoom_in_past_the_default_view(demo):
    demo.handle_touch(TapEvent(demo.width - 8, _slider_y(demo, 1.0)))  # top -> max
    assert demo._zoom_target == pytest.approx(demo.ZOOM_MAX, rel=1e-6)
    for _ in range(600):
        demo.update(1 / 60)
    assert demo.zoom == pytest.approx(demo.ZOOM_MAX, abs=1e-3)


def test_speed_slider_sets_simulation_speed(demo):
    assert demo.speed == pytest.approx(demo.SPEED_DEFAULT)
    demo.handle_touch(TapEvent(8, _slider_y(demo, 1.0)))  # left top -> fastest
    assert demo.speed == pytest.approx(demo.SPEED_MAX, rel=1e-6)
    demo.handle_touch(TapEvent(8, _slider_y(demo, 0.0)))  # left bottom -> slowest
    assert demo.speed == pytest.approx(demo.SPEED_MIN, rel=1e-6)


def test_a_drag_starting_on_a_slider_controls_it_not_a_launch(demo):
    # A press-drag whose origin is on the speed slider drives the slider and
    # never starts a launch (no trajectory preview, no spawned body).
    n_before = len(demo.masses)
    demo.handle_touch(PressDragEvent(6, _slider_y(demo, 0.8), 6, _slider_y(demo, 0.5)))
    assert demo._active_slider == "speed"
    assert demo._launch_origin_world is None
    assert demo.is_dragging() is True
    demo.handle_touch(PressReleaseEvent(6, _slider_y(demo, 0.8), 6, _slider_y(demo, 0.5)))
    assert demo._active_slider is None
    assert demo.is_dragging() is False
    assert len(demo.masses) == n_before  # nothing launched


def test_is_dragging_reflects_an_in_progress_launch(demo):
    assert demo.is_dragging() is False
    demo.handle_touch(PressDragEvent(450, 250, 420, 250))
    assert demo.is_dragging() is True
    demo.handle_touch(PressReleaseEvent(450, 250, 420, 250))
    assert demo.is_dragging() is False


def test_instant_drag_zones_are_empty_launch_can_start_anywhere(demo):
    # nbody's launch drag is intentionally allowed to start from any empty
    # point, so it keeps the standard hold-then-drag gate everywhere rather
    # than opting any region into an instant start.
    assert demo.instant_drag_zones() == ()


def test_a_tap_in_the_open_middle_still_adds_a_body(demo):
    n_before = len(demo.masses)
    demo.handle_touch(TapEvent(demo.width / 2, demo.height / 2))
    assert len(demo.masses) == n_before + 1


def test_high_speed_simulation_stays_finite(demo):
    # The speed slider sub-steps the physics so even SPEED_MAX never takes an
    # Euler step large enough to overflow into inf/nan.
    demo.handle_touch(TapEvent(8, _slider_y(demo, 1.0)))  # max speed
    assert demo.speed == pytest.approx(demo.SPEED_MAX)
    for _ in range(600):
        demo.update(1 / 60)
        assert np.isfinite(demo.positions).all()
        assert np.isfinite(demo.velocities).all()
        assert len(demo.masses) > 0
