import math
from collections import deque

import pygame

from display.demos.base import Demo
from display.manager import PressDragEvent, PressReleaseEvent, TapEvent

BG_COLOR = (8, 8, 16)
ROD_COLOR = (200, 200, 210)
PIVOT_COLOR = (140, 140, 150)
BOB1_COLOR = (225, 60, 60)  # red
BOB2_COLOR = (70, 130, 220)  # blue
TRAIL_DARK_FRACTION = 0.15
TRAIL_COLOR_BUCKETS = 6


class DoublePendulumDemo(Demo):
    """Double pendulum driven by the standard Lagrangian equations of motion
    (as derived on myphysicslab.com/pendulum/double-pendulum-en.html), with
    fading traces behind each bob like the n-body demo's planet trails."""

    # theta1/theta2 are measured from straight down (0 = hanging at rest);
    # positive rotates toward +x. Real SI units (meters, kg, m/s^2), scaled
    # to pixels only for drawing -- see PIXELS_PER_METER.
    L1 = 1.0
    L2 = 1.0
    M1 = 1.0
    M2 = 1.0
    GRAVITY = 9.8

    INITIAL_THETA1 = math.pi / 2  # both rods start horizontal, same side --
    INITIAL_THETA2 = math.pi / 2  # a high-energy start that swings chaotically

    PIXELS_PER_METER = 150.0
    PIVOT_Y_FRACTION = 0.22  # how far down the screen the fixed pivot sits

    BOB1_RADIUS = 11
    BOB2_RADIUS = 11
    GRAB_RADIUS = 32  # touch hit-test radius around each bob, in screen px

    TRAIL_LENGTH = 600  # ~10s of trace at 60fps

    # A stalled frame must never turn into one huge, unstable RK4 step.
    MAX_PHYSICS_DT = 1.0 / 30.0

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.pivot = (self.width / 2.0, self.height * self.PIVOT_Y_FRACTION)
        self.font = pygame.font.SysFont(None, 20)
        self._reset_state()

    def _reset_state(self):
        self.theta1 = self.INITIAL_THETA1
        self.theta2 = self.INITIAL_THETA2
        self.omega1 = 0.0
        self.omega2 = 0.0
        self.trail1 = deque(maxlen=self.TRAIL_LENGTH)
        self.trail2 = deque(maxlen=self.TRAIL_LENGTH)
        # Which bob (1, 2, or None) the current press-drag gesture is
        # manipulating, pinned for the gesture's duration -- see handle_touch.
        self._active_bob = None
        self._update_trail()

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._reset_state()
        elif isinstance(event, PressDragEvent):
            if self._active_bob is None:
                self._active_bob = self._bob_at(event.start_x, event.start_y) or "none"
            if self._active_bob in (1, 2):
                self._set_bob_angle(self._active_bob, event.x, event.y)
        elif isinstance(event, PressReleaseEvent):
            if self._active_bob in (1, 2):
                self._set_bob_angle(self._active_bob, event.x, event.y)
            self._active_bob = None

    def is_dragging(self):
        return self._active_bob in (1, 2)

    def instant_drag_zones(self):
        # A touch has to land directly on a bob to grab it, so there's no
        # tap-vs-drag ambiguity to protect against here -- it can start
        # dragging the instant it moves, no hold-still delay first.
        p1, p2 = self._bob_positions()
        return ((p1[0], p1[1], self.GRAB_RADIUS), (p2[0], p2[1], self.GRAB_RADIUS))

    def _bob_at(self, x, y):
        """Which bob (1, 2, or None) a touch at screen (x, y) grabs -- bob1
        wins ties since it's drawn/reached first along the rod chain."""
        p1, p2 = self._bob_positions()
        d1 = math.hypot(x - p1[0], y - p1[1])
        d2 = math.hypot(x - p2[0], y - p2[1])
        if d1 <= self.GRAB_RADIUS and d1 <= d2:
            return 1
        if d2 <= self.GRAB_RADIUS:
            return 2
        return None

    def _set_bob_angle(self, bob, x, y):
        """Rotate the grabbed bob's rod to point at (x, y) and zero its
        angular velocity, so releasing lets it fall from rest like actually
        picking it up. Dragging bob1 carries bob2 along for the ride (its
        own theta2 is untouched, so it keeps hanging the same way off the
        new bob1 position); dragging bob2 leaves bob1 fixed."""
        if bob == 1:
            self.theta1 = math.atan2(x - self.pivot[0], y - self.pivot[1])
            self.omega1 = 0.0
        else:
            p1, _ = self._bob_positions()
            self.theta2 = math.atan2(x - p1[0], y - p1[1])
            self.omega2 = 0.0
        self._update_trail()

    def _bob_positions(self):
        px, py = self.pivot
        x1 = px + self.L1 * self.PIXELS_PER_METER * math.sin(self.theta1)
        y1 = py + self.L1 * self.PIXELS_PER_METER * math.cos(self.theta1)
        x2 = x1 + self.L2 * self.PIXELS_PER_METER * math.sin(self.theta2)
        y2 = y1 + self.L2 * self.PIXELS_PER_METER * math.cos(self.theta2)
        return (x1, y1), (x2, y2)

    def _update_trail(self):
        p1, p2 = self._bob_positions()
        self.trail1.append(p1)
        self.trail2.append(p2)

    def update(self, dt):
        if self._active_bob in (1, 2):
            return  # frozen while a finger is actively repositioning a bob
        if dt <= 0:
            return
        substeps = max(1, math.ceil(dt / self.MAX_PHYSICS_DT))
        step_dt = dt / substeps
        for _ in range(substeps):
            self._step_physics(step_dt)

    def _step_physics(self, dt):
        state = (self.theta1, self.theta2, self.omega1, self.omega2)
        self.theta1, self.theta2, self.omega1, self.omega2 = rk4_step(
            state, dt, self.M1, self.M2, self.L1, self.L2, self.GRAVITY
        )
        self._update_trail()

    def draw(self, surface):
        surface.fill(BG_COLOR)
        p1, p2 = self._bob_positions()

        _draw_trail(surface, self.trail1, BOB1_COLOR)
        _draw_trail(surface, self.trail2, BOB2_COLOR)

        pivot_i = (int(self.pivot[0]), int(self.pivot[1]))
        p1_i = (int(p1[0]), int(p1[1]))
        p2_i = (int(p2[0]), int(p2[1]))
        pygame.draw.line(surface, ROD_COLOR, pivot_i, p1_i, 3)
        pygame.draw.line(surface, ROD_COLOR, p1_i, p2_i, 3)
        pygame.draw.circle(surface, PIVOT_COLOR, pivot_i, 6)
        pygame.draw.circle(surface, BOB1_COLOR, p1_i, self.BOB1_RADIUS)
        pygame.draw.circle(surface, BOB2_COLOR, p2_i, self.BOB2_RADIUS)


