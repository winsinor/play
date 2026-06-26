from display.input_touch import remap_touch_xy


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
