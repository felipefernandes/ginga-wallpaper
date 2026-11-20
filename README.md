# ginga-wallpaper

> *Ginga*: the constant, flowing sway at the heart of capoeira.

Lightweight animated wallpaper for Windows 11, built for multi-monitor setups
where the screens are **not physically aligned**.

![Calibration preview](docs/calibration.png)

## Features

- Procedural light-wave shader (GPU, no video decoding)
- **Modo berimbau** (v2): the wave dances to whatever the PC plays. Its spikes
  become a live spectrum across all monitors (bass on the left), bass swells
  the wave and loudness pulses the glow. Off by default; ~2.5% of one CPU
  core when on, zero while a game is fullscreen
- One continuous canvas across all monitors
- **Monitor alignment**: a visual mode with guide lines lines up monitors that
  sit at different heights on the desk, so the image flows across the bezel
- Lives behind the desktop icons (Windows 11 24H2+ and older layouts)
- Pauses itself while a game or video runs fullscreen
- Tray menu: pause, settings, align monitors, about, quit
- Settings window with live preview (speed, wave height, glow, texture,
  audio mode and sensitivity, FPS) and "start with Windows"
- Per-user installer (no admin) with uninstall in *Settings > Apps*, or a portable zip

## Install

1. Download `ginga-<version>-setup.exe` from the [latest release](https://github.com/felipefernandes/ginga-wallpaper/releases/latest)
   and run it. It installs for your user only (`%LOCALAPPDATA%\Programs\ginga`, no admin),
   adds a Start Menu shortcut and, optionally, starts with Windows. Uninstall from
   *Settings > Apps* (your settings in `%APPDATA%\ginga` are kept).

   Portable alternative: download `ginga-<version>-windows.zip`, extract the `ginga`
   folder somewhere permanent and run `ginga.exe` (keep `_internal` next to it).

   Nothing is code-signed yet, so Windows SmartScreen may warn (*More info → Run anyway*)
   and some antivirus heuristics may flag it as a false positive; the source and the
   build script are in this repo.

   Upgrading: run the new setup; it closes the running app and replaces the old version.
2. Right-click the wave icon in the tray:
   - **Alinhar monitores…** (align monitors): arrows move the image on the
     selected monitor until the guide lines are continuous (Shift = 10 px,
     Tab = next monitor, Space = freeze the wave, Enter = save, Esc = cancel).
   - **Configurações…** (settings): tweak the look, tick *Reagir ao som do PC*
     for the audio mode, and *Iniciar com o Windows* to start with Windows.

Logs: `%APPDATA%\ginga\ginga.log`.

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pytest
python -m ginga                 # run the app from source
```

Build `dist/ginga/ginga.exe`, the release zip and the installer
(`dist/ginga-<version>-setup.exe`, needs [Inno Setup 6](https://jrsoftware.org/isinfo.php);
skipped if `ISCC.exe` is not found, or point the `ISCC` env var at it):

```bash
pip install -e ".[build]"
python scripts/build_exe.py
```

Render previews offline (simulates a monitor that sits lower than the other):

```bash
python scripts/preview.py --out preview
```

## Configuration

Edited through the Settings window; stored at `%APPDATA%\ginga\config.toml`:

```toml
[render]
fps = 30
pause_when_fullscreen = true

[wave]
speed = 1.0
amplitude = 1.0
glow = 1.0
spikes = 1.0

[offsets.2]   # monitors are numbered left to right
x = 0
y = 120
```

## Roadmap

- ~~**v2**: audio-reactive mode ("modo berimbau")~~ done in 2.0.
- ~~**v2.1**: per-user installer with uninstall~~ done in 2.1.
- **v3**: use any wallpaper (images first, then video/GIF) spanning the
  monitors with the same alignment.

Made by Felipe Fernandes.
