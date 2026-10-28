"""Phase 3 export operations: OTIO export, batch export, project
duplication and media metadata. Stdlib only; no network, no Swift.

OTIO format: OpenTimelineIO JSON (otio_json adapter). A Timeline
contains a Stack of Tracks; each Track contains Clips with a
source_range (RationalTime start/duration at the project rate) and
an ExternalReference to the media file. Transitions become OTIO
Transition clips with in/out offsets; markers become OTIO Markers.
VibeEdit-specific data (item ids, colour, keyframes, transitions
by kind) is kept in each object's ``metadata`` dict under the
``VibeEdit`` key, so a round trip through this exporter loses
nothing the Windows model stores. The original BashCut OTIO export
keeps the same integer-frame timing, source ranges and rates
(see VibeEdit/docs/guides/automation.md, "OTIO"); this exporter
follows that description rather than any undocumented binary form.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import uuid

from .project import (Project, load_project, save_project, new_project,
                      find_project_file, PROJECT_FILENAME, fps_value,
                      frames_to_seconds, write_backup)


def _rational_time(frames: int, rate: float) -> dict:
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(rate),
            "value": int(frames)}


def _time_range(start_frames: int, dur_frames: int, rate: float) -> dict:
    return {"OTIO_SCHEMA": "TimeRange.1",
            "start_time": _rational_time(start_frames, rate),
            "duration": _rational_time(dur_frames, rate)}


def export_otio(project: dict, folder: str, out_path: str) -> dict:
    """Write an OTIO JSON timeline for ``project``. Returns a report."""
    fmt = project["format"]
    rate = fps_value(fmt["fps"])
    tracks_json = []
    trans_by_pair = {(t["from"], t["to"]): t
                     for t in project.get("transitions", [])}
    for track in project["tracks"]:
        children = []
        items = sorted(track["items"], key=lambda i: i["at"])
        prev = None
        for item in items:
            if prev is not None and (prev["id"], item["id"]) in trans_by_pair:
                trans = trans_by_pair[(prev["id"], item["id"])]
                dur_f = int(trans["duration"])
                kind = trans["kind"]
                otype = "SMPTE_Dissolve" if kind in (
                    "dissolve", "crossfade", "fade") else "Custom"
                children.append({
                    "OTIO_SCHEMA": "Transition.1",
                    "name": f"{kind} transition",
                    "transition_type": otype,
                    "in_offset": _rational_time(dur_f // 2, rate),
                    "out_offset": _rational_time(dur_f - dur_f // 2, rate),
                    "metadata": {"VibeEdit": {
                        "kind": kind, "id": trans["id"],
                        "from": trans["from"], "to": trans["to"]}},
                })
            media = next((m for m in project["media"]
                          if m["id"] == item.get("media")), None)
            clip = {
                "OTIO_SCHEMA": "Clip.1",
                "name": item.get("text") or (media["path"] if media else item["id"]),
                "source_range": _time_range(
                    int(item.get("in", 0)), int(item["dur"]), rate),
                "metadata": {"VibeEdit": {
                    "id": item["id"], "at": int(item["at"]),
                    "speed": float(item.get("speed", 1.0)),
                    "keyframes": item.get("keyframes") or [],
                    "color": item.get("color") or {},
                    "volume": item.get("volume"),
                    "fadeIn": item.get("fadeIn"),
                    "fadeOut": item.get("fadeOut")}},
            }
            if media is not None:
                clip["media_reference"] = {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": media["path"],
                    "available_range": _time_range(
                        0, int(media.get("frames") or item["dur"]), rate),
                }
            children.append(clip)
            prev = item
        tracks_json.append({
            "OTIO_SCHEMA": "Track.1",
            "name": track.get("name", track["id"]),
            "kind": "Video" if track["kind"] == "video" else
                    "Audio" if track["kind"] == "audio" else "Video",
            "children": children,
            "metadata": {"VibeEdit": {"id": track["id"],
                                      "role": track.get("role")}},
        })
    markers_json = [{
        "OTIO_SCHEMA": "Marker.1",
        "name": m.get("text", ""),
        "marked_range": _time_range(int(m["at"]), 1, rate),
        "metadata": {"VibeEdit": {"id": m["id"]}},
    } for m in project.get("markers", [])]
    timeline = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": project.get("name", "Untitled"),
        "tracks": {"OTIO_SCHEMA": "Stack.1", "children": tracks_json,
                   "markers": markers_json},
        "metadata": {"VibeEdit": {
            "schema": project.get("schema"), "id": project.get("id"),
            "format": fmt, "contentLanguage": project.get("contentLanguage"),
            # Round 22: absolute source project folder, so import
            # can relink media even when the .otio file is opened
            # from elsewhere (the .otio file itself lives in
            # render/, so its own directory is the wrong base).
            "sourceFolder": os.path.abspath(folder)}},
    }
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(timeline, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    n_clips = sum(1 for t in tracks_json for c in t["children"]
                  if c["OTIO_SCHEMA"] == "Clip.1")
    n_trans = sum(1 for t in tracks_json for c in t["children"]
                  if c["OTIO_SCHEMA"] == "Transition.1")
    return {"otio": out_path, "tracks": len(tracks_json),
            "clips": n_clips, "transitions": n_trans,
            "markers": len(markers_json)}


def import_otio(otio_path: str, dest_folder: str,
                merge: bool = False) -> dict:
    """Import a .otio JSON file written by export_otio (Phase 3) into a
    VibeEdit project.

    New-project mode (default) creates ``dest_folder`` with a fresh
    project file. Merge mode appends the OTIO tracks to an existing
    project in ``dest_folder`` (track/item ids are regenerated on
    collision, and transition from/to references are remapped).

    Media paths are resolved in order: relative to the .otio file,
    exactly as stored, relative to the destination folder (covers
    merge imports into the project the OTIO came from), by basename
    under ``dest/media/`` (covers media copied into the new
    project), and relative to the source project folder recorded
    in the OTIO metadata by export_otio (round 22). A file that
    cannot be found anywhere is still imported (its clip keeps the
    original stored path verbatim) and is listed in ``missing`` —
    never silently dropped and never replaced with invented media.
    Unknown OTIO objects are listed in ``warnings``.
    Returns a report: project path, track/clip/transition/marker
    counts, missing files, warnings.
    """
    from .project import Project
    with open(otio_path, encoding="utf-8") as fh:
        timeline = json.load(fh)
    if timeline.get("OTIO_SCHEMA") != "Timeline.1":
        raise ValueError("Not an OpenTimelineIO Timeline.1 JSON file")
    otio_dir = os.path.dirname(os.path.abspath(otio_path))
    meta = (timeline.get("metadata") or {}).get("VibeEdit") or {}
    fmt = meta.get("format") or {"width": 1080, "height": 1920,
                                 "fps": [30, 1], "sampleRate": 48000}
    rate = fps_value(fmt["fps"])
    if merge:
        found = find_project_file(dest_folder)
        if not found:
            raise FileNotFoundError(
                f"No project file in folder for merge: {dest_folder}")
        # Phase 0: a merge rewrites an existing project, so back up
        # its saved file before importing (best-effort, never blocks
        # the import itself).
        try:
            write_backup(found)
        except Exception:
            pass
        data = load_project(found)
        proj = Project(data, dest_folder)
    else:
        if os.path.exists(os.path.join(dest_folder, PROJECT_FILENAME)):
            raise ValueError(
                f"Destination already has a project: {dest_folder}")
        os.makedirs(dest_folder, exist_ok=True)
        data = new_project(timeline.get("name") or "Imported OTIO",
                           width=int(fmt["width"]), height=int(fmt["height"]),
                           fps=tuple(fmt["fps"]) if isinstance(fmt["fps"], list)
                           else fmt["fps"])
        if meta.get("contentLanguage"):
            data["contentLanguage"] = meta["contentLanguage"]
        # new_project ships default tracks; the OTIO tracks replace them.
        data["tracks"] = []
        proj = Project(data, dest_folder)
    missing: list[str] = []
    warnings: list[str] = []
    n_clips = n_trans = 0
    existing_ids = {i["id"] for t in data["tracks"] for i in t["items"]}
    existing_track_ids = {t["id"] for t in data["tracks"]}
    id_map: dict[str, str] = {}

    def fresh_id(old: str, prefix: str) -> str:
        if old and old not in existing_ids:
            existing_ids.add(old)
            return old
        new = f"{prefix}-{uuid.uuid4().hex[:8]}"
        existing_ids.add(new)
        if old:
            id_map[old] = new
        return new

    stack = timeline.get("tracks") or {}
    otio_tracks = stack.get("children") or []
    imported_transitions: list[dict] = []
    for otio_track in otio_tracks:
        if otio_track.get("OTIO_SCHEMA") != "Track.1":
            warnings.append(
                f"Skipped non-Track object: {otio_track.get('OTIO_SCHEMA')}")
            continue
        tmeta = (otio_track.get("metadata") or {}).get("VibeEdit") or {}
        kind = otio_track.get("kind", "Video")
        track_id = tmeta.get("id") or f"track-{uuid.uuid4().hex[:8]}"
        if track_id in existing_track_ids:
            track_id = f"track-{uuid.uuid4().hex[:8]}"
        existing_track_ids.add(track_id)
        role = tmeta.get("role")
        if not role:
            if kind == "Audio":
                role = "dialogue"
            elif data["tracks"] or merge:
                role = "overlay"
            else:
                role = "main"
        track = {"id": track_id,
                 "kind": "audio" if kind == "Audio" else "video",
                 "role": role,
                 "name": otio_track.get("name") or track_id, "items": []}
        prev_clip_id: str | None = None
        for child in otio_track.get("children") or []:
            schema = child.get("OTIO_SCHEMA")
            if schema == "Transition.1":
                tmeta2 = (child.get("metadata") or {}).get("VibeEdit") or {}
                if prev_clip_id is None:
                    warnings.append("Transition with no preceding clip skipped")
                    continue
                # The following clip is not known yet; stash it and
                # resolve it when the next clip arrives.
                imported_transitions.append({
                    "pending_from": prev_clip_id,
                    "kind": tmeta2.get("kind"),
                    "transition_type": child.get("transition_type"),
                    "duration": int((child.get("in_offset") or {}).get("value", 0))
                    + int((child.get("out_offset") or {}).get("value", 0)),
                    "id": tmeta2.get("id")})
                continue
            if schema != "Clip.1":
                warnings.append(f"Skipped OTIO object: {schema}")
                continue
            cmeta = (child.get("metadata") or {}).get("VibeEdit") or {}
            src_range = child.get("source_range") or {}
            start = (src_range.get("start_time") or {}).get("value", 0)
            dur = (src_range.get("duration") or {}).get("value", 0)
            at = int(cmeta.get("at", 0))
            if dur <= 0:
                warnings.append(f"Clip {cmeta.get('id')} has no duration, skipped")
                continue
            clip_id = fresh_id(cmeta.get("id") or "", "c")
            ref = child.get("media_reference") or {}
            target = ref.get("target_url")
            if target:
                # Round 22: export_otio writes project-relative
                # paths while the .otio file lives in render/, so
                # otio_dir-relative resolution alone ALWAYS missed
                # on a round-trip (the old code then stored a
                # relpath to a nonexistent file and the clip could
                # never play). Try every honest base before giving
                # up; the source folder comes from the OTIO metadata
                # written by export_otio since round 22.
                src_folder = meta.get("sourceFolder") or ""
                candidates = []
                if os.path.isabs(target):
                    candidates.append(target)
                else:
                    candidates.append(os.path.join(otio_dir, target))
                    candidates.append(target)
                    candidates.append(os.path.join(dest_folder, target))
                    candidates.append(os.path.join(
                        dest_folder, "media",
                        os.path.basename(target)))
                    if src_folder:
                        candidates.append(
                            os.path.join(src_folder, target))
                resolved = None
                for cand in candidates:
                    if os.path.isfile(cand):
                        resolved = cand
                        break
                if resolved is None:
                    missing.append(target)
                    # Keep the original target verbatim: inventing
                    # a relpath to a file that does not exist made
                    # broken records (e.g. "media/mp4") that looked
                    # playable but were not.
                    stored = target
                else:
                    # Store a path the project can open: relative
                    # to the destination folder when possible, else
                    # absolute.
                    try:
                        stored = os.path.relpath(resolved, dest_folder)
                    except ValueError:
                        stored = resolved
                medium = next((m for m in data["media"]
                               if m["path"] == stored), None)
                if medium is None:
                    medium = {"id": f"m-{uuid.uuid4().hex[:8]}",
                              "path": stored, "kind": "video"}
                    data["media"].append(medium)
                item = {"id": clip_id, "media": medium["id"],
                        "in": int(start), "dur": int(dur), "at": at,
                        "speed": float(cmeta.get("speed", 1.0) or 1.0)}
                for key in ("keyframes", "color", "volume", "fadeIn", "fadeOut"):
                    if cmeta.get(key) is not None:
                        item[key] = cmeta[key]
            else:
                # Text clip (Phase 3 exports captions this way).
                text = child.get("name") or ""
                item = {"id": clip_id, "at": at, "dur": int(dur),
                        "text": text,
                        "textStyle": {"size": 0.062, "positionY": 0.8,
                                      "positionX": 0.5}}
                # A clip with no media reference is a caption: the
                # track becomes a text track so the renderer draws it.
                track["kind"] = "text"
            track["items"].append(item)
            n_clips += 1
            # Resolve a pending transition now that its "to" clip is known.
            for pending in list(imported_transitions):
                if pending.get("resolved") or pending.get("final"):
                    continue
                pending["to"] = clip_id
                pending["resolved"] = True
                kind2 = pending["kind"]
                if not kind2:
                    kind2 = "dissolve" if pending["transition_type"] == \
                        "SMPTE_Dissolve" else None
                if kind2 is None or pending["duration"] <= 0:
                    warnings.append("Transition skipped: unknown kind "
                                    "or zero duration")
                    continue
                from .project import TRANSITION_XFADE
                if kind2 not in TRANSITION_XFADE:
                    warnings.append(
                        f"Transition kind {kind2!r} not supported, skipped")
                    continue
                from_id = id_map.get(pending["pending_from"],
                                     pending["pending_from"])
                imported_transitions.append({
                    "id": pending["id"] or f"tr-{uuid.uuid4().hex[:8]}",
                    "kind": kind2, "from": from_id, "to": clip_id,
                    "duration": int(pending["duration"]),
                    "final": True})
            prev_clip_id = clip_id
        track["items"].sort(key=lambda i: i["at"])
        data["tracks"].append(track)
    for trans in imported_transitions:
        if trans.get("final"):
            data.setdefault("transitions", []).append({
                "id": trans["id"], "kind": trans["kind"],
                "from": trans["from"], "to": trans["to"],
                "duration": trans["duration"]})
            n_trans += 1
    for marker in (stack.get("markers") or []):
        mmeta = (marker.get("metadata") or {}).get("VibeEdit") or {}
        marked = marker.get("marked_range") or {}
        at = int((marked.get("start_time") or {}).get("value", 0))
        data.setdefault("markers", []).append({
            "id": mmeta.get("id") or f"mk-{uuid.uuid4().hex[:8]}",
            "text": marker.get("name", ""), "at": at})
    data["tracks"].sort(key=lambda t: 0 if t.get("role") == "main" else 1)
    out_path = os.path.join(dest_folder, PROJECT_FILENAME)
    save_project(data, out_path)
    return {"project": out_path, "tracks": len(data["tracks"]),
            "clips": n_clips, "transitions": n_trans,
            "markers": len(data.get("markers", [])),
            "missing": missing, "warnings": warnings}


def export_karaoke_ass(project: dict, out_path: str) -> dict:
    """Write a standalone .ass file for all karaoke items in a project
    (original timeline times, not transition-adjusted)."""
    from .karaoke import build_ass
    fmt = project["format"]
    rate = fps_value(fmt["fps"])
    items = []
    for track in project["tracks"]:
        if track["kind"] != "text":
            continue
        for item in sorted(track["items"], key=lambda i: i["at"]):
            karaoke = item.get("karaoke")
            if not karaoke:
                continue
            style = item.get("textStyle") or {}
            items.append({
                "start_s": item["at"] / rate,
                "end_s": (item["at"] + item["dur"]) / rate,
                "words": karaoke["words"],
                "size_frac": float(style.get("size", 0.062)),
                "position_y": float(style.get("positionY", 0.8))})
    if not items:
        raise ValueError("Project has no karaoke items")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(build_ass(items, int(fmt["width"]), int(fmt["height"])))
    return {"ass": out_path, "karaoke_items": len(items)}


def transition_preview(project: dict, folder: str,
                       transition_id: str) -> dict:
    """Render a still previewing one transition (Phase 8).

    Builds a temporary two-clip project (only the transition's
    from/to clips, trimmed to a short window around the cut so a
    long source clip does not make the preview slow), renders it
    at draft resolution with the real renderer, then grabs one
    frame at the transition midpoint. Returns the PNG path plus
    the draft video it was grabbed from, so the UI can show the
    still without re-rendering. Raises ValueError for an unknown
    transition or clips that are not consecutive on the main track.
    """
    import re
    import subprocess
    from .render import find_tool, render
    trans = next((t for t in project.get("transitions", [])
                  if t["id"] == transition_id), None)
    if trans is None:
        raise ValueError(f"Unknown transition: {transition_id!r}")
    items = {}
    for track in project["tracks"]:
        for item in track["items"]:
            items[item["id"]] = item
    if trans["from"] not in items or trans["to"] not in items:
        raise ValueError("Transition references an unknown clip")
    from_item, to_item = items[trans["from"]], items[trans["to"]]
    if int(from_item["at"]) + int(from_item["dur"]) != int(to_item["at"]):
        raise ValueError("Transition clips are not consecutive")
    rate = fps_value(project["format"]["fps"])
    trans_frames = int(trans["duration"])
    window = trans_frames + 15  # 0.5 s of context on each side
    from_copy = copy.deepcopy(from_item)
    if int(from_copy["dur"]) > window:
        from_copy["in"] = int(from_copy.get("in", 0)) + (
            int(from_copy["dur"]) - window)
        from_copy["dur"] = window
    from_copy["at"] = 0
    to_copy = copy.deepcopy(to_item)
    if int(to_copy["dur"]) > window:
        to_copy["dur"] = window
    to_copy["at"] = int(from_copy["dur"])
    temp = copy.deepcopy(project)
    main = next(t for t in temp["tracks"]
                if t.get("role") == "main" and t["kind"] == "video")
    temp["tracks"] = [dict(main, items=[from_copy, to_copy])]
    temp["transitions"] = [copy.deepcopy(trans)]
    temp["markers"] = []
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", transition_id)
    previews = os.path.join(folder, "render", "previews")
    os.makedirs(previews, exist_ok=True)
    video = os.path.join(previews, f"transition-{safe}.mp4")
    png = os.path.join(previews, f"transition-{safe}.png")
    render(temp, folder, video, preset="draft")
    midpoint = (int(from_copy["dur"]) - trans_frames / 2.0) / rate
    proc = subprocess.run(
        [find_tool("ffmpeg"), "-y", "-v", "error",
         "-ss", f"{max(midpoint, 0):.3f}", "-i", video,
         "-frames:v", "1", png],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not os.path.isfile(png):
        raise RuntimeError(f"Transition preview frame grab failed: "
                           f"{proc.stderr[-500:]}")
    return {"transition": trans["id"], "kind": trans["kind"],
            "midpoint_seconds": round(midpoint, 3),
            "image": png, "video": video,
            "width": max(int(project["format"]["width"]) // 2, 2),
            "height": max(int(project["format"]["height"]) // 2, 2)}


def batch_export(folders: list[str], preset: str = "full",
                 out_dir: str | None = None,
                 normalize_audio: bool = False) -> list[dict]:
    """Export several projects sequentially. One failure never stops
    the rest; each result reports ok/failure individually."""
    from .render import render
    results = []
    for folder in folders:
        entry: dict = {"project": folder, "preset": preset}
        try:
            found = find_project_file(folder)
            if not found:
                raise FileNotFoundError(f"No project file in folder: {folder}")
            data = load_project(found)
            out = os.path.join(
                out_dir or os.path.join(folder, "render"),
                f"batch-{data.get('name', 'export')}-{preset}.mp4")
            report = render(data, folder, out, preset=preset,
                            normalize_audio=normalize_audio)
            entry.update({"ok": True, "output": out,
                          "duration": report["duration"]})
        except Exception as exc:  # noqa: BLE001 - reported per project
            entry.update({"ok": False, "error": str(exc)})
        results.append(entry)
    return results


def duplicate_project(src_folder: str, dest_folder: str,
                      new_name: str | None = None) -> str:
    """Copy a project folder (media + project file, not renders or
    backups) and give the copy a new id, name and rev 0."""
    if os.path.abspath(src_folder) == os.path.abspath(dest_folder):
        raise ValueError("Destination must differ from the source folder")
    found = find_project_file(src_folder)
    if not found:
        raise FileNotFoundError(f"No project file in folder: {src_folder}")
    if os.path.exists(dest_folder):
        raise ValueError(f"Destination already exists: {dest_folder}")
    os.makedirs(dest_folder)
    for entry in os.listdir(src_folder):
        src_path = os.path.join(src_folder, entry)
        if entry in ("render", "backups") or entry.endswith(".bak"):
            continue
        if os.path.isdir(src_path):
            shutil.copytree(src_path, os.path.join(dest_folder, entry))
        else:
            shutil.copy2(src_path, os.path.join(dest_folder, entry))
    data = load_project(os.path.join(dest_folder,
                                     os.path.basename(found)))
    data["id"] = uuid.uuid4().hex
    if new_name:
        data["name"] = new_name
    data["rev"] = 0
    dest_path = os.path.join(dest_folder, PROJECT_FILENAME)
    save_project(data, dest_path)
    if os.path.basename(found) != PROJECT_FILENAME:
        os.remove(os.path.join(dest_folder, os.path.basename(found)))
    return dest_path


def media_metadata(project: dict, folder: str, media_id: str) -> dict:
    """Stored media metadata, enriched with a live ffprobe when the
    file exists. Missing files return stored data plus a warning."""
    from .render import probe_media
    medium = next((m for m in project["media"] if m["id"] == media_id), None)
    if medium is None:
        raise KeyError(f"Unknown media: {media_id}")
    result = dict(medium)
    path = medium["path"]
    abs_path = path if os.path.isabs(path) else os.path.join(folder, path)
    if os.path.isfile(abs_path):
        try:
            result.update(probe_media(abs_path))
            result["probed"] = True
        except Exception as exc:  # noqa: BLE001 - stored data stands
            result["probed"] = False
            result["probe_error"] = str(exc)
    else:
        result["probed"] = False
        result["warning"] = f"Media file not found on disk: {abs_path}"
    return result
