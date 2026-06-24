import enum
from dataclasses import dataclass


class NavEvent(enum.Enum):
    NEXT = "next"
    PREV = "prev"


@dataclass(frozen=True)
class TapEvent:
    x: int
    y: int


@dataclass(frozen=True)
class LongPressEvent:
    x: int
    y: int


class DemoManager:
    """Owns the list of demos and which one is active. Switching is purely
    explicit (swipe or arrow key) -- there is no auto-advance timer."""

    def __init__(self, demos):
        if not demos:
            raise ValueError("DemoManager needs at least one demo")
        self.demos = demos
        self.index = 0
        self.screen_size = None

    @property
    def current(self):
        return self.demos[self.index]

    def setup(self, screen_size):
        self.screen_size = screen_size
        self.current.setup(screen_size)

    def handle_nav(self, nav_event):
        if nav_event == NavEvent.NEXT:
            self._switch(1)
        elif nav_event == NavEvent.PREV:
            self._switch(-1)

    def _switch(self, step):
        self.index = (self.index + step) % len(self.demos)
        self.current.setup(self.screen_size)

    def update(self, dt):
        self.current.update(dt)

    def draw(self, surface):
        self.current.draw(surface)
