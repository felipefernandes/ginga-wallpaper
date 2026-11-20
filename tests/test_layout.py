from ginga.config import Offset
from ginga.layout import Monitor, Rect, build_layout, desktop_bounds, gl_viewport


M1 = Monitor(name="Main", x=0, y=0, width=2560, height=1440)
M2 = Monitor(name="Side", x=2560, y=0, width=1920, height=1080)


def test_ids_follow_left_to_right_order():
    layout = build_layout([M2, M1], offsets={})

    assert [v.monitor_id for v in layout.views] == ["1", "2"]
    assert layout.views[0].monitor == M1


def test_no_offsets_canvas_matches_desktop():
    layout = build_layout([M1, M2], offsets={})

    assert layout.canvas_width == 2560 + 1920
    assert layout.canvas_height == 1440
    assert layout.views[0].canvas == Rect(0, 0, 2560, 1440)
    assert layout.views[1].canvas == Rect(2560, 0, 1920, 1080)


def test_offset_moves_monitor_inside_canvas():
    layout = build_layout([M1, M2], offsets={"2": Offset(x=0, y=120)})

    assert layout.views[1].canvas == Rect(2560, 120, 1920, 1080)
    assert layout.canvas_height == 1440


def test_offset_beyond_bounds_grows_canvas():
    layout = build_layout([M1, M2], offsets={"2": Offset(x=0, y=500)})

    assert layout.canvas_height == 500 + 1080


def test_negative_positions_are_normalized_to_zero_origin():
    left = Monitor(name="Left", x=-1920, y=-200, width=1920, height=1080)
    layout = build_layout([left, M1], offsets={})

    assert layout.views[0].canvas == Rect(0, 0, 1920, 1080)
    assert layout.views[1].canvas == Rect(1920, 200, 2560, 1440)
    assert layout.canvas_width == 1920 + 2560
    assert layout.canvas_height == 200 + 1440


def test_offsets_for_unknown_monitors_are_ignored():
    layout = build_layout([M1], offsets={"7": Offset(x=999, y=999)})

    assert layout.views[0].canvas == Rect(0, 0, 2560, 1440)


def test_desktop_bounds_is_union_of_monitors():
    left = Monitor(name="Left", x=-1920, y=-200, width=1920, height=1080)

    assert desktop_bounds([left, M1]) == Rect(-1920, -200, 1920 + 2560, 1640)


def test_gl_viewport_flips_y_axis():
    # Desktop: M1 at top-left (taller), M2 to the right, top-aligned.
    desktop = desktop_bounds([M1, M2])

    # GL origin is bottom-left of the window.
    assert gl_viewport(M1, desktop) == (0, 0, 2560, 1440)
    assert gl_viewport(M2, desktop) == (2560, 1440 - 1080, 1920, 1080)


def test_gl_viewport_with_negative_coords():
    left = Monitor(name="Left", x=-1920, y=-200, width=1920, height=1080)
    desktop = desktop_bounds([left, M1])

    assert gl_viewport(left, desktop) == (0, 1640 - 1080, 1920, 1080)
    assert gl_viewport(M1, desktop) == (1920, 0, 2560, 1440)
