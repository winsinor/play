from abc import ABC, abstractmethod


class Demo(ABC):
    """One full-screen visual demo (boids, maze, fractal, ...)."""

    @abstractmethod
    def setup(self, screen_size):
        """Called once when the demo becomes active. screen_size is (width, height)."""

    @abstractmethod
    def handle_event(self, event):
        """Called for every pygame event while this demo is active."""

    def handle_touch(self, event):
        """Called with a TapEvent, PressDragEvent, or PressReleaseEvent
        (screen coords) while this demo is active. Swipes are handled
        globally by DemoManager and never reach here. Optional to override
        -- default is a no-op."""

    def is_dragging(self):
        """Whether the user currently has a finger down mid-manipulation (a
        PressDragEvent gesture this demo is tracking). DemoManager checks
        this before acting on a swipe, so a drag that happens to end with a
        large net displacement (e.g. flinging a pendulum bob across the
        screen) can never also switch demos out from under it. Override
        alongside handle_touch for any demo that tracks such a gesture --
        default False."""
        return False

    def instant_drag_zones(self):
        """Screen-space (x, y, radius) circles where a touch should start
        dragging immediately, bypassing config.LONG_PRESS_MIN_DURATION --
        for a demo whose drag target is a specific, directly-grabbed object
        (e.g. a pendulum bob), which has no tap-vs-drag ambiguity to guard
        against, unlike nbody's launch drag that can start from anywhere.
        Touches starting outside every zone still go through the normal
        hold-then-drag gate, so a swipe elsewhere on the same screen still
        switches demos. Empty (no instant zones) by default."""
        return ()

    @abstractmethod
    def update(self, dt):
        """Advance simulation state by dt seconds."""

    @abstractmethod
    def draw(self, surface):
        """Render the current state onto surface."""