def compute_double_pendulum_accelerations(theta1, theta2, omega1, omega2, m1, m2, L1, L2, g):
    """Angular accelerations (alpha1, alpha2) from the standard closed-form
    double-pendulum equations of motion (Lagrangian derivation; see
    myphysicslab.com/pendulum/double-pendulum-en.html). theta1/theta2 are
    measured from straight down. The shared denominator 2*m1 + m2 -
    m2*cos(2*(theta1-theta2)) ranges over [2*m1, 2*m1+2*m2] and is therefore
    always positive -- no singularity to guard against."""
    delta = theta1 - theta2
    sin_delta = math.sin(delta)
    cos_delta = math.cos(delta)
    den = 2 * m1 + m2 - m2 * math.cos(2 * delta)

    alpha1 = (
        -g * (2 * m1 + m2) * math.sin(theta1)
        - m2 * g * math.sin(theta1 - 2 * theta2)
        - 2 * sin_delta * m2 * (omega2**2 * L2 + omega1**2 * L1 * cos_delta)
    ) / (L1 * den)

    alpha2 = (
        2
        * sin_delta
        * (
            omega1**2 * L1 * (m1 + m2)
            + g * (m1 + m2) * math.cos(theta1)
            + omega2**2 * L2 * m2 * cos_delta
        )
    ) / (L2 * den)

    return alpha1, alpha2


def _state_derivative(state, m1, m2, L1, L2, g):
    theta1, theta2, omega1, omega2 = state
    alpha1, alpha2 = compute_double_pendulum_accelerations(theta1, theta2, omega1, omega2, m1, m2, L1, L2, g)
    return (omega1, omega2, alpha1, alpha2)


def rk4_step(state, dt, m1, m2, L1, L2, g):
    """One classic RK4 step of (theta1, theta2, omega1, omega2). RK4 (rather
    than Euler) is what keeps a chaotic double pendulum's energy from
    visibly drifting over a long-running demo."""

    def combine(base, deriv, scale):
        return tuple(b + d * scale for b, d in zip(base, deriv))

    k1 = _state_derivative(state, m1, m2, L1, L2, g)
    k2 = _state_derivative(combine(state, k1, dt / 2), m1, m2, L1, L2, g)
    k3 = _state_derivative(combine(state, k2, dt / 2), m1, m2, L1, L2, g)
    k4 = _state_derivative(combine(state, k3, dt), m1, m2, L1, L2, g)

    return tuple(
        s + (dt / 6) * (a + 2 * b + 2 * c + d)
        for s, a, b, c, d in zip(state, k1, k2, k3, k4)
    )


def mechanical_energy(theta1, theta2, omega1, omega2, m1, m2, L1, L2, g):
    """Total kinetic + potential energy (pivot as the zero of potential),
    for verifying RK4 integration doesn't leak/gain energy over time."""
    kinetic = 0.5 * m1 * (L1 * omega1) ** 2 + 0.5 * m2 * (
        (L1 * omega1) ** 2
        + (L2 * omega2) ** 2
        + 2 * L1 * L2 * omega1 * omega2 * math.cos(theta1 - theta2)
    )
    potential = -(m1 + m2) * g * L1 * math.cos(theta1) - m2 * g * L2 * math.cos(theta2)
    return kinetic + potential


def _draw_trail(surface, trail, color, dark_fraction=TRAIL_DARK_FRACTION):
    n = len(trail)
    if n < 2:
        return
    points = list(trail)
    dark = tuple(int(c * dark_fraction) for c in color)
    buckets = min(TRAIL_COLOR_BUCKETS, n - 1)
    edges = [round(i * (n - 1) / buckets) for i in range(buckets + 1)]
    for b in range(buckets):
        start, end = edges[b], edges[b + 1]
        if end <= start:
            continue
        t = end / (n - 1)
        line_color = tuple(int(dark[i] + (color[i] - dark[i]) * t) for i in range(3))
        pygame.draw.lines(surface, line_color, False, points[start : end + 1], 2)
