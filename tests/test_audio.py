"""Audio analysis (pure numpy): spectrum bands, bass, level, smoothing."""

import numpy as np
import pytest

from ginga.audio import AudioFeatures, SpectrumAnalyzer, band_edges

RATE = 48000
BLOCK = 1024


def tone(freq, seconds=0.5, amp=0.5, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def feed(analyzer, signal):
    features = None
    for start in range(0, len(signal) - BLOCK + 1, BLOCK):
        features = analyzer.process(signal[start:start + BLOCK])
    return features


def peak_freq(analyzer, features):
    edges = band_edges(analyzer.n_bins, analyzer.fmin, analyzer.fmax)
    i = int(np.argmax(features.spectrum))
    return np.sqrt(edges[i] * edges[i + 1])


def test_band_edges_are_log_spaced_and_cover_the_range():
    edges = band_edges(4, 100, 1600)
    assert edges == pytest.approx([100, 200, 400, 800, 1600])


def test_silence_gives_all_zeros():
    an = SpectrumAnalyzer(RATE)
    f = feed(an, np.zeros(RATE // 2, dtype=np.float32))
    assert f.level == 0 and f.bass == 0 and not f.spectrum.any()


@pytest.mark.parametrize("freq", [60, 440, 5000])
def test_tone_lights_up_its_own_band(freq):
    an = SpectrumAnalyzer(RATE)
    f = feed(an, tone(freq))
    assert peak_freq(an, f) == pytest.approx(freq, rel=0.15)
    assert f.spectrum.max() > 0.8


def test_bass_follows_low_frequencies_only():
    low = feed(SpectrumAnalyzer(RATE), tone(60))
    high = feed(SpectrumAnalyzer(RATE), tone(5000))
    assert low.bass > 0.7
    assert high.bass < 0.1


def test_level_is_independent_of_volume_after_auto_gain():
    loud = feed(SpectrumAnalyzer(RATE), tone(440, seconds=2, amp=0.8))
    quiet = feed(SpectrumAnalyzer(RATE), tone(440, seconds=2, amp=0.05))
    assert loud.level > 0.5 and quiet.level > 0.5


def test_stereo_input_is_mixed_to_mono():
    an = SpectrumAnalyzer(RATE)
    mono = tone(440)
    stereo = np.stack([mono, mono], axis=1)
    f = feed(an, stereo)
    assert peak_freq(an, f) == pytest.approx(440, rel=0.15)


def test_release_is_slower_than_attack():
    an = SpectrumAnalyzer(RATE)
    on = feed(an, tone(60, seconds=0.5))
    after_one_block = an.process(np.zeros(BLOCK, dtype=np.float32))
    # Falls, but not to zero instantly: the wave decays smoothly after a beat.
    assert 0 < after_one_block.bass < on.bass


def test_sensitivity_scales_and_clamps_output():
    f = AudioFeatures(spectrum=np.array([0.2, 0.6], dtype=np.float32), bass=0.5, level=0.4)
    s = f.scaled(2.0)
    assert s.spectrum.tolist() == pytest.approx([0.4, 1.0])
    assert s.bass == 1.0 and s.level == pytest.approx(0.8)
