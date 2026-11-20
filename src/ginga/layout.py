"""Map physical monitors onto one continuous virtual canvas.

Every monitor shows a window into the same canvas. Its position in the canvas
is its Windows desktop position plus a user calibration offset, so the
wallpaper stays continuous even if monitors are physically misaligned.
"""

from __future__ import annotations

from dataclasses import dataclass

from ginga.config import Offset


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class Monitor:
    """A monitor in Windows desktop coordinates (y grows downward)."""

    name: str
    x: int
    y: int
    width: int
    height: int

    @property
    def rect(self) -> Rect:
        return Rect(self.x, self.y, self.width, self.height)


@dataclass(frozen=True)
class MonitorView:
    monitor_id: str
    monitor: Monitor
    canvas: Rect  # where this monitor looks into the canvas


@dataclass(frozen=True)
class Layout:
    views: list[MonitorView]
    canvas_width: int
    canvas_height: int


def _union(rects: list[Rect]) -> Rect:
    left = min(r.x for r in rects)
    top = min(r.y for r in rects)
    right = max(r.right for r in rects)
    bottom = max(r.bottom for r in rects)
    return Rect(left, top, right - left, bottom - top)


def sort_monitors(monitors: list[Monitor]) -> list[Monitor]:
    """Left-to-right (then top-to-bottom) order; defines monitor ids "1", "2", ..."""
    return sorted(monitors, key=lambda m: (m.x, m.y))


def build_layout(monitors: list[Monitor], offsets: dict[str, Offset]) -> Layout:
    ordered = sort_monitors(monitors)
    shifted = []
    for index, mon in enumerate(ordered, start=1):
        off = offsets.get(str(index), Offset())
        shifted.append((str(index), mon, Rect(mon.x + off.x, mon.y + off.y, mon.width, mon.height)))

    bounds = _union([rect for _, _, rect in shifted])
    views = [
        MonitorView(mid, mon, Rect(r.x - bounds.x, r.y - bounds.y, r.width, r.height))
        for mid, mon, r in shifted
    ]
    return Layout(views=views, canvas_width=bounds.width, canvas_height=bounds.height)


def desktop_bounds(monitors: list[Monitor]) -> Rect:
    """Rectangle covering all monitors in Windows desktop coordinates."""
    return _union([m.rect for m in monitors])


def gl_viewport(monitor: Monitor, desktop: Rect) -> tuple[int, int, int, int]:
    """OpenGL viewport (x, y, w, h) for `monitor` inside a window covering `desktop`.

    OpenGL's y axis points up from the bottom of the window, Windows' points down.
    """
    x = monitor.x - desktop.x
    y = desktop.bottom - monitor.rect.bottom
    return (x, y, monitor.width, monitor.height)
