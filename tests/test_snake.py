from display.demos.snake import build_hamiltonian_cycle, choose_next_move


def _assert_valid_cycle(cycle, cols, rows):
    assert len(cycle) == cols * rows
    assert len(set(cycle)) == cols * rows
    for cell in cycle:
        c, r = cell
        assert 0 <= c < cols
        assert 0 <= r < rows
    for a, b in zip(cycle, cycle[1:] + cycle[:1]):
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        assert (dx, dy) in ((1, 0), (0, 1))


def test_build_hamiltonian_cycle_covers_every_cell_with_adjacent_steps():
    for cols, rows in [(4, 4), (6, 4), (5, 6), (10, 2)]:
        _assert_valid_cycle(build_hamiltonian_cycle(cols, rows), cols, rows)


def test_build_hamiltonian_cycle_rejects_odd_rows():
    try:
        build_hamiltonian_cycle(4, 5)
    except ValueError:
        return
    assert False, "expected ValueError for odd rows"


def test_choose_next_move_falls_back_to_cycle_when_space_is_tight():
    cycle = build_hamiltonian_cycle(4, 4)
    cycle_index = {cell: i for i, cell in enumerate(cycle)}
    cycle_next = {cell: cycle[(i + 1) % len(cycle)] for i, cell in enumerate(cycle)}
    head = cycle[0]
    food = cycle[5]
    occupied = set(cycle[-10:])  # snake fills most of the board -> low free space
    move = choose_next_move(head, food, occupied, cycle_index, cycle_next, len(cycle), len(occupied))
    assert move == cycle_next[head]


def test_choose_next_move_never_returns_an_occupied_cell():
    cycle = build_hamiltonian_cycle(6, 4)
    cycle_index = {cell: i for i, cell in enumerate(cycle)}
    cycle_next = {cell: cycle[(i + 1) % len(cycle)] for i, cell in enumerate(cycle)}
    head = cycle[0]
    food = cycle[10]
    occupied = {head}
    move = choose_next_move(head, food, occupied, cycle_index, cycle_next, len(cycle), len(occupied))
    assert move not in occupied


def test_choose_next_move_does_not_overshoot_food():
    cycle = build_hamiltonian_cycle(6, 4)
    cycle_index = {cell: i for i, cell in enumerate(cycle)}
    cycle_next = {cell: cycle[(i + 1) % len(cycle)] for i, cell in enumerate(cycle)}
    head = cycle[0]
    food = cycle[3]
    occupied = {head}
    move = choose_next_move(head, food, occupied, cycle_index, cycle_next, len(cycle), len(occupied))
    head_idx = cycle_index[head]
    food_forward = (cycle_index[food] - head_idx) % len(cycle)
    move_forward = (cycle_index[move] - head_idx) % len(cycle)
    assert move_forward <= food_forward
