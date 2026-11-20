"""Detect fullscreen apps (games, videos) so the wallpaper can stop rendering.

The decision logic is pure and testable; only `foreground_window()` touches Win32.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from ginga.layout import Monitor, Rect

# Windows that belong to the desktop itself and cover the whole screen.
SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})


@dataclass(frozen=True)
class WindowInfo:
    class_name: str
    rect: Rect


def _covers(window: Rect, monitor: Rect) -> bool:
    return (
        window.x <= monitor.x
        and window.y <= monitor.y
        and window.right >= monitor.right
        and window.bottom >= monitor.bottom
    )


def should_pause(window: WindowInfo | None, monitors: list[Monitor]) -> bool:
    """True if the foreground window fills an entire monitor."""
    if window is None or window.class_name in SHELL_CLASSES:
        return False
    return any(_covers(window.rect, m.rect) for m in monitors)


def foreground_window() -> WindowInfo | None:
    """Return the current foreground window (Windows only; None elsewhere)."""
    if sys.platform != "win32":
        return None

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, len(buf))
    return WindowInfo(
        class_name=buf.value,
        rect=Rect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top),
    )
