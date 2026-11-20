"""Entry point: `python -m ginga` (or the `ginga` script / packaged .exe).

Runs the wallpaper behind the desktop icons with a tray icon. Only one
instance runs at a time; logs go to %APPDATA%\\ginga\\ginga.log.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from ginga.config import default_config_path, load_config

MUTEX_NAME = "Local\\ginga-wallpaper"
ERROR_ALREADY_EXISTS = 183


def _single_instance(name: str = MUTEX_NAME):
    """Hold a named mutex for the process lifetime; None if another instance owns it."""
    if sys.platform != "win32":
        return object()
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle or ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def _setup_logging() -> None:
    log_path = default_config_path().with_name("ginga.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_path, maxBytes=512_000, backupCount=1, encoding="utf-8")
    ]
    if sys.stderr is not None:  # no console under pythonw / windowed .exe
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> int:
    _setup_logging()
    log = logging.getLogger("ginga")
    mutex = _single_instance()
    if mutex is None:
        log.info("ginga is already running; exiting")
        return 0

    from ginga.app import App
    from ginga.tray import start_tray

    app = App(load_config())
    icon = start_tray(app)
    log.info("ginga started")
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("ginga crashed")
        return 1
    finally:
        icon.stop()
        log.info("ginga stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
