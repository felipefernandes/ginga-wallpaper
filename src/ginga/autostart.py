"""Start with Windows via the per-user Run key (no admin rights needed).

The command is the packaged .exe when frozen (PyInstaller), otherwise
`pythonw -m ginga` from the current environment, so no console window opens.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ginga wallpaper"


def command(frozen: bool | None = None, executable: str | None = None) -> str:
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    exe = Path(executable or sys.executable)
    if frozen:
        return f'"{exe}"'
    pythonw = exe.with_name("pythonw.exe") if exe.name.lower() == "python.exe" else exe
    return f'"{pythonw}" -m ginga'


def registered_command(key: str = RUN_KEY) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return str(winreg.QueryValueEx(k, VALUE_NAME)[0])
    except OSError:
        return None


def is_enabled(key: str = RUN_KEY) -> bool:
    return registered_command(key) is not None


def apply(wanted: bool, key: str = RUN_KEY) -> None:
    """Settings "Save": enabling always rewrites the command, so a path left
    by an older install (e.g. the v1.0 one-file exe) points to this one."""
    if wanted:
        set_enabled(True, key)
    elif is_enabled(key):
        set_enabled(False, key)


def set_enabled(enabled: bool, key: str = RUN_KEY) -> None:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, VALUE_NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, VALUE_NAME)
            except FileNotFoundError:
                pass
