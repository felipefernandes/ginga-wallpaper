"""Render offline previews of the wallpaper (no Windows needed).

Simulates two monitors where monitor 2 sits physically lower than monitor 1,
and renders it with and without calibration.

Usage:
    python scripts/preview.py --out preview
"""

from __future__ import annotations

import argparse
from pathlib import Path

import moderngl
import numpy as np
from PIL import Image, ImageDraw

from ginga.config import Offset, WaveSettings
from ginga.layout import Monitor, build_layout
from ginga.wave import WaveProgram

SCALE = 0.25          # render at 1/4 resolution to keep previews small
DROP = 120            # monitor 2 is physically 120 px lower
GAP = 24              # bezel gap drawn between monitors in the preview

MONITORS = [Monitor("Main", 0, 0, 2560, 1440), Monitor("Side", 2560, 0, 1920, 1080)]


def _context() -> moderngl.Context:
    try:
        return moderngl.create_standalone_context(backend="egl")
    except Exception:
        return moderngl.create_standalone_context()


def _scaled(m: Monitor) -> Monitor:
    return Monitor(m.name, int(m.x * SCALE), int(m.y * SCALE), int(m.width * SCALE), int(m.height * SCALE))


def render_frame(ctx, prog, offset_y: int, time: float) -> Image.Image:
    """Compose both monitors as they physically sit on the desk."""
    monitors = [_scaled(m) for m in MONITORS]
    layout = build_layout(monitors, {"2": Offset(0, int(offset_y * SCALE))})
    drop = int(DROP * SCALE)

    width = sum(m.width for m in monitors) + GAP + 40
    height = max(m.height for m in monitors) + drop + 40
    canvas = Image.new("RGB", (width, height), (38, 40, 46))
    draw = ImageDraw.Draw(canvas)

    x = 20
    for view in layout.views:
        w, h = view.canvas.width, view.canvas.height
        fbo = ctx.simple_framebuffer((w, h))
        fbo.use()
        prog.draw(layout, view, time, WaveSettings())
        img = Image.frombytes("RGB", (w, h), fbo.read(components=3)).transpose(Image.FLIP_TOP_BOTTOM)
        fbo.release()

        y = 20 + (drop if view.monitor_id == "2" else 0)
        draw.rectangle((x - 4, y - 4, x + w + 3, y + h + 3), fill=(12, 12, 14))  # bezel
        canvas.paste(img, (x, y))
        x += w + GAP
    return canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("preview"))
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    ctx = _context()
    prog = WaveProgram(ctx)

    before = render_frame(ctx, prog, offset_y=0, time=4.0)
    after = render_frame(ctx, prog, offset_y=DROP, time=4.0)
    combo = Image.new("RGB", (before.width, before.height * 2 + 50), (24, 24, 28))
    combo.paste(before, (0, 40))
    combo.paste(after, (0, before.height + 50))
    label = ImageDraw.Draw(combo)
    label.text((20, 14), "Sem calibracao (offset_y = 0)", fill=(230, 230, 230))
    label.text((20, before.height + 30), f"Com calibracao (offset_y = {DROP})", fill=(230, 230, 230))
    combo.save(args.out / "calibration.png")

    frames = [render_frame(ctx, prog, offset_y=DROP, time=i / 15) for i in range(args.frames)]
    frames[0].save(
        args.out / "animation.gif",
        save_all=True,
        append_images=frames[1:],
        duration=66,
        loop=0,
    )
    print(f"Saved previews to {args.out.resolve()}")


if __name__ == "__main__":
    main()
