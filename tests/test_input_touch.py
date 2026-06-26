import queue
from dataclasses import dataclass

import pygame
import pytest

import display.input_touch as input_touch
from display.input_touch import TouchInputThread, pinch_scale, remap_touch_xy, touch_flags_for_rotation
from display.manager import NavEvent, PinchZoomEvent, PressDragEvent, PressReleaseEvent, TapEvent


def test_remap_touch_xy_identity_when_all_flags_off():
    assert remap_touch_xy(10, 20, 0, 800, 0, 480, False, False, False) == (10, 20)


def test_remap_touch_xy_swap_only():
    x, y = remap_touch_xy(10, 20, 0, 800, 0, 480, True, False, False)
    assert (x, y) == (20, 10)


def test_remap_touch_xy_invert_x_only():
    x, y = remap_touch_xy(100, 20, 0, 800, 0, 480, False, True, False)
    assert (x, y) == (700, 20)


def test_remap_touch_xy_invert_y_only():
    x, y = remap_touch_xy(10, 50, 0, 800, 0, 480, False, False, True)
    assert (x, y) == (10, 430)


def test_remap_touch_xy_swap_then_invert_uses_post_swap_ranges():
    # After swapping, the (now-horizontal) value came from the y-channel, so
    # inverting x afterwards must use the y-axis's own min/max, not x's.
    x, y = remap_touch_xy(10, 50, 0, 800, 0, 480, True, True, False)
    assert (x, y) == (430, 10)


def test_remap_touch_xy_corners_stay_corners():
    # The four panel corners must still map to the four screen corners
    # (possibly relabeled) under any flag combination -- never off-screen.
    for swap in (False, True):
        for invert_x in (False, True):
            for invert_y in (False, True):
                for raw_x, raw_y in [(0, 0), (800, 0), (0, 480), (800, 480)]:
                    x, y = remap_touch_xy(raw_x, raw_y, 0, 800, 0, 480, swap, invert_x, invert_y)
                    assert x in (0, 480, 800)
                    assert y in (0, 480, 800)


@pytest.mark.parametrize("degrees", [0, 90, 180, 270])
def test_touch_flags_for_rotation_undoes_the_screen_rotation(degrees):
    # A touch device's native range matches the *physical* (rotated) pixel
    # grid, since it's calibrated to the panel, not to our logical canvas.
    # touch_flags_for_rotation must map a point in that rotated space back
    # to the same point in the unrotated canvas that pygame.transform.rotate
    # started from -- verified directly against pygame's own rotation here,
    # not just asserted.
    pygame.init()
    width, height = 800, 480
    canvas_points = [(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1), (400, 240), (123, 45)]
    swap_xy, invert_x, invert_y = touch_flags_for_rotation(degrees)

    for cx, cy in canvas_points:
        marker = pygame.Surface((width, height))
        marker.set_at((cx, cy), (255, 255, 255))
        rotated = pygame.transform.rotate(marker, degrees)
        rx, ry = next(
            (x, y)
            for x in range(rotated.get_width())
            for y in range(rotated.get_height())
            if rotated.get_at((x, y))[:3] == (255, 255, 255)
        )
        recovered = remap_touch_xy(
            rx, ry, 0, rotated.get_width() - 1, 0, rotated.get_height() - 1,
            swap_xy, invert_x, invert_y,
        )
        assert recovered == (cx, cy)


def test_touch_flags_for_rotation_rejects_non_right_angle():
    with pytest.raises(ValueError):
        touch_flags_for_rotation(45)


@pytest.mark.parametrize(
    "prev, new, expected",
    [
        (None, 100.0, None),
        (0.0, 100.0, None),
        (50.0, 100.0, 2.0),
        (100.0, 50.0, 0.5),
    ],
)
def test_pinch_scale(prev, new, expected):
    assert pinch_scale(prev, new) == expected


# -- Fake evdev plumbing, just enough of the protocol-B multitouch shape
# (ABS_MT_SLOT / ABS_MT_TRACKING_ID / ABS_MT_POSITION_X/Y / BTN_TOUCH) for
# TouchInputThread.run() to exercise its real gesture-classification logic
# end to end, without a real touchscreen or a separate thread.


@dataclass
class _FakeAbsEvent:
    type: int
    code: int
    value: int


class _FakeEcodes:
    EV_ABS = 3
    EV_KEY = 1
    ABS_X = 0
    ABS_Y = 1
    ABS_MT_SLOT = 47
    ABS_MT_TRACKING_ID = 57
    ABS_MT_POSITION_X = 53
    ABS_MT_POSITION_Y = 54
    BTN_TOUCH = 330


