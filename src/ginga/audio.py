"""Turn PC audio into wave controls ("modo berimbau"), as pure numpy.

`SpectrumAnalyzer.process()` takes raw sample blocks (mono or stereo) and
returns `AudioFeatures`, all in 0..1:

- `spectrum`: log-spaced bands from `fmin` to `fmax`; the shader lays them
  across the canvas (bass on the left) as the "sound spikes".
- `bass`: strongest low band; swells the wave.
- `level`: overall loudness; pulses the glow.

Auto-gain makes quiet and loud music look equally alive; a silence gate keeps
the idle animation when nothing plays. Attack is fast and release slow, so
beats hit hard and decay smoothly. Capture lives in audio_capture.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

FFT_SIZE = 2048
N_BINS = 128
FMIN, FMAX = 40.0, 16000.0
BASS_MAX_HZ = 150.0
TILT_DB_PER_OCTAVE = 3.0     # music falls ~3 dB/octave; flatten it so highs show
RANGE_DB = 45.0              # dynamic range mapped onto 0..1 below the peak
LEVEL_RANGE_DB = 30.0
PEAK_DECAY_DB_PER_S = 6.0    # auto-gain recovers this fast after loud parts
PEAK_FLOOR_DB = -60.0        # never amplify near-silence to full scale
SILENCE_DBFS = -65.0
ATTACK, RELEASE = 0.7, 0.25  # per-block smoothing toward the target


@dataclass(frozen=True)
class AudioFeatures:
    spectrum: np.ndarray  # float32, N_BINS values in 0..1
    bass: float
    level: float

    @classmethod
    def silent(cls, n_bins: int = N_BINS) -> AudioFeatures:
        return cls(np.zeros(n_bins, dtype=np.float32), 0.0, 0.0)

    def scaled(self, sensitivity: float) -> AudioFeatures:
        return AudioFeatures(
            np.clip(self.spectrum * sensitivity, 0.0, 1.0).astype(np.float32),
            min(self.bass * sensitivity, 1.0),
            min(self.level * sensitivity, 1.0),
        )


def band_edges(n_bins: int, fmin: float, fmax: float) -> np.ndarray:
    return np.geomspace(fmin, fmax, n_bins + 1)


class SpectrumAnalyzer:
    def __init__(self, sample_rate: int, n_bins: int = N_BINS, fmin: float = FMIN, fmax: float = FMAX):
        self.rate = sample_rate
        self.n_bins, self.fmin, self.fmax = n_bins, fmin, fmax
        self._buffer = np.zeros(FFT_SIZE, dtype=np.float32)
        self._window = np.hanning(FFT_SIZE).astype(np.float32)
        self._norm = 2.0 / self._window.sum()  # sine of amplitude A -> magnitude A

        edges = band_edges(n_bins, fmin, fmax)
        df = sample_rate / FFT_SIZE
        last = FFT_SIZE // 2
        self._ranges = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            a, b = int(np.ceil(lo / df)), int(np.floor(hi / df))
            if a > b:  # band narrower than an FFT bin: use the nearest bin
                a = b = int(round(np.sqrt(lo * hi) / df))
            self._ranges.append((min(a, last), min(b, last) + 1))
        centers = np.sqrt(edges[:-1] * edges[1:])
        self._tilt = (TILT_DB_PER_OCTAVE * np.log2(centers / 1000.0)).astype(np.float32)
        self._bass_bins = max(1, int(np.searchsorted(centers, BASS_MAX_HZ)))

        self._peak = PEAK_FLOOR_DB
        self._level_peak = PEAK_FLOOR_DB
        self._spectrum = np.zeros(n_bins, dtype=np.float32)
        self._bass = 0.0
        self._level = 0.0

    def process(self, block: np.ndarray) -> AudioFeatures:
        samples = np.asarray(block, dtype=np.float32)
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        n = len(samples)
        dt = n / self.rate
        if n >= FFT_SIZE:
            self._buffer[:] = samples[-FFT_SIZE:]
        elif n:
            self._buffer = np.roll(self._buffer, -n)
            self._buffer[-n:] = samples

        rms = float(np.sqrt(np.mean(samples * samples))) if n else 0.0
        rms_db = 20.0 * np.log10(rms + 1e-12)
        if rms_db < SILENCE_DBFS:
            target, target_level = np.zeros(self.n_bins, dtype=np.float32), 0.0
            self._peak = max(PEAK_FLOOR_DB, self._peak - PEAK_DECAY_DB_PER_S * dt)
            self._level_peak = max(PEAK_FLOOR_DB, self._level_peak - PEAK_DECAY_DB_PER_S * dt)
        else:
            mags = np.abs(np.fft.rfft(self._buffer * self._window)) * self._norm
            bands = np.array([mags[a:b].max() for a, b in self._ranges], dtype=np.float32)
            db = 20.0 * np.log10(bands + 1e-12) + self._tilt
            self._peak = max(float(db.max()), self._peak - PEAK_DECAY_DB_PER_S * dt, PEAK_FLOOR_DB)
            target = np.clip((db - (self._peak - RANGE_DB)) / RANGE_DB, 0.0, 1.0).astype(np.float32)

            self._level_peak = max(rms_db, self._level_peak - PEAK_DECAY_DB_PER_S * dt, PEAK_FLOOR_DB)
            target_level = float(np.clip((rms_db - (self._level_peak - LEVEL_RANGE_DB)) / LEVEL_RANGE_DB, 0, 1))

        self._spectrum = _smooth(self._spectrum, target)
        bass_target = float(target[: self._bass_bins].max())
        self._bass = float(_smooth(np.float32(self._bass), np.float32(bass_target)))
        self._level = float(_smooth(np.float32(self._level), np.float32(target_level)))
        return AudioFeatures(self._spectrum.copy(), self._bass, self._level)


def _smooth(current, target):
    rate = np.where(target > current, ATTACK, RELEASE)
    return (current + (target - current) * rate).astype(np.float32)
