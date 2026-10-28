"""Round 8: state/workflow and local-data tools for the Windows port.

Every function here works only with data the project already holds
(project JSON, analysis records, caption items, library entries) plus
stdlib / FFmpeg measurements. Nothing here invents AI output: tools
that genuinely need a provider (image generation, voice cloning, a
library-generation plugin) stay honest in ``mcp.py`` and are listed
in ``windows/PARITY.md`` with their blocker.

Original specs (read before coding, VibeEdit Swift tree, read-only):
- ``CommandCatalog+Clips.swift``: ``clip.motion`` (MotionPreset data in
  ``Packages/VibeEditCore/Sources/VibeEditProject/Keyframes.swift``)
  and ``clip.reframe``; ``clip.change-framing`` is a UIAction
  (``ProjectDocument+UIActions.swift``) that cycles ReframePreset
  (``Project.swift``: wide/medium/close/left/right).
- ``CommandCatalog+BatchFixes.swift``: ``music.replace``.
- ``CommandCatalog+Media.swift``: ``narration.windows``,
  ``media.describe`` / ``media.description`` / ``media.digest``,
  ``speech.rate`` (a MEASUREMENT from transcript words, not a TTS
  setting).
- ``CommandCatalog+Ledger.swift``: ``outcomes.import`` / ``outcomes.map``.
- ``CommandCatalog+Plan.swift``: ``run.append`` / ``run.log`` /
  ``run.status`` / ``run.checklist``. The UIAction run-panel
  actions (``run.dismiss`` / ``run.toggle`` / ``run.follow`` /
  ``run.fix-issues`` / ``run.another-recipe``) moved to
  ``round9.py`` in round 9: dismiss/toggle/follow are real
  persisted panel state, fix-issues/another-recipe return the
  exact follow-up request text for the calling agent (headless
  has no agent session to deliver to).
- ``CommandCatalog+Images.swift``: ``image.style`` (a project style
  lock — pure state), ``image.disclose`` (text items over generated
  pictures), ``image.generate`` (needs a provider — stays honest).
- ``CommandCatalog+Library.swift``: ``library.export-pack`` /
  ``library.import-pack`` / ``library.analyze``.
- ``CommandCatalog+Plugins.swift`` / ``+PluginViews.swift``: plugin
  overlays, actions, views, proposals, replacement (implemented in
  ``plugins.py``; the view host here is a JSON component model
  declared in the manifest, because the original's views are
  SwiftUI and cannot run headless).
"""

from __future__ import annotations

import copy
import csv
import io
import json
import math
import os
import re
import zipfile

from .project import (
    fps_value,
    frames_to_seconds,
    run_panel_snapshot,
    seconds_to_frames,
)

# ---------------------------------------------------------------------------
# clip.motion — MotionPreset data, verbatim values from the original
# Keyframes.swift (zoom 12% Ken Burns; text moves take 0.3 s).
# ---------------------------------------------------------------------------

MOTION_PRESETS = {
    "zoom-in": {"title": "Slow zoom in", "text": False,
                "keys": {"zoom": [{"t": 0, "value": 1, "ease": "linear"},
                                {"t": 1, "value": 1.12}]}},
    "zoom-out": {"title": "Slow zoom out", "text": False,
                 "keys": {"zoom": [{"t": 0, "value": 1.12, "ease": "linear"},
                                 {"t": 1, "value": 1}]}},
    "pan-left": {"title": "Pan left", "text": False,
                 "keys": {"zoom": [{"t": 0, "value": 1.12}],
                          "pan": [{"t": 0, "value": {"width": 0.05},
                                   "ease": "linear"},
                                  {"t": 1, "value": {"width": -0.05}}]}},
    "pan-right": {"title": "Pan right", "text": False,
                  "keys": {"zoom": [{"t": 0, "value": 1.12}],
                           "pan": [{"t": 0, "value": {"width": -0.05},
                                    "ease": "linear"},
                                   {"t": 1, "value": {"width": 0.05}}]}},
    "pan-up": {"title": "Pan up", "text": False,
               "keys": {"zoom": [{"t": 0, "value": 1.12}],
                        "tilt": [{"t": 0, "value": {"height": -0.05},
                                  "ease": "linear"},
                                 {"t": 1, "value": {"height": 0.05}}]}},
    "pan-down": {"title": "Pan down", "text": False,
                 "keys": {"zoom": [{"t": 0, "value": 1.12}],
                          "tilt": [{"t": 0, "value": {"height": 0.05},
                                    "ease": "linear"},
                                   {"t": 1, "value": {"height": -0.05}}]}},
    "fade-in-out": {"title": "Fade in and out", "text": True,
                    "keys": {"opacity": [{"t": 0, "value": 0, "ease": "out"},
                                      {"s": 0.3, "value": 1, "ease": "linear"},
                                      {"s": -0.3, "value": 1, "ease": "in"},
                                      {"t": 1, "value": 0}]}},
    "pop-in": {"title": "Pop in", "text": True,
               "keys": {"zoom": [{"t": 0, "value": 0.6, "ease": "out"},
                               {"s": 0.3, "value": 1.08},
                               {"s": 0.45, "value": 1}],
                       "opacity": [{"t": 0, "value": 0, "ease": "out"},
                                   {"s": 0.15, "value": 1}]}},
    "slide-up": {"title": "Slide up", "text": True,
                 "keys": {"tilt": [{"t": 0, "value": {"height": -0.04},
                                    "ease": "out"},
                                   {"s": 0.3, "value": 0}],
                         "opacity": [{"t": 0, "value": 0, "ease": "out"},
                                     {"s": 0.3, "value": 1}]}},
    "zoom-punch": {"title": "Zoom punch", "text": True,
                   "keys": {"zoom": [{"t": 0, "value": 1.25, "ease": "out"},
                                   {"s": 0.3, "value": 1}]}},
}

# Original motion properties -> Windows keyframe properties.
# Windows zoompan uses x/y as 0..1 crop-window fractions, so a pan
# share becomes 0.5 + share (centred), and a tilt share becomes
# 0.5 + share on y. Windows "tilt" is rotation in degrees, which is
# what the original's "rotation" maps to; the original's "tilt"
# (vertical pan) maps to y, never to rotation.
_MOTION_PROP_MAP = {
    "zoom": "scale",
    "pan": "x",
    "tilt": "y",
    "opacity": "opacity",
    "volume": "volume",
    "rotation": "tilt",
    "x": "x",
    "y": "y",
    "scale": "scale",
}


def _motion_time(point: dict, dur_frames: int, fps) -> int:
    """One original motion key time -> Windows frame offset."""
    if "frame" in point:
        return int(point["frame"])
    if "s" in point:
        seconds = float(point["s"])
        if seconds < 0:
            seconds = dur_frames / fps + seconds
        return int(round(seconds * fps))
    if "t" in point:
        return int(round(float(point["t"]) * dur_frames))
    raise ValueError(
        "Keyframe motion cần 't' (phân số), 's' (giây) hoặc 'frame'")


def _motion_value(prop: str, value):
    """One original motion key value -> Windows keyframe value."""
    target = _MOTION_PROP_MAP[prop]
    if isinstance(value, dict):
        if "width" in value:
            return target, 0.5 + float(value["width"])
        if "height" in value:
            return target, 0.5 + float(value["height"])
        raise ValueError(
            f"Giá trị motion cho {prop!r} phải mang 'width' hoặc 'height'")
    return target, float(value)


def motion_keys_to_windows(keys: dict, dur_frames: int, fps) -> list[dict]:
    """Convert original {prop: [{t|s|frame, value}]} to Windows
    keyframes [{at, x/y/scale/opacity/volume/tilt}]."""
    by_frame: dict[int, dict] = {}
    for prop, points in keys.items():
        if prop not in _MOTION_PROP_MAP:
            raise ValueError(f"Thuộc tính motion không rõ: {prop!r}")
        if not isinstance(points, list):
            raise ValueError(
                f"Keyframe motion cho {prop!r} phải là danh sách")
        for point in points:
            if not isinstance(point, dict) or "value" not in point:
                raise ValueError(
                    f"Keyframe motion cho {prop!r} cần có 'value'")
            at = _motion_time(point, dur_frames, fps)
            if not 0 <= at <= dur_frames:
                raise ValueError(
                    "Thời gian keyframe motion phải nằm trong mục")
            target, value = _motion_value(prop, point["value"])
            by_frame.setdefault(at, {"at": at})[target] = value
    return [by_frame[at] for at in sorted(by_frame)]


