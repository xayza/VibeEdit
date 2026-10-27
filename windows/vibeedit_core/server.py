"""CapCut-style web UI server for the VibeEdit Windows MVP.

Layout (mirroring the CapCut desktop layout the user already knows
from ADIT): preview on top, editor/inspector panel below it, and a
multi-track timeline strip at the bottom. Preview plays the latest
export only — it is not a live GPU timeline render (Phase 1 limit,
documented in windows/README.md).

Stdlib only (http.server). Endpoints:
  GET  /api/project            project JSON + timeline text
  GET  /api/mcp-tools          live MCP tool registry (agent dock)
  POST /api/project            {"op": ...} edit operation (see project.py)
  POST /api/undo  /api/redo     snapshot history (server session)
  POST /api/export             {"preset": "draft"|"full", "normalize": bool}
  POST /api/batch              {"folders": [...], "preset": ..., "normalize": bool}
  POST /api/otio               {} -> writes render/timeline.otio, returns it
  GET  /api/preview             latest export file, if any
  POST /api/media/upload       multipart file -> project media/
  GET  /api/media/<id>         source media file, Range support (seek)
  GET  /api/info               environment info (Python, FFmpeg tools)
  GET  /  /static/*            the web UI
"""

from __future__ import annotations

import copy
import json
import mimetypes
import os
import shutil
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .project import (Project, load_project, save_project, new_project,
                      find_project_file, PROJECT_FILENAME,
                      write_backup, unique_media_name)
from .render import render, probe_media


def _source_base() -> str:
    """windows/ folder in a source checkout (parent of vibeedit_core)."""
    return os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), ".."))


def _static_dir() -> str:
    """Resolve static/ for both layouts. In a PyInstaller frozen
    app the web UI files are bundled data: they live under
    sys._MEIPASS (one-folder builds) or next to the executable, NOT
    next to the archived server module — the old file-relative
    path silently 404'd every UI file in the frozen app. In a
    source checkout the file-relative folder is used."""
    if getattr(sys, "frozen", False):
        for base in (getattr(sys, "_MEIPASS", None),
                     os.path.dirname(os.path.abspath(sys.executable))):
            if base:
                candidate = os.path.join(base, "static")
                if os.path.isdir(candidate):
                    return candidate
        return os.path.join(getattr(sys, "_MEIPASS",
                                    os.path.dirname(
                                        os.path.abspath(sys.executable))),
                            "static")
    return os.path.join(_source_base(), "static")


def _default_project_dir() -> str:
    """Default project folder. Frozen apps must NOT store projects
    under _MEIPASS (bundled data, wiped on update and often
    read-only): they go next to the executable instead. Source
    checkouts keep windows/projects/default."""
    if getattr(sys, "frozen", False):
        return os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)),
            "projects", "default")
    return os.path.join(_source_base(), "projects", "default")


STATIC_DIR = _static_dir()
DEFAULT_PROJECT_DIR = _default_project_dir()


