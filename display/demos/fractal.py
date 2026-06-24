import numpy as np
import pygame
import pygame.surfarray

from display.demos.base import Demo

# Computed at reduced internal resolution then upscaled -- full escape-time at
# native screen res is too slow to redo every frame on a Pi 3.
INTERNAL_SIZE = (200, 120)
MAX_ITER = 60

# A few curated Julia constants (c in z = z^2 + c) known for rich boundary
# detail -- lots of edge/filament structure to zoom into, unlike e.g. c=0
# which is just a plain circle.
JULIA_CONSTANTS = [
    (-0.8, 0.156, "classic dendrite"),
    (-0.4, 0.6, "spiral"),
    (0.285, 0.01, "thin filaments"),
    (-0.70176, -0.3842, "san marco"),
    (-0.835, -0.2321, "rabbit-like"),
    (0.45, 0.1428, "feathered"),
]
ZOOM_RATE = 1.01  # multiplicative scale shrink per "tick" (dt * 30)
RESET_SCALE = 1.6
MIN_SCALE = 1e-4

# Each frame, the zoom center drifts toward the strongest nearby escape-time
# gradient (the fractal's boundary) instead of a fixed point, so it never just
# zooms straight into a featureless black (interior) or white (escaped) area.
CENTER_DRIFT = 0.12
BOUNDARY_SEARCH_MARGIN = 0.25  # only look within the central 50% of the view
MIN_GRADIENT = 1.5  # below this the view is too featureless to chase a boundary


class FractalDemo(Demo):
    def setup(self, screen_size):
        self.screen_size = screen_size
        self.constant_index = 0
        self._reset_zoom()

    def _reset_zoom(self):
        self.center_x, self.center_y = 0.0, 0.0
        self.scale = RESET_SCALE
        self.hue_shift = 0.0
        self._iterations = None

    def handle_event(self, event):
        pass

    def update(self, dt):
        c_re, c_im, _ = JULIA_CONSTANTS[self.constant_index]
        self._iterations = compute_julia(
            INTERNAL_SIZE, c_re, c_im, self.center_x, self.center_y, self.scale, MAX_ITER
        )

        target = find_boundary_target(
            self._iterations, self.center_x, self.center_y, self.scale, INTERNAL_SIZE
        )
        if target is None:
            # Nothing interesting left in view (solid interior or solid
            # escape) -- this zoom path is a dead end, move on.
            self.constant_index = (self.constant_index + 1) % len(JULIA_CONSTANTS)
            self._reset_zoom()
            return

        target_x, target_y = target
        self.center_x += (target_x - self.center_x) * CENTER_DRIFT
        self.center_y += (target_y - self.center_y) * CENTER_DRIFT

        self.scale /= ZOOM_RATE ** (dt * 30)
        self.hue_shift = (self.hue_shift + dt * 12) % 360
        if self.scale < MIN_SCALE:
            self.constant_index = (self.constant_index + 1) % len(JULIA_CONSTANTS)
            self._reset_zoom()

    def draw(self, surface):
        rgb = palette_from_iterations(self._iterations, MAX_ITER, self.hue_shift)
        small_surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
        scaled = pygame.transform.smoothscale(small_surface, self.screen_size)
        surface.blit(scaled, (0, 0))


def compute_julia(size, c_re, c_im, center_x, center_y, scale, max_iter):
    """Vectorized escape-time iteration for the Julia set of a fixed constant
    c = c_re + c_im*j (unlike Mandelbrot, where c varies per-pixel and z
    always starts at 0, here c is constant and z starts at each pixel's
    coordinate). Returns an (height, width) int array of the iteration count
    at which each point escaped (== max_iter if it didn't)."""
    width, height = size
    aspect = width / height
    x = np.linspace(center_x - scale * aspect, center_x + scale * aspect, width)
    y = np.linspace(center_y - scale, center_y + scale, height)
    zx, zy = np.meshgrid(x, y)
    z = zx + 1j * zy
    c = complex(c_re, c_im)

    iterations = np.zeros(z.shape, dtype=np.int32)
    active = np.ones(z.shape, dtype=bool)

    for i in range(max_iter):
        z[active] = z[active] * z[active] + c
        escaped = np.abs(z) > 2
        newly_escaped = escaped & active
        iterations[newly_escaped] = i
        active &= ~escaped
        if not active.any():
            break

    iterations[active] = max_iter
    return iterations


def find_boundary_target(iterations, center_x, center_y, scale, size):
    """Find a point near a strong escape-time gradient -- i.e. near the
    fractal's boundary, not deep inside a solid black interior or a solid
    escaped region -- within the central portion of the current view.
    Returns (x, y) in complex-plane coordinates, or None if the view is too
    featureless to find one."""
    width, height = size
    gradient_y, gradient_x = np.gradient(iterations.astype(np.float64))
    gradient = np.hypot(gradient_x, gradient_y)

    margin_x = int(width * BOUNDARY_SEARCH_MARGIN)
    margin_y = int(height * BOUNDARY_SEARCH_MARGIN)
    search = gradient[margin_y : height - margin_y, margin_x : width - margin_x]
    if search.size == 0 or search.max() < MIN_GRADIENT:
        return None

    local_row, local_col = np.unravel_index(np.argmax(search), search.shape)
    row, col = local_row + margin_y, local_col + margin_x

    aspect = width / height
    target_x = center_x - scale * aspect + (col / (width - 1)) * 2 * scale * aspect
    target_y = center_y - scale + (row / (height - 1)) * 2 * scale
    return target_x, target_y


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
