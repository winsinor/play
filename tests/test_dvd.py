import pytest

from display.demos.dvd import bounce_position


def test_bounce_position_starts_at_zero_and_reaches_span_at_half_period():
    assert bounce_position(0.0, 2.0, 100.0) == 0.0
    assert bounce_position(2.0, 2.0, 100.0) == 100.0


def test_bounce_position_returns_to_zero_after_full_period():
    half_period, span = 2.0, 100.0
    assert bounce_position(4.0, half_period, span) == 0.0


def test_bounce_position_is_symmetric_about_the_turnaround():
    half_period, span = 3.0, 50.0
    before = bounce_position(half_period - 1.0, half_period, span)
    after = bounce_position(half_period + 1.0, half_period, span)
    assert before == pytest.approx(after)


def test_bounce_position_never_overshoots_span():
    half_period, span = 1.7, 40.0
    for i in range(1000):
        t = i * 0.013
        pos = bounce_position(t, half_period, span)
        assert -1e-9 <= pos <= span + 1e-9
