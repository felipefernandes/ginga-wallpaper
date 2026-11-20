"""System tray icon: pause, calibrate, reload, open config, quit.

pystray runs its own message loop in a background thread; menu actions call
the thread-safe `App` methods. pystray re-adds the icon by itself when
Explorer restarts (WM_TASKBARCREATED).
"""

from __future__ import annotations

import math
import os
import threading
from pathlib import Path

from ginga.app import App
from ginga.config import default_config_path, save_config

ICON_SIZE = 64


def icon_image():
    """A small light wave in the wallpaper's colors (red -> violet -> cyan)."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    stops = [(255, 60, 90), (190, 60, 255), (40, 220, 255)]
    prev = None
    for x in range(4, ICON_SIZE - 4):
        t = (x - 4) / (ICON_SIZE - 9)
        seg = min(int(t * 2), 1)
        f = t * 2 - seg
        color = tuple(int(a + (b - a) * f) for a, b in zip(stops[seg], stops[seg + 1]))
        y = ICON_SIZE / 2 + math.sin(t * math.tau * 1.25) * ICON_SIZE * 0.28
        if prev is not None:
            draw.line([prev, (x, y)], fill=color + (255,), width=7)
        prev = (x, y)
    return img


def open_config(path: Path | None = None) -> None:
    """Open config.toml in the default editor, creating it with defaults first."""
    from ginga.config import load_config

    path = path or default_config_path()
    if not path.exists():
        save_config(load_config(path), path)
    os.startfile(path)  # type: ignore[attr-defined]  # Windows only


def start_tray(app: App):
    """Show the tray icon in a background thread; returns the pystray Icon."""
    import pystray

    def quit_(icon, _item):
        app.request_quit()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Pausar", lambda: app.toggle_pause(), checked=lambda _item: app.paused),
        pystray.MenuItem("Calibrar monitores…", lambda: app.request_calibrate()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Recarregar config", lambda: app.reload()),
        pystray.MenuItem("Abrir config", lambda: open_config()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Sair", quit_),
    )
    icon = pystray.Icon("ginga", icon_image(), "ginga wallpaper", menu)
    threading.Thread(target=icon.run, name="tray", daemon=True).start()
    return icon
