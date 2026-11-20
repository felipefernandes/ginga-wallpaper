"""Load and save user settings as TOML.

Missing or invalid files never crash the app: we fall back to defaults.
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import tomli_w

log = logging.getLogger(__name__)

MIN_FPS, MAX_FPS = 1, 144


@dataclass
class RenderSettings:
    fps: int = 30
    pause_when_fullscreen: bool = True


@dataclass
class WaveSettings:
    speed: float = 1.0       # animation speed multiplier
    amplitude: float = 1.0   # wave height multiplier
    glow: float = 1.0        # glow intensity multiplier
    spikes: float = 1.0      # strength of the spiky "sound" texture


@dataclass
class Offset:
    x: int = 0
    y: int = 0


@dataclass
class Config:
    render: RenderSettings = field(default_factory=RenderSettings)
    wave: WaveSettings = field(default_factory=WaveSettings)
    # Calibration offset per monitor id (see layout.monitor_id).
    offsets: dict[str, Offset] = field(default_factory=dict)


def default_config_path() -> Path:
    base = os.environ.get("APPDATA") or Path.home() / ".config"
    return Path(base) / "ginga" / "config.toml"


def _fill(cls, data: object):
    """Build dataclass `cls` from a dict, keeping defaults and ignoring unknown keys."""
    obj = cls()
    if not isinstance(data, dict):
        return obj
    for f in fields(cls):
        if f.name not in data:
            continue
        value = data[f.name]
        default = getattr(obj, f.name)
        is_bool_mismatch = isinstance(value, bool) != isinstance(default, bool)
        numeric_ok = isinstance(default, float) and isinstance(value, int)
        if not is_bool_mismatch and (isinstance(value, type(default)) or numeric_ok):
            setattr(obj, f.name, type(default)(value))
        else:
            log.warning("Ignoring invalid value for %s.%s: %r", cls.__name__, f.name, value)
    return obj


def load_config(path: Path | None = None) -> Config:
    path = path or default_config_path()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("Could not read %s (%s); using defaults", path, exc)
        return Config()

    cfg = Config(
        render=_fill(RenderSettings, data.get("render")),
        wave=_fill(WaveSettings, data.get("wave")),
        offsets={
            str(key): _fill(Offset, value)
            for key, value in (data.get("offsets") or {}).items()
        },
    )
    cfg.render.fps = max(MIN_FPS, min(MAX_FPS, cfg.render.fps))
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(asdict(cfg)), encoding="utf-8")
