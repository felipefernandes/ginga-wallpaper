"""Media wallpaper: an image, GIF or video spanning the whole canvas.

The file is placed on the virtual canvas (see layout.py), so with calibration
offsets one picture stays continuous across physically misaligned monitors.
Here is the pure placement math plus the frame sources; drawing is in
media_gl.py.

Images and GIFs deliver RGB frames (rows top first) already scaled down to
what the canvas needs, so huge files never reach the GPU at full size; video
delivers YUV `Planes` at full size (the GPU converts and scales them):

- still image: one frame, then nothing, so the renderer can stop drawing;
- GIF / animated WebP / APNG, and video: a player thread that publishes the
  latest frame on time and loops. `set_running(False)` parks the thread, so a
  paused wallpaper (game in fullscreen) costs nothing.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

Size = tuple[int, int]
Frames = Iterator[tuple["bytes | Planes", float]]  # (RGB bytes or YUV planes, seconds)

VIDEO_EXTENSIONS = frozenset({".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".wmv"})
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"})

GIF_CACHE_BYTES = 256 * 2**20  # keep decoded animation frames up to this much
MIN_FRAME_SECONDS = 0.02       # browsers treat 0-10 ms GIF delays as "default"
DEFAULT_FRAME_SECONDS = 0.1
RESYNC_AFTER = 0.25            # fell this far behind: drop the schedule, don't burst


class MediaError(Exception):
    """The file cannot be shown (missing, unreadable, unsupported)."""


# -- placement ------------------------------------------------------------------------


def place(media: Size, canvas: Size, fit: str) -> tuple[float, float, float, float]:
    """Rectangle (x, y, w, h) in canvas pixels where the media is drawn."""
    mw, mh = media
    cw, ch = canvas
    if fit == "stretch":
        return (0, 0, cw, ch)
    scale = (max if fit == "fill" else min)(cw / mw, ch / mh)
    w, h = mw * scale, mh * scale
    return ((cw - w) / 2, (ch - h) / 2, w, h)


def decode_size(media: Size, canvas: Size, fit: str) -> Size:
    """Pixel size worth decoding: the drawn size, but never above the original."""
    mw, mh = media
    if fit == "stretch":
        return (min(mw, canvas[0]), min(mh, canvas[1]))
    _x, _y, w, _h = place(media, canvas, fit)
    scale = min(1.0, w / mw)
    return (max(1, round(mw * scale)), max(1, round(mh * scale)))


# -- kinds ----------------------------------------------------------------------------


def media_kind(path: Path) -> str:
    """"image", "animation" (multi-frame image) or "video"."""
    path = Path(path)
    if path.suffix.lower() in VIDEO_EXTENSIONS:
        return "video"
    from PIL import Image

    try:
        with Image.open(path) as img:
            animated = getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1
    except (OSError, ValueError) as exc:
        raise MediaError(f"{path}: {exc}") from exc
    return "animation" if animated else "image"


def open_media(path: Path, canvas: Size, fit: str):
    """The right source for `path`, decoding at the size `canvas` needs."""
    path = Path(path)
    if not path.is_file():
        raise MediaError(f"{path}: file not found")
    kind = media_kind(path)
    if kind == "video":
        return _open_video(path, canvas, fit)
    from PIL import Image

    try:
        with Image.open(path) as img:
            media = _oriented_size(img) if kind == "image" else img.size
    except (OSError, ValueError) as exc:
        raise MediaError(f"{path}: {exc}") from exc
    size = decode_size(media, canvas, fit)
    if kind == "image":
        return StillSource(path, media, size)
    return Player(_animation_frames(path, size), media, size, name="gif")


# -- frames ---------------------------------------------------------------------------


def _oriented_size(img) -> Size:
    """Size after applying the EXIF orientation (phone photos)."""
    orientation = img.getexif().get(0x0112, 1)
    w, h = img.size
    return (h, w) if orientation in (5, 6, 7, 8) else (w, h)


def _to_rgb(img, size: Size) -> bytes:
    """RGB bytes at `size`, transparency flattened onto black."""
    from PIL import Image

    img = img.convert("RGBA")
    if img.size != size:
        img = img.resize(size, Image.Resampling.LANCZOS)
    black = Image.new("RGBA", size, (0, 0, 0, 255))
    return Image.alpha_composite(black, img).convert("RGB").tobytes()


class StillSource:
    animated = False
    canvas_sized = True  # decoded for the canvas: re-open when it grows a lot

    def __init__(self, path: Path, media: Size, size: Size):
        from PIL import Image, ImageOps

        self.media_size, self.size = media, size
        try:
            with Image.open(path) as img:
                self._frame: bytes | None = _to_rgb(ImageOps.exif_transpose(img), size)
        except (OSError, ValueError) as exc:
            raise MediaError(f"{path}: {exc}") from exc

    def poll(self) -> bytes | None:
        frame, self._frame = self._frame, None
        return frame

    def set_running(self, running: bool) -> None:
        pass

    def close(self) -> None:
        self._frame = None


def _animation_frames(path: Path, size: Size) -> Callable[[], Frames]:
    """Frame iterator factory; after one full pass that fits the budget, frames
    replay from memory instead of being decoded and scaled again."""
    cache: list[tuple[bytes, float]] = []
    complete = False

    def frames() -> Frames:
        nonlocal complete
        if complete:
            yield from cache
            return
        from PIL import Image, ImageSequence

        cache.clear()
        caching, used = True, 0
        with Image.open(path) as img:
            for frame in ImageSequence.Iterator(img):
                ms = frame.info.get("duration") or 0
                seconds = ms / 1000 if ms / 1000 >= MIN_FRAME_SECONDS else DEFAULT_FRAME_SECONDS
                data = _to_rgb(frame, size)
                if caching:
                    used += len(data)
                    if used > GIF_CACHE_BYTES:
                        caching = False
                        cache.clear()
                    else:
                        cache.append((data, seconds))
                yield data, seconds
        complete = caching and bool(cache)

    return frames


@dataclass(frozen=True)
class Planes:
    """A decoded video frame left in YUV: the GPU converts it (see image.frag.glsl).

    Converting to RGB on the CPU cost more than decoding itself.
    `format` is "yuv420p" (Y, U, V planes) or "nv12" (Y, interleaved UV);
    `strides` are bytes per row, which may exceed the visible width. `data`
    views the decoder's own buffers (no copy); `owner` keeps them alive.
    """

    format: str
    data: tuple[bytes | memoryview, ...]
    strides: tuple[int, ...]
    size: Size  # luma width, height
    bt709: bool
    full_range: bool
    owner: object = None


def yuv_matrix(bt709: bool, full_range: bool) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """(mat3 column-major, offset) with rgb = mat3 * (yuv - offset), yuv in 0..1."""
    kr, kb = (0.2126, 0.0722) if bt709 else (0.299, 0.114)
    kg = 1 - kr - kb
    if full_range:
        ys, cs, y0 = 1.0, 1.0, 0.0
    else:
        ys, cs, y0 = 255 / 219, 255 / 224, 16 / 255
    rv = 2 * (1 - kr)
    bu = 2 * (1 - kb)
    gu = -bu * kb / kg
    gv = -rv * kr / kg
    rows = ((ys, 0.0, rv * cs), (ys, gu * cs, gv * cs), (ys, bu * cs, 0.0))
    columns = tuple(rows[r][c] for c in range(3) for r in range(3))
    return columns, (y0, 128 / 255, 128 / 255)


PLANAR_FORMATS = {"yuv420p": ("yuv420p", False), "yuvj420p": ("yuv420p", True), "nv12": ("nv12", None)}


def _planes(frame) -> Planes:
    name = frame.format.name
    if name not in PLANAR_FORMATS:
        frame = frame.reformat(format="yuv420p")  # 10-bit, 4:4:4...: rare, costs a conversion
        name = "yuv420p"
    fmt, forced_full = PLANAR_FORMATS[name]
    full = forced_full if forced_full is not None else int(frame.color_range or 0) == 2
    colorspace = int(frame.colorspace or 2)  # 1 = BT.709, 5/6 = BT.601, 2 = unspecified
    bt709 = colorspace == 1 or (colorspace == 2 and frame.height >= 720)
    return Planes(
        format=fmt,
        data=tuple(memoryview(p).cast("B") for p in frame.planes),
        strides=tuple(p.line_size for p in frame.planes),
        size=(frame.width, frame.height),
        bt709=bt709,
        full_range=full,
        owner=frame,
    )


def _open_container(av, path: Path):
    """Prefer NVIDIA hardware decoding (a third of the CPU); fall back to software."""
    try:
        from av.codec.hwaccel import HWAccel

        return av.open(str(path), hwaccel=HWAccel("cuda", allow_software_fallback=True))
    except Exception:  # no CUDA, old PyAV, driver issue...
        return av.open(str(path))


def _open_video(path: Path, canvas: Size, fit: str) -> Player:
    try:
        import av
    except ImportError as exc:
        raise MediaError("video support (PyAV) is not installed") from exc
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            media = (stream.codec_context.width, stream.codec_context.height)
            rate = stream.average_rate or stream.guessed_rate or 30
    except (av.FFmpegError, IndexError, OSError) as exc:
        raise MediaError(f"{path}: {exc}") from exc
    if not media[0] or not media[1]:
        raise MediaError(f"{path}: video has no size")
    seconds = 1.0 / float(rate)

    def frames() -> Frames:
        with _open_container(av, path) as container:
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"  # used only by the software fallback
            log.info("Video decoding: %s",
                     "NVIDIA (CUDA)" if getattr(stream.codec_context, "is_hwaccel", False) else "software")
            while True:
                shown = 0
                for frame in container.decode(stream):
                    shown += 1
                    yield _planes(frame), seconds
                if not shown:
                    return
                try:
                    container.seek(0)  # loop in place: re-opening re-initialises CUDA
                except av.FFmpegError:
                    return  # not seekable: the player opens it again

    # Full size: the GPU scales while sampling, which is cheaper than swscale.
    return Player(frames, media, media, name="video", canvas_sized=False)


class Player:
    """Plays a looping frame iterator on a background thread.

    Thread safety: `poll`, `set_running` and `close` may be called from any
    thread; the decoding happens only on the player thread.
    """

    animated = True

    def __init__(self, frames: Callable[[], Frames], media: Size, size: Size, name: str,
                 canvas_sized: bool = True):
        self.media_size, self.size = media, size
        self.canvas_sized = canvas_sized
        self._frames = frames
        self._lock = threading.Lock()
        self._latest = None
        self._running = threading.Event()
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=f"ginga-{name}", daemon=True)
        self._started = False
        self.on_frame: Callable[[], None] | None = None  # called on the player thread

    def poll(self):
        """The newest frame (bytes or Planes) since the last call, or None."""
        with self._lock:
            frame, self._latest = self._latest, None
        return frame

    def set_running(self, running: bool) -> None:
        if running:
            if not self._started:
                self._started = True
                self._thread.start()
            self._running.set()
        else:
            self._running.clear()

    def close(self) -> None:
        self._closed.set()
        self._running.set()  # release a parked thread so it can exit
        if self._started:
            self._thread.join(timeout=2)

    # -- player thread ----------------------------------------------------------------

    def _park(self) -> bool:
        """Block while paused; False once closed."""
        while not self._running.is_set():
            self._running.wait(0.5)
        return not self._closed.is_set()

    def _loop(self) -> None:
        try:
            deadline: float | None = None
            while self._park():
                shown = 0
                for data, seconds in self._frames():
                    if not self._park():
                        return
                    with self._lock:
                        self._latest = data
                    if self.on_frame is not None:
                        self.on_frame()
                    shown += 1
                    now = time.monotonic()
                    if deadline is None or now - deadline > RESYNC_AFTER:
                        deadline = now  # first frame, or resumed after a pause
                    deadline += seconds
                    if self._closed.wait(max(0.0, deadline - time.monotonic())):
                        return
                if shown == 0:
                    raise MediaError("no frames")
        except Exception:
            log.exception("Media playback stopped")
