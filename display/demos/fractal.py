import numpy as np
import pygame
import pygame.surfarray

from display.demos.base import Demo

# Computed at reduced internal resolution then upscaled -- full escape-time at
# native screen res is too slow to redo every frame on a Pi 3.
INTERNAL_SIZE = (200, 120)
MAX_ITER = 60

# A few curated Mandelbrot coordinates worth zooming into.
ZOOM_TARGETS = [
    (-0.743643887037151, 0.13182590420533, "seahorse valley"),
    (-0.74364409, 0.13182621, "deeper seahorse"),
    (0.282, 0.01, "mini mandelbrot"),
    (-0.1, 0.651, "lightning"),
]
ZOOM_RATE = 1.01  # multiplicative scale shrink per "tick" (dt * 30)
RESET_SCALE = 2.5
MIN_SCALE = 1e-4


class FractalDemo(Demo):
    def setup(self, screen_size):
        self.screen_size = screen_size
        self.target_index = 0
        self._reset_zoom()

    def _reset_zoom(self):
        self.center_x, self.center_y, _ = ZOOM_TARGETS[self.target_index]
        self.scale = RESET_SCALE
        self.hue_shift = 0.0

    def handle_event(self, event):
        pass

    def update(self, dt):
        self.scale /= ZOOM_RATE ** (dt * 30)
        self.hue_shift = (self.hue_shift + dt * 12) % 360
        if self.scale < MIN_SCALE:
            self.target_index = (self.target_index + 1) % len(ZOOM_TARGETS)
            self._reset_zoom()

    def draw(self, surface):
        iterations = compute_mandelbrot(
            INTERNAL_SIZE, self.center_x, self.center_y, self.scale, MAX_ITER
        )
        rgb = palette_from_iterations(iterations, MAX_ITER, self.hue_shift)
        small_surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        scaled = pygame.transform.smoothscale(small_surface, self.screen_size)
        surface.blit(scaled, (0, 0))


def compute_mandelbrot(size, center_x, center_y, scale, max_iter):
    """Vectorized escape-time iteration. Returns an (height, width) int array of
    the iteration count at which each point escaped (== max_iter if it didn't)."""
    width, height = size
    aspect = width / height
    x = np.linspace(center_x - scale * aspect, center_x + scale * aspect, width)
    y = np.linspace(center_y - scale, center_y + scale, height)
    cx, cy = np.meshgrid(x, y)
    c = cx + 1j * cy

    z = np.zeros_like(c)
    iterations = np.zeros(c.shape, dtype=np.int32)
    active = np.ones(c.shape, dtype=bool)

    for i in range(max_iter):
        z[active] = z[active] * z[active] + c[active]
        escaped = np.abs(z) > 2
        newly_escaped = escaped & active
        iterations[newly_escaped] = i
        active &= ~escaped
        if not active.any():
            break

    iterations[active] = max_iter
    return iterations


def palette_from_iterations(iterations, max_iter, hue_shift):
    t = iterations / max_iter
    hue = (t * 300 + hue_shift) % 360
    in_set = iterations >= max_iter
    saturation = np.where(in_set, 0.0, 0.8)
    value = np.where(in_set, 0.0, 1.0 - 0.4 * t)
    rgb = _hsv_to_rgb_array(hue, saturation, value)
    return (rgb * 255).astype(np.uint8)


def _hsv_to_rgb_array(h, s, v):
    h = h / 60.0
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))

    conditions = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]
    r = np.select(conditions, [v, q, p, p, t, v])
    g = np.select(conditions, [t, v, v, q, p, p])
    b = np.select(conditions, [p, p, t, v, v, q])
    return np.stack([r, g, b], axis=-1)
