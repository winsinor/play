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

MOVES_PER_SECOND = 20
RESTART_PAUSE_SECONDS = 2.0

# The AI always follows a precomputed Hamiltonian cycle through every cell on
# the board as its fallback move. That alone guarantees it can never trap or
# collide with itself, and will eventually visit every cell. On top of that,
# whenever there's enough empty board left, it greedily shortcuts forward
# along the cycle toward the food (but never past it) for a much faster,
# more natural-looking game. This isn't globally shortest-path optimal --
# that's intractable in general -- but it is provably safe and will clear the
# whole board if left running.
SHORTCUT_FREE_SPACE_FRACTION = 0.35


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
    """Pick the next cell to move into: the next cell on the Hamiltonian cycle
    by default, or -- when there's a generous amount of free board left -- the
    farthest-forward-along-the-cycle neighbor that gets us closer to the food.

    Why this is provably safe (it never collides and clears the whole board):
    the snake's body always occupies a *sub-arc* of the cycle ending at the
    head -- the cells from the tail forward (in cycle order) up to the head,
    minus any cells a shortcut skipped over (those are simply empty). So every
    cell strictly between the head and the tail *going forward* is guaranteed
    empty. As long as the head only ever moves to such a cell -- i.e. its
    forward cycle-distance stays below the head->tail distance, never
    overtaking the tail -- it can't hit the body, and that move keeps the same
    invariant true for next time.

    The earlier version watched the gap to the tail but still let the head
    chase a food pellet that had been placed *behind* the tail (in a gap an
    earlier shortcut opened up). Reaching it meant overtaking the tail, which
    breaks the invariant and is what let the snake coil up and die with most
    of the board still empty. The fix is simply to never target past the tail:
    when the food is behind it, just follow the cycle until a later lap brings
    the food back ahead."""
    head_idx = cycle_index[head]
    tail_idx = cycle_index[tail]
    fallback = cycle_next[head]

    # Forward (cycle-order) distance from the head to the tail. Everything
    # strictly closer than this is in the empty arc ahead of the head. We stop
    # two short of the tail, not one: landing on the cell *immediately* before
    # the tail leaves the head with nowhere to go next turn except onto the
    # tail's cell, which the caller scores as a collision. At length 1 head ==
    # tail, so the whole board (cycle_length) is the room.
    dist_to_tail = (tail_idx - head_idx) % cycle_length or cycle_length
    max_forward = dist_to_tail - 2
    if max_forward < 1:
        return fallback  # board essentially full -- just follow the cycle

    food_forward = (cycle_index[food] - head_idx) % cycle_length
    if food_forward > max_forward:
        return fallback  # food is behind the tail; advance along the cycle

    free_space = cycle_length - snake_length
    if free_space >= cycle_length * SHORTCUT_FREE_SPACE_FRACTION:
        # Greedily take the neighbor with the largest forward step that still
        # stops short of the food (and so, of the tail) -- every such cell is
        # guaranteed empty, so no occupancy check is needed for correctness.
        best = fallback
        best_forward = 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (head[0] + dx, head[1] + dy)
            if neighbor not in cycle_index:
                continue
            forward = (cycle_index[neighbor] - head_idx) % cycle_length
            if 1 <= forward <= food_forward and forward > best_forward:
                best = neighbor
                best_forward = forward
        return best

    return fallback
