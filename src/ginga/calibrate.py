"""Calibration mode: align the wallpaper across physically misaligned monitors.

A topmost window shows the wave plus guide lines drawn in canvas space. The
arrows move the *image* on the selected monitor (Up = image goes up = +y
offset, which is what a physically lower monitor needs). Shift moves 10 px,
Tab switches monitor, Space freezes the wave, Enter saves, Esc cancels.

`Calibration` is the pure keyboard logic; `CalibrationRenderer` draws it.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from ginga.config import Config, Offset, save_config
from ginga.layout import MonitorView
from ginga.renderer import Renderer, Viewport

log = logging.getLogger(__name__)

STEP, BIG_STEP = 1, 10
# Arrow -> change of the monitor's canvas window. Moving the window down makes
# the image go up, so "up" means +y.
MOVES = {"up": (0, 1), "down": (0, -1), "left": (1, 0), "right": (-1, 0)}

HUD_SIZE = (1180, 96)
HUD_MARGIN = 48
HUD_TEXT_POS = (22, 14)
HUD_LINE_SPACING = 12


class Calibration:
    def __init__(self, monitor_ids: list[str], offsets: dict[str, Offset]):
        self.ids = list(monitor_ids)
        self.offsets = {mid: Offset(o.x, o.y) for mid, o in offsets.items()}
        for mid in self.ids:
            self.offsets.setdefault(mid, Offset())
        self.selected = self.ids[1] if len(self.ids) > 1 else self.ids[0]
        self.frozen = False  # wave paused so guides are easier to line up

    def handle(self, key: str, shift: bool = False) -> str | None:
        """Apply a key; returns "save" or "cancel" when calibration should end."""
        if key == "enter":
            return "save"
        if key == "esc":
            return "cancel"
        if key == "space":
            self.frozen = not self.frozen
        elif key == "tab":
            index = self.ids.index(self.selected)
            self.selected = self.ids[(index + 1) % len(self.ids)]
        elif key in MOVES:
            dx, dy = MOVES[key]
            step = BIG_STEP if shift else STEP
            off = self.offsets[self.selected]
            self.offsets[self.selected] = Offset(off.x + dx * step, off.y + dy * step)
        return None

    def hud_text(self) -> str:
        off = self.offsets[self.selected]
        state = "   ·   PAUSADO" if self.frozen else ""
        return (
            f"Monitor {self.selected}   x {off.x:+d}   y {off.y:+d}{state}\n"
            "Setas movem a imagem (Shift = 10 px)  ·  Tab troca monitor  ·  "
            "Espaço pausa  ·  Enter salva  ·  Esc cancela"
        )


def _hud_font():
    from PIL import ImageFont

    try:
        return ImageFont.truetype("segoeui.ttf", 24)
    except OSError:
        return ImageFont.load_default(size=24)


def _hud_image(text: str):
    """Render the HUD text into an RGBA image (top row first)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", HUD_SIZE, (10, 12, 18, 210))
    ImageDraw.Draw(img).multiline_text(
        HUD_TEXT_POS, text, font=_hud_font(), fill=(235, 245, 255, 255), spacing=HUD_LINE_SPACING
    )
    return img


class CalibrationRenderer(Renderer):
    interactive = True
    audio_supported = False  # a steady wave is easier to line up

    def __init__(self, config: Config):
        super().__init__(copy.deepcopy(config), pause_check=lambda: False)
        self._limiter.fps = max(self.config.render.fps, 60)  # snappy arrow response
        self.calibration: Calibration | None = None
        self.result: str | None = None
        self._hud_dirty = True

    @property
    def animating(self) -> bool:
        return self.calibration is None or not self.calibration.frozen

    def _init_overlay(self) -> None:
        import moderngl
        import numpy as np

        from ginga.wave import _shader

        ctx = self._ctx
        ctx.enable(moderngl.BLEND)
        ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        quad = ctx.buffer(np.array([-1, -1, 1, -1, -1, 1, 1, 1], dtype="f4").tobytes())
        vert = _shader("wave.vert.glsl")

        self._guides = ctx.program(vertex_shader=vert, fragment_shader=_shader("guides.frag.glsl"))
        self._guides_vao = ctx.vertex_array(self._guides, [(quad, "2f", "in_pos")])

        self._hud = ctx.program(
            vertex_shader=vert,
            fragment_shader="""
                #version 330
                uniform sampler2D u_tex;
                in vec2 v_uv;
                out vec4 f_color;
                void main() { f_color = texture(u_tex, vec2(v_uv.x, 1.0 - v_uv.y)); }
            """,
        )
        self._hud_vao = ctx.vertex_array(self._hud, [(quad, "2f", "in_pos")])
        self._hud_tex = ctx.texture(HUD_SIZE, 4)

    def _apply_layout(self) -> None:
        super()._apply_layout()
        if self.calibration is None and self._layout is not None:
            ids = [v.monitor_id for v in self._layout.views]
            self.calibration = Calibration(ids, self.config.offsets)

    def _draw_overlay(self, viewport: Viewport, view: MonitorView) -> None:
        import moderngl

        cal = self.calibration
        if cal is None:
            return
        selected = view.monitor_id == cal.selected
        g = self._guides
        g["u_origin"].value = (view.canvas.x, view.canvas.y)
        g["u_resolution"].value = (view.canvas.width, view.canvas.height)
        g["u_selected"].value = 1.0 if selected else 0.0
        self._guides_vao.render(moderngl.TRIANGLE_STRIP)

        if selected:
            if self._hud_dirty:
                self._hud_tex.write(_hud_image(cal.hud_text()).tobytes())
                self._hud_dirty = False
            x, y, w, _h = viewport
            hud_w, hud_h = HUD_SIZE
            self._ctx.viewport = (x + (w - hud_w) // 2, y + HUD_MARGIN, hud_w, hud_h)
            self._hud_tex.use(0)
            self._hud_vao.render(moderngl.TRIANGLE_STRIP)
            self._ctx.viewport = viewport

    def _on_key(self, window, key, _scancode, action, mods) -> None:
        import glfw

        if action not in (glfw.PRESS, glfw.REPEAT) or self.calibration is None:
            return
        names = {
            glfw.KEY_UP: "up", glfw.KEY_DOWN: "down", glfw.KEY_LEFT: "left",
            glfw.KEY_RIGHT: "right", glfw.KEY_TAB: "tab", glfw.KEY_ENTER: "enter",
            glfw.KEY_KP_ENTER: "enter", glfw.KEY_ESCAPE: "esc", glfw.KEY_SPACE: "space",
        }
        name = names.get(key)
        if name is None:
            return
        result = self.calibration.handle(name, shift=bool(mods & glfw.MOD_SHIFT))
        if result is not None:
            self.result = result
            self.stop()
            return
        self.config.offsets = dict(self.calibration.offsets)
        self._layout_dirty = True
        self._hud_dirty = True


def run_calibration(config: Config, path: Path | None = None) -> bool:
    """Show calibration mode (blocking). Saves and updates `config` on Enter."""
    renderer = CalibrationRenderer(config)
    renderer.run()
    if renderer.result != "save" or renderer.calibration is None:
        log.info("Calibration cancelled")
        return False
    config.offsets = dict(renderer.calibration.offsets)
    save_config(config, path)
    log.info("Calibration saved: %s", config.offsets)
    return True


if __name__ == "__main__":  # python -m ginga.calibrate
    from ginga.config import load_config

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run_calibration(load_config())
