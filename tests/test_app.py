"""App supervisor: renderer lifecycle driven by tray requests (fake renderers)."""

import pytest

from ginga.app import MAX_START_FAILURES, App
from ginga.calibrate import Calibration
from ginga.config import Config, Offset


class FakeRenderer:
    def __init__(self, config, script):
        self.config = config
        self.script = script
        self.paused = None
        self.reloaded = None
        self.stopped = False
        self.desktop_lost = False
        self.result = None
        self.calibration = None

    def run(self):
        if not self.stopped:  # a stop() before run() ends it immediately
            self.script(self)

    def stop(self):
        self.stopped = True

    def set_paused(self, paused):
        self.paused = paused

    def reload(self, config):
        self.reloaded = config


class Harness:
    """Builds an App whose renderers follow scripted behaviours, in order."""

    def __init__(self, wallpaper_scripts, calibration_scripts=()):
        self.wall_scripts = list(wallpaper_scripts)
        self.cal_scripts = list(calibration_scripts)
        self.walls, self.cals, self.sleeps, self.saved = [], [], [], []
        self.app = App(
            Config(),
            make_wallpaper=self._wall,
            make_calibration=self._cal,
            save=lambda cfg: self.saved.append(cfg),
            load=lambda: Config(offsets={"2": Offset(0, 7)}),
            sleep=self.sleeps.append,
        )

    def _wall(self, config):
        r = FakeRenderer(config, self.wall_scripts.pop(0))
        self.walls.append(r)
        return r

    def _cal(self, config):
        r = FakeRenderer(config, self.cal_scripts.pop(0))
        self.cals.append(r)
        return r


def test_quit_stops_the_running_wallpaper_and_returns():
    h = Harness([lambda r: h.app.request_quit()])
    h.app.run()
    assert len(h.walls) == 1 and h.walls[0].stopped


def test_calibrate_swaps_renderers_and_saves_offsets():
    def calibrate_and_save(cal):
        cal.calibration = Calibration(["1", "2"], {})
        cal.calibration.handle("up", shift=True)
        cal.result = "save"

    h = Harness(
        [lambda r: h.app.request_calibrate(), lambda r: h.app.request_quit()],
        [calibrate_and_save],
    )
    h.app.run()

    assert h.walls[0].stopped and len(h.cals) == 1
    assert h.saved[0].offsets["2"] == Offset(0, 10)
    # The wallpaper comes back with the new offsets.
    assert h.walls[1].config.offsets["2"] == Offset(0, 10)


def test_cancelled_calibration_saves_nothing():
    def cancel(cal):
        cal.calibration = Calibration(["1", "2"], {})
        cal.calibration.handle("up")
        cal.result = "cancel"

    h = Harness([lambda r: h.app.request_calibrate(), lambda r: h.app.request_quit()], [cancel])
    h.app.run()
    assert h.saved == [] and h.walls[1].config.offsets == {}


def test_quit_during_calibration_does_not_restart_wallpaper():
    h = Harness([lambda r: h.app.request_calibrate()], [lambda cal: h.app.request_quit()])
    h.app.run()
    assert len(h.walls) == 1 and h.cals[0].stopped


def test_explorer_restart_recreates_the_wallpaper():
    def lose_desktop(r):
        r.desktop_lost = True

    h = Harness([lose_desktop, lambda r: h.app.request_quit()])
    h.app.run()
    assert len(h.walls) == 2 and len(h.sleeps) == 1


def test_start_failures_are_retried_until_desktop_is_ready():
    def fail(r):
        raise RuntimeError("Progman not found")

    h = Harness([fail, fail, lambda r: h.app.request_quit()])
    h.app.run()
    assert len(h.walls) == 3 and len(h.sleeps) == 2


def test_gives_up_after_too_many_consecutive_failures():
    def fail(r):
        raise RuntimeError("no OpenGL")

    h = Harness([fail] * MAX_START_FAILURES)
    with pytest.raises(RuntimeError):
        h.app.run()


def test_window_closing_by_itself_ends_the_app():
    h = Harness([lambda r: None])
    h.app.run()
    assert len(h.walls) == 1


def test_pause_applies_now_and_survives_renderer_restarts():
    def pause_then_lose(r):
        h.app.toggle_pause()
        r.desktop_lost = True

    h = Harness([pause_then_lose, lambda r: h.app.request_quit()])
    h.app.run()
    assert h.walls[0].paused is True
    assert h.walls[1].paused is True  # restored on the recreated renderer
    assert h.app.paused


def test_reload_reads_config_and_updates_the_wallpaper():
    def reload(r):
        h.app.reload()
        h.app.request_quit()

    h = Harness([reload])
    h.app.run()
    assert h.walls[0].reloaded.offsets["2"] == Offset(0, 7)
    assert h.app.config.offsets["2"] == Offset(0, 7)


def test_reload_during_calibration_does_not_touch_the_calibration():
    def reload_then_cancel(cal):
        h.app.reload()
        cal.result = "cancel"

    h = Harness([lambda r: h.app.request_calibrate(), lambda r: h.app.request_quit()], [reload_then_cancel])
    h.app.run()
    assert h.cals[0].reloaded is None
    assert h.walls[1].config.offsets["2"] == Offset(0, 7)  # applied once wallpaper returns
