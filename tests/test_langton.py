import numpy as np

from display.demos.langton import step_ant


def test_white_cell_turns_right_and_paints_black():
    grid = np.zeros((5, 5), dtype=bool)
    new_pos, new_direction = step_ant(grid, (2, 2), 0)  # facing up
    assert grid[2, 2]  # painted black
    assert new_direction == 1  # up -> right
    assert new_pos == (3, 2)  # moved right


def test_black_cell_turns_left_and_paints_white():
    grid = np.zeros((5, 5), dtype=bool)
    grid[2, 2] = True
    new_pos, new_direction = step_ant(grid, (2, 2), 0)  # facing up
    assert not grid[2, 2]  # painted white
    assert new_direction == 3  # up -> left
    assert new_pos == (1, 2)  # moved left


def test_direction_wraps_around():
    grid = np.zeros((5, 5), dtype=bool)
    # Facing left (3) on white -> turns right -> wraps back to up (0).
    _, new_direction = step_ant(grid, (2, 2), 3)
    assert new_direction == 0


def test_first_four_steps_trace_a_small_square_then_revisit_the_start():
    # Starting on white facing up, the standard turn-right-on-white rule
    # traces exactly one full 2x2 square (painting all 4 of its cells black)
    # before returning to the start cell, now black.
    grid = np.zeros((6, 6), dtype=bool)
    pos, direction = (2, 2), 0
    for _ in range(4):
        pos, direction = step_ant(grid, pos, direction)
    assert pos == (2, 2)
    assert direction == 0
    assert grid[2, 2] and grid[2, 3] and grid[3, 2] and grid[3, 3]
    assert grid.sum() == 4

    # The 5th step lands back on the now-black start cell, turns left, and
    # paints it white again.
    pos, direction = step_ant(grid, pos, direction)
    assert not grid[2, 2]
    assert direction == 3
    assert pos == (1, 2)


def test_does_not_mutate_other_cells():
    grid = np.zeros((5, 5), dtype=bool)
    step_ant(grid, (2, 2), 0)
    assert grid.sum() == 1
