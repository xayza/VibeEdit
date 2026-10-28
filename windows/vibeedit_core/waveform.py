"""Real waveform peaks for the timeline's audio tracks.

No fake waveform: the file is decoded to mono float samples with
FFmpeg (same decoder as beats.py) and each bucket's RMS energy is
normalised by the loudest bucket, so silence is all zeros and a
loud passage is near 1.0. Peaks are data, not decoration.
"""

from __future__ import annotations

import math
import os


def waveform_peaks(path: str, buckets: int = 64) -> list[float]:
    """Return ``buckets`` RMS peaks in [0, 1] for an audio/video file."""
    if buckets <= 0:
        raise ValueError("buckets phải là số dương")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Không có file media như vậy: {path}")
    from .beats import decode_mono

    samples = decode_mono(path)
    if not samples:
        return [0.0] * buckets
    per = max(1, math.ceil(len(samples) / buckets))
    peaks = []
    for i in range(buckets):
        chunk = samples[i * per:(i + 1) * per]
        if not chunk:
            peaks.append(0.0)
        else:
            peaks.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
    top = max(peaks) or 0.0
    if top <= 0.0:
        return [0.0] * buckets
    return [round(v / top, 3) for v in peaks]
