import pygame
import pytest

from display.input_touch import remap_touch_xy, touch_flags_for_rotation


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
