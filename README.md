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
- Portable: unzip and run, no installer

## Install

1. Download `ginga-<version>-windows.zip` from the [latest release](https://github.com/felipefernandes/ginga-wallpaper/releases/latest).
2. Extract the `ginga` folder somewhere permanent (e.g. `%LOCALAPPDATA%\Programs\ginga`)
   and run `ginga.exe` inside it (keep the `_internal` folder next to it).
   The exe is not code-signed yet, so Windows SmartScreen may warn (*More info → Run anyway*)
   and some antivirus heuristics may flag it as a false positive; the source and the
   build script are in this repo.
3. Right-click the wave icon in the tray:
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

Build `dist/ginga/ginga.exe` and the release zip:

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
- **v2.1**: proper installer (Inno Setup, per-user, no admin): shows up in
  Windows *Settings > Apps* with uninstall, Start Menu shortcut, optional
  start with Windows. The portable zip stays available.
- **v3**: use any wallpaper (images first, then video/GIF) spanning the
  monitors with the same alignment.

Made by Felipe Fernandes.
