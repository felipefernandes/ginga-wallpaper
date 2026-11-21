"""Media wallpaper: placement on the canvas and the image/GIF/video sources."""

import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ginga import media


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.005)
    raise AssertionError("timed out")


# -- placement ------------------------------------------------------------------------


def test_fill_covers_the_canvas_and_crops_the_overflow_evenly():
    # 2 monitors 1920x1080 with the second 150 px lower -> canvas 3840x1230.
    x, y, w, h = media.place((1920, 1080), (3840, 1230), "fill")
    assert (w, h) == (3840, 2160)
    assert (x, y) == (0, (1230 - 2160) / 2)


def test_fit_shows_the_whole_image_centered():
    x, y, w, h = media.place((1000, 1000), (3840, 1230), "fit")
    assert (w, h) == (1230, 1230)
    assert (x, y) == ((3840 - 1230) / 2, 0)


def test_stretch_matches_the_canvas_exactly():
    assert media.place((640, 480), (3840, 1230), "stretch") == (0, 0, 3840, 1230)


def test_decode_size_downscales_big_images_but_never_upscales():
    assert media.decode_size((7680, 4320), (3840, 1230), "fill") == (3840, 2160)
    assert media.decode_size((800, 600), (3840, 1230), "fill") == (800, 600)
    assert media.decode_size((8000, 1000), (3840, 1230), "stretch") == (3840, 1000)


# -- kinds ----------------------------------------------------------------------------


def make_gif(path: Path, colors, duration=40):
    frames = [Image.new("RGB", (32, 16), c) for c in colors]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
    return path


def make_video(path: Path, colors, fps=25):
    av = pytest.importorskip("av")
    with av.open(str(path), "w") as out:
        stream = out.add_stream("mpeg4", rate=fps)
        stream.width, stream.height, stream.pix_fmt = 64, 32, "yuv420p"
        for c in colors:
            arr = np.zeros((32, 64, 3), np.uint8)
            arr[:] = c
            for packet in stream.encode(av.VideoFrame.from_ndarray(arr, format="rgb24")):
                out.mux(packet)
        for packet in stream.encode():
            out.mux(packet)
    return path


def test_media_kind(tmp_path):
    Image.new("RGB", (8, 8)).save(tmp_path / "a.png")
    make_gif(tmp_path / "b.gif", [(255, 0, 0), (0, 0, 255)])
    Image.new("RGB", (8, 8)).save(tmp_path / "still.gif")

    assert media.media_kind(tmp_path / "a.png") == "image"
    assert media.media_kind(tmp_path / "b.gif") == "animation"
    assert media.media_kind(tmp_path / "still.gif") == "image"
    assert media.media_kind(tmp_path / "clip.MP4") == "video"


def test_unreadable_files_raise_media_error(tmp_path):
    (tmp_path / "bad.png").write_text("not an image")
    with pytest.raises(media.MediaError):
        media.open_media(tmp_path / "bad.png", (100, 100), "fill")
    with pytest.raises(media.MediaError):
        media.open_media(tmp_path / "missing.jpg", (100, 100), "fill")


# -- sources --------------------------------------------------------------------------


def test_image_source_delivers_one_downscaled_frame(tmp_path):
    Image.new("RGB", (400, 200), (10, 20, 30)).save(tmp_path / "big.png")
    src = media.open_media(tmp_path / "big.png", (100, 100), "fit")
    try:
        assert not src.animated
        assert src.size == (100, 50)
        frame = src.poll()
        assert frame is not None and len(frame) == 100 * 50 * 3
        assert frame[:3] == bytes((10, 20, 30))
        assert src.poll() is None  # nothing new: the renderer can stop drawing
    finally:
        src.close()


def test_image_source_flattens_transparency_onto_black(tmp_path):
    Image.new("RGBA", (4, 4), (255, 255, 255, 0)).save(tmp_path / "clear.png")
    src = media.open_media(tmp_path / "clear.png", (4, 4), "fill")
    assert src.poll()[:3] == bytes((0, 0, 0))
    src.close()


