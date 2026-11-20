# ginga-wallpaper

Lightweight animated wallpaper for Windows 11 whose key feature is **per-monitor
calibration offsets**, so one continuous image spans monitors that are physically
misaligned (the owner's monitor 2 sits lower than monitor 1). Must stay
near-zero cost while games run (Battlefield 6, Cyberpunk 2077).

## Stack & conventions

- Python 3.12+, `glfw` + `moderngl` (OpenGL 3.3 core), Win32 via `ctypes` (no pywin32), `pystray` for the tray.
- TDD with `pytest`; keep modules small, pure logic separated from Win32/GL wrappers.
- Code, commits, docstrings in English. Talk to the user in Brazilian Portuguese.
- Work on branch `feat/v1`; PR into `main` when v1 is done.

## Commands

```bash
.venv\Scripts\activate
pytest                                    # all tests (GPU tests skip if no GL context)
python scripts/preview.py --out preview   # offline PNG/GIF previews
```

Note: the user's global `python`/`pip` were cleaned up; create venvs with `py -3.13 -m venv .venv`.

## Architecture

| Module | Role |
|---|---|
| `src/ginga/config.py` | TOML config at `%APPDATA%\ginga\config.toml`; invalid/missing values fall back to defaults |
| `src/ginga/layout.py` | Monitors + offsets -> continuous virtual canvas; monitor ids are left-to-right order (`"1"`, `"2"`); `gl_viewport` maps a monitor into one window covering the whole desktop |
| `src/ginga/gamemode.py` | `should_pause`: foreground window covering a full monitor (ignoring shell windows) pauses rendering |
| `src/ginga/wave.py` + `shaders/` | Procedural light-wave shader; all math in canvas pixel space so split views are seamless (tested) |

## Owner's hardware

- 2x 1920x1080 at 100% scale: monitor 1 at (0,0) 180Hz, monitor 2 at (1920,0) 144Hz. Windows reports them top-aligned; the physical drop is handled by calibration.
- NVIDIA RTX 2060, OpenGL 3.3.

## Status (v1)

Done: 1 scaffold, 2 config, 3 layout, 4 fullscreen detection logic, 5 shader + previews (visual approved).

Next (only testable on Windows; run and iterate with the user):
6. `renderer.py`: one borderless GL window over the whole desktop, viewport per monitor, FPS cap, pause hook.
7. `desktop.py`: attach the window behind desktop icons (Progman `0x052C` -> `WorkerW`).
8. `calibrate.py`: overlay mode with guide lines; arrows move a monitor's offset (Shift = 10px), Tab switches monitor, Enter saves, Esc cancels.
9. `tray.py` + `__main__.py`: tray menu (pause, calibrate, reload, quit), wire everything.
10. PyInstaller `.exe` + "start with Windows" instructions.

## Roadmap

- v2: audio-reactive mode ("modo berimbau").
- Later: video/GIF wallpapers with the same alignment.
