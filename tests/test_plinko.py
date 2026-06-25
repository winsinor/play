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
    peg_row_ys = np.array([10.0, 20.0])
    rng = np.random.default_rng(0)

    new_pos, new_vel, new_next, crossed = step_balls(
        positions, velocities, next_row_index, peg_row_ys, dt=1.0,
        gravity=1000.0, max_fall_speed=50.0, kick_speed=70.0, kick_decay=6.0, rng=rng,
    )
    assert not crossed.any()
    assert new_vel[0, 1] == 50.0  # capped, not 1000
    assert new_pos[0, 1] == 50.0
    assert list(new_next) == [5]


def test_step_balls_kicks_only_balls_crossing_a_row():
    positions = np.array([[0.0, -100.0], [0.0, -100.0]])
    velocities = np.array([[0.0, 1000.0], [0.0, 1000.0]])
    next_row_index = np.array([0, 1])  # second ball has already passed row 0
    peg_row_ys = np.array([0.0])
    rng = np.random.default_rng(0)

    _, new_vel, new_next, crossed = step_balls(
        positions, velocities, next_row_index, peg_row_ys, dt=1.0,
        gravity=0.0, max_fall_speed=10000.0, kick_speed=70.0, kick_decay=0.0, rng=rng,
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
    peg_row_ys = np.array([0.0])
    rng = np.random.default_rng(42)

    _, new_vel, _, crossed = step_balls(
        positions, velocities, next_row_index, peg_row_ys, dt=1.0,
        gravity=0.0, max_fall_speed=10000.0, kick_speed=70.0, kick_decay=0.0, rng=rng,
    )
    assert crossed.all()
    left = np.sum(new_vel[:, 0] < 0)
    right = np.sum(new_vel[:, 0] > 0)
    assert left + right == n
    assert abs(left - right) < n * 0.08


def test_full_drop_histogram_approximates_binomial_distribution():
    rows = 8
    n_bins = rows + 1
    peg_row_ys = np.array([float(r) for r in range(rows)])
    n_balls = 20000

    positions = np.full((n_balls, 2), [0.0, -1.0])
    velocities = np.full((n_balls, 2), [0.0, 1.0])
    next_row_index = np.zeros(n_balls, dtype=int)
    rng = np.random.default_rng(7)

    # vy=1 with row spacing 1 crosses exactly one row per step (gravity=0,
    # fixed vy) -- isolates the kick statistics from the fall-speed cap,
    # which is already covered above. One extra step beyond `rows` is needed
    # because a kick changes vx for the *next* step's position update, not
    # the step it was triggered on -- without it the final row's kick would
    # never show up in the landing x position.
    for _ in range(rows + 1):
        positions, velocities, next_row_index, _ = step_balls(
            positions, velocities, next_row_index, peg_row_ys, dt=1.0,
            gravity=0.0, max_fall_speed=10.0, kick_speed=1.0, kick_decay=0.0, rng=rng,
        )

    # Each kick moves x by +/-1 in the following step, so after `rows` kicks
    # x lands on one of rows+1 evenly-spaced even integers in [-rows, rows].
    bins = bin_index_for_x(positions[:, 0], bins_left=-(rows + 1), bin_width=2.0, n_bins=n_bins)
    counts = np.bincount(bins, minlength=n_bins)
    assert counts.sum() == n_balls

    center = n_bins // 2
    assert counts.argmax() in (center - 1, center, center + 1)

    expected_fractions = [math.comb(rows, k) / 2**rows for k in range(n_bins)]
    observed_fractions = counts / n_balls
    for observed, expected in zip(observed_fractions, expected_fractions):
        if expected > 0.02:
            assert abs(observed - expected) < 0.03
