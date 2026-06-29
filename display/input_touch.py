"""Reads the HyperPixel touchscreen directly via evdev (no X11 needed) and
turns gestures into events on a thread-safe queue: swipe-left/right become
NavEvents (handled globally by DemoManager), a quick tap becomes a TapEvent,
and a press-and-hold that then moves becomes a stream of PressDragEvents
followed by one PressReleaseEvent -- a stationary hold that never drags
produces no event at all (see Demo.handle_touch).

Runs in a background thread so it never blocks the pygame render loop. If no
touch device is present (e.g. on a dev machine), it logs once and exits
cleanly -- keyboard navigation still works.
"""

import math
import os
import threading
import time

try:
    import evdev
except ImportError:  # not installed / not on Linux
    evdev = None

from display.manager import NavEvent, PinchZoomEvent, PressDragEvent, PressReleaseEvent, TapEvent


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


def remap_touch_xy(x, y, min_x, max_x, min_y, max_y, swap_xy, invert_x, invert_y, canvas_width=None, canvas_height=None):
    """Apply a swap/invert combo to a raw touch coordinate, then rescale to canvas pixels.
    Swap is applied first, then per-axis inversion (using that axis's own min/max after the
    swap), then rescaling to canvas dimensions. Used by TouchInputThread to undo display.config.DISPLAY_ROTATE_DEGREES
    (see touch_flags_for_rotation below)."""
    if swap_xy:
        x, y, min_x, max_x, min_y, max_y = y, x, min_y, max_y, min_x, max_x
    if invert_x:
        x = max_x - (x - min_x)
    if invert_y:
        y = max_y - (y - min_y)
    
    # Rescale from device raw range to canvas pixels
    if canvas_width is not None and canvas_height is not None:
        x = (x - min_x) / (max_x - min_x) * canvas_width
        y = (y - min_y) / (max_y - min_y) * canvas_height
    
    return x, y


