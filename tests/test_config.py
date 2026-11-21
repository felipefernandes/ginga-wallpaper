from pathlib import Path

import pytest

from ginga.config import Config, Offset, load_config, save_config


def test_load_missing_file_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")

    assert cfg == Config()
    assert cfg.render.fps == 30
    assert cfg.render.pause_when_fullscreen is True
    assert cfg.offsets == {}


def test_save_then_load_roundtrip(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg = Config()
    cfg.render.fps = 24
    cfg.wave.speed = 1.5
    cfg.offsets["2"] = Offset(x=0, y=120)

    save_config(cfg, path)

    assert load_config(path) == cfg


def test_partial_file_keeps_defaults_for_missing_keys(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[render]\nfps = 60\n", encoding="utf-8")

    cfg = load_config(path)

    assert cfg.render.fps == 60
    assert cfg.render.pause_when_fullscreen is True
    assert cfg.wave == Config().wave


def test_unknown_keys_are_ignored(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[render]\nfps = 20\nbogus = 1\n[extra]\na = 1\n", encoding="utf-8")

    assert load_config(path).render.fps == 20


@pytest.mark.parametrize("fps, expected", [(0, 1), (-5, 1), (500, 144), (45, 45)])
def test_fps_is_clamped(tmp_path: Path, fps: int, expected: int):
    path = tmp_path / "config.toml"
    path.write_text(f"[render]\nfps = {fps}\n", encoding="utf-8")

    assert load_config(path).render.fps == expected


def test_invalid_toml_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("this is [not toml", encoding="utf-8")

    assert load_config(path) == Config()


def test_save_creates_parent_dirs(tmp_path: Path):
    path = tmp_path / "a" / "b" / "config.toml"

    save_config(Config(), path)

    assert path.exists()


def test_wrong_types_are_ignored(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[render]\nfps = true\npause_when_fullscreen = "yes"\n[wave]\nspeed = 2\n',
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.render.fps == 30
    assert cfg.render.pause_when_fullscreen is True
    assert cfg.wave.speed == 2.0


def test_audio_is_off_by_default_and_round_trips(tmp_path: Path):
    from ginga.config import AudioSettings

    path = tmp_path / "config.toml"
    assert load_config(path).audio == AudioSettings(enabled=False, sensitivity=1.0)
    cfg = load_config(path)
    cfg.audio.enabled = True
    cfg.audio.sensitivity = 1.8
    save_config(cfg, path)
    assert load_config(path).audio == AudioSettings(enabled=True, sensitivity=1.8)


def test_invalid_audio_values_fall_back(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[audio]\nenabled = "yes"\nsensitivity = 2\n', encoding="utf-8")
    cfg = load_config(path)
    assert cfg.audio.enabled is False and cfg.audio.sensitivity == 2.0


def test_background_defaults_to_the_wave(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")

    assert cfg.background.kind == "wave"
    assert cfg.background.path == ""
    assert cfg.background.fit == "fill"


def test_background_roundtrip(tmp_path: Path):
    path = tmp_path / "config.toml"
    cfg = Config()
    cfg.background.kind = "media"
    cfg.background.path = r"C:\Users\me\Pictures\big.jpg"
    cfg.background.fit = "fit"

    save_config(cfg, path)

    assert load_config(path).background == cfg.background


def test_unknown_background_choices_fall_back_to_defaults(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text('[background]\nkind = "plasma"\nfit = "zoom"\npath = "x.png"\n', encoding="utf-8")

    cfg = load_config(path)

    assert cfg.background.kind == "wave"
    assert cfg.background.fit == "fill"
    assert cfg.background.path == "x.png"
