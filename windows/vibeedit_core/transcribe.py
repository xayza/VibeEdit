"""Phase 3 transcription entry point — real local provider only.

This calls faster-whisper when it is installed on the machine. It
does NOT bundle, fake or stub a transcription model: when
faster-whisper is absent the function raises a clear
"not installed" error naming the install command, and nothing is
written to the project. When present, segments are added as text
items on the captions track (or the track given) and saved by the
caller (CLI/MCP save after this returns).

Phase 4 (documented in windows/README.md) would add more
providers behind this same interface: a provider is any object
with ``transcribe(path, model) -> [(start_s, end_s, text)]``.
"""

from __future__ import annotations

import os


def transcribe_media(project, media_path: str, track_id: str = "t1",
                     model: str = "small") -> list[dict]:
    """Transcribe ``media_path`` with faster-whisper and add the
    segments as text items. Returns the added items."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed on this machine, so "
            "transcription cannot run. Install it with "
            "'pip install faster-whisper' and retry; no captions "
            "were added.") from exc
    abs_path = media_path if os.path.isabs(media_path) else os.path.join(
        project.folder, media_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Media file not found: {abs_path}")
    whisper = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _info = whisper.transcribe(abs_path)
    from .project import seconds_to_frames
    track = project.track(track_id)
    if track["kind"] != "text":
        raise ValueError("Transcription captions belong on a text track")
    added = []
    for segment in segments:
        at = seconds_to_frames(float(segment.start), project.fps)
        dur = seconds_to_frames(float(segment.end), project.fps) - at
        if dur <= 0:
            continue
        try:
            added.append(project.add_text(track_id, segment.text.strip(),
                                          at, dur))
        except ValueError:
            # Overlapping segments are skipped, never forced in.
            continue
    return added