def apply_motion(proj, item_id: str, preset=None, keyframes=None,
                 focus=None, within=None) -> dict:
    """clip.motion: preset (or 'none') or keyframes JSON, replacing
    the item's animation. The result is stored with the project's
    keyframe machinery, so the renderer's zoompan/tilt/opacity paths
    animate it; focus framing needs a viewer band and is refused
    with a pointer to clip_reframe instead of being faked."""
    if focus is not None or within is not None:
        raise ValueError(
            "clip.motion focus framing cần dải viewer vẫn hiển thị (giá trị viewer trực tiếp); dùng clip_reframe cho cửa sổ reframe đã lưu")
    _, item = proj.item(item_id)
    dur = int(item["dur"])
    fps = fps_value(proj.data["format"]["fps"])
    if preset is not None:
        if preset == "none":
            proj.set_keyframes(item_id, [])
            item.pop("motion_preset", None)
            proj._bump()
            return {"item": item_id, "preset": "none",
                    "keyframes": [], "rev": proj.rev}
        spec = MOTION_PRESETS.get(preset)
        if spec is None:
            raise ValueError(
                f"Preset motion không rõ: {preset!r} (đã biết: {', '.join(sorted(MOTION_PRESETS))}, không có)")
        frames = motion_keys_to_windows(spec["keys"], dur, fps)
        proj.set_keyframes(item_id, frames)
        item["motion_preset"] = preset
        proj._bump()
        return {"item": item_id, "preset": preset,
                "keyframes": item.get("keyframes"),
                "title": spec["title"], "rev": proj.rev}
    if keyframes is None:
        raise ValueError(
            "clip.motion cần preset hoặc JSON keyframes")
    if isinstance(keyframes, str):
        try:
            keyframes = json.loads(keyframes)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"keyframes clip.motion không phải JSON hợp lệ: {exc}") from exc
    if not isinstance(keyframes, dict):
        raise ValueError(
            "keyframes clip.motion phải là object {property: [{t|s|frame, value}]}")
    frames = motion_keys_to_windows(keyframes, dur, fps)
    proj.set_keyframes(item_id, frames)
    item["motion_preset"] = "custom"
    proj._bump()
    return {"item": item_id, "preset": "custom",
            "keyframes": item.get("keyframes"), "rev": proj.rev}


# ---------------------------------------------------------------------------
# clip.change-framing — ReframePreset cycle (UIAction, Project.swift).
# ---------------------------------------------------------------------------

REFRAME_PRESETS = [
    {"id": "wide", "title": "Wide", "zoom": 1, "pan": 0, "tilt": 0},
    {"id": "medium", "title": "Medium", "zoom": 1.15, "pan": 0, "tilt": 0},
    {"id": "close", "title": "Close-up", "zoom": 1.3, "pan": 0, "tilt": 0},
    {"id": "left", "title": "Left emphasis", "zoom": 1.22,
     "pan": -120, "tilt": 0},
    {"id": "right", "title": "Right emphasis", "zoom": 1.22,
     "pan": 120, "tilt": 0},
]


def change_framing(proj, item_id: str) -> dict:
    """Cycle a video clip through wide -> medium -> close -> left
    -> right -> wide, storing reframePreset + transform. The
    transform zoom renders (fill scale); pan/tilt render as crop
    offsets (see render._crop_offsets), so every preset changes
    the rendered frame, not just stored state."""
    _, item = proj.item(item_id)
    if "media" not in item:
        raise ValueError("change-framing chỉ áp dụng cho clip media")
    current = item.get("reframePreset")
    ids = [p["id"] for p in REFRAME_PRESETS]
    nxt = REFRAME_PRESETS[0] if current not in ids else \
        REFRAME_PRESETS[(ids.index(current) + 1) % len(ids)]
    item["reframePreset"] = nxt["id"]
    item["transform"] = {"zoom": nxt["zoom"], "pan": nxt["pan"],
                         "tilt": nxt["tilt"]}
    proj._bump()
    return {"item": item_id, "preset": nxt["id"],
            "title": nxt["title"], "transform": item["transform"],
            "rev": proj.rev}


# ---------------------------------------------------------------------------
# music.replace — BatchFixes spec.
# ---------------------------------------------------------------------------

def music_replace(proj, media_id=None, library_id=None,
                  loop: bool = True) -> dict:
    """Swap the music bed: Music-track clips go, the new sound
    covers their span (first clip's start to last clip's end) on
    the first clip's track, keeping the old level (volume, muted)
    and fades. Shorter than the span, it repeats unless loop is
    false (then one clip, and the result says shortened)."""
    if library_id is not None:
        entry = next((e for e in proj.data.get("library", [])
                      if e["id"] == library_id), None)
        if entry is None:
            raise KeyError(f"Mục thư viện không rõ: {library_id}")
        media_id = (entry.get("item") or {}).get("media")
        if not media_id:
            raise ValueError(
                "Mục thư viện không phải clip audio nên không thay được nhạc nền")
    if media_id is None:
        raise ValueError("music.replace cần media hoặc library")
    medium = proj.media(media_id)
    if medium.get("kind") != "audio" and not medium.get("hasAudio"):
        raise ValueError("music.replace cần media audio")
    music_tracks = [t for t in proj.data["tracks"]
                    if t.get("role") == "music"]
    clips = []
    for track in music_tracks:
        for item in track["items"]:
            if "media" in item:
                clips.append((track, item))
    if not clips:
        raise ValueError(
            "music.replace cần các clip track Music có sẵn để phủ")
    clips.sort(key=lambda ti: int(ti[1]["at"]))
    first_track, first = clips[0]
    span_start = int(first["at"])
    span_end = max(int(i["at"]) + int(i["dur"]) for _, i in clips)
    span = span_end - span_start
    volume = first.get("volume")
    muted = first.get("muted")
    fade_in = first.get("fadeIn")
    fade_out = first.get("fadeOut")
    removed = [i["id"] for _, i in clips]
    for _, item in clips:
        proj.delete(item["id"])
    new_dur = int(medium.get("frames") or 0)
    if not new_dur and medium.get("duration"):
        new_dur = int(round(float(medium["duration"])
                            * fps_value(proj.data["format"]["fps"])))
    if new_dur <= 0:
        raise ValueError("Media thay thế không có thời lượng dùng được")
    added = []
    at = span_start
    looped = False
    while at < span_end:
        take = min(new_dur, span_end - at)
        clip = proj.add_clip(media_id, first_track["id"], at,
                             dur=take)
        if volume is not None:
            clip["volume"] = volume
        if muted is not None:
            clip["muted"] = muted
        if fade_in is not None:
            clip["fadeIn"] = fade_in
        if fade_out is not None:
            clip["fadeOut"] = fade_out
        added.append(clip)
        at += take
        if at < span_end:
            if not loop:
                break
            looped = True
    proj._bump()
    return {"track": first_track["id"], "removed": removed,
            "items": [c["id"] for c in added], "at": span_start,
            "duration": span, "looped": looped,
            "shortened": (not loop) and added
            and int(added[-1]["at"]) + int(added[-1]["dur"]) < span_end,
            "rev": proj.rev}


# ---------------------------------------------------------------------------
# Shared timeline-word helpers (captions + voiceover spans).
# ---------------------------------------------------------------------------

