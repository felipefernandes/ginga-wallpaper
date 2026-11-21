"""Draw the wallpaper into one borderless window covering the whole desktop.

Each monitor gets its own GL viewport showing its view of the shared canvas.
The background (wave or media file, see background.py) decides how often to
draw: the wave every frame, a video when it has a new frame, a still image
only after something changed (layout, settings, resume).
The frame loop is built from small pure helpers (tested); `Renderer` is the
thin GLFW/moderngl wrapper around them.

Thread safety: `run()` must be called on the main thread (GLFW requirement).
`stop()`, `set_paused()` and `reload()` may be called from any thread (e.g. the
tray icon); they only set flags and wake the loop.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable

from ginga.config import Config
from ginga.layout import (
    Layout,
    Monitor,
    MonitorView,
    Rect,
    build_layout,
    desktop_bounds,
    gl_viewport,
)

log = logging.getLogger(__name__)

PAUSE_CHECK_INTERVAL = 0.5  # seconds between fullscreen/monitor checks
PAUSED_WAIT = 0.5           # max sleep while paused (stop/resume wake it earlier)

Viewport = tuple[int, int, int, int]


# --- pure frame-loop logic -------------------------------------------------


class FrameLimiter:
    """Fixed-rate frame scheduler that does not drift and never bursts."""

    def __init__(self, fps: int):
        self.fps = fps
        self._next: float | None = None

    @property
    def interval(self) -> float:
        return 1.0 / self.fps

    def delay(self, now: float) -> float:
        """Seconds to wait before the next frame may be drawn."""
        if self._next is None:
            return 0.0
        return max(0.0, self._next - now)

    def mark(self, now: float) -> None:
        """Record that a frame was drawn at `now`."""
        if self._next is None or now - self._next >= self.interval:
            self._next = now + self.interval  # first frame, or far behind: resync
        else:
            self._next += self.interval

    def reset(self) -> None:
        self._next = None


class AnimationClock:
    """Animation time that advances with real time but skips long gaps.

    While rendering is paused nothing ticks; on resume the gap counts as at most
    `max_step`, so the wave continues smoothly instead of jumping.
    """

    # Must exceed the longest frame interval (1 / MIN_FPS) or low FPS slows the wave.
    def __init__(self, max_step: float = 1.5):
        self.max_step = max_step
        self._time = 0.0
        self._last: float | None = None

    def tick(self, now: float, running: bool = True) -> float:
        """Advance to `now`; with `running=False` time holds (frozen frame)."""
        if self._last is not None and running:
            self._time += min(max(0.0, now - self._last), self.max_step)
        self._last = now
        return self._time


class Throttle:
    """`due()` is true at most once per `interval` seconds."""

    def __init__(self, interval: float):
        self.interval = interval
        self._last: float | None = None

    def due(self, now: float) -> bool:
        if self._last is not None and now - self._last < self.interval:
            return False
        self._last = now
        return True


AUDIO_FADE = 0.4      # seconds (time constant) to blend idle <-> audio-driven
AUDIBLE = 0.02        # features below this count as silence


def ease(current: float, target: float, dt: float, tau: float) -> float:
    """Frame-rate independent exponential approach of `target`."""
    return current + (target - current) * (1.0 - math.exp(-dt / tau))


def audio_target(enabled: bool, features) -> float:
    """1.0 when the wave should follow the audio, 0.0 for the idle animation."""
    audible = features.level > AUDIBLE or float(features.spectrum.max(initial=0.0)) > AUDIBLE
    return 1.0 if enabled and audible else 0.0


def plan_viewports(layout: Layout, desktop: Rect) -> list[tuple[Viewport, MonitorView]]:
    """GL viewport of each monitor inside a window covering `desktop`."""
    return [(gl_viewport(view.monitor, desktop), view) for view in layout.views]


# --- GLFW / GL wrapper -----------------------------------------------------


def glfw_monitors() -> list[Monitor]:
    """Connected monitors in desktop pixels (GLFW must be initialized)."""
    import glfw

    monitors = []
    for handle in glfw.get_monitors():
        x, y = glfw.get_monitor_pos(handle)
        mode = glfw.get_video_mode(handle)
        name = glfw.get_monitor_name(handle)
        if isinstance(name, bytes):
            name = name.decode(errors="replace")
        monitors.append(Monitor(name, x, y, mode.size.width, mode.size.height))
    return monitors


class Renderer:
    # Subclass hooks: an interactive renderer floats on top with keyboard focus.
    interactive = False
    audio_supported = True  # calibration turns this off

    @property
    def animating(self) -> bool:
        """False freezes the wave while frames keep drawing (e.g. overlays update)."""
        return True

    def _init_overlay(self) -> None:
        """Create extra GL resources (called once the context exists)."""

    def _draw_overlay(self, viewport: Viewport, view: MonitorView) -> None:
        """Draw on top of the wave for one monitor (its viewport is bound)."""

    def __init__(
        self,
        config: Config,
        pause_check: Callable[[], bool] | None = None,
        attach_to_desktop: bool = False,
    ):
        """`pause_check` overrides the default fullscreen detection (for tests/tools).

        With `attach_to_desktop` the window lives behind the desktop icons. If
        Explorer restarts, the window dies with it: `run()` returns with
        `desktop_lost` set so the caller can start a new Renderer.
        """
        self.config = config
        self.frames = 0  # frames drawn since start (diagnostics)
        self.hwnd = 0
        self.desktop_lost = False
        self._attach_to_desktop = attach_to_desktop
        self._attachment = None
        self._pause_check = pause_check or self._fullscreen_active
        self._limiter = FrameLimiter(config.render.fps)
        self._clock = AnimationClock()
        self._checks = Throttle(PAUSE_CHECK_INTERVAL)

        self._stop = False
        self._manual_pause = False
        self._auto_pause = False
        self._pending_config: Config | None = None
        self._layout_dirty = True

        self._window = None
        self._ctx = None
        self._background = None
        self._background_dirty = True
        self._repaint = 0          # frames still owed to a non-continuous background
        self._was_paused = False
        self._monitors: list[Monitor] = []
        self._layout: Layout | None = None
        self._plan: list[tuple[Viewport, MonitorView]] = []
        self._size = (0, 0)

        self._audio = None        # AudioCapture, created on first use
        self._audio_mix = 0.0
        self._last_draw: float | None = None

    # -- thread-safe controls -------------------------------------------------

    @property
    def paused(self) -> bool:
        return self._manual_pause or self._auto_pause

    def stop(self) -> None:
        self._stop = True
        self._wake()

    def set_paused(self, paused: bool) -> None:
        self._manual_pause = paused
        self._wake()

    def reload(self, config: Config) -> None:
        """Apply new settings (fps, wave, offsets) on the next loop iteration."""
        self._pending_config = config
        self._wake()

    def _wake(self) -> None:
        if self._window is not None:
            import glfw

            glfw.post_empty_event()

    # -- main loop --------------------------------------------------------------

    def run(self) -> None:
        import glfw

        self._setup()
        try:
            while not self._stop and not glfw.window_should_close(self._window):
                self._apply_pending()
                now = time.perf_counter()

                if self._checks.due(now):
                    self._periodic_checks()
                if self._layout_dirty:
                    self._apply_layout()
                if self._background_dirty:
                    self._apply_background()
                self._sync_audio()
                self._sync_playback()

                if self.paused:
                    glfw.wait_events_timeout(PAUSED_WAIT)
                    continue
                if not self._background.continuous and self._background.update():
                    self._repaint = max(self._repaint, 1)
                if not self._background.continuous and not self._repaint:
                    # Nothing changed on screen: sleep until the player posts a
                    # new frame (video/GIF) or something else wakes us.
                    glfw.wait_events_timeout(PAUSED_WAIT)
                    continue

                delay = self._limiter.delay(now)
                if delay > 0:
                    # time.sleep is high-resolution on Windows (3.11+), unlike
                    # glfw.wait_events_timeout which rounds to the ~15 ms tick.
                    time.sleep(delay)
                    continue

                self._draw(now)
                self._repaint = max(0, self._repaint - 1)
                self._limiter.mark(now)
                glfw.poll_events()
        finally:
            self._teardown()

    def _setup(self) -> None:
        import glfw
        import moderngl

        if not glfw.init():
            raise RuntimeError("Could not initialize GLFW")

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        glfw.window_hint(glfw.DECORATED, False)
        glfw.window_hint(glfw.RESIZABLE, False)
        glfw.window_hint(glfw.VISIBLE, False)
        # An interactive overlay (calibration) sits on top and takes the keyboard.
        glfw.window_hint(glfw.FLOATING, self.interactive)
        glfw.window_hint(glfw.FOCUS_ON_SHOW, self.interactive)
        glfw.window_hint(glfw.FOCUSED, self.interactive)
        glfw.window_hint(glfw.AUTO_ICONIFY, False)
        glfw.window_hint(glfw.SCALE_TO_MONITOR, False)

        self._window = glfw.create_window(64, 64, "ginga", None, None)
        if not self._window:
            glfw.terminate()
            raise RuntimeError("Could not create an OpenGL 3.3 window")

        glfw.make_context_current(self._window)
        glfw.swap_interval(0)  # we pace frames ourselves; vsync would lock to one monitor
        glfw.set_monitor_callback(self._on_monitor_change)
        glfw.set_key_callback(self._window, self._on_key)
        if hasattr(glfw, "get_win32_window"):
            self.hwnd = glfw.get_win32_window(self._window) or 0

        self._ctx = moderngl.create_context()
        self._init_overlay()
        if self._attach_to_desktop:
            from ginga.desktop import attach

            self._attachment = attach(self.hwnd)
        self._apply_layout()
        self._apply_background()
        glfw.show_window(self._window)
        if self.interactive:
            glfw.focus_window(self._window)
        log.info("Renderer started (OpenGL %s)", self._ctx.info.get("GL_VERSION"))

    def _teardown(self) -> None:
        import glfw

        if self._audio is not None:
            self._audio.stop()
        if self._background is not None:
            self._background.release()
            self._background = None

        if self._ctx is not None:
            self._ctx.release()
            self._ctx = None
        if self._window is not None:
            glfw.destroy_window(self._window)
            self._window = None
        glfw.terminate()

    # -- state updates (main thread) --------------------------------------------

    def _apply_pending(self) -> None:
        config, self._pending_config = self._pending_config, None
        if config is None:
            return
        if config.background != self.config.background:
            self._background_dirty = True
        self.config = config
        self._limiter.fps = config.render.fps
        self._limiter.reset()
        self._layout_dirty = True

    def _periodic_checks(self) -> None:
        if self._attachment is not None and not self._attachment.alive():
            log.warning("Desktop window was destroyed (Explorer restarted?)")
            self.desktop_lost = True
            self._stop = True
            return
        try:
            self._auto_pause = self._pause_check()
        except Exception:  # never let detection crash the wallpaper
            log.exception("Pause check failed")
            self._auto_pause = False
        # Resolution/arrangement changes do not fire the GLFW monitor callback.
        if glfw_monitors() != self._monitors:
            self._layout_dirty = True

    def _apply_layout(self) -> None:
        import glfw

        self._layout_dirty = False
        self._monitors = glfw_monitors()
        if not self._monitors:
            return
        desktop = desktop_bounds(self._monitors)
        self._layout = build_layout(self._monitors, self.config.offsets)
        self._plan = plan_viewports(self._layout, desktop)
        self._size = (desktop.width, desktop.height)
        self.place_window(desktop)
        if self._background is not None:
            self._background.set_canvas(self._canvas_size())
        self.request_repaint()
        log.info(
            "Layout: desktop %s, canvas %dx%d",
            desktop, self._layout.canvas_width, self._layout.canvas_height,
        )

    def _canvas_size(self) -> tuple[int, int]:
        if self._layout is None:
            return (1, 1)
        return (self._layout.canvas_width, self._layout.canvas_height)

    def _apply_background(self) -> None:
        from ginga.background import create_background

        self._background_dirty = False
        if self._background is not None:
            self._background.release()
        self._background = create_background(
            self._ctx, self.config.background, self._canvas_size(), wake=self._wake
        )
        self.request_repaint()

    def request_repaint(self) -> None:
        """Draw again even if the background has not changed (main thread).

        Two frames, so both swap-chain buffers hold the current image."""
        self._repaint = 2

    def _sync_playback(self) -> None:
        """Media plays only while the wallpaper is shown and not frozen."""
        playing = not self.paused and self.animating
        self._background.set_running(playing)
        if self._was_paused and not self.paused:
            self.request_repaint()
        self._was_paused = self.paused

    def place_window(self, desktop: Rect) -> None:
        """Move/resize the window over `desktop` (screen coordinates)."""
        import glfw

        if self._attachment is not None:
            self._attachment.place(desktop)
            return
        glfw.set_window_pos(self._window, desktop.x, desktop.y)
        glfw.set_window_size(self._window, desktop.width, desktop.height)

    def _sync_audio(self) -> None:
        """Capture audio only while it is wanted: enabled and actually drawing."""
        want = (
            self.audio_supported
            and self.config.audio.enabled
            and self._background.uses_audio
            and not self.paused
        )
        if want and (self._audio is None or not self._audio.running):
            if self._audio is None:
                from ginga.audio_capture import AudioCapture

                self._audio = AudioCapture()
            self._audio.start()
        elif not want and self._audio is not None and self._audio.running:
            self._audio.stop()
            self._audio_mix = 0.0

    def _audio_frame(self, now: float):
        """Audio uniforms for this frame, or None when the idle wave is shown."""
        from ginga.audio import AudioFeatures
        from ginga.wave import AudioUniforms

        dt = 0.0 if self._last_draw is None else min(now - self._last_draw, 0.25)
        self._last_draw = now
        features = self._audio.latest() if self._audio is not None else AudioFeatures.silent()
        features = features.scaled(self.config.audio.sensitivity)
        target = audio_target(self.config.audio.enabled, features)
        self._audio_mix = ease(self._audio_mix, target, dt, AUDIO_FADE)
        if self._audio_mix < 1e-3:
            return None
        return AudioUniforms(self._audio_mix, features.bass, features.level, features.spectrum)

    def _fullscreen_active(self) -> bool:
        from ginga.gamemode import foreground_window, should_pause

        if not self.config.render.pause_when_fullscreen:
            return False
        info = foreground_window()
        if info is not None and self.hwnd and info.hwnd == self.hwnd:
            return False  # our own window is never a "game"
        return should_pause(info, self._monitors)

    def _on_monitor_change(self, _monitor, _event) -> None:
        self._layout_dirty = True

    def _on_key(self, window, key, _scancode, action, _mods) -> None:
        import glfw

        if key == glfw.KEY_ESCAPE and action == glfw.PRESS:
            glfw.set_window_should_close(window, True)

    # -- drawing ----------------------------------------------------------------

    def _draw(self, now: float) -> None:
        import glfw

        t = self._clock.tick(now, running=self.animating)
        audio = self._audio_frame(now)
        ctx = self._ctx
        ctx.viewport = (0, 0, *self._size)
        ctx.clear(0.0, 0.0, 0.0)  # areas no monitor covers (mixed heights)
        for viewport, view in self._plan:
            ctx.viewport = viewport
            self._background.draw(self._layout, view, t, self.config, audio=audio)
            self._draw_overlay(viewport, view)
        glfw.swap_buffers(self._window)
        self.frames += 1
