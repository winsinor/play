import random
from collections import deque

import pygame

from display.demos.base import Demo

CELL_SIZE = 22

WALL_COLOR = (235, 235, 245)
BG_COLOR = (12, 14, 20)
VISITED_COLOR = (40, 70, 110)
FRONTIER_COLOR = (90, 140, 200)
PATH_COLOR = (250, 200, 60)

DIRS = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
OPPOSITE = {"N": "S", "S": "N", "E": "W", "W": "E"}


class MazeDemo(Demo):
    STEPS_PER_FRAME_GENERATE = 3
    STEPS_PER_FRAME_SOLVE = 4
    PAUSE_SECONDS = 2.5

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.cols = max(5, self.width // CELL_SIZE)
        self.rows = max(5, self.height // CELL_SIZE)
        self.offset_x = (self.width - self.cols * CELL_SIZE) // 2
        self.offset_y = (self.height - self.rows * CELL_SIZE) // 2
        self._start_new_maze()

    def _start_new_maze(self):
        self.walls = build_full_wall_grid(self.cols, self.rows)
        self._gen_iter = generate_maze(self.cols, self.rows, self.walls)
        self.visited = set()
        self.phase = "generating"
        self.solve_path = []
        self.solve_visited = set()
        self.solve_frontier = set()
        self.pause_timer = 0.0

    def handle_event(self, event):
        pass

    def update(self, dt):
        if self.phase == "generating":
            for _ in range(self.STEPS_PER_FRAME_GENERATE):
                cell = next(self._gen_iter, None)
                if cell is None:
                    self.phase = "solving"
                    self._solve_iter = solve_maze(self.cols, self.rows, self.walls)
                    break
                self.visited.add(cell)

        elif self.phase == "solving":
            for _ in range(self.STEPS_PER_FRAME_SOLVE):
                result = next(self._solve_iter, "done")
                if result == "done":
                    self.phase = "paused"
                    self.pause_timer = 0.0
                    break
                visited_set, frontier_set, path = result
                self.solve_visited = visited_set
                self.solve_frontier = frontier_set
                if path is not None:
                    self.solve_path = path

        elif self.phase == "paused":
            self.pause_timer += dt
            if self.pause_timer >= self.PAUSE_SECONDS:
                self._start_new_maze()

    def draw(self, surface):
        surface.fill(BG_COLOR)
        for c, r in self.visited:
            self._fill_cell(surface, c, r, VISITED_COLOR)
        for c, r in self.solve_frontier:
            self._fill_cell(surface, c, r, FRONTIER_COLOR)
        for c, r in self.solve_path:
            self._fill_cell(surface, c, r, PATH_COLOR)
        self._draw_walls(surface)

    def _fill_cell(self, surface, c, r, color):
        x = self.offset_x + c * CELL_SIZE
        y = self.offset_y + r * CELL_SIZE
        pygame.draw.rect(surface, color, (x + 1, y + 1, CELL_SIZE - 2, CELL_SIZE - 2))

    def _draw_walls(self, surface):
        for r in range(self.rows):
            for c in range(self.cols):
                x = self.offset_x + c * CELL_SIZE
                y = self.offset_y + r * CELL_SIZE
                walls = self.walls[(c, r)]
                if walls["N"]:
                    pygame.draw.line(surface, WALL_COLOR, (x, y), (x + CELL_SIZE, y), 2)
                if walls["W"]:
                    pygame.draw.line(surface, WALL_COLOR, (x, y), (x, y + CELL_SIZE), 2)
                if r == self.rows - 1 and walls["S"]:
                    pygame.draw.line(
                        surface, WALL_COLOR, (x, y + CELL_SIZE), (x + CELL_SIZE, y + CELL_SIZE), 2
                    )
                if c == self.cols - 1 and walls["E"]:
                    pygame.draw.line(
                        surface, WALL_COLOR, (x + CELL_SIZE, y), (x + CELL_SIZE, y + CELL_SIZE), 2
                    )


def build_full_wall_grid(cols, rows):
    return {(c, r): {"N": True, "S": True, "E": True, "W": True} for r in range(rows) for c in range(cols)}


def generate_maze(cols, rows, walls, rng=None):
    """Randomized recursive-backtracker. Yields each newly-carved cell so callers
    can animate the reveal a few cells at a time."""
    rng = rng or random.Random()
    start = (0, 0)
    stack = [start]
    seen = {start}
    yield start

    while stack:
        c, r = stack[-1]
        neighbors = []
        for direction, (dx, dy) in DIRS.items():
            nc, nr = c + dx, r + dy
            if 0 <= nc < cols and 0 <= nr < rows and (nc, nr) not in seen:
                neighbors.append((direction, (nc, nr)))

        if not neighbors:
            stack.pop()
            continue

        direction, (nc, nr) = rng.choice(neighbors)
        walls[(c, r)][direction] = False
        walls[(nc, nr)][OPPOSITE[direction]] = False
        seen.add((nc, nr))
        stack.append((nc, nr))
        yield (nc, nr)


def solve_maze(cols, rows, walls):
    """BFS from the top-left to the bottom-right cell. Yields
    (visited, frontier, path) after each cell expansion; path is None until the
    goal is found, then the final tuple carries the reconstructed path."""
    start = (0, 0)
    goal = (cols - 1, rows - 1)
    frontier = deque([start])
    came_from = {start: None}
    visited = {start}

    while frontier:
        current = frontier.popleft()
        if current == goal:
            path = []
            node = current
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            yield (set(visited), set(frontier), path)
            return

        c, r = current
        for direction, (dx, dy) in DIRS.items():
            if walls[current][direction]:
                continue
            neighbor = (c + dx, r + dy)
            if neighbor in visited:
                continue
            visited.add(neighbor)
            came_from[neighbor] = current
            frontier.append(neighbor)

        yield (set(visited), set(frontier), None)