class State:
    def __init__(self, project_dir: str | None):
        self.lock = threading.Lock()
        self.project_dir = project_dir or DEFAULT_PROJECT_DIR
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.last_export: str | None = None
        self.last_report: dict | None = None
        self.project, self.path = self._load_or_create()
        # Phase 0 backup rule: the first save after a project is
        # opened creates one backup of the saved file as loaded.
        self._needs_first_backup = True

    def _load_or_create(self) -> tuple[Project, str]:
        os.makedirs(os.path.join(self.project_dir, "media"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "render"), exist_ok=True)
        found = find_project_file(self.project_dir)
        if found:
            data = load_project(found)
            return Project(data, self.project_dir), found
        data = new_project("Untitled")
        path = os.path.join(self.project_dir, PROJECT_FILENAME)
        save_project(data, path)
        return Project(data, self.project_dir), path

    def backup_before_change(self) -> None:
        """Back up the saved project file before a data-affecting
        operation overwrites it. Best-effort: a backup failure must
        never block the edit itself (the in-session undo stack still
        protects the change). Also clears the first-save flag so a
        destructive first operation does not create two backups."""
        try:
            write_backup(self.path)
        except Exception:
            pass
        self._needs_first_backup = False

    def save(self) -> None:
        # Autosave itself creates no backup; only the first save
        # after opening a project does (see backup_before_change).
        if self._needs_first_backup:
            self.backup_before_change()
        save_project(self.project.data, self.path)

    def projects_root(self) -> str:
        """Parent folder holding all project folders (windows/projects)."""
        return os.path.dirname(os.path.abspath(self.project_dir))

    def list_projects(self) -> list[dict]:
        """Project folders under projects_root that contain a project
        file. Only immediate subdirectories are listed; no invented
        entries, and folders without a project file are skipped."""
        root = self.projects_root()
        out = []
        if os.path.isdir(root):
            for name in sorted(os.listdir(root)):
                folder = os.path.join(root, name)
                if not os.path.isdir(folder):
                    continue
                found = find_project_file(folder)
                if not found:
                    continue
                try:
                    data = load_project(found)
                    pname = data.get("name") or name
                except Exception:
                    pname = name
                out.append({"name": pname, "folder": name,
                            "path": folder,
                            "current": os.path.abspath(folder)
                            == os.path.abspath(self.project_dir)})
        return out

    def _recent_path(self) -> str:
        return os.path.join(self.projects_root(), ".recent.json")

    def recent_projects(self) -> list[dict]:
        """Recent projects: folder names recorded on open/create in
        projects/.recent.json, filtered to folders that still contain
        a project file. No invented entries; an unreadable file is
        an empty list, not an error."""
        try:
            import json as _json
            with open(self._recent_path(), encoding="utf-8") as fh:
                names = _json.load(fh)
        except Exception:
            return []
        out = []
        for name in names if isinstance(names, list) else []:
            folder = os.path.join(self.projects_root(), name)
            if os.path.isdir(folder) and find_project_file(folder):
                out.append({"folder": name, "path": folder})
        return out

    def record_recent(self, folder: str) -> None:
        """Move ``folder`` (a name under projects_root) to the front
        of the recent list, capped at 20. Failures are ignored: a
        recent list must never block opening a project."""
        try:
            import json as _json
            root = self.projects_root()
            name = os.path.relpath(os.path.abspath(folder), root)
            if name.startswith(".."):
                return
            names = [n for n in self.recent_projects()
                     if isinstance(n, dict)]
            ordered = [name] + [n["folder"] for n in names
                                if n["folder"] != name]
            with open(self._recent_path(), "w",
                      encoding="utf-8") as fh:
                _json.dump(ordered[:20], fh)
        except Exception:
            pass

    def remove_recent(self, folder: str) -> dict:
        """Remove a recent entry only — never deletes project files."""
        import json as _json
        try:
            with open(self._recent_path(), encoding="utf-8") as fh:
                names = _json.load(fh)
        except Exception:
            names = []
        names = [n for n in (names if isinstance(names, list) else [])
                 if n != folder]
        with open(self._recent_path(), "w", encoding="utf-8") as fh:
            _json.dump(names[:20], fh)
        return {"removed": folder, "recent": self.recent_projects()}

    def open_project(self, folder: str) -> dict:
        """Restart-free project switch (code-gap batch): resolve
        ``folder`` (a project folder name, a folder path, or a project
        file path) strictly inside projects_root, load it, and point
        this server state at it (project, path, project_dir, cleared
        undo/redo and last export). Raises on traversal or a missing
        project file instead of silently staying on the old project.
        """
        root = self.projects_root()
        if os.path.isabs(folder):
            candidate = os.path.abspath(folder)
        else:
            candidate = os.path.abspath(os.path.join(root, folder))
        if os.path.isfile(candidate):
            candidate = os.path.dirname(candidate)
        if os.path.commonpath([candidate, root]) != root:
            raise ValueError("Project folder must be inside projects/")
        found = find_project_file(candidate)
        if not found:
            raise FileNotFoundError(f"No project file in folder: {folder}")
        os.makedirs(os.path.join(candidate, "media"), exist_ok=True)
        os.makedirs(os.path.join(candidate, "render"), exist_ok=True)
        data = load_project(found)
        self.project = Project(data, candidate)
        self.path = found
        self.project_dir = candidate
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.last_export = None
        self.last_report = None
        self._needs_first_backup = True
        self.record_recent(candidate)
        return {"name": data.get("name"), "folder": candidate,
                "rev": data.get("rev")}

    # Ops whose saved result cannot be recovered by re-adding media:
    # they delete items/tracks or rewrite positions/format. A backup
    # of the saved file is taken BEFORE the mutation (the undo stack
    # only protects the current session; the backup survives a crash
    # or a later save). Non-destructive ops rely on the first-save
    # backup plus undo.
    DESTRUCTIVE_OPS = frozenset({
        "delete", "remove_transition", "adjustment_remove",
        "remove_marker", "source_overwrite", "set_format",
        "set_project", "close_gaps"})

    def apply(self, op: dict) -> dict:
        proj = self.project
        if op.get("op") == "srt_export":
            return {"srt": proj.export_srt(op.get("track", "t1"))}
        if op.get("op") in self.DESTRUCTIVE_OPS:
            self.backup_before_change()
        self.undo_stack.append(proj.snapshot())
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        kind = op.get("op")
        try:
            if kind == "add_clip":
                result = proj.add_clip(op["media"], op["track"], int(op["at"]),
                                       int(op.get("in", 0)),
                                       int(op["dur"]) if op.get("dur") is not None else None,
                                       float(op.get("speed", 1.0)))
            elif kind == "add_media":
                result = proj.add_media(op["path"], op.get("kind", "video"))
            elif kind == "add_text":
                result = proj.add_text(op["track"], op["text"], int(op["at"]),
                                       int(op["dur"]))
            elif kind == "trim":
                result = proj.trim(op["item"], op["edge"], int(op["toFrame"]))
            elif kind == "split":
                result = proj.split(op["item"], int(op["atFrame"]))
            elif kind == "split_at_playhead":
                _, item = proj.item(op.get("item") or
                                    _clip_covering(proj, int(op["atFrame"]))[1]["id"])
                result = proj.split(item["id"], int(op["atFrame"]))
            elif kind == "move":
                result = proj.move(op["item"], op["track"], int(op["at"]))
            elif kind == "delete":
                proj.delete(op["item"])
                result = {"deleted": op["item"]}
            elif kind == "set_speed":
                result = proj.set_speed(op["item"], float(op["speed"]))
            elif kind == "set_fade":
                result = proj.set_fade(op["item"], op.get("fadeIn"),
                                       op.get("fadeOut"))
            elif kind == "set_text":
                result = proj.set_text(op["item"], op["text"])
            elif kind == "set_volume":
                result = proj.set_volume(op["item"], float(op["volume"]))
            elif kind == "add_transition":
                result = proj.add_transition(op["from"], op["to"],
                                             op["kind"], float(op["duration"]))
            elif kind == "remove_transition":
                proj.remove_transition(op["transition"])
                result = {"deleted": op["transition"]}
            elif kind == "set_keyframes":
                result = proj.set_keyframes(op["item"], op["keyframes"])
            elif kind == "add_keyframe":
                result = proj.add_keyframe(op["item"], float(op["at"]),
                                           op["property"], float(op["value"]))
            elif kind == "set_color":
                result = proj.set_color(op["item"], op.get("lut"),
                                        op.get("preset"),
                                        op.get("strength"),
                                        op.get("preset_strength"),
                                        eq=op.get("eq"),
                                        clear_eq=bool(op.get("clear_eq")),
                                        clear_lut=bool(op.get("clear_lut")))
            elif kind == "close_gaps":
                result = proj.close_gaps(op.get("track"))
            elif kind == "source_overwrite":
                result = proj.overwrite_insert(
                    op["media"], int(op.get("in", 0)), int(op["out"]),
                    int(op.get("at", 0)), op.get("track"))
            elif kind == "source_insert":
                # Source viewer In/Out insert (original E/Q workflow,
                # as buttons): mark a range on a source media file and
                # insert it as a clip at the playhead (or given frame).
                in_frame = int(op.get("in", 0))
                out_frame = int(op.get("out"))
                if out_frame <= in_frame:
                    raise ValueError(
                        "Source Out must be after Source In")
                medium = proj.media(op["media"])
                track_id = op.get("track")
                if not track_id:
                    want_kind = medium.get("kind") or "video"
                    if want_kind == "video":
                        track_id = next(
                            (t["id"] for t in proj.data["tracks"]
                             if t["kind"] == "video"
                             and t.get("role") == "main"),
                            None)
                    if not track_id:
                        track_id = next(
                            (t["id"] for t in proj.data["tracks"]
                             if t["kind"] == want_kind),
                            proj.data["tracks"][0]["id"])
                result = proj.add_clip(op["media"], track_id,
                                       int(op.get("at", 0)), in_frame,
                                       out_frame - in_frame,
                                       float(op.get("speed", 1.0)))
            elif kind == "add_marker":
                result = proj.add_marker(op["text"], int(op["at"]))
            elif kind == "remove_marker":
                proj.remove_marker(op["marker"])
                result = {"deleted": op["marker"]}
            elif kind == "srt_import":
                result = proj.import_srt(op.get("track", "t1"), op["srt"])
            elif kind == "karaoke_add":
                result = proj.add_karaoke(op["item"], op["words"])
            elif kind == "adjustment_add":
                result = proj.add_adjustment(int(op["at"]), int(op["dur"]),
                                             op.get("preset"), op.get("lut"),
                                             op.get("strength"),
                                             op.get("preset_strength"))
            elif kind == "adjustment_remove":
                proj.remove_adjustment(op["item"])
                result = {"deleted": op["item"]}
            elif kind == "beat_detect":
                result = proj.detect_beats(op["media"],
                                           min_gap_s=float(op.get("min_gap", 0.3)))
            elif kind == "beats_to_markers":
                result = proj.beats_to_markers()
            elif kind == "ducking_set":
                result = proj.set_ducking(
                    bool(op.get("enabled", True)),
                    amount_db=float(op.get("amount_db", 6.0)),
                    threshold=float(op.get("threshold", 0.02)),
                    ratio=op.get("ratio"))
            elif kind == "project_stats":
                result = proj.project_stats()
            elif kind == "transcribe":
                from .transcribe import transcribe_media
                medium = proj.media(op["media"])
                mpath = medium["path"]
                if not os.path.isabs(mpath):
                    mpath = os.path.join(proj.folder, mpath)
                result = transcribe_media(
                    proj, mpath, op.get("track", "t1"),
                    model=op.get("model", "tiny"))
                result = {"added": [it["id"] for it in result]}
            elif kind == "add_track":
                result = proj.add_track(op.get("kind", "video"),
                                        op.get("role", ""),
                                        op.get("name", ""))
            elif kind == "set_format":
                result = proj.set_format(op.get("width"), op.get("height"))
            elif kind == "set_project":
                proj.data["name"] = op.get("name", proj.data["name"])
                fmt = proj.data["format"]
                if op.get("width"):
                    fmt["width"] = int(op["width"])
                if op.get("height"):
                    fmt["height"] = int(op["height"])
                result = {"name": proj.data["name"]}
            elif kind == "speed_curve":
                result = proj.apply_speed_curve(op["item"], op["preset"])
            elif kind == "clip_reverse":
                result = proj.set_reverse(op["item"],
                                          bool(op.get("reverse", True)))
            elif kind == "freeze_clip":
                result = proj.freeze_clip(op["item"],
                                          int(op.get("frames", 30)))
            elif kind == "review_run":
                result = proj.run_review()
            elif kind == "review_accept":
                result = proj.accept_review()
            elif kind == "review_verify":
                result = proj.verify_review()
            elif kind == "library_add":
                result = proj.library_add(op["item"],
                                          op.get("name", ""))
            elif kind == "library_list":
                result = {"items": proj.library_list()}
            elif kind == "library_remove":
                result = proj.library_remove(op["entry"])
            elif kind == "library_place":
                result = proj.library_place(
                    op["entry"], op.get("track"),
                    int(op["at"]) if op.get("at") is not None else None)
            elif kind == "brand_set":
                result = proj.brand_set(op.get("colours"),
                                        op.get("logo_media"))
            elif kind == "brand_get":
                result = proj.brand_get()
            elif kind == "plugin_enable":
                from .plugins import set_plugin_enabled
                result = set_plugin_enabled(op["plugin"], True)
            elif kind == "plugin_disable":
                from .plugins import set_plugin_enabled
                result = set_plugin_enabled(op["plugin"], False)
            elif kind == "plugin_reload":
                from .plugins import list_plugins
                result = {"plugins": list_plugins()}
            else:
                raise ValueError(f"Unknown operation: {kind}")
        except Exception:
            proj.restore(self.undo_stack.pop())
            raise
        self.save()
        return result