class _FakeAbsInfo:
    def __init__(self, min_value, max_value):
        self.min = min_value
        self.max = max_value


class _FakeDevice:
    def __init__(self, events, min_x=0, max_x=1000, min_y=0, max_y=1000):
        self._events = events
        self.path = "/fake/touch"
        self.name = "fake-touch"
        self._caps = {
            _FakeEcodes.EV_ABS: [
                (_FakeEcodes.ABS_MT_POSITION_X, _FakeAbsInfo(min_x, max_x)),
                (_FakeEcodes.ABS_MT_POSITION_Y, _FakeAbsInfo(min_y, max_y)),
            ]
        }

    def capabilities(self):
        return self._caps

    def read_loop(self):
        return iter(self._events)


def _run_gesture(monkeypatch, events, **thread_kwargs):
    monkeypatch.setattr(input_touch, "evdev", _FakeEcodesModule())
    device = _FakeDevice(events)
    event_queue = queue.Queue()
    thread = TouchInputThread(
        event_queue,
        swipe_threshold_fraction=thread_kwargs.pop("swipe_threshold_fraction", 0.3),
        tap_max_duration=thread_kwargs.pop("tap_max_duration", 0.3),
        tap_max_distance_px=thread_kwargs.pop("tap_max_distance_px", 20),
        long_press_min_duration=thread_kwargs.pop("long_press_min_duration", 0.0),
        device=device,
        canvas_width=1000,
        canvas_height=1000,
        **thread_kwargs,
    )
    thread.run()  # called directly (not .start()) -- synchronous, no real thread needed
    drained = []
    while not event_queue.empty():
        drained.append(event_queue.get_nowait())
    return drained


class _FakeEcodesModule:
    ecodes = _FakeEcodes


def _down(slot, tracking_id, x, y):
    return [
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_SLOT, slot),
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_TRACKING_ID, tracking_id),
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_POSITION_X, x),
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_POSITION_Y, y),
    ]


def _move(slot, x, y):
    return [
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_SLOT, slot),
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_POSITION_X, x),
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_POSITION_Y, y),
    ]


def _up(slot):
    return [
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_SLOT, slot),
        _FakeAbsEvent(_FakeEcodes.EV_ABS, _FakeEcodes.ABS_MT_TRACKING_ID, -1),
    ]


def _btn(value):
    return [_FakeAbsEvent(_FakeEcodes.EV_KEY, _FakeEcodes.BTN_TOUCH, value)]


def test_quick_small_move_is_a_tap(monkeypatch):
    events = [*_down(0, 1, 100, 100), *_btn(1), *_up(0), *_btn(0)]
    result = _run_gesture(monkeypatch, events)
    assert result == [TapEvent(100, 100)]


def test_large_fast_horizontal_move_is_a_swipe(monkeypatch):
    # long_press_min_duration must be well above the (near-zero) real wall-clock
    # time this synchronous test takes to run, otherwise the drag-vs-swipe time
    # check is trivially satisfied and the move gets misclassified as a drag --
    # see the default of 0.0 used by other tests here, which exists precisely to
    # let *those* tests start dragging immediately.
    # Finger moves left from 950 to 50 (900px, 90% of the 1000px canvas, past
    # the 80% swipe_threshold_fraction), which by the swipe convention in
    # _finish_touch ("swipe left -> next") maps to NavEvent.NEXT.
    events = [*_down(0, 1, 950, 500), *_btn(1), *_move(0, 50, 500), *_up(0), *_btn(0)]
    result = _run_gesture(monkeypatch, events, swipe_threshold_fraction=0.8, long_press_min_duration=1.0)
    assert result == [NavEvent.NEXT]


def test_move_short_of_80_percent_width_is_not_a_swipe(monkeypatch):
    # Same direction as the swipe above, but only 70% of the canvas width --
    # short of the 80% bar, so it must not fire a NavEvent (and since it never
    # entered drag-mode either, it's a silent no-op, not a tap).
    events = [*_down(0, 1, 900, 500), *_btn(1), *_move(0, 200, 500), *_up(0), *_btn(0)]
    result = _run_gesture(monkeypatch, events, swipe_threshold_fraction=0.8, long_press_min_duration=1.0)
    assert result == []


