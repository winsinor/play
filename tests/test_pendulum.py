import math

import pygame
import pytest

from display.demos.base import Demo
from display.demos.pendulum import (
    DoublePendulumDemo,
    compute_double_pendulum_accelerations,
    mechanical_energy,
    rk4_step,
)
from display.manager import PressDragEvent, PressReleaseEvent, TapEvent


def test_base_demo_has_no_instant_drag_zones_and_never_reports_dragging():
    class _Stub(Demo):
        def setup(self, screen_size):
            pass

        def handle_event(self, event):
            pass

        def update(self, dt):
            pass

        def draw(self, surface):
            pass

    stub = _Stub()
    assert stub.instant_drag_zones() == ()
    assert stub.is_dragging() is False


@pytest.fixture
def demo():
    pygame.init()
    d = DoublePendulumDemo()
    d.setup((800, 480))
    return d


def test_hanging_straight_down_at_rest_has_zero_acceleration():
    alpha1, alpha2 = compute_double_pendulum_accelerations(0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 9.8)
    assert alpha1 == pytest.approx(0.0)
    assert alpha2 == pytest.approx(0.0)


def test_horizontal_start_accelerates_back_toward_vertical():
    # Both rods horizontal, same side, at rest: gravity must pull bob1 back
    # down (negative alpha, since positive theta is displaced toward +x).
    alpha1, _ = compute_double_pendulum_accelerations(
        math.pi / 2, math.pi / 2, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 9.8
    )
    assert alpha1 < 0


def test_rk4_step_conserves_energy_over_many_steps():
    m1 = m2 = 1.0
    L1 = L2 = 1.0
    g = 9.8
    state = (1.0, -0.5, 0.0, 0.0)
    initial_energy = mechanical_energy(*state, m1, m2, L1, L2, g)
    dt = 0.001
    for _ in range(5000):
        state = rk4_step(state, dt, m1, m2, L1, L2, g)
    final_energy = mechanical_energy(*state, m1, m2, L1, L2, g)
    assert final_energy == pytest.approx(initial_energy, abs=1e-3)


def test_default_state_matches_initial_constants(demo):
    assert demo.theta1 == pytest.approx(demo.INITIAL_THETA1)
    assert demo.theta2 == pytest.approx(demo.INITIAL_THETA2)
    assert demo.omega1 == 0.0
    assert demo.omega2 == 0.0


def test_update_advances_the_pendulum(demo):
    theta1_before = demo.theta1
    for _ in range(10):
        demo.update(1 / 60)
    assert demo.theta1 != pytest.approx(theta1_before)
    assert math.isfinite(demo.theta1)
    assert math.isfinite(demo.theta2)


def test_large_dt_spike_stays_finite(demo):
    demo.update(5.0)
    assert math.isfinite(demo.theta1)
    assert math.isfinite(demo.theta2)
    assert math.isfinite(demo.omega1)
    assert math.isfinite(demo.omega2)


def test_tap_does_not_reset_the_pendulum(demo):
    for _ in range(120):
        demo.update(1 / 60)
    theta1_before, theta2_before = demo.theta1, demo.theta2
    demo.handle_touch(TapEvent(10, 10))
    assert demo.theta1 == theta1_before
    assert demo.theta2 == theta2_before


def test_dragging_bob1_sets_theta_and_freezes_physics(demo):
    p1, _ = demo._bob_positions()
    start = (p1[0], p1[1])
    # Drag bob1 straight out to the side (world +x, same height as pivot).
    target = (demo.pivot[0] + 200, demo.pivot[1])
    demo.handle_touch(PressDragEvent(target[0], target[1], start[0], start[1]))
    assert demo._active_bob == 1
    assert demo.theta1 == pytest.approx(math.pi / 2, abs=1e-6)
    assert demo.omega1 == 0.0

    assert demo.is_dragging() is True

    theta1_before = demo.theta1
    demo.update(1 / 60)
    assert demo.theta1 == theta1_before  # frozen mid-drag

    demo.handle_touch(PressReleaseEvent(target[0], target[1], start[0], start[1]))
    assert demo._active_bob is None
    assert demo.is_dragging() is False
    demo.update(1 / 60)
    assert demo.theta1 != theta1_before  # resumes swinging after release


def test_dragging_bob2_leaves_bob1_untouched(demo):
    _, p2 = demo._bob_positions()
    theta1_before = demo.theta1
    target = (p2[0] + 50, p2[1])
    demo.handle_touch(PressDragEvent(target[0], target[1], p2[0], p2[1]))
    assert demo._active_bob == 2
    assert demo.theta1 == pytest.approx(theta1_before)
    assert demo.omega2 == 0.0
    demo.handle_touch(PressReleaseEvent(target[0], target[1], p2[0], p2[1]))
    assert demo._active_bob is None


def test_drag_starting_away_from_either_bob_is_a_no_op(demo):
    theta1_before, theta2_before = demo.theta1, demo.theta2
    demo.handle_touch(PressDragEvent(5, 5, 5, 5))
    assert demo._active_bob == "none"
    assert demo.is_dragging() is False  # nothing grabbed -- fine to switch demos
    demo.update(1 / 60)  # not frozen -- physics keeps running
    assert (demo.theta1, demo.theta2) != (theta1_before, theta2_before)
    demo.handle_touch(PressReleaseEvent(5, 5, 5, 5))
    assert demo._active_bob is None


def test_instant_drag_zones_track_the_live_bob_positions(demo):
    p1, p2 = demo._bob_positions()
    zones = demo.instant_drag_zones()
    assert zones == (
        (p1[0], p1[1], demo.GRAB_RADIUS),
        (p2[0], p2[1], demo.GRAB_RADIUS),
    )
    for _ in range(30):
        demo.update(1 / 60)
    p1_after, p2_after = demo._bob_positions()
    assert demo.instant_drag_zones() == (
        (p1_after[0], p1_after[1], demo.GRAB_RADIUS),
        (p2_after[0], p2_after[1], demo.GRAB_RADIUS),
    )


def test_trail_grows_as_the_pendulum_swings(demo):
    assert len(demo.trail1) == 1
    for _ in range(30):
        demo.update(1 / 60)
    assert len(demo.trail1) > 1
    assert len(demo.trail1) == len(demo.trail2)


def test_trail_length_is_capped(demo):
    for _ in range(demo.TRAIL_LENGTH + 200):
        demo.update(1 / 60)
    assert len(demo.trail1) == demo.TRAIL_LENGTH
    assert len(demo.trail2) == demo.TRAIL_LENGTH
