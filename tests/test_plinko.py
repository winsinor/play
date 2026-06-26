import math

import numpy as np

from display.demos.plinko import bin_index_for_x, step_balls


def test_bin_index_for_x_clamps_to_range():
    assert bin_index_for_x(-1000.0, bins_left=0.0, bin_width=10.0, n_bins=5) == 0
    assert bin_index_for_x(1000.0, bins_left=0.0, bin_width=10.0, n_bins=5) == 4
    assert bin_index_for_x(25.0, bins_left=0.0, bin_width=10.0, n_bins=5) == 2


def test_bin_index_for_x_vectorized():
    xs = np.array([-5.0, 5.0, 15.0, 25.0, 1000.0])
    idxs = bin_index_for_x(xs, bins_left=0.0, bin_width=10.0, n_bins=4)
    assert list(idxs) == [0, 0, 1, 2, 3]


def test_step_balls_applies_gravity_and_caps_fall_speed():
    positions = np.array([[0.0, 0.0]])
    velocities = np.array([[0.0, 0.0]])
    next_row_index = np.array([5])  # already past every row -> no kicks possible
    pending_offset = np.array([0.0])
    peg_row_ys = np.array([10.0, 20.0])
    rng = np.random.default_rng(0)

    new_pos, new_vel, new_next, new_pending, crossed = step_balls(
        positions, velocities, next_row_index, pending_offset, peg_row_ys, dt=1.0,
        gravity=1000.0, max_fall_speed=50.0, kick_speed=70.0, kick_decay=6.0,
        peg_spacing_x=52.0, ease_rate=20.0, rng=rng,
    )
    assert not crossed.any()
    assert new_vel[0, 1] == 50.0  # capped, not 1000
    assert new_pos[0, 1] == 50.0
    assert list(new_next) == [5]
    assert new_pending[0] == 0.0


def test_step_balls_kicks_only_balls_crossing_a_row():
    positions = np.array([[0.0, -100.0], [0.0, -100.0]])
    velocities = np.array([[0.0, 1000.0], [0.0, 1000.0]])
    next_row_index = np.array([0, 1])  # second ball has already passed row 0
    pending_offset = np.array([0.0, 0.0])
    peg_row_ys = np.array([0.0])
    rng = np.random.default_rng(0)

    _, new_vel, new_next, _, crossed = step_balls(
        positions, velocities, next_row_index, pending_offset, peg_row_ys, dt=1.0,
        gravity=0.0, max_fall_speed=10000.0, kick_speed=70.0, kick_decay=0.0,
        peg_spacing_x=52.0, ease_rate=20.0, rng=rng,
    )
    assert list(crossed) == [True, False]
    assert abs(new_vel[0, 0]) == 70.0
    assert new_vel[1, 0] == 0.0
    assert list(new_next) == [1, 1]


def test_step_balls_kick_split_is_unbiased():
    n = 4000
    positions = np.full((n, 2), [0.0, -100.0])
    velocities = np.full((n, 2), [0.0, 1000.0])
    next_row_index = np.zeros(n, dtype=int)
    pending_offset = np.zeros(n)
    peg_row_ys = np.array([0.0])
    rng = np.random.default_rng(42)

    _, new_vel, _, _, crossed = step_balls(
        positions, velocities, next_row_index, pending_offset, peg_row_ys, dt=1.0,
        gravity=0.0, max_fall_speed=10000.0, kick_speed=70.0, kick_decay=0.0,
        peg_spacing_x=52.0, ease_rate=20.0, rng=rng,
    )
    assert crossed.all()
    left = np.sum(new_vel[:, 0] < 0)
    right = np.sum(new_vel[:, 0] > 0)
    assert left + right == n
    assert abs(left - right) < n * 0.08


