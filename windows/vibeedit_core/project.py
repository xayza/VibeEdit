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
import re
import uuid

SCHEMA = "vibeedit.project/1"
LEGACY_SCHEMA = "bashcut.project/1"
PROJECT_FILENAME = "project.vibeedit.json"
LEGACY_PROJECT_FILENAME = "project.bashcut.json"

# Transition kinds accepted by the Windows renderer, mapped to FFmpeg
# xfade transition names in render.py. The original schema also uses
# dissolve, wipe, wipe-right, wipe-up, wipe-down, slide and slide-up;
# those are accepted as aliases and stored verbatim.
TRANSITION_XFADE = {
    # Code-gap batch 2: "dissolve" now maps to FFmpeg's literal
    # dissolve xfade (it used to map to fade; both render, dissolve
    # is the original's own kind). New original kinds below map to
    # the nearest real xfade, in the same honest-equivalent style
    # as whip->wind: shutter squeezes horizontally (squeezeh),
    # crash/seamless/infinite zoom are zoom-in, blink/flash are a
    # white flash (fadewhite). Motion-only kinds (spin, roll with
    # rotation, swing/arc, diamond, kaleidoscope, crash-out,
    # infinite-out) have no xfade and still error, never substitute.
    "dissolve": "dissolve", "crossfade": "fade", "fade": "fade",
    "shutter": "squeezeh", "double-exposure": "dissolve",
    "seamless-zoom": "zoomin", "infinite-zoom": "zoomin",
    "crash-zoom": "zoomin", "blur": "hblur",
    "flash": "fadewhite", "blink": "fadewhite",
    "roll": "slideright", "roll-right": "slideright",
    "wipe": "wiperight", "wipe-left": "wipeleft", "wipe-right": "wiperight",
    "wipe-up": "wipeup", "wipe-down": "wipedown",
    "wipe-tl": "wipetl", "wipe-tr": "wipetr",
    "wipe-bl": "wipebl", "wipe-br": "wipebr",
    "slide": "slideleft", "slide-left": "slideleft",
    "slide-right": "slideright", "slide-up": "slideup",
    "slide-down": "slidedown",
    # Phase 3: kinds from FFmpeg's xfade filter, verified against
    # `ffmpeg -h filter=xfade` on FFmpeg 8.1. "whip" has no literal
    # xfade name; the wind transitions are its honest equivalent
    # (fast directional wipe). "glitch" maps to pixelize, the
    # filter's pixelation transition. There is no literal "barn-door"
    # either; vert/horz-open are the centre-open equivalents.
    "whip": "hrwind", "whip-left": "hlwind", "whip-right": "hrwind",
    "whip-up": "vuwind", "whip-down": "vdwind",
    "iris": "circleopen", "iris-open": "circleopen",
    "iris-close": "circleclose", "radial": "radial",
    "circle-open": "circleopen", "circle-close": "circleclose",
    "zoom": "zoomin", "zoom-in": "zoomin",
    "glitch": "pixelize", "pixelize": "pixelize",
    "fadeblack": "fadeblack", "fade-black": "fadeblack",
    "fadewhite": "fadewhite", "fade-white": "fadewhite",
    "fadefast": "fadefast", "fadeslow": "fadeslow",
    "smooth-left": "smoothleft", "smooth-right": "smoothright",
    "smooth-up": "smoothup", "smooth-down": "smoothdown",
    "cover-left": "coverleft", "cover-right": "coverright",
    "cover-up": "coverup", "cover-down": "coverdown",
    "reveal-left": "revealleft", "reveal-right": "revealright",
    "reveal-up": "revealup", "reveal-down": "revealdown",
    "diag-tl": "diagtl", "diag-tr": "diagtr",
    "diag-bl": "diagbl", "diag-br": "diagbr",
    "hlslice": "hlslice", "hrslice": "hrslice",
    "vuslice": "vuslice", "vdslice": "vdslice",
    "hblur": "hblur", "fadegrays": "fadegrays",
    "squeezeh": "squeezeh", "squeezev": "squeezev",
    "vert-open": "vertopen", "vert-close": "vertclose",
    "horz-open": "horzopen", "horz-close": "horzclose",
    "barn-door": "horzopen", "rectcrop": "rectcrop",
    "circlecrop": "circlecrop", "distance": "distance",
}
# Phase B6 motion kinds: rendered by render.py motion chains, not by
# xfade. Defined literally here (NOT imported from render.py) to avoid
# a circular import, since render.py imports from project.py. Keep in
# sync with render.MOTION_TRANSITIONS. Round 4: halftone now renders
# (geq dot mask + maskedmerge in the timeline render, plus the
# Pillow pre-rendered segment path), so it is no longer
# unrenderable; it keeps its own set mirroring
# render.HALFTONE_TRANSITIONS so the two registries stay comparable.
MOTION_TRANSITION_KINDS = {
    "spin", "swing", "arc", "arc-right", "diamond", "crash-out",
    "infinite-out", "screen-in", "screen-out", "dip-black",
    "color-shift", "flicker", "kaleidoscope",
}
HALFTONE_TRANSITION_KINDS = {"halftone"}
UNRENDERABLE_TRANSITION_KINDS: set = set()
TRANSITION_KINDS = sorted(set(TRANSITION_XFADE) | MOTION_TRANSITION_KINDS
                          | HALFTONE_TRANSITION_KINDS)


