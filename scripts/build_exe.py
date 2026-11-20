"""Build dist/ginga/ (ginga.exe + _internal/), zip it, and build the installer.

One-folder rather than one-file on purpose: a one-file exe unpacks itself to
%TEMP% at every start, which antivirus heuristics associate with trojans (the
owner's Kaspersky flagged v1.0). We also embed Windows version info and never
UPX-compress. The real fix is code signing.

The installer (dist/ginga-<ver>-setup.exe, per-user, no admin) is compiled
from packaging/ginga.iss with Inno Setup 6 when ISCC.exe is found (env var
ISCC, PATH, or the default install folders); otherwise that step is skipped.

Usage (inside the venv, with `pip install -e .[build]`):
    python scripts/build_exe.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from importlib.metadata import version
from pathlib import Path

import PyInstaller.__main__

from ginga.tray import APP_NAME, AUTHOR, REPO_URL, icon_image

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def make_icon() -> Path:
    BUILD.mkdir(exist_ok=True)
    path = BUILD / "ginga.ico"
    icon_image(256).save(path, sizes=[(s, s) for s in ICON_SIZES])
    return path


def version_tuple(text: str) -> tuple[int, int, int, int]:
    parts = [int(p) for p in text.split(".")[:4] if p.isdigit()]
    return tuple((parts + [0, 0, 0, 0])[:4])  # type: ignore[return-value]


def make_version_file(ver: str) -> Path:
    """Windows VERSIONINFO resource: what Explorer shows under Properties > Details."""
    nums = version_tuple(ver)
    strings = {
        "CompanyName": AUTHOR,
        "FileDescription": f"{APP_NAME} - animated desktop wallpaper",
        "FileVersion": ver,
        "InternalName": "ginga",
        "LegalCopyright": f"(c) {AUTHOR}",
        "OriginalFilename": "ginga.exe",
        "ProductName": APP_NAME,
        "ProductVersion": ver,
        "Comments": REPO_URL,
    }
    table = ",\n          ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    path = BUILD / "version_info.txt"
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
          {table}])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""",
        encoding="utf-8",
    )
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


def find_iscc(
    env: Mapping[str, str] = os.environ,
    which: Callable[[str], str | None] = shutil.which,
) -> Path | None:
    """Inno Setup's command-line compiler: $ISCC, then PATH, then default installs."""
    if env.get("ISCC"):
        return Path(env["ISCC"])
    found = which("ISCC")
    if found:
        return Path(found)
    roots = [
        Path(env["LOCALAPPDATA"]) / "Programs" if env.get("LOCALAPPDATA") else None,
        Path(env["ProgramFiles(x86)"]) if env.get("ProgramFiles(x86)") else None,
        Path(env["ProgramFiles"]) if env.get("ProgramFiles") else None,
    ]
    for root in filter(None, roots):
        candidate = root / "Inno Setup 6" / "ISCC.exe"
        if candidate.is_file():
            return candidate
    return None


def iscc_command(iscc: Path, ver: str) -> list[str]:
    return [
        str(iscc),
        "/Q",
        f"/DAppVersion={ver}",
        f"/DSourceDir={DIST / 'ginga'}",
        f"/DOutputDir={DIST}",
        f"/DIconFile={BUILD / 'ginga.ico'}",
        str(ROOT / "packaging" / "ginga.iss"),
    ]


def build_installer(ver: str) -> Path | None:
    iscc = find_iscc()
    if iscc is None:
        print("Inno Setup 6 (ISCC.exe) not found: skipping the installer.")
        return None
    subprocess.run(iscc_command(iscc, ver), check=True)
    return DIST / f"ginga-{ver}-setup.exe"


def main() -> None:
    ver = version("ginga-wallpaper")
    shaders = ROOT / "src" / "ginga" / "shaders"
    PyInstaller.__main__.run([
        str(ROOT / "packaging" / "launcher.py"),
        "--name", "ginga",
        "--onedir",
        "--windowed",            # no console; logs go to %APPDATA%\ginga\ginga.log
        "--noupx",
        "--noconfirm",
        "--clean",
        "--icon", str(make_icon()),
        "--version-file", str(make_version_file(ver)),
        "--paths", str(ROOT / "src"),
        "--add-data", f"{shaders / '*.glsl'}{os.pathsep}ginga/shaders",
        "--copy-metadata", "ginga-wallpaper",   # version shown in "Sobre…"
        "--hidden-import", "pystray._win32",
        "--collect-data", "soundcard",          # its cffi reads *.py.h headers at runtime
        *glfw_binaries(),
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
    ])
    archive = shutil.make_archive(str(DIST / f"ginga-{ver}-windows"), "zip", DIST, "ginga")
    print(f"Built {DIST / 'ginga' / 'ginga.exe'} and {archive}")
    installer = build_installer(ver)
    if installer:
        print(f"Built {installer}")


if __name__ == "__main__":
    main()
