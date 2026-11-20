# ginga-wallpaper

> *Ginga*: the constant, flowing sway at the heart of capoeira.

Lightweight animated wallpaper for Windows 11, built for multi-monitor setups
where the screens are **not physically aligned**.

![Calibration preview](docs/calibration.png)

## Features (v1, in progress)

- [x] Procedural light-wave shader (GPU, no video decoding)
- [x] One continuous canvas across all monitors
- [x] Per-monitor calibration offsets (`config.toml`)
- [x] Fullscreen detection logic (pauses rendering while gaming)
- [ ] Desktop attach (behind icons, via `WorkerW`)
- [ ] Visual calibration mode (arrow keys)
- [ ] System tray menu
- [ ] Standalone `.exe`

## Development

Requires Python 3.12+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
pytest
```

Render previews offline (simulates a monitor that sits lower than the other):

```bash
python scripts/preview.py --out preview
```

## Configuration

Stored at `%APPDATA%\ginga\config.toml`:

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