def validate_reframe(window) -> dict:
    """Validate a reframe window (source-frame fractions, top-left
    origin). Returns a normalised dict; raises on malformed windows
    instead of silently rendering the full frame."""
    if not isinstance(window, dict):
        raise ValueError("reframe must be an object with x, y, w, h")
    try:
        x, y, w, h = (float(window["x"]), float(window["y"]),
                      float(window["w"]), float(window["h"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError("reframe needs numeric x, y, w, h")
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError("reframe x/y/w/h must be fractions in range")
    if x + w > 1 or y + h > 1:
        raise ValueError("reframe window must fit inside the source frame")
    return {"x": x, "y": y, "w": w, "h": h}


def validate_backdrop(backdrop) -> dict:
    """Validate an item backdrop (original ``clip.backdrop``, P3-J7).

    The backdrop fills a fitted picture's bars: kind ``blur`` draws a
    blurred copy of the same frame scaled to fill, kind ``color`` a
    solid colour. ``blur`` is the radius as a share of the frame's
    short side (default 0.05, range 0..0.5 — the original's
    validation test rejects blur=2); ``dim`` darkens it (0..1,
    default 0); ``color`` is #RRGGBB (default black). Returns a
    normalised dict; raises instead of silently rendering a wrong
    backdrop. One deliberate strictness over the original: the
    original parses a bad colour as black (UInt32 ?? 0); here a
    malformed colour is rejected, so a typo cannot silently turn
    the bars black.
    """
    if not isinstance(backdrop, dict):
        raise ValueError("backdrop must be an object with kind")
    kind = backdrop.get("kind")
    if kind not in ("blur", "color"):
        raise ValueError(
            f"backdrop kind must be 'blur' or 'color', not {kind!r}")
    try:
        blur = float(backdrop.get("blur", 0.05))
    except (TypeError, ValueError):
        raise ValueError("backdrop blur must be a number")
    if not 0 <= blur <= 0.5:
        raise ValueError("backdrop blur must be within 0..0.5")
    try:
        dim = float(backdrop.get("dim", 0))
    except (TypeError, ValueError):
        raise ValueError("backdrop dim must be a number")
    if not 0 <= dim <= 1:
        raise ValueError("backdrop dim must be within 0..1")
    color = backdrop.get("color", "#000000")
    if not isinstance(color, str) or not re.fullmatch(
            r"#[0-9A-Fa-f]{6}", color):
        raise ValueError(
            f"backdrop color must be #RRGGBB, not {color!r}")
    return {"kind": kind, "color": color.upper(),
            "blur": blur, "dim": dim}


def run_panel_snapshot(data: dict) -> dict:
    """The run panel's headless state, derived from project data.

    Round 9 re-examines round 8's "no run panel headless" decision:
    the panel itself is a viewer widget, but whether it is shown,
    dismissed or following is plain state, and it is stored here so
    run.dismiss / run.toggle / run.follow have something real to
    change and run.checklist has something real to report. The
    original's visibility rule is: a run with stages the user did
    not close, still going or with a result, or a panel the user
    opened with the agent button. Headless, the closest faithful
    form is: shown_by_user, or a non-empty run log that has not
    been dismissed. There is no run-number boundary in the Windows
    run log, so a dismiss lasts until an explicit show (toggle
    while hidden) rather than "until the next run" — that
    simplification is documented, not hidden.
    """
    panel = data.get("run_panel") or {}
    dismissed = bool(panel.get("dismissed"))
    shown_by_user = bool(panel.get("shown_by_user"))
    log = data.get("run_log") or []
    visible = shown_by_user or (bool(log) and not dismissed)
    return {"dismissed": dismissed, "shown_by_user": shown_by_user,
            "follow": bool(panel.get("follow")), "visible": visible}

# Honest FFmpeg eq presets for the original colour/adjustment idea.
# Values are eq filter arguments; "none" applies nothing.
COLOR_PRESETS = {
    "none": "",
    "vivid": "eq=brightness=0.02:contrast=1.15:saturation=1.25",
    "warm": "eq=brightness=0.02:contrast=1.05:saturation=1.10",
    "cool": "eq=brightness=0.00:contrast=1.05:saturation=1.05",
    "faded": "eq=brightness=0.05:contrast=0.85:saturation=0.80",
    "mono": "eq=saturation=0",
}

# Text presets (Phase 6): size is a fraction of the frame height,
# positionX/positionY are fractions of the frame (0.5 = centre).
# Applied by set_text_style(); the renderer already reads
# textStyle.size/positionX/positionY, so presets need no render change.
TEXT_PRESETS = {
    "title": {"size": 0.12, "positionX": 0.5, "positionY": 0.5},
    "subtitle": {"size": 0.055, "positionX": 0.5, "positionY": 0.85},
    "lower_third": {"size": 0.05, "positionX": 0.25, "positionY": 0.85},
    "top_caption": {"size": 0.055, "positionX": 0.5, "positionY": 0.15},
}

# Keyframe properties. Times are stored in frames relative to the start
# of their item; values are fractions for x/y, a multiplier for scale,
# 0..1 for opacity, dB for volume, and degrees for tilt (Phase 4:
# rendered with FFmpeg's rotate filter, angle expression in radians).
KEYFRAME_PROPS = ("x", "y", "scale", "opacity", "volume", "tilt")

# Neutral eq values: interpolating a preset's parameters toward
# these at strength s gives the Phase 5 preset-strength blend
# (strength 1 = full preset, strength 0 = unadjusted colour).
_EQ_NEUTRAL = {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0}


def eq_preset_filter(preset: str, strength: float = 1.0) -> str:
    """eq filter string for ``preset`` at ``strength`` (0..1).

    Each eq parameter is interpolated toward its neutral value:
    vivid at 0.5 gives brightness 0.01, contrast 1.075, saturation
    1.125. Strength 0 (or preset "none") returns "" so the caller
    skips the eq filter entirely; strength 1 returns the preset's
    stored string verbatim. Raises ValueError on an unknown preset
    or an out-of-range strength.
    """
    if preset in (None, "none"):
        return ""
    if preset not in COLOR_PRESETS:
        raise ValueError(f"Unknown colour preset: {preset!r}")
    strength = float(strength)
    if not 0.0 <= strength <= 1.0:
        raise ValueError("Colour preset strength must be 0..1")
    if strength == 0.0:
        return ""
    if strength == 1.0:
        return COLOR_PRESETS[preset]
    params: dict[str, float] = {}
    body = COLOR_PRESETS[preset]
    if body.startswith("eq="):
        body = body[3:]
    for part in body.split(":"):
        if "=" in part:
            key, value = part.split("=", 1)
            params[key] = float(value)
    blended = []
    for key in ("brightness", "contrast", "saturation"):
        if key in params:
            neutral = _EQ_NEUTRAL[key]
            value = neutral + strength * (params[key] - neutral)
            blended.append(f"{key}={value:.6g}")
    return "eq=" + ":".join(blended) if blended else ""


def validate_cube(path: str) -> int:
    """Validate a .cube LUT file. Returns LUT_3D_SIZE. Raises ValueError."""
    if not os.path.isfile(path):
        raise ValueError(f"LUT file not found: {path}")
    if not str(path).lower().endswith(".cube"):
        raise ValueError(f"LUT file must end with .cube: {path}")
    size = None
    with open(path, encoding="utf-8", errors="strict") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("LUT_3D_SIZE"):
                parts = line.split()
                if len(parts) != 2 or not parts[1].isdigit():
                    raise ValueError(f"Invalid LUT_3D_SIZE line in {path}")
                size = int(parts[1])
                break
            if line and not line.startswith(("#", "TITLE", "DOMAIN_")):
                raise ValueError(f"Invalid .cube content in {path}: {line!r}")
    if size is None:
        raise ValueError(f"No LUT_3D_SIZE found in {path}")
    return size


def keyframe_points(item: dict, prop: str, fps) -> list[tuple[float, float]]:
    """Sorted (seconds-relative-to-item-start, value) points for a property."""
    points = []
    for kf in item.get("keyframes") or []:
        if prop in kf:
            points.append((frames_to_seconds(int(kf["at"]), fps),
                           float(kf[prop])))
    points.sort()
    return points


def interpolate_keyframes(points: list[tuple[float, float]],
                          t: float) -> float | None:
    """Linear interpolation between keyframe points; clamps outside range."""
    if not points:
        return None
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    """Parse SRT text into (start_s, end_s, text) cues. Raises ValueError."""
    cues: list[tuple[float, float, str]] = []
    pattern = re.compile(
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")
    blocks = re.split(r"\r?\n\s*\r?\n", text.strip())
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines:
            continue
        match = pattern.search(lines[0])
        if not match:
            raise ValueError(f"Invalid SRT timecode line: {lines[0]!r}")
        nums = [int(g) for g in match.groups()]
        start = nums[0] * 3600 + nums[1] * 60 + nums[2] + nums[3] / 1000.0
        end = nums[4] * 3600 + nums[5] * 60 + nums[6] + nums[7] / 1000.0
        if end <= start:
            raise ValueError(f"SRT cue ends before it starts: {lines[0]!r}")
        body = " ".join(lines[1:])
        body = re.sub(r"<[^>]+>", "", body).strip()
        if body:
            cues.append((start, end, body))
    if not cues:
        raise ValueError("No SRT cues found")
    return cues

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


def source_span_to_project_frames(span_source_frames, fps_src, fps_proj) -> int:
    """Convert a source-frame span to project frames, seconds-first.

    Round 19: the pre-fix code used source frames directly as project
    frames, doubling durations whenever media fps != project fps
    (e.g. 6797 frames of 59.94fps footage in a 29.97fps project showed
    as 226.79s instead of 113.45s). When fps_src is missing (audio
    has no frame rate) the span is returned unchanged: audio In/Out
    are already in project frames by construction.
    """
    if not fps_src:
        return int(span_source_frames)
    return int(round(float(span_source_frames) / fps_value(fps_src)
                     * fps_value(fps_proj)))


def migrate_fps_units(data: dict) -> dict:
    """One-time fps-unit migration for projects saved before round 19.

    Pre-round-19 clips stored ``dur`` in SOURCE frames (add_clip's
    default and source_insert passed source spans through), while
    every consumer (timeline display, server duration, render) reads
    ``dur`` as PROJECT frames. This converts each video clip's
    ``dur`` from source frames to project frames and stamps
    ``fps_units = "project"`` so it never runs twice. ``in`` stays in
    source frames (render divides it by media fps). Clips whose media
    lacks fps are left untouched and reported as skipped. New
    projects carry the stamp from creation and skip this entirely.
    Stacked ``at`` values get the same treatment: an item placed
    exactly after a converted clip (at == prev at + prev dur, in
    pre-migration units) inherited the previous clip's buggy units,
    so its ``at`` is scaled by the previous clip's ratio. Any other
    ``at`` (gaps, overlaps, user drags) was already stored in true
    project frames and is left alone. Returns {"converted": n,
    "skipped": [item ids], "at_fixed": m}.
    """
    if data.get("fps_units") == "project":
        return {"converted": 0, "skipped": [], "at_fixed": 0}
    media_by_id = {m.get("id"): m for m in data.get("media", [])}
    fps_proj = fps_value(data["format"]["fps"])
    converted = 0
    skipped = []
    # Snapshot pre-migration geometry before dur conversion mutates it.
    old_geom = {}
    for track in data.get("tracks", []):
        for item in track.get("items", []):
            old_geom[id(item)] = (item.get("at"), item.get("dur"))
    converted_fps = {}
    for track in data.get("tracks", []):
        for item in track.get("items", []):
            medium = media_by_id.get(item.get("media"))
            if medium is None or medium.get("kind") != "video":
                continue
            fps_src = medium.get("fps")
            if not fps_src:
                skipped.append(item.get("id"))
                continue
            try:
                src = fps_value(fps_src)
            except (TypeError, ValueError):
                skipped.append(item.get("id"))
                continue
            if not src or abs(src - fps_proj) < 1e-9:
                continue
            item["dur"] = source_span_to_project_frames(
                int(item["dur"]), fps_src, data["format"]["fps"])
            converted += 1
            converted_fps[id(item)] = fps_src
    # Reflow stacked `at` values (see docstring). Compare OLD geometry
    # throughout so chained stacks use pre-migration positions.
    at_fixed = 0
    for track in data.get("tracks", []):
        items = track.get("items", [])
        ordered = sorted(
            items,
            key=lambda i: old_geom[id(i)][0]
            if old_geom[id(i)][0] is not None else 0)
        for prev, cur in zip(ordered, ordered[1:]):
            if id(prev) not in converted_fps:
                continue
            prev_at_old, prev_dur_old = old_geom[id(prev)]
            cur_at_old, _ = old_geom[id(cur)]
            if prev_at_old is None or prev_dur_old is None \
                    or cur_at_old is None:
                continue
            if int(cur_at_old) == int(prev_at_old) + int(prev_dur_old):
                cur["at"] = source_span_to_project_frames(
                    int(cur_at_old), converted_fps[id(prev)],
                    data["format"]["fps"])
                at_fixed += 1
    data["fps_units"] = "project"
    return {"converted": converted, "skipped": skipped,
            "at_fixed": at_fixed}


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
        # Phase B2: magnetic Main is ON by default (see set_magnetic).
        "magnetic": True,
        # Round 19: clip ``dur`` is in PROJECT frames (see
        # migrate_fps_units); new projects never need migration.
        "fps_units": "project",
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
    """Atomic save: temp file + rename, sorted keys, indented JSON.

    This is the autosave path and it deliberately creates NO backup
    copy: a backup on every autosave would grow one file per save.
    Backups are created only by write_backup(), called on the first
    save after a project is opened and before data-affecting
    operations (see State.backup_before_change / MCPServer.call)."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, ".vibeedit-save.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(project, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


# -- backups (Phase 0 data safety) ------------------------------------
# Retention rule, applied at every backup-creation time so the folder
# can never grow unbounded: one project.json.bak holding the
# immediately previous saved version, plus a backups/ folder holding
# at most the 5 newest timestamped copies AND at most one copy per
# day for the last 7 days (the two sets may overlap). Backups hold
# only the project JSON, never media, and backups/ is never listed
# as media (media comes from project data, not a directory scan) and
# is skipped by duplicate_project().
BACKUP_DIRNAME = "backups"
BACKUP_BASENAME = "project.json.bak"
BACKUP_KEEP_NEWEST = 5
BACKUP_KEEP_DAYS = 7


def _backup_date(entry_name: str, mtime: float) -> str:
    """Calendar date (YYYYMMDD) for a backup file, from its name if
    it carries a timestamp, else from its modification time."""
    import re
    import time
    match = re.match(r"project-(\d{8})-\d{6}", entry_name)
    if match:
        return match.group(1)
    return time.strftime("%Y%m%d", time.localtime(mtime))


def prune_backups(folder: str) -> list[str]:
    """Delete timestamped backups outside the retention rule.
    Returns the deleted filenames. Never touches project.json.bak."""
    import time
    backup_dir = os.path.join(folder, BACKUP_DIRNAME)
    if not os.path.isdir(backup_dir):
        return []
    entries = []
    for name in os.listdir(backup_dir):
        path = os.path.join(backup_dir, name)
        if os.path.isfile(path) and name.endswith(".json"):
            entries.append((os.path.getmtime(path), name))
    entries.sort(reverse=True)  # newest first
    keep: set[str] = set()
    for _, name in entries[:BACKUP_KEEP_NEWEST]:
        keep.add(name)
    cutoff = time.time() - BACKUP_KEEP_DAYS * 86400
    kept_days: set[str] = set()
    for mtime, name in entries:
        if mtime < cutoff:
            continue
        day = _backup_date(name, mtime)
        if day not in kept_days:
            kept_days.add(day)
            keep.add(name)
    deleted = []
    for _, name in entries:
        if name not in keep:
            try:
                os.remove(os.path.join(backup_dir, name))
                deleted.append(name)
            except OSError:
                pass
    return deleted


def write_backup(project_path: str) -> dict | None:
    """Back up the CURRENT SAVED project file before it is
    overwritten: copy it to project.json.bak (previous version) and
    to a timestamped copy in backups/, then prune. Returns the
    backup locations, or None when there is no saved file yet
    (nothing to back up). Backup failures must never block an edit,
    so callers swallow exceptions from this function."""
    folder = os.path.dirname(os.path.abspath(project_path))
    if not os.path.isfile(project_path):
        return None
    import shutil
    import time
    with open(project_path, "rb") as fh:
        content = fh.read()
    bak_path = os.path.join(folder, BACKUP_BASENAME)
    with open(bak_path, "wb") as fh:
        fh.write(content)
    backup_dir = os.path.join(folder, BACKUP_DIRNAME)
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    candidate = os.path.join(backup_dir, f"project-{stamp}.json")
    suffix = 2
    while os.path.exists(candidate):
        candidate = os.path.join(
            backup_dir, f"project-{stamp}-{suffix}.json")
        suffix += 1
    with open(candidate, "wb") as fh:
        fh.write(content)
    prune_backups(folder)
    return {"bak": bak_path, "copy": candidate}


def unique_media_name(media_dir: str, filename: str) -> str:
    """A stored media name that never overwrites an existing file:
    ``clip.mp4`` stays ``clip.mp4`` when free, else ``clip-2.mp4``,
    ``clip-3.mp4``, ... The caller stores under the returned name
    and records it in the project, so old clips keep pointing at
    the old file. Only the basename is used (no directories)."""
    safe = os.path.basename(filename) or "upload.bin"
    if not os.path.exists(os.path.join(media_dir, safe)):
        return safe
    stem, dot, ext = safe.rpartition(".")
    if not dot:
        stem, ext = safe, ""
    else:
        ext = "." + ext
    n = 2
    while True:
        candidate = f"{stem}-{n}{ext}"
        if not os.path.exists(os.path.join(media_dir, candidate)):
            return candidate
        n += 1


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

    def set_format(self, width, height) -> dict:
        """Change the project frame size (validated, saved by caller).

        This changes the frame size for the next export only — it
        does NOT rescale existing clips, which keep their timeline
        positions and durations."""
        try:
            width = int(width)
            height = int(height)
        except (TypeError, ValueError):
            raise ValueError("Format width and height must be integers")
        if not 240 <= width <= 3840 or not 240 <= height <= 3840:
            raise ValueError(
                "Format width and height must each be between 240 and 3840")
        self.data["format"]["width"] = width
        self.data["format"]["height"] = height
        self._bump()
        return {"width": width, "height": height}

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

    def add_track(self, kind: str, role: str, name: str) -> dict:
        """Add a new empty track (used by Add Layer and the Voiceover
        panel). Track ids follow the MCP tool convention: t1, t2, ..."""
        if kind not in ("video", "text", "audio"):
            raise ValueError(f"Unknown track kind: {kind!r}")
        used = {t["id"] for t in self.data["tracks"]}
        n = 1
        while f"t{n}" in used:
            n += 1
        track = {"id": f"t{n}", "kind": kind, "role": role or "",
                 "name": name or kind, "items": []}
        self.data["tracks"].append(track)
        self._bump()
        return track

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
                 dur: int | None = None, speed: float = 1.0,
                 reframe=None) -> dict:
        medium = self.media(media_id)
        track = self.track(track_id)
        if track["kind"] == "text":
            raise ValueError("Cannot place a media clip on a text track")
        if dur is None:
            # Round 19: ``dur`` is PROJECT frames everywhere
            # downstream (timeline, server duration, render), so a
            # media default must be converted from source time,
            # seconds-first. The old code used source frames directly
            # (``dur = frames``), doubling durations whenever media
            # fps != project fps. The duration field, when present,
            # is already in seconds and is the most reliable source.
            proj_fps = self.data["format"]["fps"]
            if medium.get("duration"):
                dur = int(round(float(medium["duration"])
                              * fps_value(proj_fps)))
            elif medium.get("frames"):
                dur = source_span_to_project_frames(
                    int(medium["frames"]), medium.get("fps"), proj_fps)
            else:
                dur = 0
        if dur <= 0:
            raise ValueError("Clip duration must be positive")
        if speed <= 0:
            raise ValueError("Speed must be positive")
        item = {"id": _new_id("c"), "media": media_id, "in": int(in_frame),
                "dur": int(dur), "at": int(at), "speed": float(speed)}
        if reframe is not None:
            item["reframe"] = validate_reframe(reframe)
        if self.magnetic_enabled and self._is_main_track(track) \
                and int(at) >= 0:
            # Magnetic insert (Phase B2): landing strictly inside a
            # clip is refused (an insert never splits a clip), but
            # inserting at a boundary or in a gap shifts every clip
            # at/after the insertion point right by the new duration
            # (with its linked audio), instead of raising overlap.
            for other in track["items"]:
                o_start = int(other["at"])
                if o_start < int(at) < o_start + int(other["dur"]):
                    raise ValueError(
                        "Magnetic insert cannot land inside a clip: "
                        "insert at a clip boundary or in a gap")
            changes: dict = {}
            for other in track["items"]:
                if int(other["at"]) >= int(at):
                    self._shift_with_partners(changes, track, other,
                                              int(dur))
            planned = self._build_planned(changes)
            self._check_planned(planned)
            self._apply_planned(changes)
            self._shift_markers_at(int(at), int(dur))
            track["items"].append(item)
            track["items"].sort(key=lambda i: i["at"])
            self._bump()
            return item
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
            new_at, new_dur = to_frame, end - to_frame
            new_in = int(item.get("in", 0)) + (to_frame - start)
            start_delta = to_frame - start
        elif edge == "end":
            if not (start < to_frame < end):
                raise ValueError("Trim end must fall strictly inside the item")
            new_at, new_dur = start, to_frame - start
            new_in = int(item.get("in", 0))
            start_delta = 0
        else:
            raise ValueError("edge must be 'start' or 'end'")
        # Linked partners take the same edge trim, by the same
        # timeline delta (start trims advance both partners' source
        # offset, end trims shorten both). A partner that would be
        # left with no duration refuses the whole trim.
        changes: dict = {item["id"]: (track["id"], new_at, new_dur)}
        in_updates = [(item, new_in)] if edge == "start" else []
        for partner_track, partner in self._link_partners(item):
            p_start = int(partner["at"])
            if edge == "start":
                p_at = p_start + start_delta
                p_dur = int(partner["dur"]) - start_delta
                p_in = int(partner.get("in", 0)) + start_delta
            else:
                p_at = p_start
                p_dur = int(partner["dur"]) - (end - to_frame)
                p_in = int(partner.get("in", 0))
            if p_dur <= 0:
                raise ValueError(
                    f"Trim would leave linked clip {partner['id']} "
                    f"with no duration")
            changes[partner["id"]] = (partner_track["id"], p_at, p_dur)
            if edge == "start":
                in_updates.append((partner, p_in))
        # Magnetic Main (direct edits only): an end-trim shortens
        # the clip's span, so followers shift left by the trimmed
        # amount; a start-trim leaves the end unchanged, so
        # followers stay. Trimming a linked audio clip trims its
        # Main video but does not ripple Main followers.
        if self.magnetic_enabled and edge == "end" \
                and self._is_main_track(track):
            for follower in self._main_followers(track, item):
                self._shift_with_partners(changes, track, follower,
                                          -(end - to_frame))
        planned = self._build_planned(changes)
        self._check_planned(planned)
        self._apply_planned(changes)
        if self.magnetic_enabled and edge == "end" \
                and self._is_main_track(track):
            self._collapse_markers(to_frame, end, to_frame)
            self._shift_markers_at(end, -(end - to_frame))
        for target, in_value in in_updates:
            target["in"] = in_value
        self._bump()
        return item

    def _split_one(self, track: dict, item: dict, at_frame: int) -> dict:
        """Split one item at a timeline frame: no link handling, no
        rev bump. The left half keeps the id; returns the right half.
        Raises before mutating when the point is outside the item."""
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
        return right

    def split(self, item_id: str, at_frame: int) -> dict:
        """Split at a timeline frame. Left half keeps the ID (original rule).

        A linked partner is split at the same timeline point (it
        must cover the point, else the whole split is refused) and
        the links are rewired so left halves link to each other and
        right halves link to each other (the original linked-split
        rule). Splitting a Main clip changes no span, so magnetic
        followers do not move."""
        track, item = self.item(item_id)
        at_frame = int(at_frame)
        start, end = int(item["at"]), int(item["at"]) + int(item["dur"])
        if not (start < at_frame < end):
            raise ValueError("Split point must fall strictly inside the item")
        partners = self._link_partners(item)
        for _partner_track, partner in partners:
            p_start = int(partner["at"])
            p_end = p_start + int(partner["dur"])
            if not (p_start < at_frame < p_end):
                raise ValueError(
                    f"Linked clip {partner['id']} does not cover "
                    f"the split point {at_frame}; split is refused")
        # Every split below is pre-validated, so nothing here can
        # fail part-way: the split is atomic without a snapshot.
        split_partners = []
        for partner_track, partner in partners:
            split_partners.append(
                (partner_track, partner,
                 self._split_one(partner_track, partner, at_frame)))
        right = self._split_one(track, item, at_frame)
        if self._linked_audio_ids(item):
            # Split video: every linked audio was split above.
            item["linked_audio"] = [p["id"] for _, p, _r in split_partners]
            right["linked_audio"] = [r["id"] for _, _p, r in split_partners]
            for _, partner, right_partner in split_partners:
                partner["linked_video"] = item["id"]
                right_partner["linked_video"] = right["id"]
        elif self._linked_video_id(item) is not None:
            # Split audio: its video partner was split above; the
            # right video half must point at the right audio half.
            _partner_track, partner, right_partner = split_partners[0]
            item["linked_video"] = partner["id"]
            right["linked_video"] = right_partner["id"]
            video_audio = self._linked_audio_ids(partner)
            right_partner["linked_audio"] = [
                right["id"] if aid == item["id"] else aid
                for aid in video_audio]
        self._bump()
        return right

    def move(self, item_id: str, track_id: str, at: int) -> dict:
        track, item = self.item(item_id)
        dest = self.track(track_id)
        if dest["kind"] == "text" and "media" in item:
            raise ValueError("Cannot move a media clip onto a text track")
        if dest["kind"] != "text" and "media" not in item:
            raise ValueError("Cannot move a text item onto a media track")
        old_track, old_at = track, int(item["at"])
        new_at = int(at)
        delta = new_at - old_at
        changes: dict = {item["id"]: (dest["id"], new_at, int(item["dur"]))}
        # Linked partners follow by the same delta on their own
        # tracks, with the same overlap validation as the move.
        for partner_track, partner in self._link_partners(item):
            self._add_shift(changes, partner["id"], partner_track["id"],
                            int(partner["at"]) + delta,
                            int(partner["dur"]))
        if self.magnetic_enabled:
            if old_track["id"] == dest["id"] \
                    and self._is_main_track(track):
                # Same-track Main move: followers shift by the delta.
                # Clip order is preserved: jumping over the previous
                # clip is refused (reordering is not a plain move;
                # the original has a separate reorder operation).
                ordered = sorted(track["items"], key=lambda i: i["at"])
                idx = next(i for i, other in enumerate(ordered)
                           if other["id"] == item["id"])
                if idx > 0:
                    prev = ordered[idx - 1]
                    if new_at < int(prev["at"]) + int(prev["dur"]):
                        raise ValueError(
                            "Magnetic move cannot jump over the "
                            "previous Main clip (clip order is "
                            "preserved)")
                for follower in ordered[idx + 1:]:
                    self._shift_with_partners(changes, track, follower,
                                              delta)
            elif self._is_main_track(old_track) \
                    and not self._is_main_track(dest):
                # Leaving Main: followers close the gap, as on delete.
                for follower in self._main_followers(old_track, item):
                    self._shift_with_partners(changes, old_track, follower,
                                              -int(item["dur"]))
            elif not self._is_main_track(old_track) \
                    and self._is_main_track(dest):
                # Entering Main: clips at/after the destination shift
                # right to make room; landing inside a clip is refused.
                for other in dest["items"]:
                    o_start = int(other["at"])
                    if o_start < new_at < o_start + int(other["dur"]):
                        raise ValueError(
                            "Magnetic move cannot land inside a "
                            "Main clip")
                for other in dest["items"]:
                    if int(other["at"]) >= new_at:
                        self._shift_with_partners(changes, dest, other,
                                                  int(item["dur"]))
        planned = self._build_planned(changes)
        self._check_planned(planned)
        self._apply_planned(changes)
        # Markers follow the move. Magnetic Main moves ripple the
        # tail, so markers at/after the old position shift by the
        # move delta (they annotated the moved clip or its
        # followers, both of which shift); leaving Main closes the
        # gap exactly like a delete; entering Main inserts room
        # exactly like an insert; any other move just carries the
        # markers inside the moved clip's own span with it.
        if self.magnetic_enabled and old_track["id"] == dest["id"] \
                and self._is_main_track(track):
            self._shift_markers_at(old_at, delta)
        elif self.magnetic_enabled and self._is_main_track(old_track) \
                and not self._is_main_track(dest):
            self._collapse_markers(old_at, old_at + int(item["dur"]),
                                   old_at)
            self._shift_markers_at(old_at + int(item["dur"]),
                                   -int(item["dur"]))
        elif self.magnetic_enabled and not self._is_main_track(old_track) \
                and self._is_main_track(dest):
            self._shift_markers_at(new_at, int(item["dur"]))
        else:
            self._shift_markers_in_span(old_at,
                                        old_at + int(item["dur"]), delta)
        self._bump()
        return item

    def delete(self, item_id: str) -> None:
        track, item = self.item(item_id)
        dur = int(item["dur"])
        removed = {item["id"]}
        changes: dict = {}
        surviving_video = None
        partners = self._link_partners(item)
        if self._linked_audio_ids(item):
            # Deleting the video takes its audio with it (original rule).
            for _partner_track, partner in partners:
                removed.add(partner["id"])
        elif self._linked_video_id(item) is not None:
            # Deleting the audio alone keeps its video, unlinked
            # (original rule): only the link field is cleared.
            surviving_video = partners[0][1]
        if self.magnetic_enabled and self._is_main_track(track):
            for follower in self._main_followers(track, item):
                self._shift_with_partners(changes, track, follower, -dur)
        planned = self._build_planned(changes, removed)
        self._check_planned(planned)
        self._apply_planned(changes, removed)
        if self.magnetic_enabled and self._is_main_track(track):
            start = int(item["at"])
            self._collapse_markers(start, start + dur, start)
            self._shift_markers_at(start + dur, -dur)
        if surviving_video is not None:
            remaining = [aid for aid in
                         self._linked_audio_ids(surviving_video)
                         if aid != item["id"]]
            if remaining:
                surviving_video["linked_audio"] = remaining
            else:
                surviving_video.pop("linked_audio", None)
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

    def set_text_style(self, item_id: str, preset: str | None = None,
                       size: float | None = None,
                       position_x: float | None = None,
                       position_y: float | None = None) -> dict:
        """Apply a text preset and/or explicit style values to a
        text item. Unknown presets raise ValueError; explicit values
        override the preset's values for that field."""
        _, item = self.item(item_id)
        if "text" not in item:
            raise ValueError("Item has no text field")
        style = dict(item.get("textStyle", {}))
        if preset is not None:
            if preset not in TEXT_PRESETS:
                raise ValueError(
                    f"Unknown text preset: {preset!r} "
                    f"(choose one of {', '.join(sorted(TEXT_PRESETS))})")
            style.update(TEXT_PRESETS[preset])
        if size is not None:
            style["size"] = float(size)
        if position_x is not None:
            style["positionX"] = float(position_x)
        if position_y is not None:
            style["positionY"] = float(position_y)
        item["textStyle"] = style
        self._bump()
        return item

    def copy_item_data(self, item: dict, track_id: str, at: int) -> dict:
        """Copy an item dict onto ``track_id`` at frame ``at`` with a
        new id, preserving keyframes, colour, fades, volume, speed,
        text style and karaoke timings. For media clips the media
        entry must already exist in this project (same media id);
        cross-project copies must copy the media entry first (see
        MCP vibeedit_clip_paste_cross_project). Overlap on the
        target track raises ValueError, like add_clip/add_text."""
        track = self.track(track_id)
        if track["kind"] == "text" and "text" not in item:
            raise ValueError("Cannot place a media clip on a text track")
        if track["kind"] != "text" and "text" in item:
            raise ValueError("Text items belong on a text track")
        if "text" in item:
            new = self.add_text(track_id, item["text"], int(at),
                                int(item["dur"]))
            if "textStyle" in item:
                new["textStyle"] = copy.deepcopy(item["textStyle"])
            if "karaoke" in item:
                new["karaoke"] = copy.deepcopy(item["karaoke"])
            self._bump()
            return new
        medium = self.media(item["media"])  # KeyError if absent
        new = self.add_clip(medium["id"], track_id, int(at),
                            int(item.get("in", 0)), int(item["dur"]),
                            float(item.get("speed", 1.0)))
        for field in ("keyframes", "color", "fadeIn", "fadeOut",
                      "volume"):
            if field in item:
                new[field] = copy.deepcopy(item[field])
        self._bump()
        return new

    def duplicate_item(self, item_id: str, track_id: str, at: int) -> dict:
        """Copy an item of this project onto ``track_id`` at ``at``."""
        _, item = self.item(item_id)
        return self.copy_item_data(item, track_id, at)

    # -- Phase 2: transitions, keyframes, colour, SRT ------------------
    def add_transition(self, from_id: str, to_id: str, kind: str,
                       duration_s: float) -> dict:
        """Add a transition between two consecutive main-track clips.

        Stored in the original transitions[] shape: {id, kind, from, to,
        duration} with duration in frames. Duration must be 0.1–2.0 s
        and must not exceed the shorter adjacent clip.
        """
        if kind in UNRENDERABLE_TRANSITION_KINDS:
            raise ValueError(
                f"Transition kind {kind!r} cannot be rendered: no FFmpeg "
                f"filter chain reproduces it; path: pre-rendered segment")
        if kind not in TRANSITION_XFADE and \
                kind not in MOTION_TRANSITION_KINDS and \
                kind not in HALFTONE_TRANSITION_KINDS:
            raise ValueError(
                f"Unknown transition kind: {kind!r} "
                f"(choose one of {', '.join(TRANSITION_KINDS)})")
        duration_s = float(duration_s)
        if not 0.1 <= duration_s <= 2.0:
            raise ValueError("Transition duration must be 0.1–2.0 seconds")
        _, from_item = self.item(from_id)
        _, to_item = self.item(to_id)
        main = next((t for t in self.data["tracks"]
                     if t.get("role") == "main" and t["kind"] == "video"), None)
        if main is None:
            raise ValueError("Project has no main video track")
        main_ids = [i["id"] for i in main["items"]]
        if from_id not in main_ids or to_id not in main_ids:
            raise ValueError("Transitions only join main-track clips")
        if int(from_item["at"]) + int(from_item["dur"]) != int(to_item["at"]):
            raise ValueError("Transition clips must be directly consecutive "
                             "(no gap between them)")
        dur_frames = seconds_to_frames(duration_s, self.fps)
        if dur_frames <= 0 or dur_frames > min(int(from_item["dur"]),
                                               int(to_item["dur"])):
            raise ValueError("Transition duration exceeds the shorter "
                             "adjacent clip")
        for existing in self.data["transitions"]:
            if existing["from"] == from_id and existing["to"] == to_id:
                raise ValueError("A transition already exists for this cut")
        transition = {"id": _new_id("tr"), "kind": kind,
                      "from": from_id, "to": to_id,
                      "duration": dur_frames}
        self.data["transitions"].append(transition)
        self._bump()
        return transition

    def remove_transition(self, transition_id: str) -> None:
        before = len(self.data["transitions"])
        self.data["transitions"] = [t for t in self.data["transitions"]
                                    if t["id"] != transition_id]
        if len(self.data["transitions"]) == before:
            raise KeyError(f"Unknown transition: {transition_id}")
        self._bump()

    def set_keyframes(self, item_id: str, keyframes: list[dict]) -> dict:
        """Replace an item's keyframes. Times are frames relative to the
        item start; values are validated per property."""
        _, item = self.item(item_id)
        dur = int(item["dur"])
        cleaned: list[dict] = []
        for kf in keyframes:
            at = int(kf["at"])
            if not 0 <= at <= dur:
                raise ValueError("Keyframe time must fall inside the item")
            entry = {"at": at}
            for prop in KEYFRAME_PROPS:
                if prop in kf:
                    value = float(kf[prop])
                    if prop in ("x", "y") and not 0.0 <= value <= 1.0:
                        raise ValueError("x/y keyframes must be 0..1")
                    if prop == "scale" and value <= 0:
                        raise ValueError("scale keyframes must be positive")
                    if prop == "opacity" and not 0.0 <= value <= 1.0:
                        raise ValueError("opacity keyframes must be 0..1")
                    if prop == "volume" and not -60.0 <= value <= 24.0:
                        raise ValueError("volume keyframes must be -60..24 dB")
                    if prop == "tilt" and not -180.0 <= value <= 180.0:
                        raise ValueError("tilt keyframes must be -180..180 degrees")
                    entry[prop] = value
            if len(entry) == 1:
                raise ValueError("Keyframe must set at least one property")
            cleaned.append(entry)
        cleaned.sort(key=lambda k: k["at"])
        item["keyframes"] = cleaned
        self._bump()
        return item

    def add_keyframe(self, item_id: str, at_seconds: float, prop: str,
                     value: float) -> dict:
        _, item = self.item(item_id)
        if prop not in KEYFRAME_PROPS:
            raise ValueError(f"Unknown keyframe property: {prop!r}")
        existing = [dict(kf) for kf in item.get("keyframes") or []]
        at = seconds_to_frames(float(at_seconds), self.fps)
        merged = False
        for kf in existing:
            if kf["at"] == at:
                kf[prop] = float(value)
                merged = True
        if not merged:
            existing.append({"at": at, prop: float(value)})
        return self.set_keyframes(item_id, existing)

    # Per-parameter eq ranges (FFmpeg eq filter, verified on FFmpeg 8):
    # brightness -1..1 (neutral 0), contrast 0..2 (neutral 1),
    # saturation 0..3 (neutral 1), gamma 0.1..10 (neutral 1).
    EQ_RANGES = {"brightness": (-1.0, 1.0), "contrast": (0.0, 2.0),
                 "saturation": (0.0, 3.0), "gamma": (0.1, 10.0)}
    EQ_NEUTRAL = {"brightness": 0.0, "contrast": 1.0,
                  "saturation": 1.0, "gamma": 1.0}

    def set_color(self, item_id: str, lut: str | None = None,
                  preset: str | None = None,
                  strength: float | None = None,
                  preset_strength: float | None = None,
                  eq: dict | None = None,
                  clear_eq: bool = False,
                  clear_lut: bool = False) -> dict:
        """Set a clip's colour: a .cube LUT file and/or an eq preset,
        plus an optional LUT strength (0..1, default 1.0 = full LUT)
        and an optional eq preset strength (0..1, default 1.0 = full
        preset, 0 = preset skipped; see eq_preset_filter).

        Code-gap batch: ``eq`` sets per-parameter FFmpeg eq values
        (brightness/contrast/saturation/gamma), stored on the clip as
        ``color["eq"]`` and rendered by _color_filters; this is the
        Windows equivalent of the original's individual colour sliders
        (the old code only had named presets). ``clear_eq``/``clear_lut``
        remove those parts. A missing or invalid LUT is a hard error,
        never a silent skip.
        """
        _, item = self.item(item_id)
        color = dict(item.get("color") or {})
        if lut is not None:
            if lut == "":
                color.pop("lut", None)
                color.pop("strength", None)
            else:
                validate_cube(lut)
                color["lut"] = lut
        if clear_lut:
            color.pop("lut", None)
            color.pop("strength", None)
        if preset is not None:
            if preset not in COLOR_PRESETS:
                raise ValueError(
                    f"Unknown colour preset: {preset!r} "
                    f"(choose one of {', '.join(sorted(COLOR_PRESETS))})")
            color["preset"] = preset
        if strength is not None:
            strength = float(strength)
            if not 0.0 <= strength <= 1.0:
                raise ValueError("LUT strength must be 0..1")
            color["strength"] = strength
        if preset_strength is not None:
            preset_strength = float(preset_strength)
            if not 0.0 <= preset_strength <= 1.0:
                raise ValueError("Colour preset strength must be 0..1")
            color["preset_strength"] = preset_strength
        if clear_eq:
            color.pop("eq", None)
        if eq is not None:
            if not isinstance(eq, dict) or not eq:
                raise ValueError("eq must be a non-empty object")
            merged = dict(color.get("eq") or {})
            for key, value in eq.items():
                if key not in self.EQ_RANGES:
                    raise ValueError(
                        f"Unknown eq parameter: {key!r} "
                        f"(choose one of {', '.join(sorted(self.EQ_RANGES))})")
                value = float(value)
                lo, hi = self.EQ_RANGES[key]
                if not lo <= value <= hi:
                    raise ValueError(
                        f"eq {key} must be {lo}..{hi}, got {value}")
                merged[key] = value
            color["eq"] = merged
        if not color:
            if clear_eq or clear_lut:
                item["color"] = {}
                self._bump()
                return item
            raise ValueError("Provide a LUT path, a colour preset, "
                             "and/or eq parameters")
        if "lut" in color:
            color.setdefault("strength", 1.0)
        if "preset" in color:
            color.setdefault("preset_strength", 1.0)
        item["color"] = color
        self._bump()
        return item

    def overwrite_insert(self, media_id: str, in_frame: int, out_frame: int,
                         at: int, track_id: str | None = None) -> dict:
        """Insert a source range at ``at``, overwriting whatever it
        covers on the target track (original Q workflow). Overlapping
        clips are trimmed at the edges, a clip spanning the whole
        range is split into left/right parts, and clips fully inside
        the range are deleted. Returns the new clip.
        """
        import copy as _copy
        if out_frame <= in_frame:
            raise ValueError("Source Out must be after Source In")
        medium = self.media(media_id)
        if track_id is None:
            want_kind = medium.get("kind") or "video"
            if want_kind == "video":
                track_id = next(
                    (t["id"] for t in self.data["tracks"]
                     if t["kind"] == "video" and t.get("role") == "main"),
                    None)
            if not track_id:
                track_id = next(
                    (t["id"] for t in self.data["tracks"]
                     if t["kind"] == want_kind),
                    self.data["tracks"][0]["id"])
        track = self.track(track_id)
        # Round 19: in/out are SOURCE frames, at/dur are PROJECT
        # frames. Convert the inserted span once; all overlap math
        # below (at/end) is in project frames.
        dur = source_span_to_project_frames(
            out_frame - in_frame, medium.get("fps"),
            self.data["format"]["fps"])
        end = at + dur

        def _span_to_item_source(item, span_proj):
            # A project-frame span consumed from an existing clip,
            # back to that clip's own source frames (for its ``in``
            # shift when split/trimmed). Audio has no fps, so its
            # span is unchanged (old behaviour).
            try:
                med = self.media(item["media"])
            except (KeyError, ValueError):
                return int(round(span_proj))
            if not med.get("fps"):
                return int(round(span_proj))
            return int(round(float(span_proj) / fps_value(
                self.data["format"]["fps"]) * fps_value(med["fps"])))
        # Phase B2: a touched clip's linked audio must follow the
        # same cut (trimmed, split, or deleted with its video), so
        # the link never silently desyncs. Overwriting a linked
        # audio clip itself is refused (its Main video would need
        # a ripple the overwrite does not perform), and a linked
        # audio that is not exactly aligned with its video is
        # refused too: mirroring a cut onto a misaligned partner
        # would invent new timings. Both refusals happen before
        # any mutation.
        for item in track["items"]:
            istart, iend = item["at"], item["at"] + item["dur"]
            if iend <= at or istart >= end:
                continue
            if self._linked_video_id(item) is not None:
                raise ValueError(
                    "Cannot overwrite a linked audio clip: unlink "
                    "it from its video first")
            for _pt, partner in self._link_partners(item):
                if int(partner["at"]) != istart \
                        or int(partner["dur"]) != int(item["dur"]):
                    raise ValueError(
                        f"Linked audio {partner['id']} is not "
                        f"aligned with clip {item['id']}: unlink "
                        f"or realign it before overwriting")
        # Partner edits are collected first and applied only after
        # the new clip is verified to fit the kept list, so a failed
        # overwrite never half-edits an audio track.
        partner_trims: list[tuple[dict, int, int, int]] = []
        partner_deletes: list[tuple[dict, dict]] = []
        partner_splits: list[tuple[dict, dict, dict, dict]] = []
        kept = []
        for item in track["items"]:
            istart, iend = item["at"], item["at"] + item["dur"]
            if iend <= at or istart >= end:
                kept.append(item)
            elif istart < at and iend > end:
                speed = item.get("speed") or 1.0
                left = dict(item)
                left["dur"] = at - istart
                right = _copy.deepcopy(item)
                right["id"] = _new_id("c")
                right["in"] = item["in"] + _span_to_item_source(
                    item, (end - istart) / speed)
                right["dur"] = iend - end
                right["at"] = end
                kept.extend([left, right])
                left_ids, right_ids = [], []
                for p_track, partner in self._link_partners(item):
                    p_speed = partner.get("speed") or 1.0
                    left_p = dict(partner)
                    left_p["dur"] = at - istart
                    right_p = _copy.deepcopy(partner)
                    right_p["id"] = _new_id("c")
                    right_p["in"] = partner.get("in", 0) + \
                        _span_to_item_source(
                            partner, (end - istart) / p_speed)
                    right_p["dur"] = iend - end
                    right_p["at"] = end
                    right_p["linked_video"] = right["id"]
                    partner_splits.append(
                        (p_track, partner, left_p, right_p))
                    left_ids.append(left_p["id"])
                    right_ids.append(right_p["id"])
                if left_ids:
                    left["linked_audio"] = left_ids
                    right["linked_audio"] = right_ids
            elif istart < at:
                item["dur"] = at - istart
                kept.append(item)
                for _pt, partner in self._link_partners(item):
                    partner_trims.append(
                        (partner, int(partner["at"]), at - istart,
                         int(partner.get("in", 0))))
            elif iend > end:
                speed = item.get("speed") or 1.0
                delta = end - istart
                item["in"] = item["in"] + _span_to_item_source(
                    item, delta / speed)
                item["dur"] = iend - end
                item["at"] = end
                kept.append(item)
                for _pt, partner in self._link_partners(item):
                    p_speed = partner.get("speed") or 1.0
                    partner_trims.append(
                        (partner, end, iend - end,
                         int(partner.get("in", 0)) +
                         _span_to_item_source(
                             partner, delta / p_speed)))
            # else: fully inside the range -> dropped
            else:
                for p_track, partner in self._link_partners(item):
                    partner_deletes.append((p_track, partner))
        new_item = {"id": _new_id("c"), "media": media_id,
                    "in": int(in_frame), "dur": int(dur), "at": int(at),
                    "speed": 1.0}
        # The new clip is placed directly, not via add_clip: an
        # overwrite preserves the covered span, so magnetic insert
        # must not shift the clips after it.
        self._check_overlap({"id": track_id, "items": kept}, new_item)
        for p_track, partner in partner_deletes:
            p_track["items"].remove(partner)
        for p_track, partner, left_p, right_p in partner_splits:
            p_track["items"].remove(partner)
            p_track["items"].extend([left_p, right_p])
            p_track["items"].sort(key=lambda i: i["at"])
        for partner, p_at, p_dur, p_in in partner_trims:
            partner["at"] = p_at
            partner["dur"] = p_dur
            partner["in"] = p_in
        track["items"] = sorted(kept, key=lambda i: i["at"])
        track["items"].append(new_item)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return new_item

    def close_gaps(self, track_id: str | None = None) -> dict:
        """Close gaps on one track: shift each clip left so it starts
        where the previous clip ends (first clip moves to frame 0).
        The Windows equivalent of a magnetic/gap-closing delete. Only
        the given track is touched; other tracks are unchanged.
        Returns the track id and the list of moved item ids.
        """
        if track_id is None:
            track_id = next((t["id"] for t in self.data["tracks"]
                             if t.get("role") == "main"),
                            self.data["tracks"][0]["id"])
        track = self.track(track_id)
        # Phase B2: plan first, then apply, so a moved clip's linked
        # audio follows it by the same delta and a collision on the
        # audio track refuses the whole close (data unchanged).
        changes: dict = {}
        moved = []
        marker_moves = []
        cursor = 0
        for item in sorted(track["items"], key=lambda i: i["at"]):
            marker_moves.append((int(item["at"]), int(item["dur"]),
                                 cursor))
            if int(item["at"]) != cursor:
                delta = cursor - int(item["at"])
                moved.append(item["id"])
                self._add_shift(changes, item["id"], track["id"],
                                cursor, int(item["dur"]))
                for partner_track, partner in self._link_partners(item):
                    self._add_shift(changes, partner["id"],
                                    partner_track["id"],
                                    int(partner["at"]) + delta,
                                    int(partner["dur"]))
            cursor += int(item["dur"])
        planned = self._build_planned(changes)
        self._check_planned(planned)
        self._apply_planned(changes)
        self._remap_markers_close_gaps(marker_moves)
        self._bump()
        return {"track": track_id, "moved": moved}

    # -- Phase B2: magnetic Main + linked audio ----------------------
    # Storage: a video item carries "linked_audio": [audio item ids];
    # each linked audio item carries "linked_video": <video item id>.
    # This is the Windows form of the original's reciprocal
    # linkedAudio/linkedVideo pair (original: singular camelCase
    # strings; Windows: a list, so one video clip may link several
    # Dialogue clips). Links are created only by link_audio() and
    # removed only by unlink_audio() or by deleting the audio clip
    # itself (which keeps its video, unlinked, as in the original);
    # no edit below silently drops a link: an operation that cannot
    # keep a link consistent raises and changes nothing.
    #
    # Magnetic Main: when magnetic_enabled (project data "magnetic",
    # default True, toggled by set_magnetic()) a direct edit to a
    # clip on the Main track ripples its tail: delete shifts
    # following Main clips left by the deleted duration, insert
    # shifts clips at/after the insertion point right by the new
    # duration, an end-trim shifts followers left by the trimmed
    # amount, and a same-track move shifts followers by the move
    # delta. Followers' linked audio shifts with them, each item
    # moving at most once per operation (the original's moved-set
    # rule). Ripple is driven by direct Main edits only: moving or
    # trimming a linked audio clip moves/trims its video but does
    # not ripple Main followers. A magnetic move preserves clip
    # order: jumping over a predecessor is refused, as is any shift
    # that would overlap or start before frame 0. Magnetic off
    # restores the old behaviour exactly (overlap rejected, no tail
    # shift); linked propagation still applies with magnetic off.
    # All B2 edits validate the planned positions before mutating
    # anything, so a refused operation leaves the project data
    # (including rev) unchanged.

    @property
    def magnetic_enabled(self) -> bool:
        """Whether Main-track edits ripple (project data "magnetic",
        default True for projects that predate the toggle)."""
        return bool(self.data.get("magnetic", True))

    def set_magnetic(self, enabled: bool) -> dict:
        """Switch magnetic Main on/off; the state is stored in the
        project data, so it survives save/load and undo (the server
        snapshots before the op, like every other edit)."""
        self.data["magnetic"] = bool(enabled)
        self._bump()
        return {"magnetic": self.magnetic_enabled}

    def _is_main_track(self, track: dict | None) -> bool:
        return bool(track is not None and track.get("role") == "main"
                    and track["kind"] == "video")

    def _main_track(self) -> dict | None:
        for track in self.data["tracks"]:
            if self._is_main_track(track):
                return track
        return None

    def _linked_audio_ids(self, item: dict) -> list[str]:
        raw = item.get("linked_audio")
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        return [str(x) for x in raw]

    def _linked_video_id(self, item: dict) -> str | None:
        raw = item.get("linked_video")
        return str(raw) if raw is not None else None

    def _link_partners(self, item: dict) -> list[tuple[dict, dict]]:
        """(track, item) pairs linked to ``item``: its audio clips
        when it is a video clip, its video clip when it is audio.
        A dangling or one-way link raises ValueError so the caller
        refuses instead of half-applying (validate() reports the
        same problems without raising, for diagnosis)."""
        partners = []
        for audio_id in self._linked_audio_ids(item):
            try:
                partner_track, partner = self.item(audio_id)
            except KeyError:
                raise ValueError(
                    f"Linked audio clip {audio_id!r} is missing")
            if self._linked_video_id(partner) != item["id"]:
                raise ValueError(
                    f"Link to {audio_id!r} is one-way: its audio "
                    f"does not link back to {item['id']!r}")
            partners.append((partner_track, partner))
        video_id = self._linked_video_id(item)
        if video_id is not None:
            try:
                partner_track, partner = self.item(video_id)
            except KeyError:
                raise ValueError(
                    f"Linked video clip {video_id!r} is missing")
            if item["id"] not in self._linked_audio_ids(partner):
                raise ValueError(
                    f"Link to {video_id!r} is one-way: its video "
                    f"does not link back to {item['id']!r}")
            partners.append((partner_track, partner))
        return partners

    def linked_audio(self, video_clip_id: str) -> list[dict]:
        """The audio items linked to a video clip (empty when unlinked)."""
        _, item = self.item(video_clip_id)
        return [audio for _, audio in self._link_partners(item)]

    def link_audio(self, video_clip_id: str, audio_clip_id: str) -> dict:
        """Link a Dialogue audio clip to a video clip. The audio
        must live on an audio track and must not already be linked
        to another video clip; a video clip may link several audio
        clips. Linking the same pair twice is refused."""
        _, video = self.item(video_clip_id)
        audio_track, audio = self.item(audio_clip_id)
        if "media" not in video or "media" not in audio:
            raise ValueError("Only media clips can be linked")
        if audio_track["kind"] != "audio":
            raise ValueError("Linked audio must live on an audio track")
        if video_clip_id == audio_clip_id:
            raise ValueError("A clip cannot link to itself")
        existing = self._linked_video_id(audio)
        if existing is not None:
            if existing == video_clip_id:
                raise ValueError("These clips are already linked")
            raise ValueError(
                f"Audio clip is already linked to {existing!r}")
        ids = self._linked_audio_ids(video)
        if audio_clip_id in ids:
            raise ValueError("These clips are already linked")
        ids.append(audio_clip_id)
        video["linked_audio"] = ids
        audio["linked_video"] = video_clip_id
        self._bump()
        return {"video": video_clip_id, "audio": audio_clip_id}

    def unlink_audio(self, video_clip_id: str,
                     audio_clip_id: str | None = None) -> dict:
        """Remove a link: one audio clip when ``audio_clip_id`` is
        given, else all of the video clip's linked audio. The audio
        clips themselves are kept; only the link fields are cleared.
        Unlinking a pair that is not linked is refused."""
        _, video = self.item(video_clip_id)
        ids = self._linked_audio_ids(video)
        if audio_clip_id is None:
            targets = list(ids)
            if not targets:
                raise ValueError("Video clip has no linked audio")
        else:
            if audio_clip_id not in ids:
                raise ValueError(
                    "Audio clip is not linked to this video clip")
            targets = [audio_clip_id]
        for target_id in targets:
            try:
                _, audio = self.item(target_id)
            except KeyError:
                continue  # dangling id: dropping it is the fix
            if self._linked_video_id(audio) == video_clip_id:
                audio.pop("linked_video", None)
        remaining = [aid for aid in ids if aid not in targets]
        if remaining:
            video["linked_audio"] = remaining
        else:
            video.pop("linked_audio", None)
        self._bump()
        return {"video": video_clip_id, "unlinked": targets}

    def _build_planned(self, changes: dict, removed=frozenset()):
        """Planned (id, at, dur) lists for every track touched by
        ``changes`` ({item_id: (track_id, at, dur)}) or ``removed``
        (item ids). Items moving tracks leave their old track's
        list and join the new track's list."""
        orig = {}
        for track in self.data["tracks"]:
            for item in track["items"]:
                if item["id"] in changes or item["id"] in removed:
                    orig[item["id"]] = track["id"]
        affected: set[str] = set()
        for item_id, (track_id, _at, _dur) in changes.items():
            affected.add(track_id)
            if item_id in orig:
                affected.add(orig[item_id])
        for item_id in removed:
            if item_id in orig:
                affected.add(orig[item_id])
        planned: dict[str, list] = {}
        for track in self.data["tracks"]:
            if track["id"] not in affected:
                continue
            entries = []
            for item in track["items"]:
                if item["id"] in removed:
                    continue
                change = changes.get(item["id"])
                if change is not None and change[0] != track["id"]:
                    continue  # moved to another track
                if change is not None:
                    entries.append((item["id"], change[1], change[2]))
                else:
                    entries.append((item["id"], int(item["at"]),
                                    int(item["dur"])))
            planned[track["id"]] = entries
        for item_id, (track_id, at, dur) in changes.items():
            entries = planned.setdefault(track_id, [])
            if not any(entry[0] == item_id for entry in entries):
                entries.append((item_id, at, dur))
        return planned

    def _check_planned(self, planned: dict) -> None:
        """Validate planned positions: no negative start, positive
        duration, no overlap on any planned track. Raises ValueError
        on the first problem found."""
        for track_id, entries in planned.items():
            ordered = sorted(entries, key=lambda e: (e[1], e[0]))
            for item_id, at, dur in ordered:
                if at < 0:
                    raise ValueError(
                        f"Item {item_id} would start before frame 0 "
                        f"on track {track_id}")
                if dur <= 0:
                    raise ValueError(
                        f"Item {item_id} would have no duration "
                        f"on track {track_id}")
            for (id1, at1, dur1), (id2, at2, _dur2) in zip(
                    ordered, ordered[1:]):
                if at1 + dur1 > at2:
                    raise ValueError(
                        f"Item {id1} would overlap {id2} "
                        f"on track {track_id}")

    def _apply_planned(self, changes: dict, removed=frozenset()) -> None:
        """Apply position/duration changes and removals validated by
        _check_planned/_build_planned, re-sorting touched tracks.
        ``changes`` and ``removed`` must be disjoint."""
        by_id = {}
        for track in self.data["tracks"]:
            for item in track["items"]:
                by_id[item["id"]] = (track, item)
        touched: set[str] = set()
        for item_id in removed:
            track, item = by_id[item_id]
            track["items"].remove(item)
            touched.add(track["id"])
        for item_id, (track_id, at, dur) in changes.items():
            track, item = by_id[item_id]
            if track["id"] != track_id:
                track["items"].remove(item)
                touched.add(track["id"])
                track = self.track(track_id)
                track["items"].append(item)
                touched.add(track_id)
            item["at"] = at
            item["dur"] = dur
        for track in self.data["tracks"]:
            if track["id"] in touched:
                track["items"].sort(key=lambda i: i["at"])

    def _add_shift(self, changes: dict, item_id: str, track_id: str,
                   at: int, dur: int) -> None:
        """Record a planned position, refusing a second, different
        position for the same item (the move-once rule: a linked
        partner moved with its clip is never moved again by the
        same operation's ripple)."""
        planned = (track_id, at, dur)
        if item_id in changes and changes[item_id] != planned:
            raise ValueError(
                f"Conflicting planned positions for item {item_id}")
        changes[item_id] = planned

    def _shift_with_partners(self, changes: dict, track: dict,
                             item: dict, delta: int) -> None:
        """Shift ``item`` on ``track`` by ``delta`` and shift each of
        its linked partners by the same delta on their own tracks.
        Partners of partners are the item itself, already shifted,
        so the shift never chains."""
        self._add_shift(changes, item["id"], track["id"],
                        int(item["at"]) + delta, int(item["dur"]))
        for partner_track, partner in self._link_partners(item):
            self._add_shift(changes, partner["id"], partner_track["id"],
                            int(partner["at"]) + delta,
                            int(partner["dur"]))

    def _main_followers(self, track: dict, item: dict) -> list[dict]:
        """Main-track items after ``item`` in timeline order."""
        ordered = sorted(track["items"], key=lambda i: i["at"])
        followers = []
        seen = False
        for other in ordered:
            if other["id"] == item["id"]:
                seen = True
            elif seen:
                followers.append(other)
        return followers

    def _shift_markers_at(self, point: int, delta: int) -> None:
        """Shift markers at or after ``point`` by ``delta`` frames
        (clamped at 0). Used by magnetic Main edits so markers track
        the timeline content they annotate."""
        for marker in self.data.get("markers", []):
            if int(marker["at"]) >= point:
                marker["at"] = max(0, int(marker["at"]) + delta)
        self.data.get("markers", []).sort(key=lambda m: m["at"])

    def _collapse_markers(self, start: int, end: int, to: int) -> None:
        """Move markers inside [start, end) to ``to`` (they annotated
        content that no longer spans those frames after a magnetic
        delete/trim). Markers at/after ``end`` are shifted by the
        caller via _shift_markers_at."""
        for marker in self.data.get("markers", []):
            if start <= int(marker["at"]) < end:
                marker["at"] = to

    def _shift_markers_in_span(self, start: int, end: int,
                               delta: int) -> None:
        """Shift markers inside [start, end) by ``delta`` frames
        (clamped at 0). Used when a clip moves without rippling the
        rest of the timeline: markers that annotated the moved clip
        follow it, markers elsewhere stay put."""
        for marker in self.data.get("markers", []):
            if start <= int(marker["at"]) < end:
                marker["at"] = max(0, int(marker["at"]) + delta)
        self.data.get("markers", []).sort(key=lambda m: m["at"])

    def _remap_markers_spans(self, spans: list) -> None:
        """Remap markers in one pass from their ORIGINAL positions.
        ``spans`` is a list of (start, end, delta); a marker inside
        exactly one span shifts by that span's delta, markers
        outside all spans stay. Single-pass matters: applying two
        span shifts sequentially would let a marker shifted by the
        first shift be caught (and shifted again) by the second
        span, which is wrong for reorder (the spans are disjoint
        in original coordinates but overlap after the first
        shift)."""
        for marker in self.data.get("markers", []):
            at = int(marker["at"])
            for start, end, delta in spans:
                if start <= at < end:
                    marker["at"] = max(0, at + delta)
                    break
        self.data.get("markers", []).sort(key=lambda m: m["at"])

    def _remap_markers_close_gaps(self, moves: list) -> None:
        """Remap markers after close_gaps. ``moves`` is a list of
        (original_at, duration, new_at) sorted by original_at.
        Markers inside a moved clip's original span shift with it;
        markers in a gap before an item collapse to that item's new
        start (the gap no longer exists); markers after the last
        item's original end are unchanged."""
        if not moves:
            return
        for marker in self.data.get("markers", []):
            at = int(marker["at"])
            for orig_at, dur, new_at in moves:
                if orig_at <= at < orig_at + dur:
                    marker["at"] = max(0, at + (new_at - orig_at))
                    break
            else:
                prev_end = 0
                for orig_at, dur, new_at in moves:
                    if prev_end <= at < orig_at:
                        marker["at"] = new_at
                        break
                    prev_end = orig_at + dur
        self.data.get("markers", []).sort(key=lambda m: m["at"])

    def reorder_main(self, item_id: str, before_id: str | None = None) -> dict:
        """Magnetic reorder on Main: move a Main clip to just before
        another Main clip (or to the end when ``before_id`` is None).
        Items between the old and new positions shift by the moved
        clip's duration (with their linked audio); all other clips
        keep their positions, and durations never change. Reordering
        is an explicit operation, so it runs even when the magnetic
        toggle is off. Moving a clip before itself is an error, and
        moving it to its current position is a no-op."""
        track, item = self.item(item_id)
        if not self._is_main_track(track):
            raise ValueError("Reorder applies to Main-track clips only")
        ordered = sorted(track["items"], key=lambda i: i["at"])
        ids = [i["id"] for i in ordered]
        if before_id is not None:
            if before_id == item_id:
                raise ValueError("Cannot reorder a clip before itself")
            if before_id not in ids:
                raise ValueError(f"Unknown clip: {before_id!r}")
            before = next(i for i in ordered if i["id"] == before_id)
            target = int(before["at"])
            if ids.index(before_id) == ids.index(item_id) + 1:
                return item  # already directly before it: no-op
        else:
            last = ordered[-1]
            if last["id"] == item_id:
                return item  # already last: no-op
            target = int(last["at"]) + int(last["dur"])
        old_at, dur = int(item["at"]), int(item["dur"])
        changes: dict = {}
        if target < old_at:
            # Moving earlier: items in [target, old_at) shift right.
            for other in ordered:
                if target <= int(other["at"]) < old_at:
                    self._shift_with_partners(changes, track, other, dur)
            self._shift_with_partners(changes, track, item,
                                      target - old_at)
        else:
            # Moving later: items strictly between the moved clip
            # and the target shift left by dur (the before-clip
            # itself shifts left too, so the moved clip lands at
            # target - dur; for "to end", target is the old track
            # end, so the clip lands at old_end - dur).
            for other in ordered:
                if old_at < int(other["at"]) < target or \
                        (before_id is None and
                         int(other["at"]) > old_at):
                    self._shift_with_partners(changes, track, other, -dur)
            self._shift_with_partners(changes, track, item,
                                      target - old_at - dur)
        planned = self._build_planned(changes)
        self._check_planned(planned)
        self._apply_planned(changes)
        # Markers follow the reorder: the whole rearranged region
        # moves as a block. Moving earlier, items in [target,
        # old_at) shift right by dur and the moved clip shifts to
        # target; moving later, the moved clip shifts to
        # target - dur and items in (old_at, target) shift left
        # by dur. Markers in each span shift with that span, in
        # ONE pass from original positions (see
        # _remap_markers_spans: sequential shifts would cascade).
        if target < old_at:
            self._remap_markers_spans([
                (target, old_at, dur),
                (old_at, old_at + dur, target - old_at)])
        else:
            self._remap_markers_spans([
                (old_at, old_at + dur, target - dur - old_at),
                (old_at + dur, target, -dur)])
        self._bump()
        return item

    # -- Code-gap batch 2: speed curves, reverse, freeze --------------
    # Speed-curve presets copied verbatim from the original's
    # SpeedCurve.swift presets: (t, speed) control points, t in 0..1.
    SPEED_CURVE_PRESETS = {
        "montage": [(0, 1), (0.2, 2.5), (0.5, 0.6), (0.8, 2.5), (1, 1)],
        "hero": [(0, 2), (0.35, 2), (0.5, 0.3), (0.65, 2), (1, 2)],
        "bullet": [(0, 2.5), (0.4, 0.25), (0.6, 0.25), (1, 2.5)],
        "jump-cut": [(0, 1), (0.4, 1), (0.5, 5), (0.6, 1), (1, 1)],
        "flash-in": [(0, 5), (0.3, 1), (1, 1)],
        "flash-out": [(0, 1), (0.7, 1), (1, 5)],
    }

    @staticmethod
    def _curve_speed(points, t: float) -> float:
        """Linear interpolation of a speed curve at fraction t."""
        if t <= points[0][0]:
            return float(points[0][1])
        for (t0, v0), (t1, v1) in zip(points, points[1:]):
            if t <= t1:
                if t1 == t0:
                    return float(v1)
                return float(v0 + (v1 - v0) * (t - t0) / (t1 - t0))
        return float(points[-1][1])

    def apply_speed_curve(self, item_id: str, preset: str) -> dict:
        """Apply an original speed-curve preset to a clip.

        The clip keeps its total timeline length; it is split at the
        preset's control-point fractions and each segment gets the
        curve's speed at that segment's midpoint. Splits happen
        first (at the original speed) so source offsets stay correct,
        then speeds are set per segment. Each segment records the
        preset id in ``speedCurve``. Only media clips (not text).
        """
        if preset not in self.SPEED_CURVE_PRESETS:
            raise ValueError(
                f"Unknown speed-curve preset: {preset!r} "
                f"(choose one of {', '.join(sorted(self.SPEED_CURVE_PRESETS))})")
        track, item = self.item(item_id)
        if "media" not in item:
            raise ValueError("Speed curves apply to media clips only")
        points = self.SPEED_CURVE_PRESETS[preset]
        start, dur = int(item["at"]), int(item["dur"])
        if dur <= 0:
            raise ValueError("Clip duration must be positive")
        bounds = []
        for t, _ in points[1:-1]:
            at = start + int(round(dur * t))
            if start < at < start + dur:
                bounds.append(at)
        bounds = sorted(set(bounds))
        # Split from the right so earlier ids/boundaries stay valid.
        segment_ids = [item["id"]]
        for at in reversed(bounds):
            right = self.split(item["id"], at)
            segment_ids.insert(1, right["id"])
        # Segments are now in timeline order on the same track.
        segments = []
        for seg_id in segment_ids:
            _, seg = self.item(seg_id)
            segments.append(seg)
        segments.sort(key=lambda i: i["at"])
        for seg in segments:
            mid = (int(seg["at"]) - start + int(seg["dur"]) / 2) / dur
            seg["speed"] = self._curve_speed(points, mid)
            seg["speedCurve"] = preset
        self._bump()
        return {"item": item_id, "preset": preset,
                "segments": [s["id"] for s in segments],
                "speeds": [s["speed"] for s in segments]}

    def set_reverse(self, item_id: str, reverse: bool = True) -> dict:
        """Flag a media clip to play backwards (FFmpeg reverse/areverse
        in the render chain). The flag is data, not a render trick:
        clearing it restores forward playback."""
        _, item = self.item(item_id)
        if "media" not in item:
            raise ValueError("Reverse applies to media clips only")
        item["reverse"] = bool(reverse)
        self._bump()
        return item

    def set_reframe(self, item_id: str, window) -> dict:
        """Set (or, with window None, clear) a clip's reframe window.
        Rendered by render.reframe_crop_filter: the window crops the
        source frame before scaling, never stretching it."""
        _, item = self.item(item_id)
        if "media" not in item:
            raise ValueError("Reframe applies to media clips only")
        if window is None:
            item.pop("reframe", None)
        else:
            item["reframe"] = validate_reframe(window)
        self._bump()
        return item

    def set_backdrop(self, item_id: str, backdrop) -> dict:
        """Set (or, with backdrop None, remove) a clip's backdrop.

        Rendered by render.py: the fitted picture over a blurred
        fill copy of itself or a solid colour (see
        validate_backdrop). Mirrors the original's guards: the item
        must be a video clip or image on a video track. One honest
        narrowing: the Windows render chain implements the backdrop
        only for main-track items, so an overlay video item is
        rejected with a clear error instead of storing a backdrop
        that would never render (overlay items are composited over
        the main picture and have no backdrop layer yet).
        """
        track, item = self.item(item_id)
        if "media" not in item or track.get("kind") != "video":
            raise ValueError(
                "Backdrop applies to video clips or images only")
        if track.get("role") != "main":
            raise ValueError(
                "Backdrop renders on the main track only in this "
                "build; overlay video items have no backdrop layer "
                "yet")
        if backdrop is None:
            item.pop("backdrop", None)
        else:
            item["backdrop"] = validate_backdrop(backdrop)
        self._bump()
        return item

    def freeze_clip(self, item_id: str, extra_frames: int) -> dict:
        """Append a freeze-frame segment after a media clip: a new clip
        on the same track, at the end of the source clip, flagged
        ``freeze`` so the render chain holds its first source frame
        for the whole segment (audio is silence for that segment).
        The new clip's ``in`` points at the source clip's last frame.
        """
        track, item = self.item(item_id)
        if "media" not in item:
            raise ValueError("Freeze applies to media clips only")
        extra_frames = int(extra_frames)
        if extra_frames <= 0:
            raise ValueError("Freeze length must be positive frames")
        try:
            media_fps = fps_value(self.media(item["media"]).get(
                "fps", self.fps))
        except KeyError:
            media_fps = fps_value(self.fps)
        last_in = int(item.get("in", 0)) + int(round(
            int(item["dur"]) / fps_value(self.fps)
            * float(item.get("speed", 1.0)) * media_fps)) - 1
        frozen = copy.deepcopy(item)
        frozen["id"] = _new_id("c")
        frozen["at"] = int(item["at"]) + int(item["dur"])
        frozen["dur"] = extra_frames
        frozen["in"] = max(0, last_in)
        frozen["freeze"] = True
        frozen["speed"] = 1.0
        self._check_overlap(track, frozen)
        track["items"].append(frozen)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return frozen

    # -- Code-gap batch 2: review workflow ----------------------------
    def run_review(self) -> dict:
        """Run a review: validation + stats + skipped/warnings are
        already real project data (see validate()/project_stats());
        this stores the run in data['review'] with its issue count so
        accept/verify can compare against it. No verdict is invented:
        issues are exactly the validation errors/warnings."""
        validation = self.validate()
        issues = list(validation.get("errors", [])) + [
            str(w) for w in validation.get("warnings", [])]
        review = {
            "status": "run",
            "issues": issues,
            "issue_count": len(issues),
            "stats": self.project_stats(),
            "rev": self.rev,
        }
        self.data["review"] = review
        self._bump()
        return review

    def accept_review(self) -> dict:
        """Accept the last review run: records the reviewed rev and
        marks status accepted. Requires a prior run_review call."""
        review = self.data.get("review")
        if not review or review.get("status") not in ("run", "verified"):
            raise ValueError("Run a review before accepting it")
        review["status"] = "accepted"
        review["accepted_rev"] = self.rev
        self._bump()
        return review

    def verify_review(self) -> dict:
        """Re-run validation and compare issue counts with the last
        review run. Returns the new count, the old count and whether
        the count changed; status becomes verified. Never invents a
        pass/fail verdict beyond the counts."""
        old = self.data.get("review")
        if not old:
            raise ValueError("Run a review before verifying it")
        fresh = self.run_review()
        fresh["status"] = "verified"
        fresh["previous_issue_count"] = old.get("issue_count")
        fresh["issue_count_changed"] = (
            fresh["issue_count"] != old.get("issue_count"))
        self.data["review"] = fresh
        self._bump()
        return fresh

    # -- Code-gap batch 2: library + brand ----------------------------
    def library_add(self, item_id: str, name: str = "") -> dict:
        """Save a clip/text item as a library item (a copy of its
        data, stored in data['library']). Library items are data
        only; placing one re-creates a real clip (see library_place).
        """
        _, item = self.item(item_id)
        entry = {"id": _new_id("lib"), "name": name.strip() or
                 item.get("text") or item.get("media") or item["id"],
                 "item": copy.deepcopy(item)}
        self.data.setdefault("library", []).append(entry)
        self._bump()
        return entry

    def library_list(self) -> list[dict]:
        return copy.deepcopy(self.data.get("library", []))

    def library_remove(self, entry_id: str) -> dict:
        before = len(self.data.get("library", []))
        self.data["library"] = [e for e in self.data.get("library", [])
                                if e["id"] != entry_id]
        if len(self.data["library"]) == before:
            raise KeyError(f"Unknown library item: {entry_id}")
        self._bump()
        return {"deleted": entry_id}

    def library_place(self, entry_id: str, track_id: str | None = None,
                      at: int | None = None) -> dict:
        """Place a library item onto the timeline at a free position
        (playhead-equivalent: ``at`` if given and free, else the end
        of the target track). Media items become real clips; text
        items become real text items. The library entry is kept."""
        entry = next((e for e in self.data.get("library", [])
                      if e["id"] == entry_id), None)
        if entry is None:
            raise KeyError(f"Unknown library item: {entry_id}")
        src = entry["item"]
        if "media" in src:
            if track_id is None:
                track_id = next(
                    (t["id"] for t in self.data["tracks"]
                     if t["kind"] == "video"
                     and t.get("role") == "main"),
                    self.data["tracks"][0]["id"])
            track = self.track(track_id)
            if at is None:
                at = max([i["at"] + i["dur"] for i in track["items"]],
                         default=0)
            return self.add_clip(src["media"], track_id, int(at),
                                 int(src.get("in", 0)),
                                 int(src["dur"]),
                                 float(src.get("speed", 1.0)))
        if track_id is None:
            track_id = next(
                (t["id"] for t in self.data["tracks"]
                 if t["kind"] == "text"),
                self.data["tracks"][0]["id"])
        track = self.track(track_id)
        if at is None:
            at = max([i["at"] + i["dur"] for i in track["items"]],
                     default=0)
        return self.add_text(track_id, src.get("text", ""),
                             int(at), int(src["dur"]))

    def brand_set(self, colours: list | None = None,
                  logo_media: str | None = None) -> dict:
        """Store a brand kit: brand colours (hex strings) and an
        optional logo media id (which must be a real project media
        entry). Colours are stored as data; they do not invent a
        brand-pose engine — the UI reuses them as text/overlay
        colour suggestions."""
        brand = dict(self.data.get("brand") or {})
        if colours is not None:
            if not isinstance(colours, list):
                raise ValueError("Brand colours must be a list")
            for c in colours:
                if not isinstance(c, str) or not c.startswith("#"):
                    raise ValueError(
                        f"Brand colour must be a hex string: {c!r}")
            brand["colours"] = list(colours)
        if logo_media is not None:
            if logo_media == "":
                brand.pop("logo_media", None)
            else:
                self.media(logo_media)  # raises if unknown
                brand["logo_media"] = logo_media
        self.data["brand"] = brand
        self._bump()
        return brand

    def brand_get(self) -> dict:
        return copy.deepcopy(self.data.get("brand") or {})

    def rename_track(self, track_id: str, name: str) -> dict:
        """Rename a track (name only; id, kind and role unchanged)."""
        track = self.track(track_id)
        name = (name or "").strip()
        if not name:
            raise ValueError("Track name must not be empty")
        track["name"] = name
        self._bump()
        return track

    def remove_track(self, track_id: str) -> dict:
        """Remove a track, but only when it holds no items — removing
        a populated track would silently delete clips, so that is a
        hard error instead. The Main track (role 'main') is protected.
        """
        track = self.track(track_id)
        if track.get("role") == "main":
            raise ValueError("Cannot remove the Main track")
        if track["items"]:
            raise ValueError("Track still has clips; delete them first")
        self.data["tracks"] = [t for t in self.data["tracks"]
                               if t["id"] != track_id]
        self._bump()
        return {"deleted": track_id}

    # -- Phase 3: markers ---------------------------------------------
    def add_marker(self, text: str, at_frame: int) -> dict:
        """Add a timeline marker (stored in the project's markers[])."""
        if not str(text).strip():
            raise ValueError("Marker text must not be empty")
        marker = {"id": _new_id("mk"), "text": str(text),
                  "at": int(at_frame)}
        self.data.setdefault("markers", []).append(marker)
        self.data["markers"].sort(key=lambda m: m["at"])
        self._bump()
        return marker

    def remove_marker(self, marker_id: str) -> None:
        before = len(self.data.get("markers", []))
        self.data["markers"] = [m for m in self.data.get("markers", [])
                                if m["id"] != marker_id]
        if len(self.data["markers"]) == before:
            raise KeyError(f"Unknown marker: {marker_id}")
        self._bump()

    def move_marker(self, marker_id: str, at_frame: int) -> dict:
        """Move a marker to a new timeline frame (Phase 8)."""
        for marker in self.data.get("markers", []):
            if marker["id"] == marker_id:
                marker["at"] = int(at_frame)
                self._bump()
                return marker
        raise KeyError(f"Unknown marker: {marker_id}")

    def clip_at_time(self, frame: int) -> dict | None:
        """The main-track clip covering ``frame``, or None (Phase 8).

        Used by the review panel and the clip_at_time MCP tool; it
        reads the project document only and never renders anything.
        """
        for track in self.data["tracks"]:
            if track.get("role") != "main" or track["kind"] != "video":
                continue
            for item in sorted(track["items"], key=lambda i: i["at"]):
                if int(item["at"]) <= int(frame) < \
                        int(item["at"]) + int(item["dur"]):
                    return {"track": track["id"], "item": item}
        return None

    def import_srt(self, track_id: str, text: str) -> list[dict]:
        """Import SRT cues onto a text track. All cues are validated
        (including overlap) before any of them is added."""
        track = self.track(track_id)
        if track["kind"] != "text":
            raise ValueError("SRT cues belong on a text track")
        cues = parse_srt(text)
        items = []
        for start_s, end_s, body in cues:
            at = seconds_to_frames(start_s, self.fps)
            dur = seconds_to_frames(end_s, self.fps) - at
            if dur <= 0:
                raise ValueError(f"SRT cue too short to place: {body!r}")
            item = {"id": _new_id("s"), "at": at, "dur": dur, "text": body,
                    "textStyle": {"size": 0.062, "positionY": 0.8,
                                  "positionX": 0.5}}
            self._check_overlap(track, item)
            for other in items:
                o_start, o_end = other["at"], other["at"] + other["dur"]
                if at < o_end and o_start < at + dur:
                    raise ValueError(
                        f"SRT cue overlaps another imported cue: {body!r}")
            items.append(item)
        for item in items:
            track["items"].append(item)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return items

    def export_srt(self, track_id: str = "t1") -> str:
        track = self.track(track_id)
        lines = []
        for index, item in enumerate(
                sorted(track["items"], key=lambda i: i["at"]), start=1):
            start = frames_to_seconds(item["at"], self.fps)
            end = frames_to_seconds(item["at"] + item["dur"], self.fps)
            lines.append(str(index))
            lines.append(f"{srt_timestamp(start)} --> {srt_timestamp(end)}")
            lines.append(item.get("text", ""))
            lines.append("")
        return "\n".join(lines)

    # -- Phase 4: adjustment layers -----------------------------------
    def adjustment_track(self) -> dict:
        """Return the adjustment track, creating it if absent."""
        for track in self.data["tracks"]:
            if track.get("role") == "adjustment":
                return track
        track = {"id": _new_id("adj"), "kind": "video",
                 "role": "adjustment", "name": "Adjustment", "items": []}
        # Adjustment sits after the main track in track order.
        self.data["tracks"].insert(1, track)
        return track

    def add_adjustment(self, at: int, dur: int, preset: str | None = None,
                       lut: str | None = None,
                       strength: float | None = None,
                       preset_strength: float | None = None) -> dict:
        """Add an adjustment layer: a colour preset and/or .cube LUT
        applied to the main-track picture for [at, at+dur) only.

        Stored as an item on the adjustment track (no media). Range
        and overlap rules match other timeline items; a missing or
        invalid LUT is a hard error, never a silent skip.
        """
        if int(dur) <= 0:
            raise ValueError("Adjustment duration must be positive")
        color: dict = {}
        if lut is not None:
            validate_cube(lut)
            color["lut"] = lut
        if preset is not None:
            if preset not in COLOR_PRESETS:
                raise ValueError(f"Unknown colour preset: {preset!r}")
            color["preset"] = preset
        if strength is not None:
            strength = float(strength)
            if not 0.0 <= strength <= 1.0:
                raise ValueError("LUT strength must be 0..1")
            color["strength"] = strength
        if preset_strength is not None:
            preset_strength = float(preset_strength)
            if not 0.0 <= preset_strength <= 1.0:
                raise ValueError("Colour preset strength must be 0..1")
            color["preset_strength"] = preset_strength
        if not color:
            raise ValueError("Provide a LUT path and/or a colour preset")
        color.setdefault("strength", 1.0)
        if "preset" in color:
            color.setdefault("preset_strength", 1.0)
        track = self.adjustment_track()
        item = {"id": _new_id("adj"), "at": int(at), "dur": int(dur),
                "color": color}
        self._check_overlap(track, item)
        track["items"].append(item)
        track["items"].sort(key=lambda i: i["at"])
        self._bump()
        return item

    def remove_adjustment(self, item_id: str) -> None:
        track = self.adjustment_track()
        before = len(track["items"])
        track["items"] = [i for i in track["items"] if i["id"] != item_id]
        if len(track["items"]) == before:
            raise KeyError(f"Unknown adjustment layer: {item_id}")
        self._bump()

    def list_adjustments(self) -> list[dict]:
        return copy.deepcopy(self.adjustment_track()["items"])

    # -- Phase 4: karaoke captions ------------------------------------
    def add_karaoke(self, item_id: str, words: list[dict]) -> dict:
        """Attach per-word timings to a text item.

        ``words`` is a list of {text, start, end} with times in seconds
        relative to the item start. Words must be non-overlapping, in
        order, inside the item, and must join (with single spaces) to
        the item's own text — otherwise the highlight would drift
        from the words on screen, so that is a hard error. Phase 5:
        a word may carry an optional ``syllables`` list of
        {text, start, end} (same time base); syllables must join
        (concatenated) to the word text and lie inside the word's
        range, and the .ass builder then emits one ``\\k`` tag per
        syllable instead of per word.
        """
        _, item = self.item(item_id)
        if "text" not in item:
            raise ValueError("Karaoke belongs on a text item")
        dur_s = frames_to_seconds(int(item["dur"]), self.fps)
        cleaned: list[dict] = []
        prev_end = 0.0
        for word in words:
            text = str(word.get("text", "")).strip()
            start, end = float(word["start"]), float(word["end"])
            if not text:
                raise ValueError("Karaoke word text must not be empty")
            if not (0.0 <= start < end <= dur_s + 1e-9):
                raise ValueError(
                    f"Karaoke word {text!r} falls outside the cue")
            if start < prev_end - 1e-9:
                raise ValueError("Karaoke words must be in order "
                                 "and non-overlapping")
            entry: dict = {"text": text, "start": start, "end": end}
            # Phase 5: optional per-syllable timings. Syllables must
            # join (concatenated, no separator) to the word text,
            # lie inside the word's time range, and be in order
            # without overlapping — otherwise the highlight would
            # drift, so that is a hard error like the word rules.
            syllables = word.get("syllables")
            if syllables is not None:
                if not isinstance(syllables, list) or not syllables:
                    raise ValueError(
                        f"Karaoke syllables for {text!r} must be a "
                        f"non-empty list")
                cleaned_syl: list[dict] = []
                prev_syl_end = start
                for syl in syllables:
                    syl_text = str(syl.get("text", ""))
                    syl_start, syl_end = float(syl["start"]), float(syl["end"])
                    if not syl_text:
                        raise ValueError(
                            "Karaoke syllable text must not be empty")
                    if not (start - 1e-9 <= syl_start < syl_end
                            <= end + 1e-9):
                        raise ValueError(
                            f"Karaoke syllable {syl_text!r} falls "
                            f"outside word {text!r}")
                    if syl_start < prev_syl_end - 1e-9:
                        raise ValueError(
                            "Karaoke syllables must be in order and "
                            "non-overlapping")
                    cleaned_syl.append({"text": syl_text,
                                        "start": syl_start,
                                        "end": syl_end})
                    prev_syl_end = syl_end
                if "".join(s["text"] for s in cleaned_syl) != text:
                    raise ValueError(
                        f"Karaoke syllables {''.join(s['text'] for s in cleaned_syl)!r} "
                        f"do not join to word {text!r}")
                entry["syllables"] = cleaned_syl
            cleaned.append(entry)
            prev_end = end
        if not cleaned:
            raise ValueError("Karaoke needs at least one word")
        joined = " ".join(w["text"] for w in cleaned)
        if " ".join(str(item["text"]).split()) != joined:
            raise ValueError(
                f"Karaoke words {joined!r} do not match cue text "
                f"{item['text']!r}")
        item["karaoke"] = {"words": cleaned}
        self._bump()
        return item

    def karaoke_get(self, item_id: str) -> dict:
        _, item = self.item(item_id)
        if "karaoke" not in item:
            raise KeyError(f"Item has no karaoke timings: {item_id}")
        return copy.deepcopy(item["karaoke"])

    # -- Phase 4: ducking ---------------------------------------------
    def set_ducking(self, enabled: bool, amount_db: float = 6.0,
                    threshold: float = 0.02, ratio: float | None = None,
                    attack: float = 20.0, release: float = 250.0) -> dict:
        """Configure music ducking: while main-track audio is present,
        music items are sidechain-compressed. ``amount_db`` sets the
        compressor ratio as 10 ** (amount_db / 20) unless ``ratio``
        is given explicitly; threshold is linear (0..1).
        """
        if not 0.0 < float(amount_db) <= 24.0:
            raise ValueError("Duck amount must be 0..24 dB")
        if not 0.0 < float(threshold) <= 1.0:
            raise ValueError("Duck threshold must be 0..1 (linear)")
        if ratio is None:
            ratio = 10.0 ** (float(amount_db) / 20.0)
        if not 1.0 <= float(ratio) <= 20.0:
            raise ValueError("Duck ratio must be 1..20")
        config = {"enabled": bool(enabled), "amountDb": float(amount_db),
                  "threshold": float(threshold), "ratio": float(ratio),
                  "attack": float(attack), "release": float(release)}
        self.data.setdefault("audio", {})["ducking"] = config
        self._bump()
        return config

    def ducking_get(self) -> dict:
        return copy.deepcopy(
            (self.data.get("audio") or {}).get("ducking") or
            {"enabled": False})

    # -- Phase 4: beat grid -------------------------------------------
    def detect_beats(self, media_id: str, min_gap_s: float = 0.3) -> dict:
        """Detect beats from a media file's audio (energy-onset method,
        see vibeedit_core/beats.py) and store them in beatGrid. The
        media path is resolved relative to the project folder.
        """
        from .beats import detect_beats as _detect
        medium = self.media(media_id)
        path = medium["path"]
        if not os.path.isabs(path):
            path = os.path.join(self.folder, path)
        beats = _detect(path, min_gap_s=min_gap_s)
        self.data["beatGrid"] = {"source": media_id, "beats": beats,
                                 "method": "energy-onset"}
        self._bump()
        return self.data["beatGrid"]

    def beat_list(self) -> list[float]:
        return list((self.data.get("beatGrid") or {}).get("beats") or [])

    def nearest_beat(self, time_s: float) -> float | None:
        beats = self.beat_list()
        if not beats:
            return None
        return min(beats, key=lambda b: abs(b - float(time_s)))

    def snap_frame(self, frame: int) -> int:
        """Snap a timeline frame to the nearest beat (frames)."""
        beat = self.nearest_beat(frames_to_seconds(int(frame), self.fps))
        if beat is None:
            raise ValueError("No beat grid detected yet")
        return seconds_to_frames(beat, self.fps)

    def beats_to_markers(self) -> list[dict]:
        """Copy the stored beat grid into timeline markers."""
        beats = self.beat_list()
        if not beats:
            raise ValueError("No beat grid detected yet")
        added = []
        for beat in beats:
            added.append(self.add_marker(
                "beat", seconds_to_frames(beat, self.fps)))
        return added

    # -- Phase 4: project stats ---------------------------------------
    def project_stats(self) -> dict:
        items = [i for t in self.data["tracks"] for i in t["items"]]
        return {
            "name": self.data.get("name"), "rev": self.rev,
            "duration_seconds": round(self.duration_seconds(), 3),
            "tracks": len(self.data["tracks"]),
            "items": len(items),
            "clips": sum(1 for i in items if "media" in i),
            "text_items": sum(1 for i in items if "text" in i),
            "karaoke_items": sum(1 for i in items if "karaoke" in i),
            "adjustment_layers": len(self.list_adjustments()),
            "transitions": len(self.data.get("transitions", [])),
            "markers": len(self.data.get("markers", [])),
            "beats": len(self.beat_list()),
            "ducking": self.ducking_get(),
        }

    # -- Phase 5: validation ----------------------------------------
    def validate(self) -> dict:
        """Check the project document and report problems without
        raising for content errors (unknown ids, overlaps, dangling
        transitions are returned as ``errors``, not exceptions, so
        an agent can read them and fix the project)."""
        errors: list[str] = []
        warnings: list[str] = []
        data = self.data
        if data.get("schema") not in (SCHEMA, LEGACY_SCHEMA):
            errors.append(f"Unsupported schema: {data.get('schema')!r}")
        # Round 19: a video clip whose media has no fps cannot have
        # its timeline duration verified against the source frame
        # rate, so it is reported (not silently trusted).
        media_by_id = {m["id"]: m for m in data.get("media", [])}
        for track in data["tracks"]:
            for item in track["items"]:
                medium = media_by_id.get(item.get("media"))
                if medium is not None and medium.get("kind") == "video" \
                        and not medium.get("fps"):
                    warnings.append(
                        f"Item {item['id']} references video media "
                        f"{medium['id']} with unknown fps: its "
                        f"timeline duration cannot be verified "
                        f"against the source frame rate")
        mains = [t for t in data["tracks"]
                 if t.get("role") == "main" and t["kind"] == "video"]
        if not mains:
            errors.append("Project has no main video track")
        media_ids = {m["id"] for m in data["media"]}
        items_by_id: dict[str, dict] = {}
        for track in data["tracks"]:
            seen: list[dict] = []
            for item in track["items"]:
                items_by_id[item["id"]] = item
                if "media" in item and item["media"] not in media_ids:
                    errors.append(
                        f"Item {item['id']} references unknown media "
                        f"{item['media']!r}")
                if int(item.get("dur", 0)) <= 0:
                    errors.append(f"Item {item['id']} has no duration")
                for other in seen:
                    o_start = int(other["at"])
                    o_end = o_start + int(other["dur"])
                    start, end = int(item["at"]), int(item["at"]) + int(item["dur"])
                    if start < o_end and o_start < end:
                        errors.append(
                            f"Item {item['id']} overlaps {other['id']} "
                            f"on track {track['id']}")
                seen.append(item)
        # Phase B2: link integrity (reported, not raised, like the
        # other validation errors): every linked id must exist and
        # the link must be reciprocal.
        for track in data["tracks"]:
            for item in track["items"]:
                linked = item.get("linked_audio")
                if linked is not None:
                    ids = [linked] if isinstance(linked, str) \
                        else list(linked)
                    for audio_id in ids:
                        partner = items_by_id.get(audio_id)
                        if partner is None:
                            errors.append(
                                f"Item {item['id']} links to unknown "
                                f"audio {audio_id!r}")
                        elif partner.get("linked_video") != item["id"]:
                            errors.append(
                                f"Item {item['id']} has a one-way "
                                f"link to {audio_id}")
                video_id = item.get("linked_video")
                if video_id is not None:
                    partner = items_by_id.get(video_id)
                    if partner is None:
                        errors.append(
                            f"Item {item['id']} links to unknown "
                            f"video {video_id!r}")
                    else:
                        partner_links = partner.get("linked_audio")
                        partner_ids = [partner_links] \
                            if isinstance(partner_links, str) \
                            else list(partner_links or [])
                        if item["id"] not in partner_ids:
                            errors.append(
                                f"Item {item['id']} has a one-way "
                                f"link to {video_id}")
        for trans in data.get("transitions", []):
            if trans.get("kind") in UNRENDERABLE_TRANSITION_KINDS:
                errors.append(
                    f"Transition {trans.get('id')} kind "
                    f"{trans.get('kind')!r} cannot be rendered")
            elif trans.get("kind") not in TRANSITION_XFADE and \
                    trans.get("kind") not in MOTION_TRANSITION_KINDS and \
                    trans.get("kind") not in HALFTONE_TRANSITION_KINDS:
                errors.append(
                    f"Transition {trans.get('id')} has unknown kind "
                    f"{trans.get('kind')!r}")
            for key in ("from", "to"):
                if trans.get(key) not in items_by_id:
                    errors.append(
                        f"Transition {trans.get('id')} references "
                        f"unknown clip {trans.get(key)!r}")
        return {"ok": not errors, "errors": errors, "warnings": warnings}

    # -- readouts -----------------------------------------------------
    def timeline_text(self) -> str:
        # Full readout, unchanged: the MCP timeline_sheet tool and
        # /api/project return this verbatim, and agents need the
        # per-clip lines. The UI status bar condenses it for display
        # in app.js (load()), it does not change this function.
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
