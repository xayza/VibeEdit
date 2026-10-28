"""Scene-cut detection and cut-list correction for the Windows port.

Faithful to the original's ``media.cuts`` semantics, read from
``CommandCatalog+Media.swift`` (not from the tool name alone):

- ``media.cuts`` is an EDIT on the cut list of an *analysed* media:
  "add cuts or remove candidates at source seconds (a removal
  matches within one sample interval; removing an added cut takes
  it back). Shots and statistics in media.analysis follow.
  Corrections live in the record and are dropped when the file is
  measured again. Returns the corrected cuts."

What the Windows port does, mapped onto that semantics:

- Measurement: the original measures picture samples and scores
  each candidate (``minScore``, default 0.1, over its own
  cut-difference score). This build measures with FFmpeg's
  ``scene`` filter instead — a different scale, so the threshold
  is named ``threshold`` (default 0.4, the usual scene-filter
  working point) and is never claimed to equal the original's
  minScore. ``showinfo`` frame times are the samples, so "one
  sample interval" for a removal match is one frame (1/fps).
- Detection runs on first use and is stored on the media record;
  later calls correct that stored list. ``remeasure=True`` measures
  again and drops earlier corrections, exactly as the original
  describes. Detections closer than 0.5 s are collapsed to the
  first one: a real cut is a single-frame event, while a dissolve
  or fast motion otherwise reports a run of high-scene frames as
  many "cuts".
- No cut list is ever invented for audio-only media: detection
  raises a clear error when the file has no video stream.
"""

from __future__ import annotations

import os
import re
import subprocess

from .render import find_tool, probe_media

#: Detections closer than this (seconds) collapse to the first one.
MERGE_WINDOW_S = 0.5

#: Default FFmpeg scene-filter threshold (0..1).
DEFAULT_THRESHOLD = 0.4

_SHOWINFO_TIME_RE = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def _parse_showinfo_times(stderr_text: str) -> list[float]:
    """Frame times from ``showinfo`` lines only. Other FFmpeg log
    lines never contain a showinfo pts_time, so a plain regex over
    the whole log is safe as long as it requires the showinfo
    marker on the line."""
    times: list[float] = []
    for line in stderr_text.splitlines():
        if "showinfo" not in line:
            continue
        match = _SHOWINFO_TIME_RE.search(line)
        if match:
            times.append(float(match.group(1)))
    return times


def _merge_close(times: list[float],
                 window: float = MERGE_WINDOW_S) -> list[float]:
    merged: list[float] = []
    for t in sorted(times):
        if merged and t - merged[-1] < window:
            continue
        merged.append(round(t, 3))
    return merged


def detect_cuts(path: str, threshold: float = DEFAULT_THRESHOLD,
                ffmpeg: str | None = None) -> dict:
    """Detect scene cuts in ``path`` with the FFmpeg scene filter.

    Returns ``{cuts, detected_frames, threshold}`` where ``cuts``
    is the merged list and ``detected_frames`` the raw per-frame
    times. Raises ValueError for a missing file, a bad threshold,
    an FFmpeg failure, or a file with no video stream (an
    audio-only file has no picture to cut).
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Không tìm thấy file media: {path}")
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold phải nằm trong khoảng 0–1 (không tính biên)")
    # FFmpeg exits 0 on an audio-only file (it simply ignores -vf
    # with no video stream to filter), so the video-stream check
    # must be explicit — never report "no cuts" for a file that
    # has no picture at all.
    try:
        info = probe_media(path)
    except Exception as exc:
        raise ValueError(
            f"Không probe được media để phát hiện cảnh: {exc}") from None
    if "width" not in info:
        raise ValueError(
            "Phát hiện cảnh cần video stream; file này không có (chỉ có audio?)")
    tool = ffmpeg or find_tool("ffmpeg")
    cmd = [tool, "-hide_banner", "-i", path, "-vf",
           f"select='gt(scene,{threshold})',showinfo",
           "-f", "null", "-"]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=300)
    if proc.returncode != 0:
        raise ValueError(
            f"Phát hiện cảnh thất bại (đây có phải file video có video stream?): {proc.stderr.strip()[-400:]}")
    raw = _parse_showinfo_times(proc.stderr or "")
    return {"cuts": _merge_close(raw),
            "detected_frames": [round(t, 3) for t in sorted(raw)],
            "threshold": threshold}


def _parse_seconds(value, label: str) -> list[float]:
    """Comma-separated source seconds from a tool argument: a
    string ("1.5, 2"), a number, or a list of numbers/strings."""
    if value is None:
        return []
    if isinstance(value, (int, float)):
        items = [value]
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError(f"{label} phải là số giây, cách nhau bằng dấu phẩy")
    out: list[float] = []
    for item in items:
        try:
            seconds = float(item)
        except (TypeError, ValueError):
            raise ValueError(
                f"{label} có mục không phải số: {item!r}") from None
        if seconds < 0:
            raise ValueError(f"{label} có giây âm: {seconds}")
        out.append(round(seconds, 3))
    return out


def apply_cut_corrections(detected: list[float], current: list[float],
                          add=None, remove=None, clear: bool = False,
                          tolerance: float = 0.04,
                          duration: float | None = None) -> dict:
    """Apply one correction step to a cut list (pure function, easy
    to test without FFmpeg).

    ``detected`` is the measured list, ``current`` the corrected
    list so far. With ``clear`` the earlier corrections are dropped
    first (base becomes ``detected``), then this call's add/remove
    apply. A removal matches the nearest cut within ``tolerance``
    (one sample interval = one frame at the media fps); a removal
    that matches nothing is reported in ``removed_unmatched``,
    never silently swallowed and never fatal to the other edits.
    Returns ``{cuts, added, removed, removed_unmatched}``.
    """
    base = list(detected) if clear else list(current)
    added = _parse_seconds(add, "add")
    removed = _parse_seconds(remove, "remove")
    if duration is not None:
        for seconds in added:
            if seconds > duration:
                raise ValueError(
                    f"thêm cut {seconds} vượt quá thời lượng media ({duration} giây)")
    cuts = sorted(set(round(t, 3) for t in base))
    for seconds in added:
        if seconds not in cuts:
            cuts.append(seconds)
    cuts.sort()
    removed_applied: list[float] = []
    removed_unmatched: list[float] = []
    for seconds in removed:
        if not cuts:
            removed_unmatched.append(seconds)
            continue
        nearest = min(cuts, key=lambda c: abs(c - seconds))
        if abs(nearest - seconds) <= tolerance:
            cuts.remove(nearest)
            removed_applied.append(nearest)
        else:
            removed_unmatched.append(seconds)
    return {"cuts": cuts, "added": added, "removed": removed_applied,
            "removed_unmatched": removed_unmatched}
