"""System tray icon: pause, settings, align monitors, about, quit.

pystray runs its own message loop in a background thread; menu actions call
the thread-safe `App` methods. pystray re-adds the icon by itself when
Explorer restarts (WM_TASKBARCREATED). pystray swallows exceptions raised by
menu actions, so every action goes through `safe()` to reach the log.
"""

from __future__ import annotations

import functools
import logging
import math
import threading
import webbrowser
from collections.abc import Callable

from ginga.app import App

log = logging.getLogger(__name__)

ICON_SIZE = 64
APP_NAME = "ginga wallpaper"
AUTHOR = "Felipe Fernandes"
REPO_URL = "https://github.com/felipefernandes/ginga-wallpaper"


def safe(action: Callable[[], object]) -> Callable[[], None]:
    """Wrap a menu action so failures are logged instead of vanishing."""

    @functools.wraps(action)
    def wrapper() -> None:
        try:
            action()
        except Exception:
            log.exception("Tray action %s failed", getattr(action, "__name__", action))

    return wrapper


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


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("ginga-wallpaper")
    except PackageNotFoundError:
        return "dev"


def about_text() -> str:
    return (
        f"{APP_NAME} — versão {_version()}\n\n"
        "Wallpaper animado leve com alinhamento entre monitores.\n\n"
        f"Feito por {AUTHOR}\n"
        f"{REPO_URL.removeprefix('https://')}\n\n"
        "Abrir o repositório no GitHub?"
    )


def show_about() -> None:
    """Native About box (own thread, so the tray menu stays responsive)."""

    def run() -> None:
        import ctypes

        MB_YESNO, MB_ICONINFORMATION, MB_SETFOREGROUND, MB_TOPMOST, IDYES = 0x4, 0x40, 0x10000, 0x40000, 6
        flags = MB_YESNO | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST
        if ctypes.windll.user32.MessageBoxW(None, about_text(), f"Sobre o {APP_NAME}", flags) == IDYES:
            webbrowser.open(REPO_URL)

    threading.Thread(target=safe(run), name="about", daemon=True).start()


def start_tray(app: App):
    """Show the tray icon in a background thread; returns the pystray Icon."""
    import pystray

    from ginga.settings_ui import open_settings

    def quit_(icon, _item):
        app.request_quit()
        icon.stop()

    item = pystray.MenuItem
    menu = pystray.Menu(
        item("Pausar", safe(app.toggle_pause), checked=lambda _item: app.paused),
        pystray.Menu.SEPARATOR,
        item("Configurações…", safe(lambda: open_settings(app)), default=True),
        item("Alinhar monitores…", safe(app.request_calibrate)),
        pystray.Menu.SEPARATOR,
        item("Sobre…", safe(show_about)),
        item("Sair", quit_),
    )
    icon = pystray.Icon("ginga", icon_image(), APP_NAME, menu)
    threading.Thread(target=icon.run, name="tray", daemon=True).start()
    return icon
