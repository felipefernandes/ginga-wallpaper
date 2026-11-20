from ginga.gamemode import WindowInfo, should_pause
from ginga.layout import Monitor, Rect

M1 = Monitor(name="Main", x=0, y=0, width=2560, height=1440)
M2 = Monitor(name="Side", x=2560, y=0, width=1920, height=1080)
MONITORS = [M1, M2]


def win(x, y, w, h, cls="UnrealWindow"):
    return WindowInfo(class_name=cls, rect=Rect(x, y, w, h))


def test_no_foreground_window_does_not_pause():
    assert should_pause(None, MONITORS) is False


def test_fullscreen_game_on_main_monitor_pauses():
    assert should_pause(win(0, 0, 2560, 1440), MONITORS) is True


def test_fullscreen_on_secondary_monitor_pauses():
    assert should_pause(win(2560, 0, 1920, 1080), MONITORS) is True


def test_window_larger_than_monitor_pauses():
    # Some games report a rect slightly bigger than the screen.
    assert should_pause(win(-8, -8, 2576, 1456), MONITORS) is True


def test_maximized_window_with_taskbar_visible_does_not_pause():
    assert should_pause(win(0, 0, 2560, 1392), MONITORS) is False


def test_small_window_does_not_pause():
    assert should_pause(win(100, 100, 800, 600), MONITORS) is False


def test_desktop_shell_windows_never_pause():
    for cls in ("Progman", "WorkerW", "Shell_TrayWnd"):
        assert should_pause(win(0, 0, 2560, 1440, cls=cls), MONITORS) is False
