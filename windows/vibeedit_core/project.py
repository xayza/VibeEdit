"""VibeEdit project model for the Windows MVP.

Project format (superset of the original, documented in
VibeEdit/docs/windows-port.md):

    {
      "schema": "vibeedit.project/1",
      "id": "...", "name": "...", "rev": 0,
      "format": {"width": 1080, "height": 1920,
                 "fps": [30000, 1001], "sampleRate": 48000},
      "contentLanguage": "vi",
      "media": [{"id", "path", "kind", "fps", "frames",
                 "width", "height", "hasAudio"}],
      "tracks": [{"id", "kind", "role", "name", "items": [
          {"id", "media", "in", "dur", "at", "speed",
           "text", "textStyle", "fadeIn", "fadeOut", "volume"}]}],
      "transitions": [], "markers": []
    }

Rules kept from the original (see docs/specs/02-project-format.md):
time is in integer frames; ``in`` is a source frame at the media fps,
``dur`` and ``at`` are timeline frames at the project fps; item IDs are
stable (a split keeps the ID on the left half and gives the right half
a new ID); unknown fields round-trip unchanged on save; writes are
atomic (temp file + rename); ``rev`` increments on every applied edit.

Compatibility: this reader also opens the original
``bashcut.project/1`` schema and ``project.bashcut.json`` files. New
projects written here use ``vibeedit.project/1`` and
``project.vibeedit.json``. Fields the MVP does not understand are
preserved, never dropped.
"""

from __future__ import annotations

import copy
import itertools
import json
import os
import uuid

SCHEMA = "vibeedit.project/1"
LEGACY_SCHEMA = "bashcut.project/1"
PROJECT_FILENAME = "project.vibeedit.json"
LEGACY_PROJECT_FILENAME = "project.bashcut.json"

_counter = itertools.count(1)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{next(_counter):04d}-{uuid.uuid4().hex[:6]}"


def fps_value(fps) -> float:
    """Rational [num, den] or plain number -> float frames per second."""
    if isinstance(fps, (list, tuple)) and len(fps) == 2 and fps[1]:
        return float(fps[0]) / float(fps[1])
    return float(fps)


def frames_to_seconds(frames: int, fps) -> float:
    return frames / fps_value(fps)


def seconds_to_frames(seconds: float, fps) -> int:
    return int(round(seconds * fps_value(fps)))


DEFAULT_TRACKS = [
    {"id": "v1", "kind": "video", "role": "main", "name": "Main", "items": []},
    {"id": "v2", "kind": "video", "role": "overlay", "name": "Overlay", "items": []},
    {"id": "t1", "kind": "text", "role": "captions", "name": "Captions", "items": []},
    {"id": "a1", "kind": "audio", "role": "dialogue", "name": "Dialogue", "items": []},
    {"id": "a2", "kind": "audio", "role": "music", "name": "Music", "items": []},
]


def new_project(name: str, width: int = 1080, height: int = 1920,
                fps=(30000, 1001), content_language: str = "vi") -> dict:
    return {
        "schema": SCHEMA,
        "id": uuid.uuid4().hex,
        "name": name,
        "rev": 0,
        "format": {"width": int(width), "height": int(height),
                   "fps": [int(fps[0]), int(fps[1])], "sampleRate": 48000},
        "contentLanguage": content_language,
        "media": [],
        "tracks": copy.deepcopy(DEFAULT_TRACKS),
        "transitions": [],
        "markers": [],
    }


def find_project_file(folder: str) -> str | None:
    for name in (PROJECT_FILENAME, LEGACY_PROJECT_FILENAME):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def load_project(path: str) -> dict:
    """Load a project file or folder. Unknown fields are preserved."""
    if os.path.isdir(path):
        found = find_project_file(path)
        if not found:
            raise FileNotFoundError(f"No project file in folder: {path}")
        path = found
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("schema") not in (SCHEMA, LEGACY_SCHEMA):
        raise ValueError(f"Unsupported project schema: {data.get('schema')!r}")
    data.setdefault("tracks", copy.deepcopy(DEFAULT_TRACKS))
    data.setdefault("media", [])
    data.setdefault("transitions", [])
    data.setdefault("markers", [])
    data.setdefault("rev", 0)
    return data


