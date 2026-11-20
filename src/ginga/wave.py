"""GPU program that draws the wave for one monitor view."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files

import moderngl
import numpy as np

from ginga.config import WaveSettings
from ginga.layout import Layout, MonitorView

SPECTRUM_BINS = 128


@dataclass(frozen=True)
class AudioUniforms:
    """Audio state for one frame; `mix` 0 disables every audio effect."""

    mix: float
    bass: float
    level: float
    spectrum: np.ndarray  # float32, SPECTRUM_BINS values in 0..1

_QUAD = np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4")


def _shader(name: str) -> str:
    return files("ginga.shaders").joinpath(name).read_text(encoding="utf-8")


class WaveProgram:
    def __init__(self, ctx: moderngl.Context):
        self.ctx = ctx
        self.program = ctx.program(
            vertex_shader=_shader("wave.vert.glsl"),
            fragment_shader=_shader("wave.frag.glsl"),
        )
        vbo = ctx.buffer(_QUAD.tobytes())
        self.vao = ctx.vertex_array(self.program, [(vbo, "2f", "in_pos")])
        self.spectrum = ctx.texture((SPECTRUM_BINS, 1), 1, dtype="f4")
        self.spectrum.filter = (moderngl.LINEAR, moderngl.LINEAR)
        self.spectrum.repeat_x = self.spectrum.repeat_y = False
        self._set("u_spectrum", 0)
        self._uploaded: np.ndarray | None = None

    def _set(self, name: str, value) -> None:
        # Unused uniforms are optimized away by the driver; skip them.
        if name in self.program:
            self.program[name].value = value

    def draw(
        self,
        layout: Layout,
        view: MonitorView,
        time: float,
        wave: WaveSettings,
        audio: AudioUniforms | None = None,
    ) -> None:
        """Draw `view` into the currently bound viewport."""
        if audio is not None and audio.spectrum is not self._uploaded:
            # Upload once per frame, not once per monitor.
            self.spectrum.write(np.ascontiguousarray(audio.spectrum, dtype="f4").tobytes())
            self._uploaded = audio.spectrum
        self.spectrum.use(0)
        self._set("u_audio", audio.mix if audio else 0.0)
        self._set("u_bass", audio.bass if audio else 0.0)
        self._set("u_level", audio.level if audio else 0.0)
        self._set("u_time", time)
        self._set("u_canvas", (layout.canvas_width, layout.canvas_height))
        self._set("u_origin", (view.canvas.x, view.canvas.y))
        self._set("u_resolution", (view.canvas.width, view.canvas.height))
        self._set("u_speed", wave.speed)
        self._set("u_amplitude", wave.amplitude)
        self._set("u_glow", wave.glow)
        self._set("u_spikes", wave.spikes)
        self.vao.render(moderngl.TRIANGLE_STRIP)
