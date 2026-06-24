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
        """Called with a TapEvent or LongPressEvent (screen coords) while this
        demo is active. Swipes are handled globally by DemoManager and never
        reach here. Optional to override -- default is a no-op."""

    @abstractmethod
    def update(self, dt):
        """Advance simulation state by dt seconds."""

    @abstractmethod
    def draw(self, surface):
        """Render the current state onto surface."""
