"""Supervise the renderers for the whole app lifetime.

`App.run()` owns the main thread (GLFW requires it) and runs one renderer at a
time: the desktop wallpaper, or the calibration overlay when requested. The
tray calls `request_*`, `toggle_pause` and `reload` from its own thread; those
only set state and stop/poke the current renderer, which are thread-safe.

Renderer factories, config I/O and sleep are injectable so the lifecycle is
tested with fakes.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

from ginga.config import Config, load_config, save_config

log = logging.getLogger(__name__)

RETRY_DELAY = 3.0         # seconds before recreating the wallpaper
MAX_START_FAILURES = 20   # ~1 min: covers Explorer still starting at logon


class RendererLike(Protocol):
    """What the supervisor needs from a renderer (real or fake)."""

    desktop_lost: bool
    result: str | None        # calibration only: "save" / "cancel"
    calibration: Any          # calibration only: ginga.calibrate.Calibration

    def run(self) -> None: ...
    def stop(self) -> None: ...
    def set_paused(self, paused: bool) -> None: ...
    def reload(self, config: Config) -> None: ...


def _wallpaper(config: Config) -> RendererLike:
    from ginga.renderer import Renderer

    return Renderer(config, attach_to_desktop=True)


def _calibration(config: Config) -> RendererLike:
    from ginga.calibrate import CalibrationRenderer

    return CalibrationRenderer(config)


class App:
    def __init__(
        self,
        config: Config,
        *,
        make_wallpaper: Callable[[Config], RendererLike] = _wallpaper,
        make_calibration: Callable[[Config], RendererLike] = _calibration,
        load: Callable[[], Config] = load_config,
        save: Callable[[Config], None] = save_config,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.paused = False
        self._make_wallpaper = make_wallpaper
        self._make_calibration = make_calibration
        self._load = load
        self._save = save
        self._sleep = sleep
        self._lock = threading.Lock()
        self._request: str | None = None
        self._current: RendererLike | None = None
        self._current_is_wallpaper = False

    # -- called from the tray thread ---------------------------------------------

    def request_quit(self) -> None:
        self._post("quit")

    def request_calibrate(self) -> None:
        with self._lock:
            if self._request == "quit" or not self._current_is_wallpaper:
                return  # already calibrating or quitting
        self._post("calibrate")

    def toggle_pause(self) -> None:
        with self._lock:
            self.paused = not self.paused
            if self._current_is_wallpaper and self._current is not None:
                self._current.set_paused(self.paused)

    def reload(self) -> None:
        config = self._load()
        with self._lock:
            self.config = config
            if self._current_is_wallpaper and self._current is not None:
                self._current.reload(config)
        log.info("Config reloaded")

    def _post(self, request: str) -> None:
        with self._lock:
            self._request = request
            if self._current is not None:
                self._current.stop()

    # -- main thread -------------------------------------------------------------------

    def run(self) -> None:
        failures = 0
        while True:
            with self._lock:
                request, self._request = self._request, None
            if request == "quit":
                return
            if request == "calibrate":
                self._calibrate()
                continue

            renderer = self._make_wallpaper(self.config)
            renderer.set_paused(self.paused)
            self._set_current(renderer, wallpaper=True)
            try:
                renderer.run()
            except Exception as exc:
                failures += 1
                log.warning("Wallpaper failed to start (%d/%d): %s", failures, MAX_START_FAILURES, exc)
                if failures >= MAX_START_FAILURES:
                    raise
                self._sleep(RETRY_DELAY)
                continue
            finally:
                self._set_current(None)
            failures = 0

            if renderer.desktop_lost:
                log.info("Desktop lost; recreating the wallpaper")
                self._sleep(RETRY_DELAY)
                continue
            with self._lock:
                if self._request is None:
                    log.info("Wallpaper window closed; exiting")
                    return

    def _calibrate(self) -> None:
        renderer = self._make_calibration(self.config)
        self._set_current(renderer, wallpaper=False)
        try:
            renderer.run()
        finally:
            self._set_current(None)
        if renderer.result == "save" and renderer.calibration is not None:
            self.config.offsets = dict(renderer.calibration.offsets)
            self._save(self.config)
            log.info("Calibration saved: %s", self.config.offsets)
        else:
            log.info("Calibration cancelled")

    def _set_current(self, renderer: RendererLike | None, wallpaper: bool = False) -> None:
        with self._lock:
            self._current = renderer
            self._current_is_wallpaper = wallpaper and renderer is not None
            pending = self._request is not None
        if renderer is not None and pending:
            renderer.stop()  # a request arrived while it was being created
