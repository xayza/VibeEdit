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
                      frames_to_seconds)


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
            "format": fmt, "contentLanguage": project.get("contentLanguage")}},
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
        if entry in ("render",) or entry.endswith(".bak"):
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
