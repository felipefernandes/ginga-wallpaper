"""Attach the wallpaper window behind the desktop icons.

Sending the undocumented message 0x052C to Progman makes Explorer split the
desktop into an icon layer (SHELLDLL_DefView) and a wallpaper layer (WorkerW).
Where those live depends on the Windows build:

- Windows 11 24H2+: both are children of Progman (icons on top). Our window
  becomes a child of Progman, placed right below the icon layer, and must be
  WS_EX_LAYERED or DWM never shows it.
- Older builds: the icons live in a top-level WorkerW; the next WorkerW in
  z-order is the wallpaper layer, and our window becomes its child.

`choose_host` holds that decision as pure logic; the rest wraps Win32 (ctypes).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ginga.layout import Rect

log = logging.getLogger(__name__)

ICONS_CLASS = "SHELLDLL_DefView"
WORKERW_CLASS = "WorkerW"
SPAWN_WORKERW = 0x052C


@dataclass(frozen=True)
class Win:
    """Snapshot of a window: handle, class and direct children (z-order, top first)."""

    hwnd: int
    class_name: str
    children: tuple[Win, ...] = ()

    def child(self, class_name: str) -> Win | None:
        return next((c for c in self.children if c.class_name == class_name), None)


@dataclass(frozen=True)
class Host:
    parent: int     # window to become a child of
    below: int = 0  # sibling to sit directly under (0: keep default z-order)


def choose_host(progman: Win, toplevels: list[Win]) -> Host | None:
    """Pick where the wallpaper goes; `toplevels` is in z-order, top first."""
    icons = progman.child(ICONS_CLASS)
    if icons is not None and progman.child(WORKERW_CLASS) is not None:
        return Host(parent=progman.hwnd, below=icons.hwnd)

    for index, win in enumerate(toplevels):
        if win.child(ICONS_CLASS) is not None:
            behind = next((w for w in toplevels[index + 1:] if w.class_name == WORKERW_CLASS), None)
            return Host(parent=behind.hwnd) if behind else None
    return None


def child_position(desktop: Rect, parent_origin: tuple[int, int]) -> tuple[int, int]:
    """Position of a child window covering `desktop` (screen coords) inside its parent."""
    return (desktop.x - parent_origin[0], desktop.y - parent_origin[1])


# --- Win32 -----------------------------------------------------------------


def _user32():
    import ctypes
    from ctypes import wintypes

    u = ctypes.WinDLL("user32", use_last_error=True)
    HWND = wintypes.HWND
    u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowW.restype = HWND
    u.FindWindowExW.argtypes = [HWND, HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    u.FindWindowExW.restype = HWND
    u.SendMessageTimeoutW.argtypes = [
        HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
    ]
    u.GetClassNameW.argtypes = [HWND, wintypes.LPWSTR, ctypes.c_int]
    u.SetParent.argtypes = [HWND, HWND]
    u.SetParent.restype = HWND
    u.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]
    u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, ctypes.c_ssize_t]
    u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    u.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u.SetLayeredWindowAttributes.argtypes = [HWND, wintypes.DWORD, wintypes.BYTE, wintypes.DWORD]
    u.ClientToScreen.argtypes = [HWND, ctypes.POINTER(wintypes.POINT)]
    u.IsWindow.argtypes = [HWND]
    return u


GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x2
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE = 0x1, 0x2, 0x4, 0x10
SMTO_NORMAL = 0x0


def _class_name(u, hwnd) -> str:
    import ctypes

    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def _children(u, parent) -> list[int]:
    out, child = [], u.FindWindowExW(parent, None, None, None)
    while child:
        out.append(child)
        child = u.FindWindowExW(parent, child, None, None)
    return out


def _snapshot(u, hwnd, depth: int) -> Win:
    kids = tuple(_snapshot(u, c, depth - 1) for c in _children(u, hwnd)) if depth else ()
    return Win(hwnd, _class_name(u, hwnd), kids)


class Attachment:
    """Our window living inside the desktop; positions are parent-relative."""

    def __init__(self, user32, hwnd: int, host: Host):
        import ctypes
        from ctypes import wintypes

        self._u = user32
        self.hwnd = hwnd
        self.host = host
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(host.parent, ctypes.byref(origin))
        self.parent_origin = (origin.x, origin.y)

    def place(self, desktop: Rect) -> None:
        x, y = child_position(desktop, self.parent_origin)
        flags = SWP_NOACTIVATE | (0 if self.host.below else SWP_NOZORDER)
        self._u.SetWindowPos(self.hwnd, self.host.below or None, x, y, desktop.width, desktop.height, flags)

    def alive(self) -> bool:
        """False once Explorer restarts (our window dies with its parent)."""
        return bool(self._u.IsWindow(self.hwnd) and self._u.IsWindow(self.host.parent))


def attach(hwnd: int) -> Attachment:
    """Re-parent `hwnd` into the desktop's wallpaper layer."""
    import ctypes

    u = _user32()
    progman = u.FindWindowW("Progman", None)
    if not progman:
        raise RuntimeError("Desktop window (Progman) not found; is Explorer running?")

    result = ctypes.c_size_t()
    for wparam, lparam in ((0xD, 0x1), (0, 0)):  # both variants seen across builds
        u.SendMessageTimeoutW(progman, SPAWN_WORKERW, wparam, lparam, SMTO_NORMAL, 1000, ctypes.byref(result))

    toplevels = [_snapshot(u, h, depth=1) for h in _children(u, None)]
    progman_win = next((w for w in toplevels if w.hwnd == progman), _snapshot(u, progman, 1))
    host = choose_host(progman_win, toplevels)
    if host is None:
        raise RuntimeError("Could not find the desktop wallpaper layer")

    style = u.GetWindowLongPtrW(hwnd, GWL_STYLE)
    u.SetWindowLongPtrW(hwnd, GWL_STYLE, (style & ~WS_POPUP) | WS_CHILD)
    if host.below:
        # Inside the 24H2+ Progman, a plain child window is never composited
        # (verified on the owner's build 26300); an opaque layered one is.
        ex_style = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
        u.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
    if not u.SetParent(hwnd, host.parent):
        raise ctypes.WinError(ctypes.get_last_error())
    log.info("Attached to desktop: parent %#x (%s), below %#x",
             host.parent, _class_name(u, host.parent), host.below)
    return Attachment(u, hwnd, host)