def pinch_scale(prev_distance, new_distance, min_distance=1e-3):
    """Multiplicative change in two-finger separation distance between
    consecutive pinch samples (new_distance / prev_distance), or None if
    there's no valid prior sample yet to compare against."""
    if prev_distance is None or prev_distance < min_distance:
        return None
    return new_distance / prev_distance


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
        swipe_threshold_fraction,
        tap_max_duration,
        tap_max_distance_px,
        long_press_min_duration,
        device=None,
        rotate_degrees=0,
        canvas_width=800,
        canvas_height=480,
        min_pinch_separation_px=60,
    ):
        super().__init__(daemon=True)
        self.event_queue = event_queue
        # A swipe must cross most of the screen so it's never confused with a
        # pinch or a slingshot drag (those are also guarded explicitly below,
        # but a high distance bar makes a misfire essentially impossible too).
        self.swipe_threshold_px = swipe_threshold_fraction * canvas_width
        self.tap_max_duration = tap_max_duration
        self.tap_max_distance_px = tap_max_distance_px
        self.long_press_min_duration = long_press_min_duration
        # Two fingers closer together than this aren't treated as a pinch. Real
        # pinch-to-zoom starts with the fingers well apart; a sub-threshold gap
        # is almost always the incidental two-finger overlap you get from
        # tapping the screen rapidly (e.g. adding planets fast in the n-body
        # demo), which must not be allowed to fire spurious zoom events.
        self.min_pinch_separation_px = min_pinch_separation_px
        self._device = device
        self.swap_xy, self.invert_x, self.invert_y = touch_flags_for_rotation(rotate_degrees)
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
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
        dragging = False

        # Multitouch state, only relevant once a second finger touches down
        # (see _maybe_emit_pinch). mt_slot is the slot the next
        # ABS_MT_POSITION_*/ABS_MT_TRACKING_ID event applies to (set by
        # ABS_MT_SLOT); primary_slot is whichever slot drives the
        # single-touch gesture machine above, so a second finger's position
        # updates never feed into (and corrupt) a tap/swipe/drag already in
        # progress on the first finger.
        mt_slot = 0
        primary_slot = None
        active_slots = set()
        slot_positions = {}
        pinch_prev_distance = None
        # True if a second finger touched down at any point during the
        # gesture currently being tracked on primary_slot -- a swipe must
        # never fire off the tail end of what was actually a pinch.
        gesture_had_second_finger = False

        try:
            for event in device.read_loop():
                if self._stop_event.is_set():
                    return

                if event.type == evdev.ecodes.EV_ABS and event.code in (
                    evdev.ecodes.ABS_MT_POSITION_X,
                    evdev.ecodes.ABS_X,
                ):
                    slot_positions.setdefault(mt_slot, [None, None])[0] = event.value
                    if primary_slot is None:
                        primary_slot = mt_slot
                    if mt_slot == primary_slot:
                        last_x = event.value
                        if start_x is None:
                            start_x = event.value
                            start_time = time.monotonic()
                            gesture_had_second_finger = False

                elif event.type == evdev.ecodes.EV_ABS and event.code in (
                    evdev.ecodes.ABS_MT_POSITION_Y,
                    evdev.ecodes.ABS_Y,
                ):
                    slot_positions.setdefault(mt_slot, [None, None])[1] = event.value
                    if primary_slot is None:
                        primary_slot = mt_slot
                    if mt_slot == primary_slot:
                        last_y = event.value
                        if start_y is None:
                            start_y = event.value

                elif event.type == evdev.ecodes.EV_ABS and event.code == evdev.ecodes.ABS_MT_SLOT:
                    mt_slot = event.value

                elif event.type == evdev.ecodes.EV_ABS and event.code == evdev.ecodes.ABS_MT_TRACKING_ID:
                    if event.value == -1:
                        active_slots.discard(mt_slot)
                        slot_positions.pop(mt_slot, None)
                        pinch_prev_distance = None
                        if mt_slot == primary_slot:
                            # the finger driving the single-touch gesture
                            # lifted -- finish it, then (rare) if another
                            # finger is still down, hand single-touch
                            # tracking over to it for whatever comes next.
                            self._finish_touch(
                                start_x, start_y, last_x, last_y, start_time, dragging, gesture_had_second_finger
                            )
                            start_x = start_y = last_x = last_y = start_time = None
                            dragging = False
                            gesture_had_second_finger = False
                            primary_slot = next(iter(active_slots), None)
                    else:
                        active_slots.add(mt_slot)
                        if len(active_slots) >= 2:
                            gesture_had_second_finger = True

                elif event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_TOUCH:
                    if event.value == 0:
                        self._finish_touch(
                            start_x, start_y, last_x, last_y, start_time, dragging, gesture_had_second_finger
                        )
                        start_x = start_y = last_x = last_y = start_time = None
                        dragging = False
                        gesture_had_second_finger = False
                        primary_slot = None
                        active_slots.clear()
                        slot_positions.clear()
                        pinch_prev_distance = None

                dragging = self._maybe_emit_drag(
                    start_x, start_y, last_x, last_y, start_time, dragging, gesture_had_second_finger
                )
                pinch_prev_distance = self._maybe_emit_pinch(active_slots, slot_positions, pinch_prev_distance)
        except OSError as exc:
            print(f"[input_touch] touch device error, stopping touch input: {exc}")

    def _remap(self, x, y):
        if x is None or y is None:
            return x, y
        return remap_touch_xy(
            x, y, self._min_x, self._max_x, self._min_y, self._max_y,
            self.swap_xy, self.invert_x, self.invert_y,
            self.canvas_width, self.canvas_height,
        )

    def _maybe_emit_pinch(self, active_slots, slot_positions, prev_distance):
        """Called after every event. Once two fingers are down and both their
        positions are known, emits a PinchZoomEvent carrying the change in
        their separation since the last sample (see pinch_scale) -- but only
        if that separation actually changed, since the docstring on
        PinchZoomEvent promises it's sent only "while ... distance apart is
        changing", and plenty of events (slot switches, an axis re-reported
        at its same value) don't move either finger at all. Returns the
        distance to compare against next time, or None if fewer than two
        fingers are currently down (so a fresh baseline gets established
        next time a second finger touches down, rather than comparing across
        an unrelated earlier pinch)."""
        if len(active_slots) < 2:
            return None
        points = []
        for slot in sorted(active_slots)[:2]:
            pos = slot_positions.get(slot)
            if pos is None or pos[0] is None or pos[1] is None:
                return prev_distance  # not all positions known yet -- keep waiting
            points.append(self._remap(pos[0], pos[1]))
        distance = math.hypot(points[0][0] - points[1][0], points[0][1] - points[1][1])
        if distance < self.min_pinch_separation_px:
            # Fingers too close to be a deliberate pinch (see
            # min_pinch_separation_px). Drop the baseline so that if they do
            # spread into a real pinch later, the first scale is measured from
            # the moment they crossed the threshold rather than from this tiny
            # -- and noise-amplifying -- separation.
            return None
        scale = pinch_scale(prev_distance, distance)
        if scale is not None and distance != prev_distance:
            self.event_queue.put(PinchZoomEvent(scale))
        return distance

    def _maybe_emit_drag(self, start_x, start_y, last_x, last_y, start_time, dragging, had_second_finger=False):
        """Called after every position update for the touch in progress (if
        any). Once a hold has both lasted long_press_min_duration and moved
        past tap_max_distance_px, it becomes a drag: emits a PressDragEvent
        for this position and every subsequent one, and once started never
        reverts back to non-dragging for this touch (checked by the caller,
        which skips re-entering this method once a touch has ended).

        A drag is never started or continued once a second finger has joined
        the gesture: that's a pinch, and the primary finger's motion during it
        must not also be reported as a one-finger drag. Without this, pinching
        to zoom the n-body demo would drift the first finger far enough to fire
        PressDragEvents -- popping up the slingshot launch preview and, on
        release, actually launching a planet. (The swipe path and _finish_touch
        already guard against the same second-finger contamination.)"""
        if had_second_finger:
            return dragging
        if start_x is None or start_y is None or last_x is None or last_y is None or start_time is None:
            return dragging
        if self.swap_xy or self.invert_x or self.invert_y:
            start_x, start_y = self._remap(start_x, start_y)
            last_x, last_y = self._remap(last_x, last_y)
        if not dragging:
            distance = max(abs(last_x - start_x), abs(last_y - start_y))
            elapsed = time.monotonic() - start_time
            if elapsed < self.long_press_min_duration or distance < self.tap_max_distance_px:
                return dragging
            dragging = True
        self.event_queue.put(PressDragEvent(last_x, last_y, start_x, start_y))
        return dragging

    def _finish_touch(self, start_x, start_y, end_x, end_y, start_time, dragging, had_second_finger=False):
        if start_x is None or end_x is None or start_time is None:
            return
        if self.swap_xy or self.invert_x or self.invert_y:
            start_x, start_y = self._remap(start_x, start_y)
            end_x, end_y = self._remap(end_x, end_y)

        x = end_x if end_x is not None else start_x
        y = end_y if end_y is not None else start_y

        if dragging:
            self.event_queue.put(PressReleaseEvent(x, y, start_x, start_y))
            return

        delta_x = end_x - start_x
        delta_y = (end_y - start_y) if (start_y is not None and end_y is not None) else 0
        duration = time.monotonic() - start_time

        # A pinch's tail end (second finger lifts, then the first finger's
        # own lift closes out the gesture) must never be misread as a swipe,
        # even if that finger drifted past the swipe distance during the pinch.
        if not had_second_finger and abs(delta_x) >= self.swipe_threshold_px:
            # swipe left (finger moves left, negative delta) -> next; swipe right -> prev
            self.event_queue.put(NavEvent.PREV if delta_x > 0 else NavEvent.NEXT)
            return

        distance = max(abs(delta_x), abs(delta_y))
        if distance > self.tap_max_distance_px:
            return  # an ambiguous drag that wasn't a swipe and never reached drag-mode -- ignore

        if duration <= self.tap_max_duration:
            self.event_queue.put(TapEvent(x, y))
        # else: a stationary hold past tap_max_duration that never moved far
        # enough to start dragging -- intentionally a no-op, since hold-to-reset
        # has been removed project-wide.
