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


def _render_one(ctx, audio, w=320, h=120, time=3.0):
    from ginga.wave import WaveProgram

    prog = WaveProgram(ctx)
    layout = build_layout([Monitor("All", 0, 0, w, h)], {})
    fbo = ctx.simple_framebuffer((w, h))
    fbo.use()
    fbo.clear()
    prog.draw(layout, layout.views[0], time, WaveSettings(), audio=audio)
    img = np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3).astype(int)
    fbo.release()
    return img


def test_audio_mix_zero_is_exactly_the_idle_wave(ctx):
    from ginga.wave import AudioUniforms

    loud = AudioUniforms(mix=0.0, bass=1.0, level=1.0, spectrum=np.ones(128, dtype=np.float32))
    assert np.array_equal(_render_one(ctx, None), _render_one(ctx, loud))


def test_spectrum_drives_the_spikes_when_audio_is_on(ctx):
    from ginga.wave import AudioUniforms

    quiet = AudioUniforms(mix=1.0, bass=0.0, level=0.0, spectrum=np.zeros(128, dtype=np.float32))
    loud = AudioUniforms(mix=1.0, bass=0.0, level=0.0, spectrum=np.ones(128, dtype=np.float32))
    lit_quiet = (_render_one(ctx, quiet).sum(axis=2) > 60).sum()
    lit_loud = (_render_one(ctx, loud).sum(axis=2) > 60).sum()
    assert lit_loud > lit_quiet * 1.5


def test_audio_view_is_still_seamless_across_monitors(ctx):
    from ginga.wave import AudioUniforms, WaveProgram

    spectrum = np.linspace(0, 1, 128, dtype=np.float32)
    audio = AudioUniforms(mix=1.0, bass=0.6, level=0.5, spectrum=spectrum)
    prog = WaveProgram(ctx)

    def draw(monitors):
        layout = build_layout(monitors, {})
        out = []
        for view in layout.views:
            fbo = ctx.simple_framebuffer((view.canvas.width, view.canvas.height))
            fbo.use()
            prog.draw(layout, view, 3.0, WaveSettings(), audio=audio)
            out.append(np.frombuffer(fbo.read(components=3), dtype=np.uint8)
                       .reshape(view.canvas.height, view.canvas.width, 3))
            fbo.release()
        return out

    whole = draw([Monitor("All", 0, 0, 320, 120)])[0]
    left, right = draw([Monitor("L", 0, 0, 160, 120), Monitor("R", 160, 0, 160, 120)])
    assert np.abs(np.hstack([left, right]).astype(int) - whole.astype(int)).max() <= 2
