"""Start with Windows: command line and registry round trip (scratch key)."""

import sys

import pytest

from ginga import autostart


def test_command_for_packaged_exe_is_the_exe_itself():
    assert autostart.command(frozen=True, executable=r"C:\Apps\ginga\ginga.exe") == '"C:\\Apps\\ginga\\ginga.exe"'


def test_command_from_source_uses_pythonw_without_console():
    cmd = autostart.command(frozen=False, executable=r"C:\dev\g\.venv\Scripts\python.exe")
    assert cmd == '"C:\\dev\\g\\.venv\\Scripts\\pythonw.exe" -m ginga'


@pytest.mark.skipif(sys.platform != "win32", reason="registry is Windows-only")
def test_enable_disable_round_trip_on_a_scratch_key():
    import winreg

    key = r"Software\ginga-wallpaper-tests\Run"
    try:
        assert not autostart.is_enabled(key=key)
        autostart.set_enabled(True, key=key)
        assert autostart.is_enabled(key=key)
        autostart.set_enabled(False, key=key)
        assert not autostart.is_enabled(key=key)
        autostart.set_enabled(False, key=key)  # disabling twice is fine
    finally:
        for sub in (key, r"Software\ginga-wallpaper-tests"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass


@pytest.mark.skipif(sys.platform != "win32", reason="registry is Windows-only")
def test_apply_rewrites_a_stale_path_from_an_older_install():
    import winreg

    key = r"Software\ginga-wallpaper-tests\Run2"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, autostart.VALUE_NAME, 0, winreg.REG_SZ, r'"C:\old\ginga.exe"')
        autostart.apply(True, key=key)  # box already ticked, user presses Save
        assert autostart.registered_command(key=key) == autostart.command()
        autostart.apply(False, key=key)
        assert autostart.registered_command(key=key) is None
    finally:
        for sub in (key, r"Software\ginga-wallpaper-tests"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass
