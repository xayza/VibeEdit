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
            "Máy này chưa cài faster-whisper nên không phiên âm được. Hãy cài bằng 'pip install faster-whisper' rồi thử lại; chưa thêm phụ đề nào.") from exc
    abs_path = media_path if os.path.isabs(media_path) else os.path.join(
        project.folder, media_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Không tìm thấy file media: {abs_path}")
    whisper = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _info = whisper.transcribe(abs_path)
    from .project import seconds_to_frames
    track = project.track(track_id)
    if track["kind"] != "text":
        raise ValueError("Phụ đề phiên âm thuộc về track chữ")
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


def snap_items_to_segments(items: list, segments: list, fps) -> list:
    """Pure mapping used by align_captions (unit-testable without a
    model): for each caption item, find the transcribed segment it
    overlaps most (by frame overlap); snap the item's start/duration
    to that segment's boundaries. Items with no overlapping segment
    are left untouched, and a snap that would create an overlap with
    a neighbour is skipped, never forced in."""
    from .project import frames_to_seconds, seconds_to_frames
    snapped = []
    ordered = sorted(items, key=lambda i: i["at"])
    for index, item in enumerate(ordered):
        start, end = int(item["at"]), int(item["at"]) + int(item["dur"])
        best, best_overlap = None, 0
        for seg in segments:
            s_at = seconds_to_frames(float(seg["start"]), fps)
            s_end = seconds_to_frames(float(seg["end"]), fps)
            overlap = min(end, s_end) - max(start, s_at)
            if overlap > best_overlap:
                best, best_overlap = seg, overlap
        if best is None:
            continue
        new_at = seconds_to_frames(float(best["start"]), fps)
        new_dur = seconds_to_frames(float(best["end"]), fps) - new_at
        if new_dur <= 0:
            continue
        prev_end = None
        if index > 0:
            prev = ordered[index - 1]
            prev_end = int(prev["at"]) + int(prev["dur"])
        next_start = None
        if index + 1 < len(ordered):
            next_start = int(ordered[index + 1]["at"])
        if (prev_end is not None and new_at < prev_end) or \
                (next_start is not None and new_at + new_dur > next_start):
            continue
        snapped.append({"item": item["id"], "from": (start, end),
                        "to": (new_at, new_dur)})
    return snapped


def align_captions(project, track_id: str, media_path: str,
                   model: str = "tiny") -> dict:
    """Re-time the text items on ``track_id`` to the speech segments
    detected in ``media_path`` by faster-whisper. Requires
    faster-whisper installed; otherwise raises the same clear error
    as transcribe_media (no captions are invented and no timings are
    changed). Returns the list of snaps actually applied."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Máy này chưa cài faster-whisper nên không căn thời gian phụ đề được. Hãy cài bằng 'pip install faster-whisper' rồi thử lại; chưa đổi timing nào.") from exc
    import os
    abs_path = media_path if os.path.isabs(media_path) else \
        os.path.join(project.folder, media_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Không tìm thấy file media: {abs_path}")
    whisper = WhisperModel(model, device="cpu", compute_type="int8")
    segments, _info = whisper.transcribe(abs_path)
    seg_list = [{"start": float(s.start), "end": float(s.end)}
                for s in segments]
    track = project.track(track_id)
    if track["kind"] != "text":
        raise ValueError("Phụ đề thuộc về track chữ")
    snaps = snap_items_to_segments(track["items"], seg_list,
                                   project.fps)
    by_id = {item["id"]: item for item in track["items"]}
    applied = []
    for snap in snaps:
        item = by_id[snap["item"]]
        item["at"], item["dur"] = snap["to"]
        applied.append(snap)
    track["items"].sort(key=lambda i: i["at"])
    project._bump()
    return {"snapped": len(applied), "snaps": applied}
