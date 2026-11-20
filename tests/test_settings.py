"""Settings screen model (pure) and how the App applies settings."""

import dataclasses

from ginga.config import Config, Offset, WaveSettings
from ginga.settings import FIELDS, field, format_value, get_value, offsets_summary, with_value


def test_every_field_maps_to_a_real_config_attribute():
    cfg = Config()
    for f in FIELDS:
        assert get_value(cfg, f) == getattr(getattr(cfg, f.section), f.name)
        assert f.minimum <= get_value(cfg, f) <= f.maximum  # defaults fit the slider


def test_with_value_returns_a_copy_and_leaves_original_untouched():
    cfg = Config()
    new = with_value(cfg, field("wave.speed"), 2.0)
    assert new.wave.speed == 2.0 and cfg.wave.speed == 1.0


def test_values_are_clamped_and_snapped_to_the_slider_step():
    speed = field("wave.speed")
    assert with_value(Config(), speed, 99).wave.speed == speed.maximum
    assert with_value(Config(), speed, -1).wave.speed == speed.minimum
    assert with_value(Config(), speed, 1.234).wave.speed == 1.25


def test_fps_stays_an_int():
    fps = with_value(Config(), field("render.fps"), 59.7).render.fps
    assert fps == 60 and isinstance(fps, int)


def test_format_value():
    assert format_value(field("render.fps"), 60) == "60"
    assert format_value(field("wave.glow"), 1.5) == "1.50"


def test_offsets_summary():
    assert offsets_summary({}) == "Sem ajuste: monitores alinhados pelo Windows"
    cfg = {"2": Offset(0, 130), "1": Offset(0, 0)}
    assert offsets_summary(cfg) == "Monitor 2: x +0, y +130"


# --- App integration (fake renderer from test_app) ---------------------------------

from test_app import Harness  # noqa: E402  (pytest puts tests/ on sys.path)


def _tweaked(**wave):
    return dataclasses.replace(Config(), wave=WaveSettings(**wave))


def test_preview_updates_running_wallpaper_without_saving():
    def preview(r):
        h.app.update_settings(_tweaked(speed=2.0), persist=False)
        h.app.request_quit()

    h = Harness([preview])
    h.app.run()
    assert h.walls[0].reloaded.wave.speed == 2.0
    assert h.saved == []


def test_settings_never_overwrite_calibration_offsets():
    def save_settings(r):
        h.app.config.offsets = {"2": Offset(0, 130)}  # e.g. just calibrated
        stale = _tweaked(speed=2.0)                   # settings window copy, no offsets
        h.app.update_settings(stale, persist=True)
        h.app.request_quit()

    h = Harness([save_settings])
    h.app.run()
    assert h.saved[0].wave.speed == 2.0
    assert h.saved[0].offsets == {"2": Offset(0, 130)}


def test_saving_calibration_does_not_persist_unsaved_previews():
    def preview_then_calibrate(r):
        h.app.update_settings(_tweaked(speed=2.5), persist=False)
        h.app.request_calibrate()

    def save(cal):
        from ginga.calibrate import Calibration

        cal.calibration = Calibration(["1", "2"], {})
        cal.calibration.handle("up")
        cal.result = "save"

    h = Harness([preview_then_calibrate, lambda r: h.app.request_quit()], [save])
    h.app.run()
    # Harness.load returns the file's config: speed 1.0, offsets {"2": (0, 7)}.
    assert h.saved[0].wave.speed == 1.0
    assert h.saved[0].offsets["2"] == Offset(0, 1)
    assert h.app.config.wave.speed == 2.5  # preview still live
