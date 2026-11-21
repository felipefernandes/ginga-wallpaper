"""What the renderer draws behind the icons: the procedural wave or a media file.

Both backgrounds share one small interface so the frame loop does not care
which is active:

- `continuous`: redraw every frame (the wave); otherwise only when `update()`
  reports a new frame or the renderer asks for a repaint (still images cost
  nothing between repaints);
- `uses_audio`: whether "modo berimbau" capture is worth running;
- `set_canvas(size)` after layout changes, `set_running(bool)` on pause,
  `draw(...)` per monitor viewport, `release()`.

A media file that cannot be shown falls back to the wave (logged), never a crash.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import moderngl

from ginga import media
from ginga.config import BackgroundSettings, Config
from ginga.layout import Layout, MonitorView
from ginga.wave import AudioUniforms, WaveProgram, _QUAD, _shader

log = logging.getLogger(__name__)

REOPEN_RATIO = 1.1  # decode size off by more than 10%: decode again at the new size


def create_background(ctx: moderngl.Context, settings: BackgroundSettings, canvas: media.Size,
                      wake: Callable[[], None] | None = None):
    """`wake` (thread-safe) is called whenever an animated source has a new frame."""
    if settings.kind == "media" and settings.path:
        try:
            return MediaBackground(ctx, settings, canvas, wake)
        except media.MediaError as exc:
            log.warning("Cannot show %s (%s); using the wave", settings.path, exc)
    return WaveBackground(ctx, settings)


class WaveBackground:
    continuous = True
    animated = True
    uses_audio = True

    def __init__(self, ctx: moderngl.Context, settings: BackgroundSettings):
        self.settings = settings
        self._program = WaveProgram(ctx)

    def set_canvas(self, canvas: media.Size) -> None:
        pass

    def set_running(self, running: bool) -> None:
        pass

    def update(self) -> bool:
        return False

    def draw(self, layout: Layout, view: MonitorView, time: float, config: Config,
             audio: AudioUniforms | None = None) -> None:
        self._program.draw(layout, view, time, config.wave, audio=audio)

    def release(self) -> None:
        pass


class MediaBackground:
    continuous = False
    uses_audio = False

    def __init__(self, ctx: moderngl.Context, settings: BackgroundSettings, canvas: media.Size,
                 wake: Callable[[], None] | None = None):
        self.ctx = ctx
        self.settings = settings
        self.path = Path(settings.path)
        self._wake = wake  # thread-safe: wakes the frame loop when a frame is ready
        self.program = ctx.program(
            vertex_shader=_shader("wave.vert.glsl"),
            fragment_shader=_shader("image.frag.glsl"),
        )
        for unit, name in enumerate(("u_plane0", "u_plane1", "u_plane2")):
            if name in self.program:
                self.program[name].value = unit
        vbo = ctx.buffer(_QUAD.tobytes())
        self.vao = ctx.vertex_array(self.program, [(vbo, "2f", "in_pos")])
        self.source = None
        # Two texture sets, written alternately: uploading into the set the
        # previous frame still reads would stall the driver (4K video: 24 fps).
        self._textures: dict[tuple[int, int], moderngl.Texture] = {}
        self._shapes: dict[tuple[int, int], tuple] = {}
        self._shown = 0     # texture set the next draw samples
        self._writing = 0   # texture set uploads go to
        self._mode = 0
        self._running = False
        self._open(canvas)

    @property
    def animated(self) -> bool:
        return self.source.animated

    def _open(self, canvas: media.Size) -> None:
        source = media.open_media(self.path, canvas, self.settings.fit)
        self._close_source()
        self.source = source
        if source.animated:
            source.on_frame = self._wake
        self._mode = 0
        self._shown = self._writing = 0
        self._plane(0, (1, 1), 3, bytes(3))  # black until the first frame arrives
        source.set_running(self._running)
        log.info("Media wallpaper %s: %s, %dx%d, uploaded at %dx%d", self.path.name,
                 "animated" if source.animated else "still", *source.media_size, *source.size)

    def _close_source(self) -> None:
        if self.source is not None:
            self.source.close()
            self.source = None
        for texture in self._textures.values():
            texture.release()
        self._textures, self._shapes = {}, {}

    def _plane(self, index: int, size: media.Size, components: int, data: bytes) -> None:
        """Write one plane of the set being uploaded, (re)creating its texture
        when the frame shape changes."""
        key, shape = (self._writing, index), (size, components)
        if self._shapes.get(key) != shape:
            if key in self._textures:
                self._textures[key].release()
            texture = self.ctx.texture(size, components, alignment=1)
            texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
            texture.repeat_x = texture.repeat_y = False
            self._textures[key], self._shapes[key] = texture, shape
        self._textures[key].write(data)

    def _upload(self, frame) -> None:
        self._writing = 1 - self._shown
        self._write_planes(frame)
        self._shown = self._writing

    def _write_planes(self, frame) -> None:
        if not isinstance(frame, media.Planes):
            self._mode = 0
            self._plane(0, self.source.size, 3, frame)
            return
        w, h = frame.size
        cw, ch = (w + 1) // 2, (h + 1) // 2
        s0, s1 = frame.strides[0], frame.strides[1]
        self._plane(0, (s0, h), 1, frame.data[0][: s0 * h])
        if frame.format == "nv12":
            self._mode = 2
            self._plane(1, (s1 // 2, ch), 2, frame.data[1][: s1 * ch])
            chroma_scale = cw / (s1 // 2)
        else:
            self._mode = 1
            s2 = frame.strides[2]
            self._plane(1, (s1, ch), 1, frame.data[1][: s1 * ch])
            self._plane(2, (s2, ch), 1, frame.data[2][: s2 * ch])
            chroma_scale = cw / s1
        matrix, offset = media.yuv_matrix(frame.bt709, frame.full_range)
        self._set("u_luma_scale", (w / s0, 1.0))
        self._set("u_chroma_scale", (chroma_scale, 1.0))
        self._set("u_yuv", matrix)
        self._set("u_yuv_offset", offset)

    def _set(self, name: str, value) -> None:
        if name in self.program:
            self.program[name].value = value

    def set_canvas(self, canvas: media.Size) -> None:
        """Calibration nudges change the canvas by a few px: only re-decode when
        the needed resolution really changed (e.g. a monitor was added). Video
        is always uploaded at full size, so it never needs this."""
        if not self.source.canvas_sized:
            return
        wanted = media.decode_size(self.source.media_size, canvas, self.settings.fit)
        have = self.source.size
        ratios = (wanted[0] / have[0], wanted[1] / have[1])
        if any(r > REOPEN_RATIO or r < 1 / REOPEN_RATIO for r in ratios):
            try:
                self._open(canvas)
            except media.MediaError as exc:
                log.warning("Could not re-open %s: %s", self.path, exc)

    def set_running(self, running: bool) -> None:
        self._running = running
        self.source.set_running(running)

    def update(self) -> bool:
        """Upload a new frame if the source has one; True when something changed."""
        frame = self.source.poll()
        if frame is None:
            return False
        self._upload(frame)
        return True

    def draw(self, layout: Layout, view: MonitorView, time: float, config: Config,
             audio: AudioUniforms | None = None) -> None:
        rect = media.place(self.source.media_size, (layout.canvas_width, layout.canvas_height),
                           self.settings.fit)
        self._set("u_rect", tuple(float(v) for v in rect))
        self._set("u_origin", (view.canvas.x, view.canvas.y))
        self._set("u_resolution", (view.canvas.width, view.canvas.height))
        self._set("u_mode", self._mode)
        for unit in range(3):
            texture = self._textures.get((self._shown, unit))
            if texture is not None:
                texture.use(unit)
        self.vao.render(moderngl.TRIANGLE_STRIP)

    def release(self) -> None:
        self._close_source()