def test_swipe_does_not_fire_after_a_pinch_even_past_distance_threshold(monkeypatch):
    # Two fingers touch down (a pinch), then the second lifts and the first
    # finger -- which happened to have drifted past the swipe distance while
    # the pinch was happening -- lifts too. This must never be read as a
    # swipe (it's the tail end of a zoom gesture, not a one-finger swipe).
    events = [
        *_down(0, 1, 950, 500),
        *_btn(1),
        *_down(1, 2, 100, 100),  # second finger touches down -> pinch
        *_move(0, 50, 500),  # primary finger drifts 900px, past any swipe threshold
        *_up(1),  # second finger lifts
        *_up(0),  # primary finger lifts -- must not be classified as a swipe
        *_btn(0),
    ]
    result = _run_gesture(monkeypatch, events, swipe_threshold_fraction=0.8, long_press_min_duration=1.0)
    assert not any(e in (NavEvent.PREV, NavEvent.NEXT) for e in result)


def test_drag_past_threshold_emits_drag_then_release(monkeypatch):
    events = [
        *_down(0, 1, 100, 100),
        *_btn(1),
        *_move(0, 150, 100),  # 50px -- past tap_max_distance_px (20), starts dragging
        *_move(0, 200, 100),
        *_up(0),
        *_btn(0),
    ]
    result = _run_gesture(monkeypatch, events)
    assert all(isinstance(e, PressDragEvent) for e in result[:-1])
    assert len(result) >= 2
    assert isinstance(result[-1], PressReleaseEvent)
    assert result[-1].x == 200 and result[-1].y == 100
    assert result[-1].start_x == 100 and result[-1].start_y == 100
    # never misclassified as a tap or a swipe
    assert not any(isinstance(e, TapEvent) for e in result)
    assert not any(e in (NavEvent.PREV, NavEvent.NEXT) for e in result)


def test_stationary_hold_past_tap_duration_is_a_no_op(monkeypatch):
    # Never moves past tap_max_distance_px, so it never starts dragging --
    # with hold-to-reset removed project-wide, a hold that overstays
    # tap_max_duration without dragging should produce nothing at all.
    events = [*_down(0, 1, 100, 100), *_btn(1), *_up(0), *_btn(0)]
    result = _run_gesture(monkeypatch, events, tap_max_duration=-1.0)  # force "too slow for a tap"
    assert result == []


def test_second_finger_does_not_corrupt_first_fingers_drag(monkeypatch):
    # A pinch starting mid-drag must never leak into the first finger's
    # gesture -- regression guard for the slot-aware primary-finger tracking.
    events = [
        *_down(0, 1, 100, 100),
        *_btn(1),
        *_move(0, 150, 100),  # finger 1 starts dragging
        *_down(1, 2, 900, 900),  # finger 2 touches down far away
        *_move(1, 800, 800),  # finger 2 moves -- must not affect finger 1's drag state
        *_move(0, 200, 100),  # finger 1 continues its own drag
        *_up(1),
        *_move(0, 250, 100),
        *_up(0),
        *_btn(0),
    ]
    result = _run_gesture(monkeypatch, events)
    drags = [e for e in result if isinstance(e, PressDragEvent)]
    assert drags, "expected finger 1's drag to be tracked"
    assert all(d.start_x == 100 and d.start_y == 100 for d in drags)
    releases = [e for e in result if isinstance(e, PressReleaseEvent)]
    assert len(releases) == 1
    assert releases[0].x == 250 and releases[0].y == 100


def test_two_finger_pinch_apart_emits_growing_scale(monkeypatch):
    events = [
        *_down(0, 1, 400, 500),
        *_down(1, 2, 600, 500),
        *_move(0, 300, 500),  # fingers spreading apart -> distance grows
        *_move(1, 700, 500),
    ]
    result = _run_gesture(monkeypatch, events)
    pinches = [e for e in result if isinstance(e, PinchZoomEvent)]
    assert pinches, "expected at least one PinchZoomEvent"
    assert all(p.scale > 1.0 for p in pinches)


def test_two_finger_pinch_together_emits_shrinking_scale(monkeypatch):
    events = [
        *_down(0, 1, 300, 500),
        *_down(1, 2, 700, 500),
        *_move(0, 400, 500),  # fingers coming together -> distance shrinks
        *_move(1, 600, 500),
    ]
    result = _run_gesture(monkeypatch, events)
    pinches = [e for e in result if isinstance(e, PinchZoomEvent)]
    assert pinches, "expected at least one PinchZoomEvent"
    assert all(p.scale < 1.0 for p in pinches)