def save_project(project: dict, path: str) -> None:
    """Atomic save: temp file + rename, sorted keys, indented JSON."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, ".vibeedit-save.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(project, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


class Project:
    """Mutable view over a project dict, with validated edit operations."""

    def __init__(self, data: dict, folder: str):
        self.data = data
        self.folder = folder

    # -- lookups ------------------------------------------------------
    @property
    def fps(self):
        return self.data["format"]["fps"]

    @property
    def width(self) -> int:
        return int(self.data["format"]["width"])

    @property
    def height(self) -> int:
        return int(self.data["format"]["height"])

    @property
    def rev(self) -> int:
        return int(self.data.get("rev", 0))

    def track(self, track_id: str) -> dict:
        for track in self.data["tracks"]:
            if track["id"] == track_id:
                return track
        raise KeyError(f"Unknown track: {track_id}")

    def item(self, item_id: str) -> tuple[dict, dict]:
        for track in self.data["tracks"]:
            for item in track["items"]:
                if item["id"] == item_id:
                    return track, item
        raise KeyError(f"Unknown item: {item_id}")

    def media(self, media_id: str) -> dict:
        for medium in self.data["media"]:
            if medium["id"] == media_id:
                return medium
        raise KeyError(f"Unknown media: {media_id}")

    def duration_frames(self) -> int:
        end = 0
        for track in self.data["tracks"]:
            for item in track["items"]:
                end = max(end, int(item["at"]) + int(item["dur"]))
        return end

    def duration_seconds(self) -> float:
        return frames_to_seconds(self.duration_frames(), self.fps)

    # -- validation ---------------------------------------------------
    def _check_overlap(self, track: dict, item: dict, exclude_id=None):
        start, end = int(item["at"]), int(item["at"]) + int(item["dur"])
        for other in track["items"]:
            if other["id"] == exclude_id:
                continue
            o_start, o_end = int(other["at"]), int(other["at"]) + int(other["dur"])
            if start < o_end and o_start < end:
                raise ValueError(
                    f"Item overlaps {other['id']} on track {track['id']}")

    def _bump(self):
        self.data["rev"] = self.rev + 1

    # -- edits --------------------------------------------------------
    def add_media(self, path: str, kind: str = "video", **meta) -> dict:
        medium = {"id": _new_id("m"), "path": path, "kind": kind}
        medium.update(meta)
        self.data["media"].append(medium)
        self._bump()
        return medium

    def add_clip(self, media_id: str, track_id: str, at: int, in_frame: int = 0,
                 dur: int | None = None, speed: float = 1.0) -> dict:
        medium = self.media(media_id)
        track = self.track(track_id)
        if track["kind"] == "text":
            raise ValueError("Cannot place a media clip on a text track")
        if dur is None:
            dur = int(medium.get("frames") or 0)
        if dur <= 0:
            raise ValueError("Clip duration must be positive")
        if speed <= 0:
            raise ValueError("Speed must be positive")
        item = {"id": _new_id("c"), "media": media_id, "in": int(in_frame),
                "dur": int(dur), "at": int(at), "speed": float(speed)}
        self._check_overlap(track, item)
        track["items"].append(item)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return item

    def add_text(self, track_id: str, text: str, at: int, dur: int,
                 size: float = 0.062, position_y: float = 0.8,
                 position_x: float = 0.5) -> dict:
        track = self.track(track_id)
        if track["kind"] != "text":
            raise ValueError("Text items belong on a text track")
        item = {"id": _new_id("s"), "at": int(at), "dur": int(dur),
                "text": text,
                "textStyle": {"size": float(size), "positionY": float(position_y),
                              "positionX": float(position_x)}}
        self._check_overlap(track, item)
        track["items"].append(item)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return item

    def trim(self, item_id: str, edge: str, to_frame: int) -> dict:
        track, item = self.item(item_id)
        to_frame = int(to_frame)
        start, end = int(item["at"]), int(item["at"]) + int(item["dur"])
        if edge == "start":
            if not (start < to_frame < end):
                raise ValueError("Trim start must fall strictly inside the item")
            item["in"] = int(item.get("in", 0)) + (to_frame - start)
            item["dur"] = end - to_frame
            item["at"] = to_frame
        elif edge == "end":
            if not (start < to_frame < end):
                raise ValueError("Trim end must fall strictly inside the item")
            item["dur"] = to_frame - start
        else:
            raise ValueError("edge must be 'start' or 'end'")
        self._bump()
        return item

    def split(self, item_id: str, at_frame: int) -> dict:
        """Split at a timeline frame. Left half keeps the ID (original rule)."""
        track, item = self.item(item_id)
        at_frame = int(at_frame)
        start, end = int(item["at"]), int(item["at"]) + int(item["dur"])
        if not (start < at_frame < end):
            raise ValueError("Split point must fall strictly inside the item")
        right = copy.deepcopy(item)
        right["id"] = _new_id("c" if "media" in item else "s")
        right["at"] = at_frame
        right["dur"] = end - at_frame
        if "media" in item:
            # Source offset advances by the output time consumed on the
            # left half, scaled by speed, converted into source frames at
            # the media fps (falls back to the project fps when unknown).
            try:
                media_fps = fps_value(self.media(item["media"]).get(
                    "fps", self.fps))
            except KeyError:
                media_fps = fps_value(self.fps)
            out_seconds = (at_frame - start) / fps_value(self.fps)
            right["in"] = int(item.get("in", 0)) + int(round(
                out_seconds * float(item.get("speed", 1.0)) * media_fps))
        item["dur"] = at_frame - start
        track["items"].append(right)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return right

    def move(self, item_id: str, track_id: str, at: int) -> dict:
        track, item = self.item(item_id)
        dest = self.track(track_id)
        if dest["kind"] == "text" and "media" in item:
            raise ValueError("Cannot move a media clip onto a text track")
        if dest["kind"] != "text" and "media" not in item:
            raise ValueError("Cannot move a text item onto a media track")
        old_track, old_at = track, item["at"]
        track["items"].remove(item)
        item["at"] = int(at)
        try:
            self._check_overlap(dest, item)
        except ValueError:
            track["items"].append(item)
            track["items"].sort(key=lambda i: i["at"])
            item["at"] = old_at
            raise
        dest["items"].append(item)
        dest["items"].sort(key=lambda i: i["at"])
        self._bump()
        return item

    def delete(self, item_id: str) -> None:
        track, item = self.item(item_id)
        track["items"].remove(item)
        self._bump()

    def set_speed(self, item_id: str, speed: float) -> dict:
        _, item = self.item(item_id)
        if speed <= 0:
            raise ValueError("Speed must be positive")
        item["speed"] = float(speed)
        self._bump()
        return item

    def set_fade(self, item_id: str, fade_in: float | None = None,
                 fade_out: float | None = None) -> dict:
        _, item = self.item(item_id)
        if fade_in is not None:
            item["fadeIn"] = float(fade_in)
        if fade_out is not None:
            item["fadeOut"] = float(fade_out)
        self._bump()
        return item

    def set_text(self, item_id: str, text: str) -> dict:
        _, item = self.item(item_id)
        if "text" not in item:
            raise ValueError("Item has no text field")
        item["text"] = text
        self._bump()
        return item

    def set_volume(self, item_id: str, volume_db: float) -> dict:
        _, item = self.item(item_id)
        item["volume"] = float(volume_db)
        self._bump()
        return item

    # -- readouts -----------------------------------------------------
    def timeline_text(self) -> str:
        fps = fps_value(self.fps)
        lines = [f"project {self.data.get('name')} rev {self.rev} "
                 f"{self.width}x{self.height} {fps:g}fps "
                 f"{self.duration_seconds():.2f}s"]
        for track in self.data["tracks"]:
            for item in sorted(track["items"], key=lambda i: i["at"]):
                start = frames_to_seconds(item["at"], self.fps)
                end = frames_to_seconds(item["at"] + item["dur"], self.fps)
                desc = item.get("text", item.get("media", ""))
                if isinstance(desc, str):
                    desc = desc.replace("\n", " / ")
                lines.append(f"{track['role'].upper()} {item['id']} "
                             f"{start:.2f}-{end:.2f} {desc}")
        return "\n".join(lines)

    def snapshot(self) -> dict:
        return copy.deepcopy(self.data)

    def restore(self, snapshot: dict) -> None:
        self.data.clear()
        self.data.update(copy.deepcopy(snapshot))
