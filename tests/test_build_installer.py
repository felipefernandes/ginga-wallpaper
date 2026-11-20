"""Installer step of scripts/build_exe.py: finding ISCC and its command line."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("PyInstaller")  # build extra: pip install -e .[build]

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("build_exe", ROOT / "scripts" / "build_exe.py")
build_exe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_exe)


def test_find_iscc_prefers_explicit_env_var(tmp_path):
    exe = tmp_path / "ISCC.exe"
    exe.write_text("")
    assert build_exe.find_iscc(env={"ISCC": str(exe)}, which=lambda _: None) == exe


def test_find_iscc_falls_back_to_path_then_known_installs(tmp_path):
    on_path = tmp_path / "path" / "ISCC.exe"
    assert build_exe.find_iscc(env={}, which=lambda _: str(on_path)) == on_path

    local = tmp_path / "local"
    (local / "Programs" / "Inno Setup 6").mkdir(parents=True)
    (local / "Programs" / "Inno Setup 6" / "ISCC.exe").write_text("")
    found = build_exe.find_iscc(env={"LOCALAPPDATA": str(local)}, which=lambda _: None)
    assert found == local / "Programs" / "Inno Setup 6" / "ISCC.exe"


def test_find_iscc_returns_none_when_inno_setup_is_missing(tmp_path):
    assert build_exe.find_iscc(env={"LOCALAPPDATA": str(tmp_path)}, which=lambda _: None) is None


def test_iscc_command_passes_version_and_paths():
    cmd = build_exe.iscc_command(Path("ISCC.exe"), "2.1.0")
    assert cmd[0] == "ISCC.exe"
    assert "/DAppVersion=2.1.0" in cmd
    assert f"/DSourceDir={build_exe.DIST / 'ginga'}" in cmd
    assert f"/DOutputDir={build_exe.DIST}" in cmd
    assert cmd[-1] == str(build_exe.ROOT / "packaging" / "ginga.iss")
