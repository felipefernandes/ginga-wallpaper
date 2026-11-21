"""GPU tests for the media wallpaper (skip without an OpenGL context)."""

import numpy as np
import pytest
from PIL import Image

from ginga.config import BackgroundSettings, Config, Offset
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


@pytest.fixture
def gradient(tmp_path):
    """Horizontal red ramp and vertical green ramp: every pixel is unique-ish."""
    w, h = 320, 120
    arr = np.zeros((h, w, 3), np.uint8)
    arr[..., 0] = np.linspace(0, 255, w, dtype=np.uint8)[None, :]
    arr[..., 1] = np.linspace(0, 255, h, dtype=np.uint8)[:, None]
    path = tmp_path / "ramp.png"
    Image.fromarray(arr).save(path)
    return path


def render(ctx, path, monitors, offsets=None, fit="fill"):
    from ginga.background import create_background

    layout = build_layout(monitors, offsets or {})
    settings = BackgroundSettings(kind="media", path=str(path), fit=fit)
    bg = create_background(ctx, settings, (layout.canvas_width, layout.canvas_height))
    assert bg.update()  # the still frame is uploaded once...
    assert not bg.update()  # ...then there is nothing new to draw
    images = {}
    for view in layout.views:
        w, h = view.canvas.width, view.canvas.height
        fbo = ctx.simple_framebuffer((w, h))
        fbo.use()
        bg.draw(layout, view, 0.0, Config())
        data = np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3)
        images[view.monitor_id] = np.flipud(data)
        fbo.release()
    bg.release()
    return images


def test_image_spans_split_monitors_seamlessly(ctx, gradient):
    whole = render(ctx, gradient, [Monitor("All", 0, 0, 320, 120)])["1"]
    parts = render(ctx, gradient, [Monitor("L", 0, 0, 160, 120), Monitor("R", 160, 0, 160, 120)])

    stitched = np.concatenate([parts["1"], parts["2"]], axis=1)
    assert np.abs(stitched.astype(int) - whole.astype(int)).max() <= 2
    assert abs(int(whole[60, 0, 0]) - 0) <= 2 and abs(int(whole[60, -1, 0]) - 255) <= 2


def test_lower_monitor_shows_the_image_further_down(ctx, gradient):
    """Monitor 2 sits 20 px lower: its top row continues where monitor 1's row 20 is."""
    monitors = [Monitor("L", 0, 0, 160, 100), Monitor("R", 160, 0, 160, 100)]
    imgs = render(ctx, gradient, monitors, {"2": Offset(0, 20)}, fit="stretch")

    left_green = imgs["1"][20:, -1, 1].astype(int)
    right_green = imgs["2"][:80, 0, 1].astype(int)
    assert np.abs(left_green - right_green).max() <= 3


def test_fit_leaves_black_bars(ctx, gradient):
    img = render(ctx, gradient, [Monitor("Tall", 0, 0, 160, 240)], fit="fit")["1"]
    assert img[:30].max() == 0 and img[-30:].max() == 0
    assert img[100:140].max() > 100


def test_missing_file_falls_back_to_the_wave(ctx, tmp_path):
    from ginga.background import WaveBackground, create_background

    settings = BackgroundSettings(kind="media", path=str(tmp_path / "gone.png"))
    assert isinstance(create_background(ctx, settings, (100, 100)), WaveBackground)


def _draw_full(ctx, bg, w, h):
    layout = build_layout([Monitor("All", 0, 0, w, h)], {})
    fbo = ctx.simple_framebuffer((w, h))
    fbo.use()
    bg.draw(layout, layout.views[0], 0.0, Config())
    img = np.flipud(np.frombuffer(fbo.read(components=3), dtype=np.uint8).reshape(h, w, 3))
    fbo.release()
    return img


@pytest.mark.parametrize("fmt", ["yuv420p", "nv12"])
def test_yuv_frames_with_padded_rows_convert_on_the_gpu(ctx, gradient, fmt):
    """Left half red, right half blue (BT.601 limited); padding is garbage (255)."""
    from ginga.background import create_background
    from ginga.media import Planes

    w, h, pad = 64, 32, 32
    y = np.full((h, w + pad), 255, np.uint8)
    y[:, : w // 2], y[:, w // 2 : w] = 81, 41
    u = np.full((h // 2, w // 2 + pad), 255, np.uint8)
    v = np.full((h // 2, w // 2 + pad), 255, np.uint8)
    u[:, : w // 4], u[:, w // 4 : w // 2] = 90, 240
    v[:, : w // 4], v[:, w // 4 : w // 2] = 240, 110
    if fmt == "nv12":
        uv = np.full((h // 2, w + 2 * pad), 255, np.uint8)
        uv[:, 0 : w : 2], uv[:, 1 : w : 2] = u[:, : w // 2], v[:, : w // 2]
        planes = Planes("nv12", (y.tobytes(), uv.tobytes()), (w + pad, w + 2 * pad), (w, h), False, False)
    else:
        planes = Planes("yuv420p", (y.tobytes(), u.tobytes(), v.tobytes()),
                        (w + pad, w // 2 + pad, w // 2 + pad), (w, h), False, False)

    bg = create_background(ctx, BackgroundSettings(kind="media", path=str(gradient), fit="stretch"), (w, h))
    bg.source.media_size = (w, h)
    bg._upload(planes)
    img = _draw_full(ctx, bg, w, h).astype(int)
    bg.release()

    red, blue = img[16, 8], img[16, 56]
    assert red[0] > 220 and red[1] < 30 and red[2] < 30, red
    assert blue[2] > 200 and blue[0] < 40, blue
    assert img[:, 60:].min(axis=(0, 1))[1] < 40  # right edge: no garbage from the padding
