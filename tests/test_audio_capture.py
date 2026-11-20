"""Audio capture thread, with a fake sound device."""

import contextlib
import time

import numpy as np

from ginga.audio_capture import AudioCapture

RATE, BLOCK = 48000, 1024


def wait_for(condition, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


class FakeDevice:
    """Plays a 60 Hz tone; can fail to open and switch default device."""

    def __init__(self, fail_first=0):
        self.fail_first = fail_first
        self.opened = []
        self.default = "headset"
        self._phase = 0

    def default_device(self):
        return self.default

    @contextlib.contextmanager
    def open(self, device, rate, block):
        if self.fail_first:
            self.fail_first -= 1
            raise RuntimeError("device busy")
        self.opened.append(device)
        yield self

    def record(self, numframes):
        time.sleep(0.002)  # real recording blocks for the block's duration
        t = (self._phase + np.arange(numframes)) / RATE
        self._phase += numframes
        return (0.5 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)


def make(device, **kw):
    return AudioCapture(
        open_stream=device.open, default_device=device.default_device,
        rate=RATE, block=BLOCK, retry_delay=0.01, device_check=0.05, **kw,
    )


def test_latest_is_silent_before_start():
    assert make(FakeDevice()).latest().level == 0


def test_captures_until_stopped():
    cap = make(FakeDevice())
    cap.start()
    try:
        assert wait_for(lambda: cap.latest().bass > 0.5)
    finally:
        cap.stop()
    assert not cap.running
    assert cap.latest().bass == 0  # stopped capture reads as silence


def test_open_failures_are_retried():
    device = FakeDevice(fail_first=2)
    cap = make(device)
    cap.start()
    try:
        assert wait_for(lambda: device.opened == ["headset"])
    finally:
        cap.stop()


def test_reopens_when_the_default_device_changes():
    device = FakeDevice()
    cap = make(device)
    cap.start()
    try:
        assert wait_for(lambda: device.opened == ["headset"])
        device.default = "speakers"
        assert wait_for(lambda: device.opened == ["headset", "speakers"])
    finally:
        cap.stop()


def test_start_is_idempotent_and_restartable():
    device = FakeDevice()
    cap = make(device)
    cap.start()
    cap.start()
    assert wait_for(lambda: len(device.opened) == 1)
    cap.stop()
    cap.start()
    try:
        assert wait_for(lambda: len(device.opened) == 2)
    finally:
        cap.stop()
