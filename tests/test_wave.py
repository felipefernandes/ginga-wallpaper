"""GPU tests: run headless where an OpenGL context is available, skip otherwise."""

import numpy as np
import pytest

from ginga.config import WaveSettings
from ginga.layout import Monitor, build_layout

moderngl = pytest.importorskip("moderngl")


@pytest.fixture(scope="module")
def ctx():
    try:
        context = moderngl.create_standalone_context(backend="egl")
    except Exception:
        try:
            context = moderngl.create_standalone_context()
        except Exception as exc:
            pytest.skip(f"No OpenGL context available: {exc}")
    yield context
    context.release()


def render(ctx, monitors, offsets=None, time=3.0):
    """Render each monitor's view and return {monitor_id: RGB array}."""
    from ginga.wave import WaveProgram

    prog = WaveProgram(ctx)
    layout = build_layout(monitors, offsets or {})
    images = {}
    for view in layout.views:
        w, h = view.canvas.width, view.canvas.height
        fbo = ctx.simple_framebuffer((w, h))
        fbo.use()
        fbo.clear()
        prog.draw(layout, view, time, WaveSettings())
        data = np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3)
        images[view.monitor_id] = np.flipud(data)  # top row first
        fbo.release()
    return images


def test_split_monitors_match_single_canvas(ctx):
    whole = render(ctx, [Monitor("All", 0, 0, 320, 120)])["1"]
    parts = render(ctx, [Monitor("L", 0, 0, 160, 120), Monitor("R", 160, 0, 160, 120)])

    stitched = np.concatenate([parts["1"], parts["2"]], axis=1)
    diff = np.abs(stitched.astype(int) - whole.astype(int))
    assert diff.max() <= 2


def test_wave_is_bright_in_middle_and_dark_at_edges(ctx):
    img = render(ctx, [Monitor("All", 0, 0, 320, 240)])["1"].astype(float)

    assert img[110:130].mean() > 4 * img[:20].mean()
    assert img[:20].mean() < 10
