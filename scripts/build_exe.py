"""Build dist/ginga.exe: one file, no console window, wave icon.

Usage (inside the venv, with `pip install -e .[build]`):
    python scripts/build_exe.py
"""

from __future__ import annotations

import os
from pathlib import Path

import PyInstaller.__main__

from ginga.tray import icon_image

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def make_icon() -> Path:
    BUILD.mkdir(exist_ok=True)
    path = BUILD / "ginga.ico"
    icon_image(256).save(path, sizes=[(s, s) for s in ICON_SIZES])
    return path


def glfw_binaries() -> list[str]:
    """pyGLFW loads glfw3.dll via ctypes, which PyInstaller cannot see; when
    frozen it looks in <bundle>/glfw/, so ship its DLLs exactly there."""
    import glfw

    package = Path(glfw.__file__).parent
    args = []
    for dll in sorted(package.glob("*.dll")):
        args += ["--add-binary", f"{dll}{os.pathsep}glfw"]
    if not args:
        raise SystemExit(f"No GLFW DLL found in {package}")
    return args


def main() -> None:
    shaders = ROOT / "src" / "ginga" / "shaders"
    PyInstaller.__main__.run([
        str(ROOT / "packaging" / "launcher.py"),
        "--name", "ginga",
        "--onefile",
        "--windowed",            # no console; logs go to %APPDATA%\ginga\ginga.log
        "--noconfirm",
        "--clean",
        "--icon", str(make_icon()),
        "--paths", str(ROOT / "src"),
        "--add-data", f"{shaders / '*.glsl'}{os.pathsep}ginga/shaders",
        "--copy-metadata", "ginga-wallpaper",   # version shown in "Sobre…"
        "--hidden-import", "pystray._win32",
        *glfw_binaries(),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
    ])


if __name__ == "__main__":
    main()
