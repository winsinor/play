import numpy as np

from display.demos.life import step_life


def test_block_still_life_is_stable():
    grid = np.zeros((6, 6), dtype=bool)
    grid[2:4, 2:4] = True  # 2x2 block -- a classic still life
    next_grid = step_life(grid)
    assert np.array_equal(next_grid, grid)


def test_blinker_oscillates_with_period_two():
    grid = np.zeros((7, 7), dtype=bool)
    grid[3, 2:5] = True  # horizontal blinker

    vertical = np.zeros((7, 7), dtype=bool)
    vertical[2:5, 3] = True

    gen1 = step_life(grid)
    assert np.array_equal(gen1, vertical)

    gen2 = step_life(gen1)
    assert np.array_equal(gen2, grid)


def test_glider_moves_diagonally_after_four_generations():
    grid = np.zeros((10, 10), dtype=bool)
    for c, r in [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]:
        grid[r, c] = True

    generation = grid
    for _ in range(4):
        generation = step_life(generation)

    expected = np.zeros((10, 10), dtype=bool)
    for c, r in [(1, 0), (2, 1), (0, 2), (1, 2), (2, 2)]:
        expected[r + 1, c + 1] = True
    assert np.array_equal(generation, expected)


def test_empty_grid_stays_empty():
    grid = np.zeros((5, 5), dtype=bool)
    assert not step_life(grid).any()


def test_neighbor_count_wraps_around_grid_edges():
    grid = np.zeros((3, 3), dtype=bool)
    # Three live cells clustered across the wrap boundary at column 0/2 --
    # without toroidal wrap these wouldn't be mutual neighbors at all.
    grid[0, 0] = True
    grid[0, 2] = True
    grid[1, 0] = True
    next_grid = step_life(grid)
    assert next_grid[0, 0]  # has neighbors (0,2)+wrap and (1,0): stays alive (2 neighbors)
