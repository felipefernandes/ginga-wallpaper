"""What the Settings screen edits, as pure logic (the Tk UI is settings_ui.py).

Each slider is a `Field` bound to one config attribute. Edits always produce a
new Config, so previews never mutate the app's config behind its back.
Calibration offsets are not edited here (see App.update_settings).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from ginga.config import Config, Offset


@dataclass(frozen=True)
class Field:
    section: str   # "wave" or "render"
    name: str      # attribute inside the section
    label: str
    minimum: float
    maximum: float
    step: float
    hint: str = ""

    @property
    def key(self) -> str:
        return f"{self.section}.{self.name}"

    @property
    def is_int(self) -> bool:
        return self.section == "render" and self.name == "fps"


FIELDS: tuple[Field, ...] = (
    Field("wave", "speed", "Velocidade", 0.1, 3.0, 0.05, "Quão rápido a onda se move"),
    Field("wave", "amplitude", "Altura da onda", 0.2, 2.0, 0.05, "Quanto a onda sobe e desce"),
    Field("wave", "glow", "Brilho", 0.0, 3.0, 0.05, "Intensidade do brilho em volta da linha"),
    Field("wave", "spikes", "Textura de som", 0.0, 2.0, 0.05, "Os picos finos em volta da onda"),
    Field("render", "fps", "Quadros por segundo", 5, 144, 1, "Mais FPS = mais suave, mais uso de GPU"),
)


def field(key: str) -> Field:
    return next(f for f in FIELDS if f.key == key)


def get_value(config: Config, f: Field) -> float:
    return getattr(getattr(config, f.section), f.name)


def with_value(config: Config, f: Field, value: float) -> Config:
    """Copy of `config` with `f` set to `value`, clamped and snapped to the step."""
    value = min(max(float(value), f.minimum), f.maximum)
    value = f.minimum + round((value - f.minimum) / f.step) * f.step
    new = copy.deepcopy(config)
    setattr(getattr(new, f.section), f.name, int(round(value)) if f.is_int else round(value, 4))
    return new


def format_value(f: Field, value: float) -> str:
    return str(int(value)) if f.is_int else f"{value:.2f}"


def offsets_summary(offsets: dict[str, Offset]) -> str:
    adjusted = [
        f"Monitor {mid}: x {o.x:+d}, y {o.y:+d}"
        for mid, o in sorted(offsets.items())
        if o.x or o.y
    ]
    return "  ·  ".join(adjusted) or "Sem ajuste: monitores alinhados pelo Windows"
