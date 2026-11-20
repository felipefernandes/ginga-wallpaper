"""GPU program that draws the wave for one monitor view."""

from __future__ import annotations

from importlib.resources import files

import moderngl
import numpy as np

from ginga.config import WaveSettings
from ginga.layout import Layout, MonitorView

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

    def _set(self, name: str, value) -> None:
        # Unused uniforms are optimized away by the driver; skip them.
        if name in self.program:
            self.program[name].value = value

    def draw(self, layout: Layout, view: MonitorView, time: float, wave: WaveSettings) -> None:
        """Draw `view` into the currently bound viewport."""
        self._set("u_time", time)
        self._set("u_canvas", (layout.canvas_width, layout.canvas_height))
        self._set("u_origin", (view.canvas.x, view.canvas.y))
        self._set("u_resolution", (view.canvas.width, view.canvas.height))
        self._set("u_speed", wave.speed)
        self._set("u_amplitude", wave.amplitude)
        self._set("u_glow", wave.glow)
        self._set("u_spikes", wave.spikes)
        self.vao.render(moderngl.TRIANGLE_STRIP)
