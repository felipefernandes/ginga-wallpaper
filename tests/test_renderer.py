"""Pure frame-loop logic of the renderer (no window or GL needed)."""

import pytest

from ginga.config import Offset
from ginga.layout import Monitor, build_layout, desktop_bounds
from ginga.renderer import AnimationClock, FrameLimiter, Throttle, plan_viewports

OWNER = [Monitor("1", 0, 0, 1920, 1080), Monitor("2", 1920, 0, 1920, 1080)]


class TestFrameLimiter:
    def test_first_frame_draws_immediately(self):
        assert FrameLimiter(30).delay(now=5.0) == 0

    def test_waits_until_next_frame_slot(self):
        lim = FrameLimiter(25)  # 40 ms per frame
        lim.mark(now=1.0)
        assert lim.delay(now=1.01) == pytest.approx(0.03)
        assert lim.delay(now=1.05) == 0

    def test_schedule_does_not_drift_on_late_frames(self):
        lim = FrameLimiter(25)
        lim.mark(now=0.0)
        lim.mark(now=0.045)  # 5 ms late: next slot stays at 80 ms, not 85 ms
        assert lim.delay(now=0.045) == pytest.approx(0.035)

    def test_resyncs_after_falling_far_behind(self):
        lim = FrameLimiter(25)
        lim.mark(now=0.0)
        lim.mark(now=10.0)  # e.g. after a pause: no burst of catch-up frames
        assert lim.delay(now=10.0) == pytest.approx(0.04)

    def test_fps_can_change(self):
        lim = FrameLimiter(30)
        lim.fps = 10
        lim.mark(now=0.0)
        assert lim.delay(now=0.0) == pytest.approx(0.1)

    def test_reset_draws_immediately(self):
        lim = FrameLimiter(1)
        lim.mark(now=0.0)
        lim.reset()
        assert lim.delay(now=0.0) == 0


class TestAnimationClock:
    def test_starts_at_zero_and_advances(self):
        clock = AnimationClock()
        assert clock.tick(now=100.0) == 0
        assert clock.tick(now=100.5) == pytest.approx(0.5)

    def test_long_gaps_are_capped(self):
        # After a pause (game, sleep) the wave continues instead of jumping.
        clock = AnimationClock(max_step=0.25)
        clock.tick(now=0.0)
        assert clock.tick(now=600.0) == pytest.approx(0.25)

    def test_clock_going_backwards_is_ignored(self):
        clock = AnimationClock()
        clock.tick(now=10.0)
        assert clock.tick(now=9.0) == 0


class TestThrottle:
    def test_due_first_time_then_once_per_interval(self):
        t = Throttle(0.5)
        assert t.due(now=0.0)
        assert not t.due(now=0.3)
        assert t.due(now=0.5)
        assert not t.due(now=0.9)


class TestPlanViewports:
    def test_each_monitor_gets_its_own_viewport_and_view(self):
        layout = build_layout(OWNER, {"2": Offset(0, 100)})
        plan = plan_viewports(layout, desktop_bounds(OWNER))

        assert [(vp, v.monitor_id) for vp, v in plan] == [
            ((0, 0, 1920, 1080), "1"),
            ((1920, 0, 1920, 1080), "2"),
        ]
        # Monitor 2 looks 100 px lower into the canvas than monitor 1.
        assert plan[1][1].canvas.y - plan[0][1].canvas.y == 100

    def test_shorter_monitor_is_anchored_to_window_top(self):
        monitors = [Monitor("a", 0, 0, 2560, 1440), Monitor("b", 2560, 0, 1920, 1080)]
        layout = build_layout(monitors, {})
        plan = plan_viewports(layout, desktop_bounds(monitors))
        # GL y is bottom-up: a 1080 px monitor at the top of a 1440 px window starts at 360.
        assert plan[1][0] == (2560, 360, 1920, 1080)
