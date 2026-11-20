"""Choosing where to attach the wallpaper window in the desktop window tree."""

from ginga.desktop import Host, Win, choose_host, child_position
from ginga.layout import Rect

DEFVIEW = Win(10, "SHELLDLL_DefView", (Win(11, "SysListView32"),))


def test_windows_11_24h2_attaches_inside_progman_below_icons():
    progman = Win(1, "Progman", (DEFVIEW, Win(2, "WorkerW")))
    assert choose_host(progman, [progman]) == Host(parent=1, below=10)


def test_legacy_attaches_to_workerw_behind_icon_layer():
    progman = Win(1, "Progman")
    toplevels = [
        Win(5, "WorkerW"),                 # unrelated WorkerW above the icons
        Win(6, "WorkerW", (DEFVIEW,)),     # hosts the icons
        Win(7, "Notepad"),
        Win(8, "WorkerW"),                 # the one behind the icons
        progman,
    ]
    assert choose_host(progman, toplevels) == Host(parent=8, below=0)


def test_legacy_when_icons_still_live_in_progman():
    progman = Win(1, "Progman", (DEFVIEW,))
    toplevels = [Win(8, "WorkerW"), progman]
    # WorkerW must come *after* the icon host in z-order; here it is before.
    assert choose_host(progman, toplevels) is None


def test_no_icon_layer_found():
    progman = Win(1, "Progman")
    assert choose_host(progman, [Win(8, "WorkerW"), progman]) is None


def test_child_position_is_relative_to_parent_client_origin():
    assert child_position(Rect(0, 0, 3840, 1080), (0, 0)) == (0, 0)
    # Monitor left of the primary: desktop starts at x=-1920, like the parent.
    assert child_position(Rect(-1920, -200, 3840, 1280), (-1920, -200)) == (0, 0)
    assert child_position(Rect(0, 0, 1920, 1080), (-1920, 0)) == (1920, 0)
