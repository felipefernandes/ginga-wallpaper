"""What the Settings screen edits, as pure logic (the Tk UI is settings_ui.py).

Each slider is a `Field` bound to one config attribute. Edits always produce a
new Config, so previews never mutate the app's config behind its back.
Calibration offsets are not edited here (see App.update_settings).
"""

from __future__ import annotations

import copy
from pathlib import Path
from dataclasses import dataclass

from ginga.config import Config, Offset


@dataclass(frozen=True)
class Field:
    section: str   # "wave", "audio" or "render"
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
    Field("audio", "sensitivity", "Sensibilidade", 0.3, 3.0, 0.05, "Quanto a onda reage ao som"),
    Field("render", "fps", "Quadros por segundo", 5, 144, 1, "Mais FPS = mais suave, mais uso de GPU"),
)


@dataclass(frozen=True)
class Toggle:
    section: str
    name: str
    label: str
    before_sliders: bool = False  # e.g. the switch that enables its section

    @property
    def key(self) -> str:
        return f"{self.section}.{self.name}"


TOGGLES: tuple[Toggle, ...] = (
    Toggle("audio", "enabled", "Reagir ao som do PC (música, vídeos, jogos)", before_sliders=True),
    Toggle("render", "pause_when_fullscreen", "Pausar quando um jogo ou vídeo estiver em tela cheia"),
)


def get_toggle(config: Config, t: Toggle) -> bool:
    return bool(getattr(getattr(config, t.section), t.name))


def with_toggle(config: Config, t: Toggle, value: bool) -> Config:
    new = copy.deepcopy(config)
    setattr(getattr(new, t.section), t.name, bool(value))
    return new


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


# -- background -------------------------------------------------------------------------

FIT_LABELS: tuple[tuple[str, str], ...] = (
    ("fill", "Preencher (corta as bordas)"),
    ("fit", "Ajustar (mostra tudo)"),
    ("stretch", "Esticar"),
)

MEDIA_FILETYPES = (
    ("Imagens, GIFs e vídeos",
     "*.jpg *.jpeg *.png *.bmp *.webp *.gif *.tif *.tiff *.mp4 *.m4v *.mkv *.webm *.mov *.avi *.wmv"),
    ("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff"),
    ("GIFs", "*.gif"),
    ("Vídeos", "*.mp4 *.m4v *.mkv *.webm *.mov *.avi *.wmv"),
    ("Todos os arquivos", "*.*"),
)


def with_background(
    config: Config, kind: str | None = None, path: str | None = None, fit: str | None = None,
) -> Config:
    """Copy of `config` with the background changed; picking a file selects it."""
    new = copy.deepcopy(config)
    bg = new.background
    if path is not None:
        bg.path = path
        bg.kind = "media"
    if kind is not None:
        bg.kind = kind
    if fit is not None:
        bg.fit = fit
    return new


def media_problem(path: str) -> str | None:
    """Why `path` cannot be the wallpaper (PT-BR, for the Settings window), or None."""
    from ginga import media

    if not path:
        return "Nenhum arquivo escolhido."
    try:
        source = media.open_media(Path(path), (64, 64), "fill")
    except media.MediaError:
        return "Não foi possível abrir este arquivo como imagem, GIF ou vídeo."
    source.close()
    return None
