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
python -m ginga                           # the app: wallpaper + tray (log: %APPDATA%\ginga\ginga.log)
python -m ginga.calibrate                 # calibration only
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
| `src/ginga/renderer.py` | Frame loop: borderless GLFW window over the desktop, viewport per monitor, own FPS pacing (no vsync), auto/manual pause; `stop`/`set_paused`/`reload` are thread-safe |
| `src/ginga/desktop.py` | Attach behind icons after Progman `0x052C`. 24H2+: child of Progman right below `SHELLDLL_DefView`, and it **must be `WS_EX_LAYERED`** (alpha 255) or DWM never shows it. Legacy: child of the `WorkerW` after the icon host. Explorer restart kills the window: `Renderer.desktop_lost` tells the caller to recreate it |
| `src/ginga/calibrate.py` + `guides.frag.glsl` | `CalibrationRenderer` (topmost, interactive `Renderer` subclass): canvas-space guide lines + Pillow-rendered HUD. Arrows move the *image* (Up = +y, what a physically lower monitor needs), Shift 10px, Tab, Space freezes the wave, Enter saves, Esc cancels |
| `src/ginga/app.py` | Supervisor on the main thread: one renderer at a time (wallpaper or calibration), retries start (Explorer not ready at logon), recreates on `desktop_lost`; tray-facing methods are thread-safe |
| `src/ginga/tray.py` + `__main__.py` | pystray menu in a background thread (PT-BR labels: Pausar, Configurações…, Alinhar monitores…, Sobre…, Sair; re-adds itself on Explorer restart; actions wrapped in `safe()` because pystray swallows exceptions; About box via MessageBoxW); entry point with named-mutex single instance and rotating log file |
| `src/ginga/settings.py` + `settings_ui.py` | Settings screen for non-technical users: pure slider model (`Field`, clamp/snap) + tkinter window on its own thread with live preview, Save/Cancel/Restore defaults. Never edits offsets: `App.update_settings` keeps the app's offsets, and calibration saves only offsets |

## Owner's hardware

- 2x 1920x1080 at 100% scale: monitor 1 at (0,0) 180Hz, monitor 2 at (1920,0) 144Hz. Windows reports them top-aligned; the physical drop is handled by calibration.
- NVIDIA RTX 2060, OpenGL 3.3.

## Status (v1)

Done: 1 scaffold, 2 config, 3 layout, 4 fullscreen detection logic, 5 shader + previews (visual approved), 6 renderer (`scripts/run_renderer.py [--desktop]` runs it standalone and reports fps/CPU), 7 desktop attach (verified by screenshot on build 26300), 8 calibration (`python -m ginga.calibrate`, owner calibrated monitor 2 at ~y+130), 9 tray + app (smoke-tested: attach, single instance, log), settings UI (owner asked: editing TOML is too hard for lay users).

Next (only testable on Windows; run and iterate with the user):
10. PyInstaller `.exe` + "start with Windows"; then PR to `main` and tag `v1.0`.

## Roadmap

- v2: audio-reactive mode ("modo berimbau"): the wave reacts to the PC's audio output.
- v3: load any wallpaper (static images first, then video/GIF) from Settings, spanning the monitors with the same calibration. This is the owner's original frustration: big wallpapers on physically misaligned monitors.
