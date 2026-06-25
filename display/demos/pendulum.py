import math
import random
from collections import deque

import numpy as np
import pygame

from display.demos.base import Demo
from display.manager import LongPressEvent, TapEvent

BG_COLOR = (10, 10, 18)
ROD_COLOR = (180, 190, 210)
PIVOT_COLOR = (120, 130, 150)
BOB1_COLOR = (90, 200, 255)
BOB2_COLOR = (255, 120, 180)
# The trail fades from this (oldest) to BOB2_COLOR (newest), so it reads as a
# glowing ribbon streaming off the lower bob.
TRAIL_DARK = (40, 14, 40)


class DoublePendulumDemo(Demo):
    # Gravity in px/s^2. With arms ~100px long this gives a base swing period
    # of ~2s -- lively without being a blur. (Only the ratio g/length sets the
    # timescale, so this stays the same feel across screen sizes.)
    GRAVITY = 980.0
    BOB_MASS = 1.0
    PIVOT_Y_FRAC = 0.40
    ARM_LENGTH_FRAC = 0.21
    BOB1_RADIUS = 11
    BOB2_RADIUS = 9
    # Chaotic systems are unstable under big explicit steps, so we never
    # integrate at the (variable, ~1/60s) frame dt directly -- we advance in
    # fixed 1/240s RK4 substeps and just run however many fit each frame. That
    # keeps the motion identical whether the display is running at 45 or 60fps.
    PHYS_DT = 1.0 / 240.0
    # If the loop ever stalls (e.g. a long GC pause) don't try to catch up an
    # unbounded number of substeps in one frame -- cap the catch-up so we never
    # spiral into doing more and more work per frame.
    MAX_FRAME_DT = 0.05
    # Trail length in *substeps* (not frames): 360 / 240Hz ~= 1.5s of tail.
    TRAIL_LENGTH = 360

    def setup(self, screen_size):
        self.width, self.height = screen_size
        self.px = self.width // 2
        self.py = int(self.height * self.PIVOT_Y_FRAC)
        self.l1 = self.l2 = self.ARM_LENGTH_FRAC * min(self.width, self.height)
        self.m1 = self.m2 = self.BOB_MASS
        self.trail = deque(maxlen=self.TRAIL_LENGTH)
        self._accum = 0.0
        self._reset_default()

    @property
    def _params(self):
        return dict(l1=self.l1, l2=self.l2, m1=self.m1, m2=self.m2, g=self.GRAVITY)

    def _reset_default(self):
        # Release the whole pendulum straight (both arms at the same angle)
        # from rest at a random position, like actually dropping it -- giving
        # each arm an independent random angle instead stores uneven
        # potential energy right at the start, so the coupling yanks bob1
        # into an immediate, unnatural-looking kick rather than a smooth
        # fall. Starting aligned still diverges into the usual chaos within a
        # second or two, just gradually, driven by gravity/momentum alone.
        theta = random.uniform(math.pi * 0.45, math.pi * 0.9) * random.choice((-1, 1))
        self.state = np.array([theta, 0.0, theta, 0.0])
        self.trail.clear()
        self._accum = 0.0

    def _release_toward(self, x, y):
        # Point the whole (straightened) pendulum at the touch point and drop
        # it from rest there. theta is measured from straight-down, with
        # x = px + l*sin(theta), y = py + l*cos(theta), so this inverts to:
        theta = math.atan2(x - self.px, y - self.py)
        self.state = np.array([theta, 0.0, theta, 0.0])
        self.trail.clear()
        self._accum = 0.0

    def handle_event(self, event):
        pass

    def handle_touch(self, event):
        if isinstance(event, TapEvent):
            self._release_toward(event.x, event.y)
        elif isinstance(event, LongPressEvent):
            self._reset_default()

    def _positions(self):
        theta1, _, theta2, _ = self.state
        x1 = self.px + self.l1 * math.sin(theta1)
        y1 = self.py + self.l1 * math.cos(theta1)
        x2 = x1 + self.l2 * math.sin(theta2)
        y2 = y1 + self.l2 * math.cos(theta2)
        return (x1, y1), (x2, y2)

    def update(self, dt):
        self._accum += min(dt, self.MAX_FRAME_DT)
        while self._accum >= self.PHYS_DT:
            self.state = rk4_step(self.state, self.PHYS_DT, **self._params)
            self._accum -= self.PHYS_DT
            (_, _), (x2, y2) = self._positions()
            self.trail.append((int(x2), int(y2)))

    def draw(self, surface):
        surface.fill(BG_COLOR)

        pts = self.trail
        n = len(pts)
        if n > 1:
            step = max(1.0, n - 1)
            for i in range(1, n):
                color = _lerp_color(TRAIL_DARK, BOB2_COLOR, i / step)
                pygame.draw.line(surface, color, pts[i - 1], pts[i], 2)

        (x1, y1), (x2, y2) = self._positions()
        pivot = (self.px, self.py)
        joint = (int(x1), int(y1))
        end = (int(x2), int(y2))

        pygame.draw.line(surface, ROD_COLOR, pivot, joint, 3)
        pygame.draw.line(surface, ROD_COLOR, joint, end, 3)
        pygame.draw.circle(surface, PIVOT_COLOR, pivot, 4)
        pygame.draw.circle(surface, BOB1_COLOR, joint, self.BOB1_RADIUS)
        pygame.draw.circle(surface, BOB2_COLOR, end, self.BOB2_RADIUS)


