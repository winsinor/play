"""Reads the HyperPixel touchscreen directly via evdev (no X11 needed) and
turns gestures into events on a thread-safe queue: swipe-left/right become
NavEvents (handled globally by DemoManager), tap and long-press become
TapEvent/LongPressEvent carrying the touch position (handled by the current
demo, if it cares -- see Demo.handle_touch).

Runs in a background thread so it never blocks the pygame render loop. If no
touch device is present (e.g. on a dev machine), it logs once and exits
cleanly -- keyboard navigation still works.
"""

import os
import threading
import time

try:
    import evdev
except ImportError:  # not installed / not on Linux
    evdev = None

from display.manager import LongPressEvent, NavEvent, TapEvent


def find_touch_device():
    if evdev is None:
        return None

    override = os.environ.get("EVDEV_TOUCH_DEVICE")
    if override:
        return evdev.InputDevice(override)

    for path in evdev.list_devices():
        device = evdev.InputDevice(path)
        capabilities = device.capabilities()
        abs_codes = {code for code, _ in capabilities.get(evdev.ecodes.EV_ABS, [])}
        if evdev.ecodes.ABS_MT_POSITION_X in abs_codes or evdev.ecodes.ABS_X in abs_codes:
            return device
    return None


def remap_touch_xy(x, y, min_x, max_x, min_y, max_y, swap_xy, invert_x, invert_y):
    """Apply a swap/invert combo to a raw touch coordinate. Swap is applied
    first, then per-axis inversion (using that axis's own min/max after the
    swap). Used by TouchInputThread to undo display.config.DISPLAY_ROTATE_DEGREES
    (see touch_flags_for_rotation below)."""
    if swap_xy:
        x, y, min_x, max_x, min_y, max_y = y, x, min_y, max_y, min_x, max_x
    if invert_x:
        x = max_x - (x - min_x)
    if invert_y:
        y = max_y - (y - min_y)
    return x, y


def touch_flags_for_rotation(degrees):
    """The (swap_xy, invert_x, invert_y) combo that undoes a counterclockwise
    pygame.transform.rotate(canvas, degrees) of the screen, mapping a raw
    touch point in the *rotated* (physical) coordinate space back to the
    unrotated canvas space the demos draw in. Derived from -- and verified
    against -- pygame's actual rotation pixel mapping, not guessed."""
    degrees = degrees % 360
    try:
        return {
            0: (False, False, False),
            90: (True, True, False),
            180: (False, True, True),
            270: (True, False, True),
        }[degrees]
    except KeyError:
        raise ValueError(f"DISPLAY_ROTATE_DEGREES must be 0/90/180/270, got {degrees}") from None


class TouchInputThread(threading.Thread):
    def __init__(
        self,
        event_queue,
        swipe_threshold_px,
        tap_max_duration,
        tap_max_distance_px,
        long_press_min_duration,
        device=None,
        rotate_degrees=0,
    ):
        super().__init__(daemon=True)
        self.event_queue = event_queue
        self.swipe_threshold_px = swipe_threshold_px
        self.tap_max_duration = tap_max_duration
        self.tap_max_distance_px = tap_max_distance_px
        self.long_press_min_duration = long_press_min_duration
        self._device = device
        self.swap_xy, self.invert_x, self.invert_y = touch_flags_for_rotation(rotate_degrees)
        self._min_x = self._max_x = self._min_y = self._max_y = 0
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        device = self._device or find_touch_device()
        if device is None:
            print("[input_touch] no touchscreen device found; keyboard nav only")
            return
        print(f"[input_touch] reading touch events from {device.path} ({device.name})")

        abs_caps = dict(device.capabilities().get(evdev.ecodes.EV_ABS, []))
        x_code = evdev.ecodes.ABS_MT_POSITION_X if evdev.ecodes.ABS_MT_POSITION_X in abs_caps else evdev.ecodes.ABS_X
        y_code = evdev.ecodes.ABS_MT_POSITION_Y if evdev.ecodes.ABS_MT_POSITION_Y in abs_caps else evdev.ecodes.ABS_Y
        self._min_x, self._max_x = abs_caps[x_code].min, abs_caps[x_code].max
        self._min_y, self._max_y = abs_caps[y_code].min, abs_caps[y_code].max

        start_x = start_y = None
        last_x = last_y = None
        start_time = None

        try:
            for event in device.read_loop():
                if self._stop_event.is_set():
                    return

                if event.type == evdev.ecodes.EV_ABS and event.code in (
                    evdev.ecodes.ABS_MT_POSITION_X,
                    evdev.ecodes.ABS_X,
                ):
                    last_x = event.value
                    if start_x is None:
                        start_x = event.value
                        start_time = time.monotonic()

                elif event.type == evdev.ecodes.EV_ABS and event.code in (
                    evdev.ecodes.ABS_MT_POSITION_Y,
                    evdev.ecodes.ABS_Y,
                ):
                    last_y = event.value
                    if start_y is None:
                        start_y = event.value

                elif event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
                    if event.value == 0:
                        self._finish_touch(start_x, start_y, last_x, last_y, start_time)
                        start_x = start_y = last_x = last_y = start_time = None

                elif (
                    event.type == evdev.ecodes.EV_ABS
                    and event.code == evdev.ecodes.ABS_MT_TRACKING_ID
                    and event.value == -1
                ):
                    self._finish_touch(start_x, start_y, last_x, last_y, start_time)
                    start_x = start_y = last_x = last_y = start_time = None
        except OSError as exc:
            print(f"[input_touch] touch device error, stopping touch input: {exc}")

    def _remap(self, x, y):
        if x is None or y is None:
            return x, y
        return remap_touch_xy(
            x, y, self._min_x, self._max_x, self._min_y, self._max_y,
            self.swap_xy, self.invert_x, self.invert_y,
        )

    def _finish_touch(self, start_x, start_y, end_x, end_y, start_time):
        if start_x is None or end_x is None or start_time is None:
            return
        if self.swap_xy or self.invert_x or self.invert_y:
            start_x, start_y = self._remap(start_x, start_y)
            end_x, end_y = self._remap(end_x, end_y)
        delta_x = end_x - start_x
        delta_y = (end_y - start_y) if (start_y is not None and end_y is not None) else 0
        duration = time.monotonic() - start_time

        if abs(delta_x) >= self.swipe_threshold_px:
            # swipe left (finger moves left, negative delta) -> next; swipe right -> prev
            self.event_queue.put(NavEvent.PREV if delta_x > 0 else NavEvent.NEXT)
            return

        distance = max(abs(delta_x), abs(delta_y))
        if distance > self.tap_max_distance_px:
            return  # an ambiguous drag that wasn't a swipe -- ignore

        x = end_x if end_x is not None else start_x
        y = end_y if end_y is not None else start_y
        if duration <= self.tap_max_duration:
            self.event_queue.put(TapEvent(x, y))
        elif duration >= self.long_press_min_duration:
            self.event_queue.put(LongPressEvent(x, y))
