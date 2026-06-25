import math
import random
from pathlib import Path

import pygame

from display.demos.base import Demo

LOGO_ASSET_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "dvd_logo.png"
LOGO_WIDTH = 160  # display width in pixels; height follows the source image's aspect ratio
LOGO_ROTATION_DEGREES = 90  # fixed rotation applied once at load time, not animated --
# if it ends up rotated the wrong way, try -90 instead.

COLORS = [
    (230, 60, 60),
    (60, 200, 90),
    (70, 130, 230),
    (230, 210, 60),
    (210, 70, 200),
    (60, 210, 210),
    (240, 150, 50),
    (235, 235, 245),
]

# The corner-hit period and the (coprime) number of wall-touches per axis per
# period. With these, the logo's x and y positions are exactly commensurate
# (see bounce_position), so they line up at a wall *simultaneously* -- a
# corner hit -- once every CORNER_PERIOD seconds, by construction rather than
# by chance. Non-corner wall bounces happen in between. (20, 23) keeps the
# per-axis speed close to a smaller, more frequent-feeling pair like (2, 3)
# while pushing the corner-hit period itself out to roughly once a minute.
CORNER_PERIOD = 60.0
AXIS_TOUCHES_PER_PERIOD = (20, 23)  # (x, y) -- must be coprime

CORNER_FLASH_DURATION = 0.6
BG_COLOR = (8, 8, 14)


class DvdDemo(Demo):
    def setup(self, screen_size):
        self.screen_size = screen_size
        self.color = random.choice(COLORS)
        self.logo = _render_logo(self.color)

        travel_x = max(1, screen_size[0] - self.logo.get_width())
        travel_y = max(1, screen_size[1] - self.logo.get_height())
        touches_x, touches_y = AXIS_TOUCHES_PER_PERIOD
        self.travel_x = travel_x
        self.travel_y = travel_y
        self.half_period_x = CORNER_PERIOD / touches_x
        self.half_period_y = CORNER_PERIOD / touches_y

        self.elapsed = 0.0
        self.prev_touch_count_x = 0
        self.prev_touch_count_y = 0
        self.flash_timer = 0.0

    def handle_event(self, event):
        pass

    def update(self, dt):
        self.elapsed += dt
        x = bounce_position(self.elapsed, self.half_period_x, self.travel_x)
        y = bounce_position(self.elapsed, self.half_period_y, self.travel_y)
        self.pos = (x, y)

        touch_count_x = int(self.elapsed // self.half_period_x)
        touch_count_y = int(self.elapsed // self.half_period_y)
        touched_x = touch_count_x != self.prev_touch_count_x
        touched_y = touch_count_y != self.prev_touch_count_y
        self.prev_touch_count_x = touch_count_x
        self.prev_touch_count_y = touch_count_y

        if touched_x and touched_y:
            self.flash_timer = CORNER_FLASH_DURATION
            self._recolor()
        elif touched_x or touched_y:
            self._recolor()

        self.flash_timer = max(0.0, self.flash_timer - dt)

    def _recolor(self):
        self.color = random.choice([c for c in COLORS if c != self.color])
        self.logo = _render_logo(self.color)

    def draw(self, surface):
        surface.fill(BG_COLOR)
        x, y = self.pos
        center = (x + self.logo.get_width() / 2, y + self.logo.get_height() / 2)

        if self.flash_timer > 0:
            progress = 1.0 - self.flash_timer / CORNER_FLASH_DURATION
            self._draw_corner_flash(surface, center, progress)
            scale = 1.0 + 0.4 * math.sin(progress * math.pi)
            logo = pygame.transform.smoothscale(
                self.logo,
                (int(self.logo.get_width() * scale), int(self.logo.get_height() * scale)),
            )
            blit_pos = (center[0] - logo.get_width() / 2, center[1] - logo.get_height() / 2)
        else:
            logo = self.logo
            blit_pos = (x, y)

        surface.blit(logo, blit_pos)

    def _draw_corner_flash(self, surface, center, progress):
        max_radius = max(self.logo.get_width(), self.logo.get_height()) * 1.6
        radius = int(max_radius * progress)
        alpha = int(255 * (1.0 - progress))
        if radius <= 0 or alpha <= 0:
            return
        ring = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*self.color, alpha), (radius, radius), radius, width=4)
        surface.blit(ring, (center[0] - radius, center[1] - radius))


def bounce_position(t, half_period, span):
    """Position of a point bouncing back and forth across [0, span] at
    constant speed, where half_period is the one-way crossing time. A pure
    function of absolute elapsed time t, recomputed fresh each call rather
    than integrated frame-by-frame -- so it never accumulates drift no matter
    how long the demo runs or how jittery dt is."""
    phase = t % (2 * half_period)
    if phase <= half_period:
        return (phase / half_period) * span
    return (1 - (phase - half_period) / half_period) * span


_base_logo = None  # lazily loaded -- needs pygame initialized, so not at import time


def _load_base_logo():
    global _base_logo
    if _base_logo is None:
        image = pygame.image.load(str(LOGO_ASSET_PATH)).convert_alpha()
        aspect = image.get_height() / image.get_width()
        size = (LOGO_WIDTH, round(LOGO_WIDTH * aspect))
        scaled = pygame.transform.smoothscale(image, size)
        _base_logo = pygame.transform.rotate(scaled, LOGO_ROTATION_DEGREES)
    return _base_logo


def _render_logo(color):
    # The source asset is solid black (with anti-aliased alpha edges) on a
    # transparent background, so recoloring means filling a same-size
    # surface with the target color and copying over the source's alpha
    # channel -- preserves the anti-aliasing exactly, unlike a flat
    # BLEND_RGBA_MULT tint (which can't brighten black pixels at all).
    base = _load_base_logo()
    tinted = pygame.Surface(base.get_size(), pygame.SRCALPHA)
    tinted.fill((*color, 255))
    alpha = pygame.surfarray.pixels_alpha(tinted)
    alpha[:] = pygame.surfarray.array_alpha(base)
    del alpha
    return tinted