def _clip_covering(proj: Project, frame: int) -> tuple[dict, dict]:
    for track in proj.data["tracks"]:
        if track["kind"] != "video":
            continue
        for item in track["items"]:
            if item["at"] <= frame < item["at"] + item["dur"]:
                return track, item
    raise ValueError("No clip covers the playhead frame")


def _parse_multipart(body: bytes, boundary: bytes) -> dict[str, tuple[str, bytes]]:
    """Minimal multipart/form-data parser (stdlib only).

    Phase 0 fix: parameters are parsed ONLY from the
    Content-Disposition line, one header line at a time. The old code
    split the whole header block on ';', so a part with a Content-Type
    header (which every real browser sends) produced a filename like
    'clip.mp4"\\r\\nContent-Type: video/mp4', which os.path.basename
    then collapsed to just 'mp4' — every mp4 upload landed as a file
    literally named 'mp4', 'mp4-2', ... instead of its real name.
    """
    parts: dict[str, tuple[str, bytes]] = {}
    for chunk in body.split(b"--" + boundary):
        if b"Content-Disposition" not in chunk:
            continue
        head, _, payload = chunk.partition(b"\r\n\r\n")
        payload = payload.rsplit(b"\r\n", 1)[0]
        name = None
        filename = None
        for line in head.decode(errors="replace").split("\r\n"):
            line = line.strip()
            if not line.lower().startswith("content-disposition:"):
                continue
            params = line.split(";", 1)[1] if ";" in line else ""
            for piece in params.split(";"):
                piece = piece.strip()
                if piece.startswith("name="):
                    name = piece[5:].strip('"')
                elif piece.startswith("filename="):
                    filename = piece[9:].strip('"')
        if name:
            parts[name] = (filename or "", payload)
    return parts


