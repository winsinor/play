import enum
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

    def handle_event(self, event):
        self._guard(self.current.handle_event, event)

    def handle_touch(self, event):
        self._guard(self.current.handle_touch, event)

    def update(self, dt):
        self._guard(self.current.update, dt)

    def draw(self, surface):
        self._guard(self.current.draw, surface)

    def _guard(self, method, *args):
        # No demo's update/draw/event handling is allowed to take the whole
        # app down -- a single bad frame resets just that demo (or, failing
        # that, advances past it) instead of crashing the process.
        demo_name = type(self.current).__name__
        try:
            method(*args)
        except Exception:
            logger.exception("%s failed in %s(); resetting it", demo_name, method.__name__)
            self._recover_current()

    def _recover_current(self):
        try:
            self.current.setup(self.screen_size)
        except Exception:
            logger.exception(
                "%s failed to reset; advancing to next demo", type(self.current).__name__
            )
            self._switch(1)