def test_step_balls_eases_deflection_over_multiple_small_steps():
    # At a real-time-scale dt (~60fps), a peg crossing's deflection should
    # not land in full on the very frame it occurs -- it should ease in
    # gradually, looking like a deflection rather than a teleport.
    positions = np.array([[0.0, -1.0]])
    velocities = np.array([[0.0, 1000.0]])
    next_row_index = np.array([0])
    pending_offset = np.array([0.0])
    peg_row_ys = np.array([0.0])
    rng = np.random.default_rng(0)
    dt = 1 / 60

    positions, velocities, next_row_index, pending_offset, crossed = step_balls(
        positions, velocities, next_row_index, pending_offset, peg_row_ys, dt=dt,
        gravity=0.0, max_fall_speed=10000.0, kick_speed=0.0, kick_decay=0.0,
        peg_spacing_x=52.0, ease_rate=20.0, rng=rng,
    )
    assert crossed[0]
    # Only a partial fraction of the +/-26px deflection should land this frame.
    assert 0.0 < abs(positions[0, 0]) < 26.0
    assert abs(pending_offset[0]) > 0.0

    # No further crossings -- the rest should ease in over subsequent frames
    # and converge to the full half-peg-spacing deflection.
    for _ in range(300):
        positions, velocities, next_row_index, pending_offset, crossed = step_balls(
            positions, velocities, next_row_index, pending_offset, peg_row_ys, dt=dt,
            gravity=0.0, max_fall_speed=10000.0, kick_speed=0.0, kick_decay=0.0,
            peg_spacing_x=52.0, ease_rate=20.0, rng=rng,
        )
        assert not crossed.any()

    assert abs(abs(positions[0, 0]) - 26.0) < 0.01
    assert abs(pending_offset[0]) < 0.01


def test_full_drop_histogram_approximates_binomial_distribution():
    rows = 8
    n_bins = rows + 1
    peg_spacing_x = 2.0
    peg_row_ys = np.array([float(r) for r in range(rows)])
    n_balls = 20000

    positions = np.full((n_balls, 2), [0.0, -1.0])
    velocities = np.full((n_balls, 2), [0.0, 1.0])
    next_row_index = np.zeros(n_balls, dtype=int)
    pending_offset = np.zeros(n_balls)
    rng = np.random.default_rng(7)

    # vy=1 with row spacing 1 crosses exactly one row per step (gravity=0,
    # fixed vy) -- isolates the deflection statistics from the fall-speed
    # cap, which is already covered above. ease_rate=20 with dt=1.0 consumes
    # essentially all of each step's pending offset immediately (exp(-20) is
    # negligible), so the deterministic +/-peg_spacing_x/2 jump still lands
    # on the same step as the crossing, same as the un-eased version.
    # kick_speed=0 here: the deflection alone determines the landing bin, so
    # the cosmetic between-row vx motion (which would otherwise persist
    # un-decayed at kick_decay=0 and corrupt the landing position) is left
    # out entirely.
    for _ in range(rows):
        positions, velocities, next_row_index, pending_offset, _ = step_balls(
            positions, velocities, next_row_index, pending_offset, peg_row_ys, dt=1.0,
            gravity=0.0, max_fall_speed=10.0, kick_speed=0.0, kick_decay=0.0,
            peg_spacing_x=peg_spacing_x, ease_rate=20.0, rng=rng,
        )

    # After `rows` deflections of +/-peg_spacing_x/2 each, x lands on one of
    # rows+1 evenly-spaced points in [-rows*peg_spacing_x/2, rows*peg_spacing_x/2],
    # matching the real demo's bins_left/bin_width formulas exactly.
    bins_left = -(rows * peg_spacing_x / 2 + peg_spacing_x / 2)
    bins = bin_index_for_x(positions[:, 0], bins_left=bins_left, bin_width=peg_spacing_x, n_bins=n_bins)
    counts = np.bincount(bins, minlength=n_bins)
    assert counts.sum() == n_balls

    center = n_bins // 2
    assert counts.argmax() in (center - 1, center, center + 1)

    expected_fractions = [math.comb(rows, k) / 2**rows for k in range(n_bins)]
    observed_fractions = counts / n_balls
    for observed, expected in zip(observed_fractions, expected_fractions):
        if expected > 0.02:
            assert abs(observed - expected) < 0.03