def timeline_words(proj) -> list[dict]:
    """Caption words with timeline times (even split per item, the
    same computation as captions_words) plus, when an analysed
    media's transcript words exist, they are NOT timeline words and
    are deliberately left out here."""
    words = []
    fps = fps_value(proj.data["format"]["fps"])
    for track in proj.data["tracks"]:
        for item in track["items"]:
            if "text" not in item:
                continue
            parts = item["text"].split()
            if not parts:
                continue
            per = item["dur"] / len(parts)
            for i, word in enumerate(parts):
                words.append({
                    "item": item["id"], "word": word,
                    "at": int(item["at"] + i * per), "dur": per,
                    "at_s": frames_to_seconds(
                        int(item["at"] + i * per), fps),
                    "end_s": frames_to_seconds(
                        int(item["at"] + (i + 1) * per), fps)})
    words.sort(key=lambda w: w["at_s"])
    return words


def _spans(items) -> list[tuple[float, float]]:
    spans = sorted((float(i["at_s"]), float(i["end_s"]))
                   for i in items)
    merged: list[list[float]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _overlap_share(spans, start: float, end: float) -> float:
    if end <= start:
        return 0.0
    hit = 0.0
    for s, e in spans:
        hit += max(0.0, min(e, end) - max(s, start))
    return round(hit / (end - start), 4)


def narration_windows(proj, min_seconds: float = 1.0,
                      rate=None) -> dict:
    """Stretches of at least min_seconds with no spoken word
    (caption words) and no voiceover item, with anchors, covered
    shares and a word budget when rate (units/second) is given.
    Speech-map levels are not rendered here (that is the
    media-level mix render of the original's `levels` flag); the
    window list itself is computed from real timeline data."""
    if min_seconds <= 0:
        raise ValueError("narration.windows cần min_seconds > 0")
    fps = fps_value(proj.data["format"]["fps"])
    total_s = proj.duration_seconds()
    words = timeline_words(proj)
    spoken = _spans([{"at_s": w["at_s"], "end_s": w["end_s"]}
                     for w in words])
    voiceover = []
    for track in proj.data["tracks"]:
        if track.get("role") == "voiceover":
            for item in track["items"]:
                voiceover.append({
                    "at_s": frames_to_seconds(int(item["at"]), fps),
                    "end_s": frames_to_seconds(
                        int(item["at"]) + int(item["dur"]), fps)})
    busy = _spans([{"at_s": s, "end_s": e}
                   for s, e in spoken + _spans(voiceover)])
    cuts = sorted({int(i["at"]) for t in proj.data["tracks"]
                   for i in t["items"] if "media" in i})
    cuts_s = [frames_to_seconds(c, fps) for c in cuts]
    beats = list(proj.beat_list())
    markers = sorted(proj.data.get("markers", []),
                     key=lambda m: frames_to_seconds(int(m["at"]), fps))
    music_spans = [(frames_to_seconds(int(i["at"]), fps),
                    frames_to_seconds(int(i["at"]) + int(i["dur"]), fps))
                   for t in proj.data["tracks"]
                   if t.get("role") == "music" for i in t["items"]
                   if "media" in i]
    main_spans = [(frames_to_seconds(int(i["at"]), fps),
                   frames_to_seconds(int(i["at"]) + int(i["dur"]), fps))
                  for t in proj.data["tracks"]
                  if t.get("role") == "main" for i in t["items"]
                  if "media" in i]
    windows = []
    cursor = 0.0
    for start, end in busy + [(total_s, total_s)]:
        if start - cursor >= min_seconds and cursor < total_s:
            w_end = min(start, total_s)
            if w_end - cursor >= min_seconds:
                before = [w for w in words if w["end_s"] <= cursor]
                after_word = before[-1]["word"] if before else None
                inside_cuts = [c for c in cuts_s
                               if cursor < c < w_end]
                first_cut = inside_cuts[0] if inside_cuts else None
                inside_beats = [b for b in beats
                                if cursor < b < w_end]
                first_beat = inside_beats[0] if inside_beats else None
                section_markers = [m for m in markers
                                   if frames_to_seconds(int(m["at"]),
                                                        fps) <= cursor]
                section = (section_markers[-1].get("text")
                           if section_markers else None)
                starts_inside = [m.get("text") for m in markers
                                 if cursor < frames_to_seconds(
                                     int(m["at"]), fps) < w_end]
                windows.append({
                    "at": frames_to_seconds(
                        int(round(cursor * fps)), fps),
                    "end": frames_to_seconds(
                        int(round(w_end * fps)), fps),
                    "atSeconds": round(cursor, 3),
                    "endSeconds": round(w_end, 3),
                    "anchors": {
                        "afterWord": after_word,
                        "firstCut": first_cut,
                        "firstBeat": first_beat,
                        "section": section,
                        "sectionStartsInside": starts_inside},
                    "covered": {
                        "music": _overlap_share(music_spans, cursor,
                                                w_end),
                        "footage": _overlap_share(main_spans, cursor,
                                                  w_end)},
                    "budget": (round(rate * (w_end - cursor), 2)
                               if rate is not None else None)})
        cursor = max(cursor, end)
    return {"windows": windows, "minSeconds": min_seconds,
            "rate": rate, "projectSeconds": round(total_s, 3),
            "note": "Windows are timeline gaps between caption words "
                    "and voiceover items; analysis-transcript words "
                    "are source times, not timeline times, and are "
                    "not used here."}


# ---------------------------------------------------------------------------
# outcomes — Ledger spec: stored per export, mapped onto sections.
# ---------------------------------------------------------------------------

def _normalise_curve(payload) -> tuple[list[dict], dict]:
    """Accept the original's three shapes: {curve, totals}, a list
    of points, or CSV text. Returns (curve, totals). Curve points
    keep their unit: 't' seconds or 'position' percent."""
    totals: dict = {}
    if isinstance(payload, str):
        rows = list(csv.DictReader(io.StringIO(payload)))
        if not rows:
            raise ValueError("CSV outcomes không có dòng nào")
        t_key = next((k for k in rows[0]
                      if k and ("position" in k.lower()
                                or k.lower().strip() in
                                ("t", "time", "seconds"))), None)
        r_key = next((k for k in rows[0]
                      if k and "retention" in k.lower()), None)
        if t_key is None or r_key is None:
            raise ValueError(
                "CSV outcomes cần cột time/position và cột retention")
        curve = []
        for row in rows:
            try:
                t_val = float(row[t_key])
                r_val = float(row[r_key])
            except (TypeError, ValueError):
                continue
            if "position" in t_key.lower():
                curve.append({"position": t_val, "retention": r_val})
            else:
                curve.append({"t": t_val, "retention": r_val})
        return curve, totals
    if isinstance(payload, list):
        curve = []
        for point in payload:
            if not isinstance(point, dict):
                raise ValueError("điểm curve outcomes phải là object")
            if "t" in point:
                curve.append({"t": float(point["t"]),
                              "retention": float(point["retention"])})
            elif "position" in point:
                curve.append({"position": float(point["position"]),
                              "retention": float(point["retention"])})
            else:
                raise ValueError(
                    "điểm curve outcomes cần 't' hoặc 'position'")
        return curve, totals
    if isinstance(payload, dict):
        totals = dict(payload.get("totals") or {})
        raw = payload.get("curve") or []
        curve, _ = _normalise_curve(raw)
        return curve, totals
    raise ValueError(
        "payload outcomes phải là JSON {curve, totals}, danh sách điểm, hoặc text CSV")


def import_outcomes(proj, export_id: str, payload) -> dict:
    """Import an export's retention curve + totals, stored per
    export in project data (the original stores .vibeedit/outcomes
    per export; the Windows port stores the same records in the
    project, so they ride save/backup/undo). Re-import replaces."""
    if not export_id:
        raise ValueError("outcomes.import cần export id")
    curve, totals = _normalise_curve(payload)
    if not curve:
        raise ValueError("outcomes.import không tìm thấy điểm curve nào")
    store = proj.data.setdefault("outcomes", {})
    store[export_id] = {"curve": curve, "totals": totals}
    proj._bump()
    return {"export": export_id, "points": len(curve),
            "totals": totals, "rev": proj.rev}


def _retention_at(curve, x: float, time_based: bool,
                  duration: float) -> float | None:
    """Interpolate retention at timeline seconds x. Time-based
    curves use seconds directly; position curves use percent of
    the project duration."""
    pts = []
    for point in curve:
        if time_based:
            pts.append((float(point["t"]), float(point["retention"])))
        else:
            pts.append((float(point["position"]) / 100.0 * duration,
                        float(point["retention"])))
    pts.sort()
    if not pts or x < pts[0][0] or x > pts[-1][0]:
        return None
    for (x0, r0), (x1, r1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return r0
            return r0 + (r1 - r0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def map_outcomes(proj, export_id: str, window_seconds: float = 5.0) -> dict:
    """Map an imported export's outcomes onto its sections
    (project markers in time order, else the whole video), with
    per-section start/end retention, change, drop/lift points,
    replay peak and views at section start; then the whole
    curve's largest drops with the caption words heard near them.
    Retention stays in the file's unit; viewsAtStart normalises
    percent to a fraction when the file used percent."""
    store = proj.data.get("outcomes") or {}
    record = store.get(export_id)
    if record is None:
        raise KeyError(
            f"Không có outcomes đã import cho export {export_id!r}; hãy chạy outcomes.import trước")
    curve = record["curve"]
    totals = record.get("totals") or {}
    time_based = "t" in curve[0]
    duration = proj.duration_seconds()
    fps = fps_value(proj.data["format"]["fps"])
    markers = sorted(proj.data.get("markers", []),
                     key=lambda m: int(m["at"]))
    bounds = [0.0] + [frames_to_seconds(int(m["at"]), fps)
                      for m in markers] + [duration]
    bounds = sorted(set(round(b, 6) for b in bounds if 0 <= b <= duration))
    if len(bounds) < 2:
        bounds = [0.0, duration]
    views = totals.get("views")
    words = timeline_words(proj)

    def _words_near(t: float) -> list[str]:
        return [w["word"] for w in words
                if abs(w["at_s"] - t) <= window_seconds]

    def _as_fraction(retention):
        if retention is None:
            return None
        return retention / 100.0 if retention > 1 else retention

    sections = []
    for start, end in zip(bounds, bounds[1:]):
        r_start = _retention_at(curve, start, time_based, duration)
        r_end = _retention_at(curve, end, time_based, duration)
        pts = []
        for point in curve:
            x = (float(point["t"]) if time_based else
                 float(point["position"]) / 100.0 * duration)
            if start <= x <= end:
                pts.append((x, float(point["retention"])))
        drop = lift = peak = None
        for (x0, r0), (x1, r1) in zip(pts, pts[1:]):
            change = r1 - r0
            if drop is None or change < drop["change"]:
                drop = {"at": x1, "change": change,
                        "words": _words_near(x1)}
            if lift is None or change > lift["change"]:
                lift = {"at": x1, "change": change}
        if pts:
            px, pr = max(pts, key=lambda p: p[1])
            peak = {"at": px, "retention": pr}
        sections.append({
            "start": start, "end": end,
            "startRetention": r_start, "endRetention": r_end,
            "change": (r_end - r_start
                       if r_start is not None
                       and r_end is not None else None),
            "drop": drop, "lift": lift, "replayPeak": peak,
            "viewsAtStart": (views * _as_fraction(r_start)
                             if views is not None
                             and r_start is not None else None)})
    drops = []
    all_pts = []
    for point in curve:
        x = (float(point["t"]) if time_based else
             float(point["position"]) / 100.0 * duration)
        all_pts.append((x, float(point["retention"])))
    all_pts.sort()
    for (x0, r0), (x1, r1) in zip(all_pts, all_pts[1:]):
        drops.append({"at": x1, "from": r0, "to": r1,
                      "change": r1 - r0,
                      "section": next(
                          (s for s in sections
                           if s["start"] <= x1 <= s["end"]), None),
                      "words": _words_near(x1)})
    drops.sort(key=lambda d: d["change"])
    return {"export": export_id, "sections": sections,
            "largestDrops": drops[:10],
            "note": "Retention is in the file's unit (percent or "
                    "fraction); viewsAtStart normalises percent."}


# ---------------------------------------------------------------------------
# run log — Plan spec: append-only entries + derived checklist.
# ---------------------------------------------------------------------------

RUN_STAGE_IDS = ("intake", "survey", "story", "rough-cut", "rhythm",
                 "voiceover", "sound", "captions", "colour", "effects",
                 "review", "export", "learn", "cut", "color")


def append_run_entry(proj, kind: str, fields: dict | None = None) -> dict:
    """Append one run-log entry (project-stored; the original uses
    .vibeedit/run-log.jsonl, the Windows port stores the same
    entries in the project so they ride save/backup/undo).
    Enforces the spec's gates that are checkable here: kind is
    1-40 chars and never 'gate'; a stage marked done without
    evidence is stored unverified; a skipped stage needs a reason;
    marking review done while a plan-required stage is still open
    returns stage_pending instead of done."""
    fields = dict(fields or {})
    if not isinstance(kind, str) or not 1 <= len(kind) <= 40 \
            or kind == "gate":
        raise ValueError(
            "kind của run.append phải dài 1–40 ký tự và không phải 'gate'")
    entry: dict = {"kind": kind}
    entry.update(fields)
    if kind == "stage":
        stage = fields.get("stage")
        status = fields.get("status", "started")
        if status == "done" and not fields.get("evidence"):
            entry["unverified"] = True
        if status == "skipped" and not fields.get("reason"):
            raise ValueError(
                "run.append stage skipped cần lý do")
        if stage == "review" and status == "done":
            plan = proj.data.get("plan") or {}
            stages = plan.get("stages") or {}
            log = proj.data.get("run_log") or []
            done = set()
            for old in log:
                if old.get("kind") == "stage" \
                        and old.get("status") in ("done", "skipped"):
                    done.add(old.get("stage"))
            open_required = [sid for sid, spec in stages.items()
                             if isinstance(spec, dict)
                             and spec.get("required")
                             and sid not in done
                             and sid != stage]
            if open_required:
                entry["stage_pending"] = open_required
                entry["status"] = "started"
                log = proj.data.setdefault("run_log", [])
                log.append(entry)
                proj._bump()
                return {"entry": entry, "status": "stage_pending",
                        "openRequired": open_required,
                        "rev": proj.rev}
    log = proj.data.setdefault("run_log", [])
    log.append(entry)
    proj._bump()
    return {"entry": entry, "entries": len(log), "rev": proj.rev}


def run_checklist(proj) -> dict:
    """The run's checklist, derived from the plan and the run log
    (never hand-written): stage statuses, skill reads, audits,
    recipe and what is still open."""
    plan = proj.data.get("plan") or {}
    plan_stages = plan.get("stages") or {}
    log = proj.data.get("run_log") or []
    stages: dict[str, dict] = {}
    for sid, spec in plan_stages.items():
        if isinstance(spec, dict):
            stages[sid] = {
                "id": sid, "skill": spec.get("skill"),
                "skillRead": False, "skillReadUnverified": False,
                "status": "pending",
                "required": bool(spec.get("required")),
                "evidence": None, "reason": None,
                "unverified": False, "by": spec.get("by"),
                "rules": spec.get("rules")}
    audits: dict[str, dict | None] = {"strategy": None,
                                      "draft": None, "process": None}
    audit_details: list[dict] = []
    for entry in log:
        if entry.get("kind") == "stage" and entry.get("stage"):
            sid = entry["stage"]
            stage = stages.setdefault(sid, {
                "id": sid, "skill": None, "skillRead": False,
                "skillReadUnverified": False, "status": "pending",
                "required": False, "evidence": None, "reason": None,
                "unverified": False, "by": None, "rules": None})
            stage["status"] = entry.get("status", "started")
            if entry.get("evidence"):
                stage["evidence"] = entry["evidence"]
            if entry.get("reason"):
                stage["reason"] = entry["reason"]
            if entry.get("unverified"):
                stage["unverified"] = True
        elif entry.get("kind") == "skill":
            name = entry.get("name") or ""
            for stage in stages.values():
                if stage.get("skill") == name:
                    if entry.get("verifiedBy") == "hook":
                        stage["skillRead"] = True
                    else:
                        stage["skillReadUnverified"] = True
        elif entry.get("kind") == "audit":
            point = entry.get("point")
            if point in audits:
                audits[point] = entry.get("verdict")
            audit_details.append({
                "verdict": entry.get("verdict"),
                "by": entry.get("by", "self"),
                "findings": entry.get("findings"),
                "rev": proj.rev, "current": True})
    open_items = [s["id"] for s in stages.values()
                  if s["status"] not in ("done", "skipped", "n/a")]
    return {"stages": [stages[sid] for sid in sorted(stages)],
            "audits": audits, "auditDetails": audit_details,
            "recipe": plan.get("recipe"),
            "open": open_items,
            # Round 9: the run panel's headless state, so
            # run.dismiss / run.toggle / run.follow are observable
            # here instead of write-only flags.
            "panel": run_panel_snapshot(proj.data)}


# ---------------------------------------------------------------------------
# media.describe / description / digest — caller-supplied facts.
# ---------------------------------------------------------------------------

_DESCRIBE_FACTS = ("size", "angle", "move", "direction", "subjects",
                   "tags", "people", "onScreenText", "confidence",
                   "bestMoment", "looked", "note")


def describe_media(proj, media_id: str, shots, append: bool = False) -> dict:
    """Store what the caller saw in a source media, shot by shot
    (the original's media.describe: the caller supplies the facts;
    nothing is measured or invented here). Shots may not overlap;
    each needs at least one fact field. Replaces unless append."""
    medium = proj.media(media_id)
    if not isinstance(shots, list) or not shots:
        raise ValueError("media.describe cần danh sách shots không rỗng")
    cleaned = []
    for shot in shots:
        if not isinstance(shot, dict):
            raise ValueError("shots của media.describe phải là object")
        try:
            start = float(shot["start"])
            end = float(shot["end"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                "shots của media.describe cần start và end dạng số") from None
        if not 0 <= start < end:
            raise ValueError(
                "shot của media.describe cần 0 <= start < end")
        if not any(k in shot for k in _DESCRIBE_FACTS):
            raise ValueError(
                "shots của media.describe cần ít nhất một fact (size, angle, move, direction, subjects, tags, people, onScreenText, confidence, bestMoment, looked hoặc note)")
        if "confidence" in shot:
            conf = float(shot["confidence"])
            if not 0 <= conf <= 1:
                raise ValueError("confidence của media.describe phải trong 0..1")
        cleaned.append(dict(shot))
    cleaned.sort(key=lambda s: s["start"])
    for prev, nxt in zip(cleaned, cleaned[1:]):
        if nxt["start"] < prev["end"]:
            raise ValueError("shots của media.describe không được chồng lấn")
    store = proj.data.setdefault("media_descriptions", {})
    if append and media_id in store:
        merged = sorted(store[media_id]["shots"] + cleaned,
                        key=lambda s: s["start"])
        for prev, nxt in zip(merged, merged[1:]):
            if nxt["start"] < prev["end"]:
                raise ValueError(
                    "shots thêm vào của media.describe chồng lấn shots có sẵn")
        store[media_id] = {"shots": merged, "describedBy": "caller"}
    else:
        store[media_id] = {"shots": cleaned, "describedBy": "caller"}
    proj._bump()
    return {"media": media_id, "shots": len(store[media_id]["shots"]),
            "rev": proj.rev}


def _measured_shots(medium: dict) -> list[dict]:
    """Measured shots from an analysis record: cut-derived segments
    when the record has cuts, else []."""
    record = medium.get("analysis_record") or {}
    picture = record.get("picture") or {}
    cuts = picture.get("cuts") or record.get("cuts") or []
    shots = []
    bounds = [0.0] + [float(c) for c in cuts
                      if isinstance(c, (int, float))]
    duration = None
    tech = record.get("tech") or {}
    if tech.get("seconds"):
        duration = float(tech["seconds"])
    elif medium.get("duration"):
        duration = float(medium["duration"])
    if duration:
        bounds.append(duration)
    bounds = sorted(set(bounds))
    for start, end in zip(bounds, bounds[1:]):
        shots.append({"start": start, "end": end})
    return shots


def media_description(proj, media_id=None) -> dict:
    """Read media descriptions with coverage. With media: the
    description plus coverage against measured shots (a measured
    shot counts as covered when half or more of it is described).
    Without: every media's coverage, totals and the vocabulary."""
    store = proj.data.get("media_descriptions") or {}

    def _coverage(medium: dict) -> dict:
        desc = store.get(medium["id"])
        shots = (desc or {}).get("shots") or []
        described = sum(float(s["end"]) - float(s["start"])
                        for s in shots)
        measured = _measured_shots(medium)
        covered = 0
        missing = []
        for i, mshot in enumerate(measured):
            hit = 0.0
            for shot in shots:
                hit += max(0.0, min(float(shot["end"]), mshot["end"])
                           - max(float(shot["start"]), mshot["start"]))
            if hit >= 0.5 * (mshot["end"] - mshot["start"]):
                covered += 1
            else:
                missing.append({"index": i, "start": mshot["start"],
                                "end": mshot["end"]})
        duration = None
        medium_duration = medium.get("duration")
        if medium_duration:
            duration = float(medium_duration)
        return {
            "shots": len(shots),
            "describedSeconds": round(described, 3),
            "describedShare": (round(described / duration, 4)
                               if duration else None),
            "measuredShots": len(measured),
            "coveredShots": covered,
            "missing": missing}

    if media_id is not None:
        medium = proj.media(media_id)
        return {"media": media_id,
                "description": store.get(media_id),
                "coverage": _coverage(medium)}
    per_media = {}
    total_measured = total_covered = total_described = 0
    missing_media = []
    vocabulary: dict[str, set] = {"size": set(), "angle": set(),
                                  "move": set(), "direction": set()}
    for medium in proj.data["media"]:
        cov = _coverage(medium)
        per_media[medium["id"]] = cov
        total_measured += cov["measuredShots"]
        total_covered += cov["coveredShots"]
        total_described += cov["shots"]
        if not (store.get(medium["id"]) or {}).get("shots"):
            missing_media.append(medium["id"])
        for shot in (store.get(medium["id"]) or {}).get("shots") or []:
            for key in vocabulary:
                if shot.get(key):
                    vocabulary[key].add(str(shot[key]))
    return {"media": per_media,
            "describedMedia": sum(
                1 for m in proj.data["media"]
                if (store.get(m["id"]) or {}).get("shots")),
            "totalMedia": len(proj.data["media"]),
            "measuredShots": total_measured,
            "coveredShots": total_covered,
            "describedShots": total_described,
            "missingMedia": missing_media,
            "vocabulary": {k: sorted(v) for k, v in vocabulary.items()}}


def media_digest(proj, media_id: str) -> dict:
    """Footage facts in one read: a header, then the described
    shots in time order in the original's line format, plus
    measured facts from the analysis record when one exists."""
    medium = proj.media(media_id)
    store = proj.data.get("media_descriptions") or {}
    desc = store.get(media_id) or {}
    shots = sorted(desc.get("shots") or [], key=lambda s: s["start"])
    duration = None
    if medium.get("duration"):
        duration = float(medium["duration"])
    elif medium.get("frames"):
        duration = float(medium["frames"]) / fps_value(
            proj.data["format"]["fps"])
    record = medium.get("analysis_record") or {}
    transcript = record.get("transcript") or {}
    words = transcript.get("words") or []
    speech_share = None
    if duration and words:
        sound_time = sum(float(w.get("end", 0)) - float(w.get("start", 0))
                         for w in words
                         if "start" in w and "end" in w)
        speech_share = round(sound_time / duration, 4)
    clips = sum(1 for t in proj.data["tracks"] for i in t["items"]
                if i.get("media") == media_id)
    lines = []
    for shot in shots:
        subjects = shot.get("subjects") or []
        if isinstance(subjects, str):
            subjects = [subjects]
        lines.append(
            f"shot {shot['start']}-{shot['end']} "
            f"{shot.get('size', '')} {shot.get('angle', '')} "
            f"{shot.get('move', '')} | {', '.join(subjects)} | "
            f"{shot.get('note', '')} | "
            f"best {shot.get('bestMoment')}")
    facts = {}
    picture = record.get("picture") or {}
    if picture.get("cuts") is not None:
        facts["cuts"] = len(picture["cuts"])
    sound = record.get("sound") or {}
    for key in ("floorDb", "medianDb", "loudDb", "peakDb"):
        if sound.get(key) is not None:
            facts[key] = sound[key]
    return {
        "header": {
            "media": media_id,
            "seconds": duration,
            "size": ((medium.get("width"), medium.get("height"))
                     if medium.get("width") else None),
            "speechShare": speech_share,
            "counts": {"shots": len(shots),
                       "transcriptWords": len(words),
                       "timelineClips": clips}},
        "shots": shots,
        "lines": lines,
        "facts": facts,
        "described": bool(shots),
        "note": "Shot facts are caller-supplied via "
                "media.describe; header numbers are measured or "
                "stored metadata, never invented."}


# ---------------------------------------------------------------------------
# speech.rate — measurement from transcript words.
# ---------------------------------------------------------------------------

def _percentile(sorted_values: list, share: float):
    if not sorted_values:
        return None
    idx = min(len(sorted_values) - 1,
              max(0, int(math.ceil(share * len(sorted_values))) - 1))
    return sorted_values[idx]


def _phrase_rates(words, gap_s: float, unit: str):
    """Group words into phrases (gap > gap_s splits) and rate each
    phrase in units/second. Units: Vietnamese syllables are the
    whitespace tokens themselves; CJK counts characters; anything
    else counts tokens as words."""
    phrases = []
    current: list[dict] = []
    for word in words:
        if current and word["start"] - current[-1]["end"] > gap_s:
            phrases.append(current)
            current = []
        current.append(word)
    if current:
        phrases.append(current)
    rates = []
    for phrase in phrases:
        start = phrase[0]["start"]
        end = phrase[-1]["end"]
        if end <= start:
            continue
        if unit in ("zh", "ja", "ko", "characters"):
            units = sum(len(w["word"].replace(" ", ""))
                        for w in phrase)
        else:
            units = len(phrase)
        rates.append({"start": start, "end": end, "units": units,
                      "rate": round(units / (end - start), 3)})
    return rates


def _rate_summary(rates, words):
    values = sorted(r["rate"] for r in rates)
    total_units = sum(r["units"] for r in rates)
    total_time = sum(r["end"] - r["start"] for r in rates)
    sound_time = sum(w["end"] - w["start"] for w in words
                     if w["end"] > w["start"])
    return {
        "phrases": len(rates),
        "p10": _percentile(values, 0.10),
        "p50": _percentile(values, 0.50),
        "p90": _percentile(values, 0.90),
        "overall": (round(total_units / total_time, 3)
                    if total_time else None),
        "articulation": (round(total_units / sound_time, 3)
                         if sound_time else None)}


def speech_rate(proj, media_id=None, unit=None) -> dict:
    """Measure speaking rate from transcript words: per transcribed
    media (analysis-record words when faster-whisper ran) and, for
    the whole timeline, from caption items split evenly. No normal
    rate is assumed. Synthesised takes are reported as unavailable
    for this measurement: voice takes in this build do not store
    their text, so no rate is fabricated for them."""
    lang = (proj.data.get("contentLanguage") or "vi").lower()
    if unit is None:
        unit = {"vi": "syllables", "zh": "characters",
                "ja": "characters", "ko": "characters"}.get(lang, "words")
    per_media = []
    if media_id is not None:
        medium = proj.media(media_id)
        record = medium.get("analysis_record") or {}
        words = []
        for w in (record.get("transcript") or {}).get("words") or []:
            if "start" in w and "end" in w:
                words.append({"word": w.get("word", ""),
                              "start": float(w["start"]),
                              "end": float(w["end"])})
        if not words:
            raise ValueError(
                "speech.rate cần transcript cho media này: hãy chạy media_analyze (faster-whisper) để media mang theo từ transcript")
        rates = _phrase_rates(words, 0.5, unit)
        per_media.append({"media": media_id, "unit": unit,
                          "words": len(words),
                          **_rate_summary(rates, words),
                          "phraseRates": rates})
    else:
        for medium in proj.data["media"]:
            record = medium.get("analysis_record") or {}
            words = []
            for w in (record.get("transcript") or {}).get("words") or []:
                if "start" in w and "end" in w:
                    words.append({"word": w.get("word", ""),
                                  "start": float(w["start"]),
                                  "end": float(w["end"])})
            if not words:
                continue
            rates = _phrase_rates(words, 0.5, unit)
            per_media.append({"media": medium["id"], "unit": unit,
                              "words": len(words),
                              **_rate_summary(rates, words),
                              "phraseRates": rates})
        caption_words = timeline_words(proj)
        if caption_words:
            cw = [{"word": w["word"], "start": w["at_s"],
                   "end": w["end_s"]} for w in caption_words]
            rates = _phrase_rates(cw, 0.5, unit)
            per_media.append({"media": None, "source": "captions",
                              "unit": unit, "words": len(cw),
                              **_rate_summary(rates, cw),
                              "phraseRates": rates})
    return {"perMedia": per_media, "unit": unit,
            "voices": {"available": False,
                       "reason": "Take giọng đọc tổng hợp trong bản build này không lưu text nên không tính voice rate cho chúng thay vì bịa ra."}}


# ---------------------------------------------------------------------------
# image.style / image.disclose / image.generate_list — project state.
# ---------------------------------------------------------------------------

def image_style(proj, style=None, references=None, seed=None,
                disclosure=None, clear: bool = False) -> dict:
    """Read or set the project's style lock for image generation:
    style prompt, reference pictures, seed and the disclosure
    label. Given fields replace those fields; clear removes the
    lock (a brand kit's illustration then applies, if the brand
    declares one). With no field, returns the lock in use."""
    if clear:
        proj.data.pop("image_style", None)
        proj._bump()
        return {"styleLock": None, "cleared": True, "rev": proj.rev}
    lock = dict(proj.data.get("image_style") or {})
    changed = False
    if style is not None:
        lock["style"] = style
        changed = True
    if references is not None:
        if references == "":
            lock["references"] = []
        else:
            lock["references"] = [r.strip() for r in str(references)
                                  .split(",") if r.strip()]
        changed = True
    if seed is not None:
        seed = int(seed)
        if seed < 0:
            raise ValueError("seed của image.style phải >= 0")
        lock["seed"] = seed
        changed = True
    if disclosure is not None:
        lock["disclosure"] = disclosure
        changed = True
    if changed:
        proj.data["image_style"] = lock
        proj._bump()
    return {"styleLock": lock or None, "rev": proj.rev}


def image_disclose(proj, text=None) -> dict:
    """Put the disclosure label over every generated picture on
    the timeline that lacks one: one text item (disclosure: true,
    small, top left) per run of generated pictures, on the
    captions layer, in one undo step. The label is the given text,
    else the style lock's or the brand's disclosure. When no label
    is configured anywhere, nothing is added and the result says
    so — no label is invented."""
    label = text
    if label is None:
        label = (proj.data.get("image_style") or {}).get("disclosure")
    if label is None:
        label = (proj.data.get("brand") or {}).get("disclosure")
    if not label:
        return {"added": [], "rev": proj.rev,
                "note": "No disclosure label configured: pass text "
                        "or set one with image.style first."}
    generated = {m["id"] for m in proj.data["media"]
                 if m.get("generated")}
    if not generated:
        return {"added": [], "rev": proj.rev,
                "note": "No generated pictures are on the timeline."}
    captions_track = next((t for t in proj.data["tracks"]
                           if t.get("role") == "captions"
                           and t["kind"] == "text"), None)
    if captions_track is None:
        raise ValueError("Chưa có track chữ phụ đề nào")
    clips = []
    for track in proj.data["tracks"]:
        if track["kind"] != "video":
            continue
        for item in track["items"]:
            if item.get("media") in generated:
                clips.append(item)
    clips.sort(key=lambda i: int(i["at"]))
    runs = []
    for clip in clips:
        if runs and int(clip["at"]) <= runs[-1][1]:
            runs[-1][1] = max(runs[-1][1],
                              int(clip["at"]) + int(clip["dur"]))
        else:
            runs.append([int(clip["at"]),
                         int(clip["at"]) + int(clip["dur"])])
    added = []
    for start, end in runs:
        item = proj.add_text(captions_track["id"], label, start,
                             end - start, size=0.03, position_y=0.06,
                             position_x=0.08)
        item["disclosure"] = True
        added.append(item["id"])
    proj._bump()
    return {"added": added, "label": label, "rev": proj.rev}


def image_generate_list(proj) -> dict:
    """List the project's generated pictures (media entries flagged
    generated) — the read side of image.generate, which itself
    still needs a provider."""
    items = []
    for medium in proj.data["media"]:
        if medium.get("generated"):
            items.append({"id": medium["id"], "media": medium["id"],
                          "path": medium.get("path"),
                          "width": medium.get("width"),
                          "height": medium.get("height"),
                          "prompt": medium.get("prompt")})
    return {"images": items}


# ---------------------------------------------------------------------------
# library packs — pack.json + files, licence-gated per the spec.
# ---------------------------------------------------------------------------

_MAX_PACK_BYTES = 50 * 1024 * 1024


def _library_kind(entry: dict) -> str:
    if entry.get("kind"):
        return entry["kind"]
    item = entry.get("item") or {}
    if "text" in item:
        return "text"
    medium_kind = None
    return medium_kind or "clip"


def export_pack(proj, output: str, pack=None, kind=None) -> dict:
    """Write library items as a pack folder (pack.json and files)
    to share or import elsewhere. Refuses, naming them, items
    whose own licence says redistribute false; items whose licence
    does not say are exported and listed as unknownLicenses.
    Library entries in this build are data-only, so files are
    copied only when an entry's media file resolves inside the
    project folder."""
    entries = list(proj.data.get("library") or [])
    if pack is not None:
        entries = [e for e in entries if e.get("pack") == pack]
    if kind is not None:
        entries = [e for e in entries
                   if _library_kind(e) == kind]
    if os.path.exists(output) and os.listdir(output):
        raise ValueError(
            "đầu ra library.export-pack phải là thư mục mới hoặc rỗng")
    os.makedirs(output, exist_ok=True)
    files_dir = os.path.join(output, "files")
    os.makedirs(files_dir, exist_ok=True)
    refused = []
    unknown = []
    exported = []
    files: list[dict] = []
    media_by_id = {m["id"]: m for m in proj.data["media"]}
    for entry in entries:
        licence = entry.get("license") or entry.get("licence") or {}
        if isinstance(licence, dict) \
                and licence.get("redistribute") is False:
            refused.append(entry["id"])
            continue
        if not licence:
            unknown.append(entry["id"])
        item = entry.get("item") or {}
        media_id = item.get("media")
        if media_id and media_id in media_by_id:
            medium = media_by_id[media_id]
            rel = medium.get("path") or ""
            src = rel if os.path.isabs(rel) else os.path.join(
                proj.folder, rel)
            if os.path.isfile(src):
                dest_name = os.path.basename(src)
                with open(src, "rb") as fh:
                    data = fh.read()
                if len(data) > _MAX_PACK_BYTES:
                    refused.append(entry["id"])
                    continue
                with open(os.path.join(files_dir, dest_name),
                          "wb") as fh:
                    fh.write(data)
                files.append({"entry": entry["id"],
                              "file": dest_name,
                              "media": media_id})
        exported.append(copy.deepcopy(entry))
    with open(os.path.join(output, "pack.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"items": exported, "files": files}, fh,
                  ensure_ascii=False, indent=2)
    return {"output": output, "exported": [e["id"] for e in exported],
            "refused": refused, "unknownLicenses": unknown,
            "files": files}


def import_pack(proj, path: str, replace: bool = False) -> dict:
    """Add a pack (a folder with pack.json and files, or a .zip of
    one) to the project library. IDs already there are refused
    unless replace saves them as new versions (a fresh id with
    version bumped). Zip entries are traversal-checked."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Không tìm thấy pack: {path}")
    import tempfile
    tmp = None
    folder = path
    if os.path.isfile(path):
        if not zipfile.is_zipfile(path):
            raise ValueError("File pack phải là .zip của một pack")
        tmp = tempfile.mkdtemp(prefix="vibeedit-pack-")
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    raise ValueError(
                        f"Entry zip pack thoát khỏi thư mục của nó: {info.filename!r}")
                if info.file_size > _MAX_PACK_BYTES:
                    raise ValueError(
                        f"Entry zip pack quá lớn: {info.filename!r}")
                dest = os.path.join(tmp, name)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(info) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
        folder = tmp
        pack_path = os.path.join(tmp, "pack.json")
        if not os.path.isfile(pack_path):
            for root, _dirs, names in os.walk(tmp):
                if "pack.json" in names:
                    pack_path = os.path.join(root, "pack.json")
                    folder = root
                    break
    else:
        pack_path = os.path.join(folder, "pack.json")
    if not os.path.isfile(pack_path):
        raise ValueError("Thư mục pack không có pack.json")
    with open(pack_path, encoding="utf-8") as fh:
        pack = json.load(fh)
    if not isinstance(pack, dict) or not isinstance(
            pack.get("items"), list):
        raise ValueError("pack.json phải là object có danh sách 'items'")
    library = proj.data.setdefault("library", [])
    existing = {e["id"] for e in library}
    added = []
    refused = []
    for entry in pack["items"]:
        if not isinstance(entry, dict) or "id" not in entry:
            refused.append(str(entry)[:40])
            continue
        if entry["id"] in existing and not replace:
            refused.append(entry["id"])
            continue
        new_entry = copy.deepcopy(entry)
        if entry["id"] in existing and replace:
            base = entry["id"]
            version = int(entry.get("version") or 1) + 1
            new_id = f"{base}-v{version}"
            while new_id in existing:
                version += 1
                new_id = f"{base}-v{version}"
            new_entry["id"] = new_id
            new_entry["version"] = version
            new_entry["replaces"] = base
        library.append(new_entry)
        existing.add(new_entry["id"])
        added.append(new_entry["id"])
    proj._bump()
    return {"added": added, "refused": refused, "rev": proj.rev}


# ---------------------------------------------------------------------------
# library.analyze — measure an audio library item's file.
# ---------------------------------------------------------------------------

def analyze_library_item(proj, entry_id: str, media_path=None) -> dict:
    """Measure an audio library item's file and save the values as
    a new version: length, integrated loudness and true peak from
    FFmpeg loudnorm/astats, landmarks {onset, peak, tail} from the
    RMS envelope (the -70 LUFS gate of the spec is approximated
    with the measured dBFS envelope and labelled as such), tempo
    from the project's beat detector when it yields one, and
    energy {rangeDb, liftAt, peakAt}. Values a missing provider
    cannot supply stay null with a note naming the gap — the
    original's audio.loudness / audio.beats / audio.energy
    providers do not exist as separate providers in this build;
    the measurements below are the Windows equivalents."""
    entry = next((e for e in proj.data.get("library", [])
                  if e["id"] == entry_id), None)
    if entry is None:
        raise KeyError(f"Mục thư viện không rõ: {entry_id}")
    if media_path is None:
        item = entry.get("item") or {}
        medium = next((m for m in proj.data["media"]
                       if m["id"] == item.get("media")), None)
        if medium is None:
            raise ValueError(
                "Mục thư viện không có file media giải quyết được để đo; hãy truyền media_path")
        rel = medium.get("path") or ""
        media_path = rel if os.path.isabs(rel) else os.path.join(
            proj.folder, rel)
    if not os.path.isfile(media_path):
        raise FileNotFoundError(
            f"Không tìm thấy file audio: {media_path}")
    from .analysis import decode_sound_levels, probe_tech
    from .render import find_tool
    tech = probe_tech(media_path)
    duration = tech.get("seconds")
    if duration is None:
        for stream in ("audio", "video"):
            part = tech.get(stream) or {}
            if part.get("seconds"):
                duration = part["seconds"]
                break
    levels = decode_sound_levels(media_path)
    sound = levels.get("levels") if levels else None
    loudness = None
    true_peak = None
    notes: list[str] = []
    ffmpeg = find_tool("ffmpeg")
    if ffmpeg and sound is not None:
        import subprocess
        try:
            proc = subprocess.run(
                [ffmpeg, "-i", media_path, "-vn", "-af",
                 "loudnorm=print_format=json", "-f", "null", "-"],
                capture_output=True, text=True, timeout=120)
            text = proc.stderr or ""
            start = text.rfind("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                loudness = json.loads(text[start:end + 1])
                tp = loudness.get("input_tp")
                try:
                    true_peak = float(tp) if tp not in (None, "-inf") \
                        else None
                except (TypeError, ValueError):
                    true_peak = None
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            notes.append(f"loudnorm measurement failed: {exc}")
    else:
        notes.append("FFmpeg loudnorm unavailable or no sound "
                     "envelope decoded")
    landmarks = None
    energy = None
    if sound:
        step = 0.1
        gate = -70.0
        above = [i for i, v in enumerate(sound) if v > gate]
        if above:
            onset = above[0] * step
            peak_idx = max(range(len(sound)), key=lambda i: sound[i])
            peak = peak_idx * step
            tail = above[-1] * step
            landmarks = {"onset": round(onset, 2),
                         "peak": round(peak, 2),
                         "tail": round(tail, 2)}
            energy = {"rangeDb": round(max(sound) - min(sound), 2),
                      "liftAt": round(onset, 2),
                      "peakAt": round(peak, 2)}
        else:
            notes.append("No sound window passes the -70 dB gate, "
                         "so landmarks are null")
    tempo = None
    try:
        from .beats import detect_beats
        beats = detect_beats(media_path)
        times = beats.get("beats") or beats.get("times") or []
        if len(times) >= 2:
            gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
            if gaps:
                gaps.sort()
                median_gap = gaps[len(gaps) // 2]
                if median_gap > 0:
                    tempo = round(60.0 / median_gap, 1)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        notes.append(f"Tempo detection unavailable: {exc}")
    if tempo is None:
        notes.append("Tempo is null: the beat detector yielded no "
                     "usable beat grid for this file")
    measured = {"duration": duration,
                "loudness": loudness,
                "truePeakDbTP": true_peak,
                "landmarks": landmarks, "tempoBpm": tempo,
                "energy": energy, "notes": notes,
                "gateNote": "Landmark gate uses the measured dBFS "
                            "envelope as the -70 LUFS gate "
                            "approximation; loudness/peak come from "
                            "FFmpeg loudnorm, not a separate "
                            "audio.loudness provider."}
    new_entry = copy.deepcopy(entry)
    new_entry["analysis"] = measured
    new_entry["version"] = int(entry.get("version") or 1) + 1
    new_entry["id"] = f"{entry_id}-v{new_entry['version']}"
    proj.data.setdefault("library", []).append(new_entry)
    proj._bump()
    return {"item": entry_id, "newVersion": new_entry["id"],
            "analysis": measured, "rev": proj.rev}


# ---------------------------------------------------------------------------
# library.brand-pose (image path only) — cutout via vision.
# ---------------------------------------------------------------------------

def brand_pose_image(proj, brand: str, pose: str, image=None,
                     media_id=None) -> dict:
    """Add a mascot pose to a brand kit from a photo: the photo's
    subject is cut out with vision.cutout (OpenCV grabCut) and
    stored as a sticker. The `generate` path of the original needs
    an image.generate provider and stays unavailable; this is the
    image path only."""
    if not pose:
        raise ValueError("library.brand-pose cần tên pose")
    if image is None and media_id is not None:
        medium = proj.media(media_id)
        rel = medium.get("path") or ""
        image = rel if os.path.isabs(rel) else os.path.join(
            proj.folder, rel)
    if image is None or not os.path.isfile(image):
        raise FileNotFoundError(
            "library.brand-pose cần file ảnh có sẵn hoặc media id")
    from .vision import cutout
    brand_dir = os.path.join(proj.folder, "brand")
    os.makedirs(brand_dir, exist_ok=True)
    safe_pose = re.sub(r"[^A-Za-z0-9_-]+", "-", pose).strip("-")
    if not safe_pose:
        raise ValueError("Tên pose không có ký tự dùng được")
    sticker = os.path.join(brand_dir, f"{safe_pose}.png")
    cutout(image, sticker)
    kit = proj.data.setdefault("brand", {})
    poses = kit.setdefault("poses", [])
    poses.append({"pose": pose, "sticker": sticker, "brand": brand})
    proj._bump()
    return {"brand": brand, "poses": [{"pose": pose,
                                       "sticker": sticker}],
            "rev": proj.rev}


# ---------------------------------------------------------------------------
# agent.kit — local kit status + skill-pack install.
# ---------------------------------------------------------------------------

def kit_check(kit_dir=None) -> dict:
    """Local agent-kit status: the kit folder and its skills, as
    listed by the skills store. The original checks signed
    releases for a newer kit; this build has no releases channel
    configured (the same unconfigured state as the updater), so
    no newer-release check can run and none is claimed: newer is
    null and the channel field says so. A chosen kit folder is
    never updated by this tool."""
    from .skills import list_skills, _default_skills_dir
    folder = kit_dir or _default_skills_dir()
    try:
        skills = list_skills(folder)
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        return {"kitFolder": folder, "skills": [],
                "error": str(exc),
                "channel": None,
                "newer": None,
                "note": "No agent-kit releases channel is configured "
                        "in this build, so no newer-release check "
                        "runs; this reports the local kit only."}
    names = []
    for skill in skills:
        if isinstance(skill, dict):
            names.append(skill.get("id") or skill.get("name"))
        else:
            names.append(str(skill))
    return {"kitFolder": folder, "skills": names,
            "count": len(names), "channel": None, "newer": None,
            "note": "No agent-kit releases channel is configured "
                    "in this build, so no newer-release check runs; "
                    "this reports the local kit only."}


def kit_install_skills(path: str, kit_dir=None) -> dict:
    """Install agent-kit skills from a folder of .md files (or one
    .md file) into the kit folder. Skill ids must be safe
    lowercase-hyphenated names; existing skills are refused
    unless overwrite is passed via the file already existing
    check below (callers pass overwrite separately). Files are
    copied, never executed.

    Round 23: a .zip bundle and a nested Claude-plugin folder
    (``skills/<id>/SKILL.md``) are accepted too — the old code
    raised FileNotFoundError for zips (no .md at the top) and
    ValueError for nested folders (no top-level .md files). Folder
    skills install as their SKILL.md content under the flat
    ``<id>.md`` name, matching the kit folder's flat layout; the
    discovery (and its zip-slip/size guards) comes from
    skill_import.plan_import, so one layout table serves both
    install paths.
    """
    from .skill_import import _discover, _mark_exists, _read_source_bytes
    from .skills import _default_skills_dir, _SAFE_ID
    folder = kit_dir or _default_skills_dir()
    os.makedirs(folder, exist_ok=True)
    # One discovery run serves both the listing and the copy
    # sources (plan_import's public view strips the src handles).
    candidates, _warnings = _discover(path)
    _mark_exists(candidates, folder)
    if not candidates:
        raise ValueError("Nguồn skill kit không có file .md nào")
    installed = []
    refused = []
    for src in candidates:
        skill_id = src["id"]
        if not _SAFE_ID.match(skill_id):
            refused.append(skill_id)
            continue
        dest = os.path.join(folder, skill_id + ".md")
        if src.get("exists") or os.path.exists(dest):
            # Either form already owns this id (a folder-form skill
            # would shadow a new flat file, so refuse, never stack).
            refused.append(skill_id)
            continue
        raw = _read_source_bytes(src, src["main_rel"])
        tmp = dest + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, dest)
        installed.append(skill_id)
    return {"kitFolder": folder, "installed": installed,
            "refused": refused}
