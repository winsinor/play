import random

from display.demos.maze import (
    DIRS,
    OPPOSITE,
    build_full_wall_grid,
    generate_maze,
    solve_maze,
)


def test_generate_maze_visits_every_cell_exactly_once():
    cols, rows = 8, 6
    walls = build_full_wall_grid(cols, rows)
    rng = random.Random(42)
    visited_order = list(generate_maze(cols, rows, walls, rng))
    assert len(visited_order) == cols * rows
    assert len(set(visited_order)) == cols * rows


def test_generate_maze_walls_are_symmetric_between_neighbors():
    cols, rows = 8, 6
    walls = build_full_wall_grid(cols, rows)
    rng = random.Random(7)
    list(generate_maze(cols, rows, walls, rng))

    for (c, r), cell_walls in walls.items():
        for direction, (dx, dy) in DIRS.items():
            nc, nr = c + dx, r + dy
            if 0 <= nc < cols and 0 <= nr < rows:
                assert cell_walls[direction] == walls[(nc, nr)][OPPOSITE[direction]]


def test_solver_finds_a_valid_path_from_start_to_goal():
    cols, rows = 6, 6
    walls = build_full_wall_grid(cols, rows)
    rng = random.Random(1)
    list(generate_maze(cols, rows, walls, rng))

    *_, last = solve_maze(cols, rows, walls)
    _visited, _frontier, path = last

    assert path is not None
    assert path[0] == (0, 0)
    assert path[-1] == (cols - 1, rows - 1)

    for a, b in zip(path, path[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        direction = next(d for d, v in DIRS.items() if v == (dx, dy))
        assert not walls[a][direction]
