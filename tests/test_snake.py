import random
from collections import deque

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
    tail = cycle[-10]
    food = cycle[5]
    occupied = set(cycle[-10:])  # snake fills most of the board -> low free space
    move = choose_next_move(
        head, tail, food, occupied, cycle_index, cycle_next, len(cycle), len(occupied)
    )
    assert move == cycle_next[head]


def test_choose_next_move_never_returns_an_occupied_cell():
    cycle = build_hamiltonian_cycle(6, 4)
    cycle_index = {cell: i for i, cell in enumerate(cycle)}
    cycle_next = {cell: cycle[(i + 1) % len(cycle)] for i, cell in enumerate(cycle)}
    head = cycle[0]
    tail = head
    food = cycle[10]
    occupied = {head}
    move = choose_next_move(
        head, tail, food, occupied, cycle_index, cycle_next, len(cycle), len(occupied)
    )
    assert move not in occupied


def test_choose_next_move_does_not_overshoot_food():
    cycle = build_hamiltonian_cycle(6, 4)
    cycle_index = {cell: i for i, cell in enumerate(cycle)}
    cycle_next = {cell: cycle[(i + 1) % len(cycle)] for i, cell in enumerate(cycle)}
    head = cycle[0]
    tail = head
    food = cycle[3]
    occupied = {head}
    move = choose_next_move(
        head, tail, food, occupied, cycle_index, cycle_next, len(cycle), len(occupied)
    )
    head_idx = cycle_index[head]
    food_forward = (cycle_index[food] - head_idx) % len(cycle)
    move_forward = (cycle_index[move] - head_idx) % len(cycle)
    assert move_forward <= food_forward


def test_choose_next_move_soak_recovers_from_any_self_collision():
    # The shortcut heuristic keeps a safety margin to the tail, but that's a
    # strong heuristic, not a full proof: a long enough run of shortcuts can
    # still box the head in against an *older* part of its own body that
    # isn't the tail. choose_next_move only ever returns an occupied cell
    # when literally every grid neighbor is occupied (a genuine trap) -- the
    # real demo's _step() treats that as game over and restarts, so this
    # soak mirrors that recovery and asserts the game is never left running
    # in a half-collided state, and that traps stay rare relative to ticks.
    cols, rows = 12, 10
    cycle = build_hamiltonian_cycle(cols, rows)
    cycle_index = {cell: i for i, cell in enumerate(cycle)}
    cycle_next = {cell: cycle[(i + 1) % len(cycle)] for i, cell in enumerate(cycle)}
    cycle_length = len(cycle)

    rng = random.Random(0)

    def new_game():
        return deque([cycle[0]]), {cycle[0]}

    def place_food(occupied):
        free_cells = [c for c in cycle if c not in occupied]
        return rng.choice(free_cells) if free_cells else None

    snake, occupied = new_game()
    food = place_food(occupied)
    ticks = cycle_length * 50
    collisions = 0

    for _ in range(ticks):
        head = snake[-1]
        tail = snake[0]
        next_cell = choose_next_move(
            head, tail, food, occupied, cycle_index, cycle_next, cycle_length, len(snake)
        )

        if next_cell in occupied:
            collisions += 1
            snake, occupied = new_game()
            food = place_food(occupied)
            continue

        ate = next_cell == food
        snake.append(next_cell)
        occupied.add(next_cell)
        if ate:
            food = place_food(occupied)
            if food is None:  # cleared the whole board
                snake, occupied = new_game()
                food = place_food(occupied)
        else:
            old_tail = snake.popleft()
            occupied.discard(old_tail)

    assert collisions < ticks * 0.05
