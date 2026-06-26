import colorsys

import pygame

from display.demos.base import Demo
from display.manager import TapEvent

BG_COLOR = (10, 10, 18)
GRID_COLOR = (40, 44, 58)
BORDER_COLOR = (90, 200, 255)
DIAGONAL_COLOR = (255, 90, 90)
ANTI_DIAGONAL_COLOR = (90, 255, 140)
LABEL_COLOR = (200, 205, 215)
HINT_COLOR = (130, 135, 145)

GRID_SPACING = 40
MARK_RADIUS = 7
CROSSHAIR_LENGTH = 14


class DrawDemo(Demo):
    """Touch-alignment test screen, not a generative-art demo: a labeled grid
    with both diagonals plus a persistent mark at every tap, so a tap can be
    checked against exactly where it visually lands. Unlike e.g. NBodyDemo
    (where a tapped-in body immediately drifts under gravity), nothing here
    ever moves on its own -- the mark stays exactly where the tap landed
    until cleared. The two diagonals are drawn specifically because a
    swapped-x/y touch axis shows up as taps mirroring across one of them
    (see docs/pi-setup.md's Tuning section on DISPLAY_ROTATE_DEGREES).
    """

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.font_label = pygame.font.SysFont(None, 22)
        self.font_mark = pygame.font.SysFont(None, 16)
        self.marks = []  # list of (x, y, color, index)
        self._next_color_index = 0

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._add_mark(event.x, event.y)

    def _add_mark(self, x, y):
        color = _mark_color(self._next_color_index)
        self._next_color_index += 1
        self.marks.append((x, y, color, len(self.marks)))

    def update(self, dt):
        pass

    def draw(self, surface):
        surface.fill(BG_COLOR)
        self._draw_grid(surface)
        self._draw_diagonals(surface)
        pygame.draw.rect(surface, BORDER_COLOR, (0, 0, self.width, self.height), 2)
        self._draw_labels(surface)
        for x, y, color, index in self.marks:
            self._draw_mark(surface, x, y, color, index)
        if not self.marks:
            self._draw_text(
                surface, self.font_label, "Tap to mark a point - long-press to clear",
                self.width / 2, self.height / 2, HINT_COLOR, anchor="center",
            )

    def _draw_grid(self, surface):
        for x in range(0, self.width, GRID_SPACING):
            pygame.draw.line(surface, GRID_COLOR, (x, 0), (x, self.height))
        for y in range(0, self.height, GRID_SPACING):
            pygame.draw.line(surface, GRID_COLOR, (0, y), (self.width, y))

    def _draw_diagonals(self, surface):
        pygame.draw.line(surface, DIAGONAL_COLOR, (0, 0), (self.width, self.height), 1)
        pygame.draw.line(surface, ANTI_DIAGONAL_COLOR, (self.width, 0), (0, self.height), 1)

    def _draw_labels(self, surface):
        margin = 10
        corners = [
            ("TL", margin, margin, "topleft"),
            ("TR", self.width - margin, margin, "topright"),
            ("BL", margin, self.height - margin, "bottomleft"),
            ("BR", self.width - margin, self.height - margin, "bottomright"),
        ]
        edges = [
            ("TOP", self.width / 2, margin, "midtop"),
            ("BOTTOM", self.width / 2, self.height - margin, "midbottom"),
            ("LEFT", margin, self.height / 2, "midleft"),
            ("RIGHT", self.width - margin, self.height / 2, "midright"),
        ]
        for text, x, y, anchor in corners + edges:
            self._draw_text(surface, self.font_label, text, x, y, LABEL_COLOR, anchor=anchor)

    def _draw_mark(self, surface, x, y, color, index):
        pygame.draw.line(surface, color, (x - CROSSHAIR_LENGTH, y), (x + CROSSHAIR_LENGTH, y), 1)
        pygame.draw.line(surface, color, (x, y - CROSSHAIR_LENGTH), (x, y + CROSSHAIR_LENGTH), 1)
        pygame.draw.circle(surface, color, (int(x), int(y)), MARK_RADIUS, 2)
        self._draw_text(
            surface, self.font_mark, f"#{index} ({int(x)},{int(y)})",
            x, y + CROSSHAIR_LENGTH + 4, color, anchor="midtop",
        )

    def _draw_text(self, surface, font, text, x, y, color, anchor="topleft"):
        rendered = font.render(text, True, color)
        rect = rendered.get_rect()
        setattr(rect, anchor, (x, y))
        rect.clamp_ip(surface.get_rect())
        surface.blit(rendered, rect)


def _mark_color(seed_index):
    """Deterministic, well-separated hue per index via golden-ratio stepping,
    same technique as nbody.py's _planet_color -- keeps consecutive marks
    visually distinct."""
    hue = (seed_index * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.7, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))
