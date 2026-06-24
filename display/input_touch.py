"""Reads the HyperPixel touchscreen directly via evdev (no X11 needed) and turns
swipe-left/right and tap gestures into NavEvents on a thread-safe queue.

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

from display.manager import NavEvent


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


class TouchInputThread(threading.Thread):
    def __init__(
        self,
        event_queue,
        swipe_threshold_px,
        tap_max_duration,
        tap_max_distance_px,
        device=None,
    ):
        super().__init__(daemon=True)
        self.event_queue = event_queue
        self.swipe_threshold_px = swipe_threshold_px
        self.tap_max_duration = tap_max_duration
        self.tap_max_distance_px = tap_max_distance_px
        self._device = device
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        device = self._device or find_touch_device()
        if device is None:
            print("[input_touch] no touchscreen device found; keyboard nav only")
            return
        print(f"[input_touch] reading touch events from {device.path} ({device.name})")

        start_x = None
        start_time = None
        last_x = None

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

                elif event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
                    if event.value == 0:
                        self._finish_touch(start_x, last_x, start_time)
                        start_x = last_x = start_time = None

                elif (
                    event.type == evdev.ecodes.EV_ABS
                    and event.code == evdev.ecodes.ABS_MT_TRACKING_ID
                    and event.value == -1
                ):
                    self._finish_touch(start_x, last_x, start_time)
                    start_x = last_x = start_time = None
        except OSError as exc:
            print(f"[input_touch] touch device error, stopping touch input: {exc}")

    def _finish_touch(self, start_x, end_x, start_time):
        if start_x is None or end_x is None or start_time is None:
            return
        delta_x = end_x - start_x
        duration = time.monotonic() - start_time
        if abs(delta_x) >= self.swipe_threshold_px:
            # swipe left (finger moves left, negative delta) -> next; swipe right -> prev
            self.event_queue.put(NavEvent.PREV if delta_x > 0 else NavEvent.NEXT)
        elif abs(delta_x) <= self.tap_max_distance_px and duration <= self.tap_max_duration:
            self.event_queue.put(NavEvent.TOGGLE_PAUSE)
