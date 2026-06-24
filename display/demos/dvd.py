import math
import random

import pygame

from display.demos.base import Demo

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
# by chance. Non-corner wall bounces happen in between.
CORNER_PERIOD = 6.0
AXIS_TOUCHES_PER_PERIOD = (2, 3)  # (x, y) -- must be coprime

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


def _render_logo(color):
    font = pygame.font.SysFont(None, 90, bold=True)
    return font.render("DVD", True, color)
