import enum


class NavEvent(enum.Enum):
    NEXT = "next"
    PREV = "prev"
    TOGGLE_PAUSE = "toggle_pause"


class DemoManager:
    """Owns the list of demos, which one is active, and the auto-advance timer."""

    def __init__(self, demos, auto_advance_seconds):
        if not demos:
            raise ValueError("DemoManager needs at least one demo")
        self.demos = demos
        self.auto_advance_seconds = auto_advance_seconds
        self.index = 0
        self.paused = False
        self.time_since_advance = 0.0
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
        elif nav_event == NavEvent.TOGGLE_PAUSE:
            self.paused = not self.paused

    def _switch(self, step):
        self.index = (self.index + step) % len(self.demos)
        self.current.setup(self.screen_size)
        self.time_since_advance = 0.0

    def update(self, dt):
        self.current.update(dt)
        if not self.paused:
            self.time_since_advance += dt
            if self.time_since_advance >= self.auto_advance_seconds:
                self._switch(1)

    def draw(self, surface):
        self.current.draw(surface)
