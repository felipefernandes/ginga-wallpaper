"""Keyboard logic of calibration mode (no window needed)."""

from ginga.calibrate import Calibration
from ginga.config import Offset
from ginga.layout import Monitor, build_layout


def make(offsets=None):
    return Calibration(["1", "2"], offsets or {})


def test_selects_second_monitor_first():
    # Monitor 1 is the natural reference; the other one is the one to move.
    assert make().selected == "2"
    assert Calibration(["1"], {}).selected == "1"


def test_up_moves_image_up_which_is_a_positive_y_offset():
    cal = make()
    cal.handle("up")
    assert cal.offsets["2"] == Offset(0, 1)

    # Proof against the layout: a physically lower monitor needs +y.
    monitors = [Monitor("a", 0, 0, 1920, 1080), Monitor("b", 1920, 0, 1920, 1080)]
    layout = build_layout(monitors, cal.offsets)
    assert layout.views[1].canvas.y - layout.views[0].canvas.y == 1


def test_arrows_and_shift_step():
    cal = make()
    cal.handle("down", shift=True)
    cal.handle("left")
    cal.handle("left")
    cal.handle("right")
    assert cal.offsets["2"] == Offset(1, -10)


def test_tab_cycles_monitors():
    cal = make()
    cal.handle("tab")
    assert cal.selected == "1"
    cal.handle("up")
    assert cal.offsets["1"] == Offset(0, 1)
    cal.handle("tab")
    assert cal.selected == "2"


def test_enter_saves_and_esc_cancels():
    cal = make()
    assert cal.handle("enter") == "save"
    assert cal.handle("esc") == "cancel"
    assert cal.handle("up") is None


def test_unknown_keys_are_ignored():
    cal = make({"2": Offset(3, 4)})
    assert cal.handle("f5") is None
    assert cal.offsets["2"] == Offset(3, 4)


def test_does_not_mutate_the_offsets_it_was_given():
    original = {"2": Offset(0, 50)}
    cal = Calibration(["1", "2"], original)
    cal.handle("up")
    assert original["2"] == Offset(0, 50)
    assert cal.offsets["2"] == Offset(0, 51)


def test_hud_text_shows_selected_monitor_and_offset():
    cal = make({"2": Offset(-2, 120)})
    assert "Monitor 2" in cal.hud_text()
    assert "x -2" in cal.hud_text() and "y +120" in cal.hud_text()


def test_hud_image_renders_with_expected_size():
    from ginga.calibrate import HUD_SIZE, _hud_image

    img = _hud_image(make().hud_text())
    assert img.size == HUD_SIZE and img.mode == "RGBA"


def test_guides_shader_draws_lines_in_canvas_space():
    import numpy as np
    import pytest

    moderngl = pytest.importorskip("moderngl")
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as exc:
        pytest.skip(f"No OpenGL context available: {exc}")

    from ginga.wave import _shader

    prog = ctx.program(vertex_shader=_shader("wave.vert.glsl"), fragment_shader=_shader("guides.frag.glsl"))
    quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4").tobytes())
    vao = ctx.vertex_array(prog, [(quad, "2f", "in_pos")])

    def alpha_rows(origin_y):
        fbo = ctx.simple_framebuffer((200, 200), components=4)
        fbo.use()
        fbo.clear()
        prog["u_origin"].value = (0, origin_y)
        prog["u_resolution"].value = (200, 200)
        prog["u_selected"].value = 0.0
        vao.render(moderngl.TRIANGLE_STRIP)
        rgba = np.frombuffer(fbo.read(components=4), dtype=np.uint8).reshape(200, 200, 4)
        return np.flipud(rgba)[:, 100, 3]  # alpha down the middle column, top row first

    # A horizontal line at canvas y=60 shows at local row 60, or 50 when the
    # monitor looks 10 px lower into the canvas.
    assert alpha_rows(0)[60] > 80 and alpha_rows(0)[30] < 80
    assert alpha_rows(10)[50] > 80
    ctx.release()


def test_hud_text_fits_inside_the_hud():
    from PIL import Image, ImageDraw

    from ginga.calibrate import HUD_LINE_SPACING, HUD_SIZE, HUD_TEXT_POS, _hud_font

    # Worst case: big offsets on both axes.
    text = make({"2": Offset(-9999, -9999)}).hud_text()
    draw = ImageDraw.Draw(Image.new("RGBA", HUD_SIZE))
    left, top, right, bottom = draw.multiline_textbbox(
        HUD_TEXT_POS, text, font=_hud_font(), spacing=HUD_LINE_SPACING
    )
    assert right <= HUD_SIZE[0] - HUD_TEXT_POS[0]
    assert bottom <= HUD_SIZE[1]