def make_handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep the console readable
            pass

        def _send_json(self, obj, status=200):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def _project_view(self) -> dict:
            proj = state.project
            return {"project": proj.data,
                    "timeline": proj.timeline_text(),
                    "duration_seconds": proj.duration_seconds(),
                    "can_undo": bool(state.undo_stack),
                    "can_redo": bool(state.redo_stack),
                    "last_export": state.last_export}

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/api/info":
                # Real environment info only: a tool that cannot be
                # found is reported as "not found", never invented.
                import subprocess
                info = {"python": sys.version.split()[0],
                        "project_dir": state.project_dir,
                        "ffmpeg": "not found", "ffprobe": "not found"}
                from .render import find_tool
                for tool in ("ffmpeg", "ffprobe"):
                    try:
                        path = find_tool(tool)
                        out = subprocess.run(
                            [path, "-version"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace",
                            timeout=5)
                        first = (out.stdout or "").splitlines()
                        info[tool] = first[0].strip() if first else path
                    except Exception:  # noqa: BLE001 - "not found" is data
                        info[tool] = "not found"
                self._send_json(info)
            elif parsed.path.startswith("/api/thumbnail/"):
                self._serve_thumbnail(parsed.path[len("/api/thumbnail/"):])
            elif parsed.path.startswith("/api/media/"):
                self._serve_media(parsed.path[len("/api/media/"):])
            elif parsed.path == "/api/project":
                with state.lock:
                    self._send_json(self._project_view())
            elif parsed.path == "/api/projects":
                with state.lock:
                    self._send_json({"projects": state.list_projects(),
                                     "recent": state.recent_projects(),
                                     "current": state.project_dir})
            elif parsed.path == "/api/recent":
                with state.lock:
                    self._send_json({"recent": state.recent_projects()})
            elif parsed.path == "/api/plugins":
                from .plugins import list_plugins
                with state.lock:
                    self._send_json({"plugins": list_plugins()})
            elif parsed.path == "/api/mcp-tools":
                # Phase 5 agent dock: the live tool registry from
                # mcp.py (names + descriptions), not a hardcoded list.
                from .mcp import TOOLS
                self._send_json({"tools": TOOLS, "count": len(TOOLS)})
            elif parsed.path == "/api/preview":
                if state.last_export and os.path.isfile(state.last_export):
                    self._serve_file(state.last_export)
                else:
                    self._send_json({"error": "No export yet"}, 404)
            elif parsed.path == "/api/waveform":
                # Real waveform peaks for one media id (decoded with
                # FFmpeg, RMS per bucket, normalised). Never invented:
                # an undecodable file is a 400, not a drawn shape.
                from .waveform import waveform_peaks
                query = urllib.parse.parse_qs(parsed.query)
                media_id = (query.get("media") or [""])[0]
                buckets = int((query.get("buckets") or ["64"])[0])
                try:
                    with state.lock:
                        medium = state.project.media(media_id)
                        path = medium["path"]
                        if not os.path.isabs(path):
                            path = os.path.join(state.project_dir, path)
                        peaks = waveform_peaks(path, buckets)
                except (KeyError, FileNotFoundError, ValueError,
                        RuntimeError) as exc:
                    self._send_json({"error": str(exc)}, 400)
                    return
                self._send_json({"media": media_id, "buckets": buckets,
                                 "peaks": peaks})
            elif parsed.path == "/api/review":
                # Phase 8 review panel: validation + stats from the
                # live project document, plus the last export report
                # (its skipped/warnings lists are real render data,
                # never invented). No export is run by this endpoint.
                with state.lock:
                    report = state.last_report or {}
                    self._send_json({
                        "validation": state.project.validate(),
                        "stats": state.project.project_stats(),
                        "last_export": state.last_export,
                        "last_export_report": report,
                        "skipped": report.get("skipped", []),
                        "warnings": report.get("warnings", []),
                    })
            elif parsed.path == "/api/transition-preview":
                # GET serves a previously generated preview PNG;
                # POST generates one (see do_POST).
                query = urllib.parse.parse_qs(parsed.query)
                trans_id = (query.get("transition") or [""])[0]
                import re
                safe = re.sub(r"[^A-Za-z0-9_-]+", "_", trans_id)
                path = os.path.join(state.project_dir, "render",
                                    "previews",
                                    f"transition-{safe}.png")
                if trans_id and os.path.isfile(path):
                    self._serve_file(path)
                else:
                    self._send_json(
                        {"error": "No preview yet for this transition; "
                         "generate it first"}, 404)
            elif parsed.path == "/":
                self._serve_file(os.path.join(STATIC_DIR, "index.html"))
            elif parsed.path.startswith("/static/"):
                name = os.path.basename(parsed.path)
                path = os.path.join(STATIC_DIR, name)
                if os.path.isfile(path):
                    self._serve_file(path)
                else:
                    self._send_json({"error": "Not found"}, 404)
            else:
                self._send_json({"error": "Not found"}, 404)

        def _media_file(self, media_id):
            """Return (medium, real_path) for a project media id, or
            None when unknown / outside <project>/media (traversal)."""
            if not media_id or "/" in media_id or "\\" in media_id:
                return None
            with state.lock:
                try:
                    medium = state.project.media(media_id)
                except KeyError:
                    return None
                path = medium["path"]
                if not os.path.isabs(path):
                    path = os.path.join(state.project_dir, path)
            media_dir = os.path.realpath(
                os.path.join(state.project_dir, "media"))
            real = os.path.realpath(path)
            if os.path.commonpath([real, media_dir]) != media_dir:
                return None
            if not os.path.isfile(real):
                return None
            return medium, real

        def _serve_thumbnail(self, raw_id: str):
            """GET /api/thumbnail/<id>: first-frame PNG for video, the
            original file for still images, 404 for unknown ids,
            traversal, audio (no thumbnail exists) and undecodable
            files — never a fake frame."""
            from .thumbnail import generate_thumbnail, thumbnail_path
            media_id = urllib.parse.unquote(raw_id)
            found = self._media_file(media_id)
            if not found:
                self._send_json({"error": "Unknown media"}, 404)
                return
            medium, real = found
            try:
                thumb = generate_thumbnail(
                    real, thumbnail_path(state.project_dir, media_id),
                    medium.get("kind", ""))
            except (ValueError, RuntimeError, FileNotFoundError):
                self._send_json({"error": "No thumbnail for this media"},
                                404)
                return
            self._serve_file(thumb)

        def _serve_file(self, path: str):
            mime, _ = mimetypes.guess_type(path)
            with open(path, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", mime or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_media(self, raw_id: str):
            """Serve one project source file, with HTTP Range support
            so <video> can seek. ONLY files listed in the project
            media list and inside <project>/media are served: an
            unknown id is 404, and a stored path that resolves
            outside the media folder is 404 (never a traversal)."""
            media_id = urllib.parse.unquote(raw_id)
            if not media_id or "/" in media_id or "\\" in media_id:
                self._send_json({"error": "Unknown media"}, 404)
                return
            with state.lock:
                try:
                    medium = state.project.media(media_id)
                except KeyError:
                    self._send_json({"error": "Unknown media"}, 404)
                    return
                path = medium["path"]
                if not os.path.isabs(path):
                    path = os.path.join(state.project_dir, path)
            media_dir = os.path.realpath(
                os.path.join(state.project_dir, "media"))
            real = os.path.realpath(path)
            if os.path.commonpath([real, media_dir]) != media_dir:
                self._send_json({"error": "Unknown media"}, 404)
                return
            if not os.path.isfile(real):
                self._send_json({"error": "Media file missing"}, 404)
                return
            size = os.path.getsize(real)
            mime, _ = mimetypes.guess_type(real)
            start, end = 0, size - 1
            status = 200
            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    spec = range_header[len("bytes="):].strip()
                    if "," in spec:
                        raise ValueError("multi-range not supported")
                    a, _, b = spec.partition("-")
                    start = int(a) if a else max(0, size - int(b))
                    end = int(b) if b else size - 1
                except ValueError:
                    self._send_json({"error": "Invalid Range"}, 400)
                    return
                if start < 0 or end >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = 206
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type",
                             mime or "application/octet-stream")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range",
                                 f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(real, "rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def do_POST(self):
            parsed = urllib.parse.urlparse(self.path)
            try:
                with state.lock:
                    if parsed.path == "/api/project":
                        op = self._read_json()
                        result = state.apply(op)
                        self._send_json({"ok": True, "result": result,
                                         **self._project_view()})
                    elif parsed.path == "/api/project/open":
                        body = self._read_json()
                        result = state.open_project(body["folder"])
                        self._send_json({"ok": True, "result": result,
                                         **self._project_view()})
                    elif parsed.path == "/api/project/create":
                        body = self._read_json()
                        name = (body.get("name") or "").strip()
                        if not name or "/" in name or "\\" in name \
                                or ".." in name:
                            raise ValueError(
                                "Project name must be a plain folder name")
                        root = state.projects_root()
                        folder = os.path.join(root, name)
                        if os.path.exists(folder):
                            raise ValueError(
                                f"Project folder already exists: {name}")
                        os.makedirs(os.path.join(folder, "media"),
                                    exist_ok=True)
                        os.makedirs(os.path.join(folder, "render"),
                                    exist_ok=True)
                        path = os.path.join(folder, PROJECT_FILENAME)
                        save_project(new_project(name), path)
                        result = state.open_project(folder)
                        self._send_json({"ok": True, "result": result,
                                         **self._project_view()})
                    elif parsed.path == "/api/recent/remove":
                        body = self._read_json()
                        result = state.remove_recent(body["folder"])
                        self._send_json({"ok": True, "result": result})
                    elif parsed.path == "/api/reveal":
                        body = self._read_json()
                        folder = body.get("folder", "")
                        root = state.projects_root()
                        candidate = os.path.abspath(
                            os.path.join(root, folder)) \
                            if not os.path.isabs(folder) \
                            else os.path.abspath(folder)
                        if os.path.commonpath([candidate, root]) != root \
                                or not os.path.isdir(candidate):
                            raise ValueError(
                                "Reveal target must be a project folder "
                                "inside projects/")
                        if sys.platform == "win32":
                            os.startfile(candidate)  # noqa: S606
                        elif shutil.which("xdg-open"):
                            import subprocess
                            subprocess.Popen(["xdg-open", candidate])
                        else:
                            raise RuntimeError(
                                "Reveal is only supported on Windows "
                                "(os.startfile); copy the project path "
                                "from the welcome panel instead")
                        self._send_json({"ok": True, "path": candidate})
                    elif parsed.path == "/api/undo":
                        self._read_json()
                        if not state.undo_stack:
                            raise ValueError("Nothing to undo")
                        state.redo_stack.append(state.project.snapshot())
                        state.project.restore(state.undo_stack.pop())
                        state.save()
                        self._send_json({"ok": True, **self._project_view()})
                    elif parsed.path == "/api/redo":
                        self._read_json()
                        if not state.redo_stack:
                            raise ValueError("Nothing to redo")
                        state.undo_stack.append(state.project.snapshot())
                        state.project.restore(state.redo_stack.pop())
                        state.save()
                        self._send_json({"ok": True, **self._project_view()})
                    elif parsed.path == "/api/save":
                        # Phase 2: explicit save for Ctrl+S. Every
                        # successful edit already autosaves, so this
                        # just re-writes the current in-memory state
                        # (and, per the Phase 0 rule, only the first
                        # save after opening creates a backup).
                        self._read_json()
                        state.save()
                        self._send_json({"ok": True, **self._project_view()})
                    elif parsed.path == "/api/export":
                        body = self._read_json()
                        preset = body.get("preset", "full")
                        export_preset = body.get("export_preset")
                        ext = "mp4"
                        if export_preset:
                            from .render import export_preset_info
                            fmt = state.project.data["format"]
                            ext = export_preset_info(
                                export_preset, int(fmt["width"]),
                                int(fmt["height"]))["ext"]
                        slug = (export_preset or preset).replace("/", "_")
                        out = os.path.join(state.project_dir, "render",
                                           f"export-{slug}.{ext}")
                        report = render(state.project.data,
                                        state.project_dir, out, preset=preset,
                                        normalize_audio=bool(body.get("normalize", False)),
                                        export_preset=export_preset)
                        state.last_export = out
                        state.last_report = report
                        self._send_json({"ok": True, "report": report})
                    elif parsed.path == "/api/batch":
                        from .export_ops import batch_export
                        body = self._read_json()
                        folders = [state.project_dir] + [
                            f for f in body.get("folders", [])
                            if f != state.project_dir]
                        results = batch_export(
                            folders,
                            preset=body.get("preset", "full"),
                            normalize_audio=bool(body.get("normalize", False)))
                        self._send_json({"ok": True, "results": results})
                    elif parsed.path == "/api/otio":
                        from .export_ops import export_otio
                        self._read_json()
                        out = os.path.join(state.project_dir, "render",
                                           "timeline.otio")
                        report = export_otio(state.project.data,
                                             state.project_dir, out)
                        with open(out, encoding="utf-8") as fh:
                            otio_text = fh.read()
                        self._send_json({"ok": True, "report": report,
                                         "otio": otio_text})
                    elif parsed.path == "/api/otio-import":
                        from .export_ops import import_otio
                        body = self._read_json()
                        report = import_otio(body["otio"], body["dest"],
                                             merge=bool(body.get("merge", False)))
                        self._send_json({"ok": True, "report": report})
                    elif parsed.path == "/api/karaoke-ass":
                        from .export_ops import export_karaoke_ass
                        self._read_json()
                        out = os.path.join(state.project_dir, "render",
                                           "karaoke.ass")
                        report = export_karaoke_ass(state.project.data, out)
                        with open(out, encoding="utf-8") as fh:
                            ass_text = fh.read()
                        self._send_json({"ok": True, "report": report,
                                         "ass": ass_text})
                    elif parsed.path == "/api/plugin":
                        from .plugins import apply_plugin, load_plugins
                        body = self._read_json()
                        state.undo_stack.append(state.project.snapshot())
                        if len(state.undo_stack) > 50:
                            state.undo_stack.pop(0)
                        state.redo_stack.clear()
                        try:
                            info = load_plugins().get(body["plugin"], {})
                            hook = next((k for k, v in info.items()
                                         if callable(v)), None)
                            if not hook:
                                raise ValueError(
                                    f"Plugin {body['plugin']!r} has no hook")
                            item = apply_plugin(state.project,
                                                body["plugin"], hook,
                                                body["item"])
                            state.save()
                        except Exception:
                            state.project.restore(state.undo_stack.pop())
                            raise
                        self._send_json({"ok": True, "item": item})
                    elif parsed.path == "/api/stats":
                        self._read_json()
                        self._send_json({"ok": True,
                                         "stats": state.project.project_stats()})
                    elif parsed.path == "/api/transition-preview":
                        from .export_ops import transition_preview
                        body = self._read_json()
                        result = transition_preview(
                            state.project.data, state.project_dir,
                            body["transition"])
                        self._send_json({"ok": True, "preview": result})
                    elif parsed.path == "/api/media/upload":
                        length = int(self.headers.get("Content-Length") or 0)
                        body = self.rfile.read(length)
                        ctype = self.headers.get("Content-Type", "")
                        boundary = ctype.split("boundary=")[-1].encode()
                        parts = _parse_multipart(body, boundary)
                        filename, payload = parts["file"]
                        # Phase 0: never overwrite an existing media
                        # file. A second upload of the same name is
                        # stored as name-2.ext, so clips pointing at
                        # the first file keep their content.
                        media_dir = os.path.join(state.project_dir,
                                                 "media")
                        os.makedirs(media_dir, exist_ok=True)
                        safe = unique_media_name(media_dir, filename)
                        dest = os.path.join(media_dir, safe)
                        with open(dest, "wb") as fh:
                            fh.write(payload)
                        info = probe_media(dest)
                        kind = "video" if info.get("width") else "audio"
                        medium = state.project.add_media(
                            f"media/{safe}", kind=kind,
                            **{k: v for k, v in info.items() if k in
                               ("width", "height", "fps", "frames",
                                "duration", "hasAudio")})
                        state.save()
                        self._send_json({"ok": True, "media": medium})
                    else:
                        self._send_json({"error": "Not found"}, 404)
            except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
                self._send_json({"error": str(exc)}, 400)
            except Exception as exc:  # noqa: BLE001 - surfaced to the UI
                self._send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    return Handler


def open_browser(url: str) -> bool:
    """Open a URL in the default browser. Returns False (never
    raises) when no browser can be opened, so the server keeps
    running and the user can still open the URL by hand."""
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001 - browser opening is best-effort
        return False


def run_server(project_dir: str | None, port: int = 8000,
               open_browser_flag: bool = False) -> None:
    state = State(project_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    url = f"http://127.0.0.1:{port}/"
    print(f"VibeEdit Windows MVP running at {url}")
    print(f"Project folder: {state.project_dir}")
    if open_browser_flag:
        if open_browser(url):
            print(f"Opened {url} in your browser.")
        else:
            print(f"Could not open a browser automatically; "
                  f"open {url} yourself.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nVibeEdit stopped.")
    finally:
        # Phase 2 clean shutdown: without server_close the socket
        # can stay bound after Ctrl+C on some platforms. (No
        # shutdown() here: serve_forever runs on this same thread,
        # and shutdown() must be called from another thread.)
        try:
            server.server_close()
        except Exception:
            pass