def _lerp_color(c0, c1, t):
    return (
        int(c0[0] + (c1[0] - c0[0]) * t),
        int(c0[1] + (c1[1] - c0[1]) * t),
        int(c0[2] + (c1[2] - c0[2]) * t),
    )


def double_pendulum_derivatives(state, *, l1, l2, m1, m2, g):
    """Time-derivative of the double-pendulum state [theta1, omega1, theta2,
    omega2], independent of pygame so it's testable without a display. Angles
    are measured from straight-down; this is the standard closed-form
    Lagrangian solution (see e.g. myphysicslab's double pendulum)."""
    theta1, omega1, theta2, omega2 = state
    delta = theta1 - theta2
    cos_d = math.cos(delta)
    sin_d = math.sin(delta)
    # Shared denominator; never zero for positive masses/lengths since
    # 2*m1 + m2 - m2*cos(...) >= 2*m1 > 0.
    den = 2 * m1 + m2 - m2 * math.cos(2 * theta1 - 2 * theta2)

    domega1 = (
        -g * (2 * m1 + m2) * math.sin(theta1)
        - m2 * g * math.sin(theta1 - 2 * theta2)
        - 2 * sin_d * m2 * (omega2**2 * l2 + omega1**2 * l1 * cos_d)
    ) / (l1 * den)

    domega2 = (
        2
        * sin_d
        * (
            omega1**2 * l1 * (m1 + m2)
            + g * (m1 + m2) * math.cos(theta1)
            + omega2**2 * l2 * m2 * cos_d
        )
    ) / (l2 * den)

    return np.array([omega1, domega1, omega2, domega2])


def rk4_step(state, dt, *, l1, l2, m1, m2, g):
    """One classical 4th-order Runge-Kutta step. RK4 (not Euler) because the
    double pendulum is chaotic: Euler steadily pumps in spurious energy and the
    motion blows up, while RK4 stays stable and very nearly conserves energy at
    this step size."""
    p = dict(l1=l1, l2=l2, m1=m1, m2=m2, g=g)
    k1 = double_pendulum_derivatives(state, **p)
    k2 = double_pendulum_derivatives(state + 0.5 * dt * k1, **p)
    k3 = double_pendulum_derivatives(state + 0.5 * dt * k2, **p)
    k4 = double_pendulum_derivatives(state + dt * k3, **p)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
