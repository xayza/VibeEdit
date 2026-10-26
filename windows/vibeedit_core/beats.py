"""Beat detection for the VibeEdit Windows port (Phase 4).

No ML model and no fake beat data: the audio file is decoded to mono
float samples with FFmpeg and an energy-onset detector runs over them.
A beat is a local energy maximum whose onset (energy rise over the
previous window) clears a threshold derived from the track's own
energy distribution. On synthetic burst audio this is precise (see
tests); on real music it is a rough grid, and callers should report
the measured result rather than claim musical accuracy.
"""

from __future__ import annotations

import array
import statistics
import subprocess

SAMPLE_RATE = 11025


def decode_mono(path: str, sample_rate: int = SAMPLE_RATE) -> list[float]:
    """Decode ``path`` to mono float32 samples via FFmpeg."""
    from .render import find_tool  # local import: render never imports beats
    cmd = [find_tool("ffmpeg"), "-v", "error", "-i", path, "-ac", "1",
           "-ar", str(sample_rate), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg could not decode {path}: "
            f"{proc.stderr[-500:].decode('utf-8', errors='replace')}")
    samples = array.array("f")
    samples.frombytes(proc.stdout)
    return list(samples)


def detect_beats(path: str, min_gap_s: float = 0.3,
                 sample_rate: int = SAMPLE_RATE) -> list[float]:
    """Return beat times (seconds) detected in an audio file.

    Method: RMS energy in 1024-sample windows stepped by 256 samples;
    onset = positive energy rise; a beat is a local onset maximum
    above median + 0.5 * (max - median), at least ``min_gap_s`` after
    the previous beat. Returns [] for silence or undecodable audio
    (the latter raises; silence is a legitimate empty result).
    """
    samples = decode_mono(path, sample_rate)
    if not samples:
        return []
    # Window 512 samples (~46 ms at 11025 Hz), hop 256. Beat times are
    # reported at the window centre: the onset rises when the window
    # first overlaps a burst, so the window start alone would sit
    # ~one window early; the centre lands on the burst itself.
    win, hop = 512, 256
    energies: list[float] = []
    for start in range(0, max(len(samples) - win, 0) + 1, hop):
        chunk = samples[start:start + win]
        energies.append(sum(v * v for v in chunk) / len(chunk))
    if not energies:
        return []
    onsets = [0.0] + [max(0.0, energies[i] - energies[i - 1])
                      for i in range(1, len(energies))]
    med = statistics.median(onsets)
    peak = max(onsets)
    if peak <= 0.0:
        return []
    threshold = med + 0.5 * (peak - med)
    beats: list[float] = []
    last_beat = -min_gap_s
    for i, onset in enumerate(onsets):
        if onset < threshold:
            continue
        if i > 0 and onset < onsets[i - 1]:
            continue
        if i + 1 < len(onsets) and onset < onsets[i + 1]:
            continue
        t = (i * hop + win // 2) / sample_rate
        if t - last_beat >= min_gap_s:
            beats.append(round(t, 3))
            last_beat = t
    return beats