def test_gif_plays_its_frames_in_a_loop(tmp_path):
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    src = media.open_media(make_gif(tmp_path / "a.gif", colors, duration=30), (32, 16), "fill")
    try:
        assert src.animated and src.size == (32, 16)
        src.set_running(True)
        seen = []
        deadline = time.monotonic() + 3
        while len(set(seen)) < 3 or seen.count(seen[0]) < 2:
            assert time.monotonic() < deadline
            frame = src.poll()
            if frame is not None:
                seen.append(frame[:3])
            time.sleep(0.005)
        assert set(seen) == {bytes(c) for c in colors}
    finally:
        src.close()


def test_paused_player_stops_producing_frames(tmp_path):
    src = media.open_media(make_gif(tmp_path / "a.gif", [(255, 0, 0), (0, 0, 255)], 20), (32, 16), "fill")
    try:
        src.set_running(True)
        wait_for(src.poll)
        src.set_running(False)
        time.sleep(0.1)
        src.poll()  # drain a frame published just before the pause
        time.sleep(0.15)
        assert src.poll() is None
    finally:
        src.close()


def centre_rgb(planes):
    """RGB of the centre pixel of a YUV frame, as the shader computes it."""
    w, h = planes.size
    x, y = w // 2, h // 2
    luma = planes.data[0][y * planes.strides[0] + x]
    row = (y // 2) * planes.strides[1]
    if planes.format == "nv12":
        u, v = planes.data[1][row + (x // 2) * 2], planes.data[1][row + (x // 2) * 2 + 1]
    else:
        u, v = planes.data[1][row + x // 2], planes.data[2][(y // 2) * planes.strides[2] + x // 2]
    return to_rgb(luma, u, v, planes.bt709, planes.full_range)


def test_video_source_delivers_full_size_yuv_planes(tmp_path):
    colors = [(250, 0, 0)] * 5 + [(0, 0, 250)] * 5
    src = media.open_media(make_video(tmp_path / "clip.mp4", colors), (32, 32), "fit")
    try:
        assert src.animated and src.size == (64, 32)  # the GPU scales video
        src.set_running(True)
        frame = wait_for(src.poll)
        assert isinstance(frame, media.Planes) and frame.format in ("yuv420p", "nv12")
        assert frame.size == (64, 32) and frame.strides[0] >= 64
        r, g, b = centre_rgb(frame)
        assert r > 0.8 and g < 0.2 and b < 0.2
        wait_for(lambda: (f := src.poll()) is not None and centre_rgb(f)[2] > 0.8)
    finally:
        src.close()


# -- YUV -> RGB ----------------------------------------------------------------------


def to_rgb(y, u, v, bt709=True, full_range=False):
    matrix, offset = media.yuv_matrix(bt709, full_range)
    m = np.array(matrix, dtype=float).reshape(3, 3).T  # GLSL mat3 is column-major
    return m @ (np.array([y, u, v]) / 255 - np.array(offset))


def test_limited_range_white_and_black():
    assert np.allclose(to_rgb(235, 128, 128), 1, atol=1e-3)
    assert np.allclose(to_rgb(16, 128, 128), 0, atol=1e-3)


def test_full_range_extremes():
    assert np.allclose(to_rgb(255, 128, 128, full_range=True), 1, atol=3e-3)
    assert np.allclose(to_rgb(0, 128, 128, full_range=True), 0, atol=3e-3)


def test_primaries_for_both_matrices():
    # Limited-range red: BT.709 (63, 102, 240), BT.601 (81, 90, 240).
    assert np.allclose(to_rgb(63, 102, 240, bt709=True), [1, 0, 0], atol=0.02)
    assert np.allclose(to_rgb(81, 90, 240, bt709=False), [1, 0, 0], atol=0.02)
