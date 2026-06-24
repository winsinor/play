from abc import ABC, abstractmethod


class Demo(ABC):
    """One full-screen visual demo (boids, maze, fractal, ...)."""

    @abstractmethod
    def setup(self, screen_size):
        """Called once when the demo becomes active. screen_size is (width, height)."""

    @abstractmethod
    def handle_event(self, event):
        """Called for every pygame event while this demo is active."""

    @abstractmethod
    def update(self, dt):
        """Advance simulation state by dt seconds."""

    @abstractmethod
    def draw(self, surface):
        """Render the current state onto surface."""
