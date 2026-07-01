import pygame
import pytest

from display.demos.base import Demo
from display.manager import DemoManager, NavEvent


class _StubDemo(Demo):
    """Minimal demo whose is_dragging()/instant_drag_zones() are controlled
    directly by the test, so DemoManager's swipe-guarding logic can be
    exercised without any real physics/rendering."""

    def __init__(self):
        self.setup_count = 0
        self.dragging = False
        self.zones = ()

    def setup(self, screen_size):
        self.setup_count += 1

    def handle_event(self, event):
        pass

    def update(self, dt):
        pass

    def draw(self, surface):
        pass

    def is_dragging(self):
        return self.dragging

    def instant_drag_zones(self):
        return self.zones


@pytest.fixture
def manager():
    pygame.init()
    m = DemoManager([_StubDemo(), _StubDemo()])
    m.setup((800, 480))
    return m


def test_nav_switches_demo_when_not_dragging(manager):
    assert manager.index == 0
    manager.handle_nav(NavEvent.NEXT)
    assert manager.index == 1


def test_nav_is_ignored_while_the_active_demo_is_dragging(manager):
    manager.current.dragging = True
    manager.handle_nav(NavEvent.NEXT)
    assert manager.index == 0  # swipe swallowed, no demo switch

    manager.current.dragging = False
    manager.handle_nav(NavEvent.NEXT)
    assert manager.index == 1  # released -- swipe works again


def test_instant_drag_zones_passes_through_the_active_demo(manager):
    manager.current.zones = ((10, 20, 30),)
    assert manager.instant_drag_zones() == ((10, 20, 30),)


def test_is_dragging_survives_a_broken_demo(manager):
    def _boom():
        raise ValueError("boom")

    manager.current.is_dragging = _boom
    assert manager.is_dragging() is False


def test_instant_drag_zones_survives_a_broken_demo(manager):
    def _boom():
        raise ValueError("boom")

    manager.current.instant_drag_zones = _boom
    assert manager.instant_drag_zones() == ()
