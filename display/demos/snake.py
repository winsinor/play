import random
from collections import deque

import pygame

from display.demos.base import Demo

CELL_SIZE = 20
BG_COLOR = (10, 12, 18)
GRID_COLOR = (24, 28, 38)
SNAKE_COLOR = (60, 200, 90)
HEAD_COLOR = (140, 235, 160)
FOOD_COLOR = (210, 60, 60)

MOVES_PER_SECOND = 14
RESTART_PAUSE_SECONDS = 2.0

# The AI always follows a precomputed Hamiltonian cycle through every cell on
# the board as its fallback move. That alone guarantees it can never trap or
# collide with itself, and will eventually visit every cell. On top of that,
# whenever there's enough empty board left, it greedily shortcuts forward
# along the cycle toward the food (but never past it) for a much faster,
# more natural-looking game. This isn't globally shortest-path optimal --
# that's intractable in general -- but it is provably safe and will clear the
# whole board if left running.
SHORTCUT_FREE_SPACE_FRACTION = 0.5


class SnakeDemo(Demo):
    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.cols = max(4, self.width // CELL_SIZE)
        self.rows = max(4, self.height // CELL_SIZE)
        if self.rows % 2 != 0:
            self.rows -= 1
        self.offset_x = (self.width - self.cols * CELL_SIZE) // 2
        self.offset_y = (self.height - self.rows * CELL_SIZE) // 2

        self.cycle = build_hamiltonian_cycle(self.cols, self.rows)
        self.cycle_index = {cell: i for i, cell in enumerate(self.cycle)}
        self.cycle_next = {
            cell: self.cycle[(i + 1) % len(self.cycle)] for i, cell in enumerate(self.cycle)
        }

        self.move_interval = 1.0 / MOVES_PER_SECOND
        self._start_new_game()

    def _start_new_game(self):
        start = self.cycle[0]
        self.snake = deque([start])
        self.occupied = {start}
        self.move_timer = 0.0
        self.pause_timer = 0.0
        self.game_over = False
        self._place_food()

    def _place_food(self):
        free_cells = [c for c in self.cycle if c not in self.occupied]
        self.food = random.choice(free_cells) if free_cells else None
        if self.food is None:
            self.game_over = True

    def handle_event(self, event):
        pass

    def update(self, dt):
        if self.game_over:
            self.pause_timer += dt
            if self.pause_timer >= RESTART_PAUSE_SECONDS:
                self._start_new_game()
            return

        self.move_timer += dt
        while self.move_timer >= self.move_interval and not self.game_over:
            self.move_timer -= self.move_interval
            self._step()

    def _step(self):
        head = self.snake[-1]
        tail = self.snake[0]
        next_cell = choose_next_move(
            head,
            tail,
            self.food,
            self.occupied,
            self.cycle_index,
            self.cycle_next,
            len(self.cycle),
            len(self.snake),
        )

        if next_cell in self.occupied:
            # Should be unreachable given choose_next_move's safety margin,
            # but never silently step onto our own body -- treat it as a
            # real collision (game over) rather than corrupting state.
            self.game_over = True
            return

        ate = next_cell == self.food
        self.snake.append(next_cell)
        self.occupied.add(next_cell)
        if ate:
            self._place_food()
        else:
            tail = self.snake.popleft()
            self.occupied.discard(tail)

    def draw(self, surface):
        surface.fill(BG_COLOR)
        self._draw_grid(surface)
        if self.food is not None:
            self._fill_cell(surface, self.food, FOOD_COLOR)
        for cell in list(self.snake)[:-1]:
            self._fill_cell(surface, cell, SNAKE_COLOR)
        if self.snake:
            self._fill_cell(surface, self.snake[-1], HEAD_COLOR)

    def _draw_grid(self, surface):
        board_w = self.cols * CELL_SIZE
        board_h = self.rows * CELL_SIZE
        for c in range(self.cols + 1):
            x = self.offset_x + c * CELL_SIZE
            pygame.draw.line(surface, GRID_COLOR, (x, self.offset_y), (x, self.offset_y + board_h))
        for r in range(self.rows + 1):
            y = self.offset_y + r * CELL_SIZE
            pygame.draw.line(surface, GRID_COLOR, (self.offset_x, y), (self.offset_x + board_w, y))

    def _fill_cell(self, surface, cell, color):
        c, r = cell
        x = self.offset_x + c * CELL_SIZE
        y = self.offset_y + r * CELL_SIZE
        pygame.draw.rect(surface, color, (x + 1, y + 1, CELL_SIZE - 2, CELL_SIZE - 2))


def build_hamiltonian_cycle(cols, rows):
    """Build a Hamiltonian cycle covering every (col, row) cell exactly once,
    as an ordered list where consecutive cells (and the last-to-first wrap)
    are always grid-adjacent. Requires rows to be even: row 0 is walked in
    full left-to-right, rows 1..rows-1 are boustrophedon over columns
    1..cols-1, and column 0's remaining cells close the loop back to (0, 0)."""
    if rows % 2 != 0:
        raise ValueError("rows must be even")

    cycle = [(c, 0) for c in range(cols)]
    for r in range(1, rows):
        sweep_index = r - 1
        col_order = range(cols - 1, 0, -1) if sweep_index % 2 == 0 else range(1, cols)
        cycle.extend((c, r) for c in col_order)
    cycle.extend((0, r) for r in range(rows - 1, 0, -1))
    return cycle


def choose_next_move(head, tail, food, occupied, cycle_index, cycle_next, cycle_length, snake_length):
    """Pick the next cell to move into. Falls back to the next cell on the
    Hamiltonian cycle (always safe under normal cycle-following) unless
    there's a generous amount of free board left, in which case it greedily
    takes the farthest-forward-along-the-cycle empty neighbor that doesn't
    pass the food.

    A shortcut jumps the head forward by more than one cycle index per move,
    which breaks the usual invariant that the snake's body is a contiguous
    arc of the cycle directly behind the head -- so a shortcut candidate is
    only accepted if it still leaves a cycle-index gap to our own tail
    bigger than the snake's length. Without that margin, repeated
    shortcutting can let the head lap close enough to the tail that even
    the "always safe" fallback move lands on an occupied cell."""
    fallback = cycle_next[head]
    free_space = cycle_length - snake_length

    if free_space >= cycle_length * SHORTCUT_FREE_SPACE_FRACTION:
        head_idx = cycle_index[head]
        tail_idx = cycle_index[tail]
        food_forward = (cycle_index[food] - head_idx) % cycle_length

        def is_safe(cell_idx):
            return (tail_idx - cell_idx) % cycle_length > snake_length

        best = fallback if fallback not in occupied and is_safe(cycle_index[fallback]) else None
        best_forward = (cycle_index[fallback] - head_idx) % cycle_length if best else -1

        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (head[0] + dx, head[1] + dy)
            if neighbor not in cycle_index or neighbor in occupied:
                continue
            forward = (cycle_index[neighbor] - head_idx) % cycle_length
            if forward == 0 or forward > food_forward:
                continue
            if not is_safe(cycle_index[neighbor]):
                continue
            if forward > best_forward:
                best = neighbor
                best_forward = forward

        if best is not None:
            return best

    if fallback not in occupied:
        return fallback

    # Last resort: the cycle-following invariant has broken down (only
    # possible as a side effect of an earlier shortcut) and even the
    # "always safe" cycle move is blocked. Prefer any unoccupied grid
    # neighbor over stepping onto our own body; if truly none exists, the
    # caller's own occupancy check turns this into a real game over.
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        neighbor = (head[0] + dx, head[1] + dy)
        if neighbor in cycle_index and neighbor not in occupied:
            return neighbor
    return fallback
