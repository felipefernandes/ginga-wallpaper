"""Capture what the PC is playing (WASAPI loopback) on a background thread.

The thread wakes ~30 times a second, drains whatever audio arrived from the
default output device (blocking reads made soundcard busy-poll: ~6% of a
core versus ~1% this way), runs it
through `SpectrumAnalyzer` and keeps only the latest `AudioFeatures`, which
the renderer reads once per frame. It follows changes of the default device
(headset <-> speakers) and retries after errors. `stop()` ends it so a paused
wallpaper costs nothing.

The device layer is injectable (`open_stream`, `default_device`) for tests;
by default it is the `soundcard` package.
"""

from __future__ import annotations

import logging
import threading
import time
import warnings
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from ginga.audio import AudioFeatures, SpectrumAnalyzer

log = logging.getLogger(__name__)

RATE = 48000
BLOCK = 1024           # WASAPI buffer size hint (~21 ms at 48 kHz)
POLL = 1 / 30          # seconds between drains of the capture buffer
RETRY_DELAY = 2.0      # seconds after a device error
DEVICE_CHECK = 2.0     # seconds between default-device checks


def _soundcard_default_device() -> str:
    import soundcard

    return str(soundcard.default_speaker().name)


def _soundcard_open(device: str, rate: int, block: int) -> AbstractContextManager[Any]:
    import soundcard

    # soundcard re-installs an "always" filter on import; silence its
    # "data discontinuity" warnings (raised whenever nothing is playing).
    warnings.filterwarnings("ignore", category=soundcard.SoundcardRuntimeWarning)

    mic = soundcard.get_microphone(id=device, include_loopback=True)
    return mic.recorder(samplerate=rate, channels=2, blocksize=block)


class AudioCapture:
    def __init__(
        self,
        open_stream: Callable[[str, int, int], AbstractContextManager[Any]] = _soundcard_open,
        default_device: Callable[[], str] = _soundcard_default_device,
        rate: int = RATE,
        block: int = BLOCK,
        retry_delay: float = RETRY_DELAY,
        device_check: float = DEVICE_CHECK,
        poll: float = POLL,
    ):
        self._open = open_stream
        self._default_device = default_device
        self.rate, self.block = rate, block
        self._retry_delay = retry_delay
        self._device_check = device_check
        self._poll = poll
        self._lock = threading.Lock()
        self._latest = AudioFeatures.silent()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def latest(self) -> AudioFeatures:
        with self._lock:
            return self._latest

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._publish(AudioFeatures.silent())

    def _publish(self, features: AudioFeatures) -> None:
        with self._lock:
            self._latest = features

    def _run(self) -> None:
        analyzer = SpectrumAnalyzer(self.rate)  # fresh auto-gain per session
        while not self._stop.is_set():
            try:
                device = self._default_device()
                with self._open(device, self.rate, self.block) as stream:
                    log.info("Audio capture started on %s", device)
                    self._capture(stream, device, analyzer)
            except Exception as exc:
                log.warning("Audio capture error (%s); retrying", exc)
                self._publish(AudioFeatures.silent())
                self._stop.wait(self._retry_delay)

    def _capture(self, stream, device: str, analyzer: SpectrumAnalyzer) -> None:
        last_check = time.monotonic()
        while not self._stop.wait(self._poll):
            # numframes=None: whatever arrived since the last drain (maybe none
            # when nothing plays; the analyzer then reports silence).
            self._publish(analyzer.process(stream.record(numframes=None)))
            if time.monotonic() - last_check >= self._device_check:
                last_check = time.monotonic()
                if self._default_device() != device:
                    log.info("Default audio device changed; reopening")
                    return
