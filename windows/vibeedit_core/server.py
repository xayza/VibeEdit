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
                      write_backup, unique_media_name, migrate_fps_units)
from .render import RenderCancel, RenderCancelled, render, probe_media
from .filelock import ProjectFileLock


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



def mcp_client_command(project_dir):
    """Round 22: the real MCP client command for this app install.

    Derived from actual paths, never hardcoded and never a
    template: the Windows folder comes from this file's location,
    the Python from the install's .venv when present (the shape
    the tester verified: <windows>\\.venv\\Scripts\\python.exe)
    else this interpreter, and the project folder from the open
    project. Returns {"command", "args", "command_line"} where
    command_line is the paste-ready quoted single line and
    command/args is the MCP client-config shape. Returns None
    fields when no project folder is known.
    """
    import os
    import sys
    windows_dir = os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))
    candidates = [os.path.join(windows_dir, ".venv", "Scripts",
                               "python.exe"),
                  os.path.join(windows_dir, ".venv", "bin", "python")]
    python = next((c for c in candidates if os.path.isfile(c)),
                  sys.executable)
    script = os.path.join(windows_dir, "vibeedit.py")
    if not project_dir:
        return {"command": None, "args": None, "command_line": None}
    folder = os.path.abspath(project_dir)
    args = [script, "mcp", folder]
    line = " ".join(f'"{p}"' for p in [python] + args)
    return {"command": python, "args": args, "command_line": line}


def agent_status_for(project_dir):
    """Round 14: last MCP activity for one project dir (see mcp.py
    _touch_agent_status). connected=True only when an MCP process
    touched the stamp within the last hour; the stamp holds a
    timestamp only, never conversation content."""
    import hashlib
    import json
    import os
    import tempfile
    import time
    if not project_dir:
        status = {"connected": False, "last_seen": None,
                  "age_seconds": None}
    else:
        folder = os.path.normcase(os.path.abspath(project_dir))
        key = hashlib.sha1(folder.encode()).hexdigest()[:12]
        stamp = os.path.join(tempfile.gettempdir(),
                             f"vibeedit-mcp-{key}.json")
    try:
        with open(stamp, encoding="utf-8") as fh:
            last = float(json.load(fh).get("last_seen", 0))
    except Exception:
        status = {"connected": False, "last_seen": None,
                  "age_seconds": None}
    else:
        age = time.time() - last
        status = {"connected": age < 3600, "last_seen": last,
                  "age_seconds": age}
    # Round 22: the Agent dock's copy button copies this real
    # command (see mcp_client_command), never the template.
    cmd = mcp_client_command(project_dir)
    status["mcp_command"] = cmd["command_line"]
    status["mcp_client"] = {"command": cmd["command"],
                            "args": cmd["args"]}
    return status

class State:
    def __init__(self, project_dir: str | None):
        self.lock = threading.Lock()
        self.project_dir = project_dir or DEFAULT_PROJECT_DIR
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.last_export: str | None = None
        self.last_report: dict | None = None
        # Round 22: background export jobs. Rendering used to run
        # synchronously inside do_POST while holding state.lock, so
        # every other request (including GET /api/project) queued
        # behind a minutes-long full render and the UI looked hung.
        # Jobs now render on a worker thread from a snapshot, so the
        # editor stays responsive; only publishing the result takes
        # state.lock briefly. Guarded by their own lock, never by
        # state.lock, so status reads stay fast during a render.
        self.export_jobs: dict[str, dict] = {}
        # Round 24: one cancel token per job, kept OUT of the job
        # dict so job dicts stay JSON-serializable for the status
        # endpoint (a token object in the dict would break _send_json).
        self.export_tokens: dict[str, RenderCancel] = {}
        self.export_lock = threading.Lock()
        self.export_seq = 0
        self.project, self.path = self._load_or_create()
        # Phase 0 backup rule: the first save after a project is
        # opened creates one backup of the saved file as loaded.
        self._needs_first_backup = True
        # Round 22 P0: True when the most recent refresh_from_disk()
        # call reloaded a newer on-disk project (external writer,
        # e.g. an MCP agent). Surfaced in _project_view so the UI
        # can tell the user their view was refreshed from disk.
        self._last_external_reload = False

    def _load_or_create(self) -> tuple[Project, str]:
        os.makedirs(os.path.join(self.project_dir, "media"), exist_ok=True)
        os.makedirs(os.path.join(self.project_dir, "render"), exist_ok=True)
        found = find_project_file(self.project_dir)
        if found:
            data = load_project(found)
            # Round 19: migrate pre-fix source-frame durations once,
            # backing up the pre-migration file first (best effort,
            # never blocking the open).
            if migrate_fps_units(data)["converted"]:
                try:
                    write_backup(found)
                except Exception:
                    pass
                save_project(data, found)
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

    def start_export_job(self, data: dict, folder: str, out: str,
                           preset: str, normalize: bool,
                           export_preset: str | None) -> dict:
        """Start a background export job; returns its job dict.

        ``data`` must already be a snapshot (deep copy): the worker
        renders without state.lock, so later edits must not mutate
        the data being rendered. Cancelling (round 24) SIGKILLs the
        running FFmpeg process via the job's RenderCancel token and
        removes the partial output file; a job that already reached
        "publishing" keeps the old semantics (a late cancel can no
        longer divert it, and the cancel response then honestly
        reports done).
        """
        with self.export_lock:
            self.export_seq += 1
            job_id = f"export-{self.export_seq}"
            job: dict = {"id": job_id, "status": "running",
                         "preset": preset, "output": out,
                         "error": None, "report": None}
            self.export_jobs[job_id] = job
            token = RenderCancel()
            self.export_tokens[job_id] = token

        def _remove_partial() -> None:
            try:
                if os.path.isfile(out):
                    os.remove(out)
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass

        def _run() -> None:
            try:
                report = render(data, folder, out, preset=preset,
                                normalize_audio=normalize,
                                export_preset=export_preset,
                                cancel=token)
            except RenderCancelled:
                with self.export_lock:
                    job["status"] = "cancelled"
                    job["killed"] = token.killed
                _remove_partial()
                return
            except Exception as exc:  # noqa: BLE001 - reported on job
                with self.export_lock:
                    if job["status"] == "cancelled":
                        # A failed render that was also cancelled:
                        # never publish, and drop the partial file.
                        _remove_partial()
                        return
                    job["status"] = "error"
                    job["error"] = str(exc)
                return
            # Publish under the two locks separately, never nested:
            # cancel only flips "running" -> "cancelled", so once the
            # job is "publishing" a late cancel can no longer divert
            # it, and the cancel response then honestly reports done.
            with self.export_lock:
                if job["status"] == "cancelled":
                    return
                job["status"] = "publishing"
            with self.lock:
                self.last_export = out
                self.last_report = report
            with self.export_lock:
                job["status"] = "done"
                job["report"] = report

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return job

    def export_job(self, job_id: str | None) -> dict | None:
        """One job by id, or the latest job when id is None."""
        with self.export_lock:
            if job_id:
                job = self.export_jobs.get(job_id)
                return dict(job) if job else None
            if not self.export_jobs:
                return None
            latest = max(self.export_jobs.values(),
                         key=lambda j: int(j["id"].split("-")[1]))
            return dict(latest)

    def cancel_export_job(self, job_id: str) -> dict | None:
        """Cancel a running job AND terminate its FFmpeg process.

        Round 24: previously this only flipped the status, so a
        render already inside FFmpeg kept running to completion in
        the background (its output was never published, but the
        process, CPU time and disk writes continued). Now the job's
        cancel token SIGKILLs the FFmpeg process; the worker then
        removes the partial output file. A job that already reached
        "publishing" keeps the old semantics: the cancel response
        honestly reports done.
        """
        with self.export_lock:
            job = self.export_jobs.get(job_id)
            if job is None:
                return None
            if job["status"] == "running":
                job["status"] = "cancelled"
                token = self.export_tokens.get(job_id)
                if token is not None:
                    token.request()
            return dict(job)

    def project_lock(self) -> ProjectFileLock:
        """Round 25: cross-process lock for this project's file.

        The web server's threading lock (state.lock) serializes only
        threads inside this process; an external MCP agent is a
        separate process and needs the file lock. Every project write
        path holds this across [refresh, mutate, save] so two writers
        serialize instead of racing (both reading rev N and writing
        rev N+1, losing one update). Never held across renders,
        exports, transcription, or network calls — see apply().
        """
        return ProjectFileLock(self.path)

    def save(self) -> None:
        # Autosave itself creates no backup; only the first save
        # after opening a project does (see backup_before_change).
        if self._needs_first_backup:
            self.backup_before_change()
        save_project(self.project.data, self.path)

    def refresh_from_disk(self) -> bool:
        """Reload project.json when the file on disk is NEWER than RAM.

        Round 22 P0 (silent data loss): the web server holds the
        project in RAM while an external MCP agent writes the same
        file. Without this check the next web save overwrote the
        agent's edits wholesale (reported: MCP markers_add -> disk
        rev 107 with 35 markers, then web set_speed -> disk rev 107
        with 34 markers, the agent's marker silently lost; both
        writers ended at rev 107 because the web copy started from
        the older rev 106).
        Reload only when disk rev > RAM rev; an equal or older disk
        never overwrites RAM, and a failed read/parse never touches
        RAM (a refresh must never break the op in progress). A
        reload invalidates undo/redo snapshots (they describe the
        old state), so both stacks are cleared. Callers run this
        BEFORE mutating (apply/undo/redo/save) and before serving
        GET /api/project, so a later write always starts from the
        newest disk state and rev increases monotonically.
        True simultaneous writes (both writers refreshing at the
        same instant) can still race; that needs file locking and
        is out of scope — the sequential interleave, which is the
        reported case, is fully covered.
        """
        try:
            disk = load_project(self.path)
            disk_rev = int(disk.get("rev", 0) or 0)
        except Exception:
            self._last_external_reload = False
            return False
        if disk_rev <= self.project.rev:
            self._last_external_reload = False
            return False
        self.project.restore(disk)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._last_external_reload = True
        return True

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
        file path), load it, and point this server state at it
        (project, path, project_dir, cleared undo/redo and last
        export). Raises on a missing project file instead of silently
        staying on the old project.

        Round 22: absolute paths outside projects_root are now
        allowed. The old strict-inside-projects rule made the picker
        unable to open any second project stored elsewhere (the
        welcome panel offered no path input at all), while the
        server binds localhost only and the path comes from the
        user's own UI/API call — the same authorization as a desktop
        app's Open dialog. Bare names still resolve inside root.
        """
        root = self.projects_root()
        if os.path.isabs(folder):
            candidate = os.path.abspath(folder)
        else:
            candidate = os.path.abspath(os.path.join(root, folder))
        if os.path.isfile(candidate):
            candidate = os.path.dirname(candidate)
        found = find_project_file(candidate)
        if not found:
            raise FileNotFoundError(f"Không có file project trong thư mục: {folder}")
        os.makedirs(os.path.join(candidate, "media"), exist_ok=True)
        os.makedirs(os.path.join(candidate, "render"), exist_ok=True)
        data = load_project(found)
        # Round 19: same one-time fps-unit migration as on startup.
        if migrate_fps_units(data)["converted"]:
            try:
                write_backup(found)
            except Exception:
                pass
            save_project(data, found)
        self.project = Project(data, candidate)
        self.path = found
        self.project_dir = candidate
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.last_export = None
        self.last_report = None
        self._needs_first_backup = True
        self._last_external_reload = False
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
        # Round 25: serialize the read-modify-write critical section
        # across processes. refresh_from_disk() inside the lock is
        # what closes the true-simultaneous race: two writers can no
        # longer both read rev N, mutate, and write rev N+1. The one
        # exception is the transcribe op, which runs for minutes;
        # holding the file lock across it would wedge MCP writers for
        # the whole transcription, so it keeps the round-22 behaviour
        # (refresh first, unlocked) — the sequential case stays
        # covered, and only a truly overlapping locked write could
        # still win over a transcription save.
        if op.get("op") == "transcribe":
            return self._apply_inner(op)
        with self.project_lock():
            return self._apply_inner(op)

    def _apply_inner(self, op: dict) -> dict:
        # Round 22 P0: reload-before-write. An external writer (MCP
        # agent) may have advanced the disk file since this State
        # loaded it; applying on top of stale RAM and then saving
        # would silently discard the agent's edits. Refresh first
        # so the op lands on the newest disk state (rev monotonic).
        # Callers hold project_lock() around this (except the
        # transcribe bypass in apply()), so the refresh, the
        # mutation, and the save at the end are one atomic section
        # against other processes.
        self.refresh_from_disk()
        proj = self.project
        if op.get("op") == "srt_export":
            return {"srt": proj.export_srt(op.get("track", "t1"))}
        # Round 22: read-only ops must not push undo snapshots.
        # magnetic_get used to fall through to the push below, so
        # every UI load() (which fetched it) planted a post-edit
        # snapshot: undo after Delete then needed two presses
        # (first restored the identical post-delete state).
        if op.get("op") == "magnetic_get":
            return {"magnetic": proj.magnetic_enabled}
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
                        "Source Out phải đứng sau Source In")
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
                # Round 19: in/out are SOURCE frames, dur is PROJECT
                # frames — convert the span (see project.py).
                from .project import source_span_to_project_frames
                medium = proj.media(op["media"])
                result = proj.add_clip(
                    op["media"], track_id, int(op.get("at", 0)), in_frame,
                    source_span_to_project_frames(
                        out_frame - in_frame, medium.get("fps"),
                        proj.data["format"]["fps"]),
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
            elif kind == "knowledge":
                from . import knowledge as _k
                action = op.get("action", "")
                data = proj.data
                if action == "add_lesson":
                    result = _k.add_lesson(data, op["text"],
                                           op.get("title"))
                elif action == "lessons":
                    result = {"lessons": _k.lessons(data)}
                elif action == "get":
                    result = _k.get_lesson(data, op["lesson"])
                elif action == "update_lesson":
                    result = _k.update_lesson(data, op["lesson"],
                                              op["text"])
                elif action == "remove_lesson":
                    result = _k.remove_lesson(data, op["lesson"])
                elif action == "approve":
                    if op.get("proposal"):
                        result = _k.approve_proposal(data,
                                                     op["proposal"])
                    else:
                        result = _k.approve_lesson(data, op["lesson"])
                elif action == "reject":
                    if op.get("proposal"):
                        result = _k.reject_proposal(data,
                                                    op["proposal"])
                    else:
                        result = _k.reject_lesson(data, op["lesson"])
                elif action == "facts":
                    result = {"facts": _k.facts(data)}
                elif action == "set_fact":
                    result = _k.set_fact(data, op["key"], op["value"])
                elif action == "prefs":
                    result = {"prefs": _k.prefs(data)}
                elif action == "set_pref":
                    result = _k.set_pref(data, op["key"], op["value"])
                elif action == "claims":
                    result = {"claims": _k.claims(data)}
                elif action == "set_claim":
                    result = _k.set_claim(data, op["key"],
                                          op["statement"])
                elif action == "memo":
                    if "text" in op:
                        result = _k.set_memo(data, op["text"])
                    else:
                        result = {"memo": _k.get_memo(data)}
                elif action == "split_memo":
                    result = _k.split_memo(data)
                elif action == "proposals":
                    result = {"proposals": _k.proposals(data)}
                elif action == "verdicts":
                    result = {"verdicts": _k.verdicts(data)}
                elif action == "history":
                    result = {"history": _k.history(data)}
                elif action == "revert":
                    result = _k.revert(data, int(op.get("steps", 1)))
                elif action == "migrate":
                    result = _k.migrate(data)
                else:
                    raise ValueError(f"Action knowledge không rõ: {action}")
            elif kind == "skills_save":
                from .skills import save_skill
                result = save_skill(None, op["skill"], op.get("title", ""),
                                    op["body"],
                                    overwrite=bool(op.get("overwrite",
                                                          False)))
            elif kind == "skills_enable":
                from .skills import set_skill_enabled
                result = set_skill_enabled(None, op["skill"], True)
            elif kind == "skills_disable":
                from .skills import set_skill_enabled
                result = set_skill_enabled(None, op["skill"], False)
            elif kind == "skills_export":
                from .skills import export_skill
                result = export_skill(None, op["skill"], op.get("dest"))
            elif kind == "skills_remove":
                from .skills import remove_skill
                result = remove_skill(None, op["skill"],
                                      confirm=bool(op.get("confirm",
                                                          False)))
            elif kind == "skills_propose":
                from .skills import propose_skill
                result = propose_skill(None, op["skill"],
                                       op.get("title", ""), op["body"])
            elif kind == "skills_import_plan":
                # Round 23: preview only — plan_import writes nothing.
                from .skill_import import plan_import
                if not op.get("path"):
                    raise ValueError(
                        "Nhập skill cần đường dẫn nguồn (file .md, "
                        "thư mục hoặc file .zip)")
                result = plan_import(op["path"])
            elif kind == "skills_import":
                # Round 23: install only the preview's ticked rows
                # (only=...); never auto-enables anything.
                from .skill_import import apply_import
                if not op.get("path"):
                    raise ValueError(
                        "Nhập skill cần đường dẫn nguồn (file .md, "
                        "thư mục hoặc file .zip)")
                result = apply_import(
                    op["path"],
                    overwrite=bool(op.get("overwrite", False)),
                    only=op.get("only"))
            elif kind == "captions_transcribe":
                from .transcribe import transcribe_media
                medium = proj.media(op["media"])
                mpath = medium["path"]
                if not os.path.isabs(mpath):
                    mpath = os.path.join(proj.folder, mpath)
                added = transcribe_media(proj, mpath,
                                         op.get("track", "t1"),
                                         model=op.get("model", "tiny"))
                result = {"added": [it["id"] for it in added]}
            elif kind == "captions_generate":
                from .transcribe import transcribe_media
                medium = proj.media(op["media"])
                mpath = medium["path"]
                if not os.path.isabs(mpath):
                    mpath = os.path.join(proj.folder, mpath)
                track = op.get("track", "t1")
                added = transcribe_media(proj, mpath, track,
                                         model=op.get("model", "tiny"))
                result = {"added": [it["id"] for it in added],
                          "srt": proj.export_srt(track)}
            elif kind == "captions_align":
                from .transcribe import align_captions
                medium = proj.media(op["media"])
                mpath = medium["path"]
                if not os.path.isabs(mpath):
                    mpath = os.path.join(proj.folder, mpath)
                result = align_captions(proj, op.get("track", "t1"),
                                        mpath, model=op.get("model",
                                                            "tiny"))
            elif kind == "fonts_import":
                from .render import import_font
                result = import_font(op["path"])
            elif kind == "timeline_reorder":
                result = proj.reorder_main(op["item"], op.get("before"))
            elif kind == "voice_check":
                import importlib.util as _ilu
                import shutil as _sh
                takes = 0
                for track in proj.data["tracks"]:
                    if track.get("role") == "voiceover":
                        takes += len(track.get("items", []))
                result = {"backends": {
                    "piper": _sh.which("piper") is not None,
                    "edge_tts": _ilu.find_spec("edge_tts") is not None},
                    "voiceover_takes": takes}
            elif kind == "voice_generate":
                # Round 3: real generation via Edge TTS / Piper
                # (vibeedit_core.voice). The output is added as
                # project audio media; cloning is not wired.
                from .voice import synthesize as _synth
                out = os.path.join(proj.folder, "media",
                                   op.get("file") or "voice_take.wav")
                res = _synth(op["text"], out,
                             provider=op.get("provider"),
                             voice=op.get("voice"),
                             model=op.get("model"))
                medium = proj.add_media(res["path"], kind="audio",
                                        duration=res["duration"])
                result = {"media": medium["id"], "path": res["path"],
                          "backend": res["backend"],
                          "voice": res["voice"],
                          "duration": res["duration"]}
            elif kind == "voice_place":
                from .voice import place_on_voiceover as _place
                result = _place(proj, op["media"], op.get("at"))
            elif kind == "voice_use":
                proj.data["voice"] = {
                    "provider": op.get("provider"),
                    "voice": op.get("voice"),
                    "model": op.get("model")}
                result = {"voice": proj.data["voice"]}
            elif kind == "voice_fit":
                _track, item = proj.item(op["item"])
                target = int(op.get("frames") or op["to_frame"])
                if target <= 0:
                    raise ValueError("voice_fit cần đích frames/to_frame dương")
                needed = int(item["dur"]) / target
                proj.set_speed(op["item"], needed)
                result = {"item": op["item"], "speed": needed,
                          "frames": target}
            elif kind == "app_update_check":
                from .updater import update_status as _update_status
                result = _update_status()
            elif kind == "plugin_install":
                from .plugins import install_plugin
                result = install_plugin(
                    op["source"],
                    overwrite=bool(op.get("overwrite", False)),
                    source_label=op.get("source_label"))
            elif kind == "plugin_download":
                # Gated step: a URL download only runs with an explicit
                # user confirmation in the op; it never installs or
                # executes anything.
                if not op.get("confirm"):
                    raise ValueError(
                        "plugin_download cần confirm: true (nguồn không tin cậy); hãy tải về trước, rồi plugin_install gói đã tải")
                import os as _os
                import tempfile as _tf
                from .plugins import download_plugin_bundle
                dest = op.get("dest") or _os.path.join(
                    _tf.gettempdir(), "vibeedit-plugin-bundle.zip")
                result = download_plugin_bundle(op["url"], dest)
            elif kind == "plugin_remove":
                from .plugins import remove_plugin
                result = remove_plugin(op["plugin"])
            elif kind == "plugin_update_check":
                from .plugins import check_plugin_update
                result = check_plugin_update(op["plugin"])
            elif kind == "link_audio":
                result = proj.link_audio(op["video"], op["audio"])
            elif kind == "unlink_audio":
                result = proj.unlink_audio(op["video"], op.get("audio"))
            elif kind == "magnetic_get":
                result = {"magnetic": proj.magnetic_enabled}
            elif kind == "magnetic_set":
                proj.set_magnetic(bool(op["enabled"]))
                result = {"magnetic": proj.magnetic_enabled}
            elif kind == "clip_reframe":
                result = proj.set_reframe(op["item"], op.get("window"))
            elif kind == "transitions_renderability":
                from .render import list_transition_renderability
                result = {"transitions": list_transition_renderability()}
            elif kind == "skills_list":
                from .skills import list_skills
                result = {"skills": list_skills()}
            elif kind == "skills_get":
                from .skills import get_skill
                result = {"skill": get_skill(None, op["skill"])}
            elif kind == "skills_search":
                from .skills import search_skills
                result = {"skills": search_skills(None, op.get("query", ""))}
            elif kind == "skills_sync_claude":
                # Round 23: export to <repo>/.claude/skills/<id>/
                # SKILL.md (+ references/); target_dir overrides the
                # derived default (tests use a temp dir).
                from .skill_import import sync_claude
                result = sync_claude(
                    target_dir=op.get("target_dir"),
                    overwrite=bool(op.get("overwrite", False)))
            elif kind == "vision_cutout_model":
                from .vision import cutout_segmented as _seg
                medium = proj.media(op["media"])
                path = medium["path"]
                if not os.path.isabs(path):
                    path = os.path.join(proj.folder, path)
                result = _seg(path, op["model"], op.get("output"))
            elif kind in ("vision_ocr", "vision_faces", "vision_cutout"):
                from .vision import VisionUnavailable
                from .vision import cutout as _cut
                from .vision import detect_faces as _faces
                from .vision import ocr_image as _ocr
                import os as _os
                medium = proj.media(op["media"])
                path = medium["path"]
                if not _os.path.isabs(path):
                    path = _os.path.join(proj.folder, path)
                try:
                    if kind == "vision_ocr":
                        result = _ocr(path)
                    elif kind == "vision_faces":
                        result = _faces(path)
                    else:
                        out = op.get("output") or _os.path.join(
                            proj.folder, "render",
                            _os.path.splitext(
                                _os.path.basename(path))[0] + "_cutout.png")
                        result = _cut(path, out)
                except VisionUnavailable as exc:
                    raise ValueError(
                        f"Thiếu backend vision: {exc}")
            else:
                raise ValueError(f"Thao tác không rõ: {kind}")
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
    raise ValueError("Không có clip nào phủ khung hình playhead")


def _safe_upload_name(filename: str) -> str:
    """Sanitize an uploaded filename to a plain basename.

    Round 19: strips Windows backslash paths too (os.path.basename
    on Linux does not split '\\\\'), so a name can never smuggle a
    directory or collapse to an extension-only fragment.
    """
    base = (filename or "").replace("\\", "/").split("/")[-1].strip()
    return base or "upload.bin"


def _find_media_by_sha256(project, project_dir: str,
                          digest: str) -> dict | None:
    """Find a media record whose content hash matches ``digest``.

    Records without a hash get one backfilled from their stored file
    (once, then it persists on the next save), so old projects gain
    dedupe without re-import. A record whose file no longer exists
    is never returned: reusing it would point at a missing file.
    """
    import hashlib
    for medium in project.data["media"]:
        stored = medium.get("sha256")
        if stored is None:
            path = os.path.join(project_dir, medium.get("path", ""))
            if not os.path.isfile(path):
                continue
            try:
                hasher = hashlib.sha256()
                with open(path, "rb") as fh:
                    for block in iter(lambda: fh.read(1 << 20), b""):
                        hasher.update(block)
                stored = medium["sha256"] = hasher.hexdigest()
            except OSError:
                continue
        if stored == digest:
            path = os.path.join(project_dir, medium.get("path", ""))
            if os.path.isfile(path):
                return medium
    return None


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
        # Round 19: accept LF-only bodies too (some clients send
        # \n instead of \r\n). The old code split the head only on
        # \r\n\r\n, so an LF-only upload produced an empty payload
        # and a filename polluted with the following headers.
        head, sep, payload = chunk.partition(b"\r\n\r\n")
        if not sep:
            head, sep, payload = chunk.partition(b"\n\n")
        if not sep:
            continue
        if sep == b"\r\n\r\n":
            payload = payload.rsplit(b"\r\n", 1)[0]
        else:
            payload = payload.rsplit(b"\n", 1)[0]
        name = None
        filename = None
        for line in head.decode(errors="replace").splitlines():
            line = line.strip()
            if not line.lower().startswith("content-disposition:"):
                continue
            params = line.split(";", 1)[1] if ";" in line else ""
            for piece in params.split(";"):
                piece = piece.strip()
                if piece.startswith("name="):
                    name = piece[5:].strip('"')
                elif piece.startswith("filename="):
                    # A filename never contains a line break; cut
                    # there so a stray header line can never pollute
                    # it (the old 'media/mp4' failure mode).
                    filename = piece[9:].strip('"').split("\r")[0] \
                        .split("\n")[0]
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
                    # Round 22: single source of truth for the
                    # Magnetic toggle (server-computed, with the True
                    # default for projects predating the toggle). The
                    # UI used to fetch magnetic_get separately on
                    # every load — which misread the response shape
                    # (result.magnetic, not top-level) AND pushed a
                    # junk undo snapshot on every load (see apply).
                    # Round 22 P0: whether the latest refresh reloaded
                    # a newer on-disk project (external writer).
                    "external_reload": state._last_external_reload,
                    "magnetic": proj.magnetic_enabled,
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
                    state.refresh_from_disk()
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
            elif parsed.path == "/api/agent-status":
                self._send_json(agent_status_for(state.project_dir))
            elif parsed.path == "/api/mcp-tools":
                # Phase 5 agent dock: the live tool registry from
                # mcp.py (names + descriptions), not a hardcoded list.
                from .mcp import TOOLS
                self._send_json({"tools": TOOLS, "count": len(TOOLS)})
            elif parsed.path == "/api/export/status":
                # Round 22: deliberately lock-free (export_lock only,
                # inside export_job): polling export progress must
                # stay fast while a render holds no state.lock at all.
                query = urllib.parse.parse_qs(parsed.query)
                job_id = (query.get("job") or [None])[0]
                job = state.export_job(job_id)
                if job is None:
                    self._send_json({"job": None})
                else:
                    self._send_json({"job": job})
            elif parsed.path == "/api/preview":
                if state.last_export and os.path.isfile(state.last_export):
                    self._serve_file(state.last_export)
                else:
                    self._send_json({"error": "Chưa có bản xuất nào"}, 404)
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
                        {"error": "Chưa có xem trước cho transition này; "
                         "hãy tạo nó trước"}, 404)
            elif parsed.path == "/":
                self._serve_file(os.path.join(STATIC_DIR, "index.html"))
            elif parsed.path.startswith("/static/"):
                name = os.path.basename(parsed.path)
                path = os.path.join(STATIC_DIR, name)
                if os.path.isfile(path):
                    self._serve_file(path)
                else:
                    self._send_json({"error": "Không tìm thấy"}, 404)
            else:
                self._send_json({"error": "Không tìm thấy"}, 404)

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
                self._send_json({"error": "Media không rõ"}, 404)
                return
            medium, real = found
            try:
                thumb = generate_thumbnail(
                    real, thumbnail_path(state.project_dir, media_id),
                    medium.get("kind", ""))
            except (ValueError, RuntimeError, FileNotFoundError):
                self._send_json({"error": "Không có thumbnail cho media này"},
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
                self._send_json({"error": "Media không rõ"}, 404)
                return
            with state.lock:
                try:
                    medium = state.project.media(media_id)
                except KeyError:
                    self._send_json({"error": "Media không rõ"}, 404)
                    return
                path = medium["path"]
                if not os.path.isabs(path):
                    path = os.path.join(state.project_dir, path)
            media_dir = os.path.realpath(
                os.path.join(state.project_dir, "media"))
            real = os.path.realpath(path)
            if os.path.commonpath([real, media_dir]) != media_dir:
                self._send_json({"error": "Media không rõ"}, 404)
                return
            if not os.path.isfile(real):
                self._send_json({"error": "Thiếu file media"}, 404)
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
                        raise ValueError("Không hỗ trợ multi-range")
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
                # Round 22: background export. This branch runs BEFORE
                # state.lock: it snapshots the project under the lock
                # briefly, starts the worker thread, and returns the
                # job immediately, so GET /api/project and every other
                # request keep answering while FFmpeg renders. The old
                # synchronous branch (render inside state.lock) hung
                # the whole UI for the length of a full render.
                if parsed.path == "/api/export":
                    body = self._read_json()
                    preset = body.get("preset", "full")
                    export_preset = body.get("export_preset")
                    with state.lock:
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
                        snapshot = copy.deepcopy(state.project.data)
                        job = state.start_export_job(
                            snapshot, state.project_dir, out,
                            preset=preset,
                            normalize=bool(body.get("normalize", False)),
                            export_preset=export_preset)
                    self._send_json({"ok": True, "job": dict(job)})
                    return
                if parsed.path == "/api/export/cancel":
                    body = self._read_json()
                    job = state.cancel_export_job(body.get("job", ""))
                    if job is None:
                        self._send_json({"error": "Không rõ job xuất"},
                                        404)
                    else:
                        self._send_json({"ok": True, "job": job})
                    return
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
                                "Tên project phải là tên thư mục thường")
                        root = state.projects_root()
                        folder = os.path.join(root, name)
                        if os.path.exists(folder):
                            raise ValueError(
                                f"Thư mục project đã tồn tại: {name}")
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
                                "Thư mục đích hiện phải là thư mục project bên trong projects/")
                        if sys.platform == "win32":
                            os.startfile(candidate)  # noqa: S606
                        elif shutil.which("xdg-open"):
                            import subprocess
                            subprocess.Popen(["xdg-open", candidate])
                        else:
                            raise RuntimeError(
                                "Chức năng hiện thư mục chỉ hỗ trợ trên Windows (os.startfile); hãy sao chép đường dẫn project từ panel chào mừng")
                        self._send_json({"ok": True, "path": candidate})
                    elif parsed.path == "/api/undo":
                        self._read_json()
                        # Round 22 P0: an external writer invalidates
                        # the undo stack (refresh clears it), so a
                        # stale snapshot can never overwrite newer
                        # disk state. Round 25: refresh, restore, and
                        # save are one locked section, so a concurrent
                        # writer cannot slip in between them.
                        with state.project_lock():
                            state.refresh_from_disk()
                            if not state.undo_stack:
                                raise ValueError("Không có gì để hoàn tác")
                            state.redo_stack.append(
                                state.project.snapshot())
                            state.project.restore(state.undo_stack.pop())
                            state.save()
                        self._send_json({"ok": True, **self._project_view()})
                    elif parsed.path == "/api/redo":
                        self._read_json()
                        # Round 22 P0: same stale-stack guard as undo.
                        # Round 25: locked with the refresh and save.
                        with state.project_lock():
                            state.refresh_from_disk()
                            if not state.redo_stack:
                                raise ValueError("Không có gì để làm lại")
                            state.undo_stack.append(
                                state.project.snapshot())
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
                        # Round 22 P0: a plain re-save of stale RAM
                        # must never overwrite a newer disk file.
                        # Round 25: refresh and save are one locked
                        # section, so a concurrent writer cannot land
                        # between them.
                        with state.project_lock():
                            state.refresh_from_disk()
                            state.save()
                        self._send_json({"ok": True, **self._project_view()})
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
                        info = load_plugins().get(body["plugin"], {})
                        hook = next((k for k, v in info.items()
                                     if callable(v)), None)
                        if not hook:
                            raise ValueError(
                                f"Plugin {body['plugin']!r} không có hook")
                        # Round 25: refresh, snapshot, apply, and save
                        # are one locked section (see apply()). The
                        # snapshot is taken after the refresh, so a
                        # failed apply restores the newest state, and
                        # a missing hook no longer leaves a junk
                        # snapshot on the undo stack.
                        with state.project_lock():
                            state.refresh_from_disk()
                            state.undo_stack.append(state.project.snapshot())
                            if len(state.undo_stack) > 50:
                                state.undo_stack.pop(0)
                            state.redo_stack.clear()
                            try:
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
                    elif parsed.path == "/api/voiceover/record":
                        # Round 4: a browser-recorded voiceover take.
                        # The browser records microphone audio only
                        # (MediaRecorder/getUserMedia; permission is
                        # the browser's, and a denial surfaces as a
                        # clear client-side error, never a fake
                        # file). The uploaded blob is stored exactly
                        # like any other media file (unique name,
                        # never overwriting) and registered as audio
                        # media, so the existing voiceover form can
                        # place it on the Voiceover track. Only
                        # audio is accepted here: a filename whose
                        # extension is not an audio/container audio
                        # type is rejected rather than stored as a
                        # voiceover take.
                        length = int(self.headers.get("Content-Length") or 0)
                        body = self.rfile.read(length)
                        ctype = self.headers.get("Content-Type", "")
                        boundary = ctype.split("boundary=")[-1].encode()
                        parts = _parse_multipart(body, boundary)
                        filename, payload = parts["file"]
                        ext = os.path.splitext(filename)[1].lower()
                        if ext not in (".webm", ".mp4", ".m4a", ".ogg",
                                       ".oga", ".wav", ".mp3", ".flac"):
                            raise ValueError(
                                f"Bản ghi voiceover phải là file audio, không phải {filename!r}")
                        if len(payload) == 0:
                            raise ValueError(
                                "Bản ghi voiceover rỗng; hãy giữ nút ghi, nói, rồi dừng")
                        media_dir = os.path.join(state.project_dir,
                                                 "media")
                        os.makedirs(media_dir, exist_ok=True)
                        safe = unique_media_name(
                            media_dir, _safe_upload_name(filename))
                        dest = os.path.join(media_dir, safe)
                        with open(dest, "wb") as fh:
                            fh.write(payload)
                        info = probe_media(dest)
                        # Round 25: refresh, add, and save are one
                        # locked section (see apply()).
                        with state.project_lock():
                            state.refresh_from_disk()
                            medium = state.project.add_media(
                                f"media/{safe}", kind="audio",
                                **{k: v for k, v in info.items() if k in
                                   ("duration", "hasAudio")})
                            state.save()
                        self._send_json({"ok": True, "media": medium})
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
                        # Round 19 dedupe: the same file uploaded
                        # twice reuses the first media id (content
                        # hash, not name) and writes no second file.
                        # A different file with the same name keeps
                        # the old name-2/name-3 behaviour (its hash
                        # differs, so dedupe does not affect it).
                        import hashlib
                        digest = hashlib.sha256(payload).hexdigest()
                        # Round 25: refresh, dedupe/add, and save are
                        # one locked section (see apply()).
                        with state.project_lock():
                            state.refresh_from_disk()
                            existing = _find_media_by_sha256(
                                state.project, state.project_dir, digest)
                            if existing is not None:
                                # Persist any hash backfills from the
                                # lookup, then reuse without writing.
                                state.save()
                                result = {"ok": True, "media": existing,
                                          "reused": True}
                            else:
                                safe = unique_media_name(
                                    media_dir, _safe_upload_name(filename))
                                dest = os.path.join(media_dir, safe)
                                with open(dest, "wb") as fh:
                                    fh.write(payload)
                                info = probe_media(dest)
                                kind = ("video" if info.get("width")
                                        else "audio")
                                medium = state.project.add_media(
                                    f"media/{safe}", kind=kind,
                                    sha256=digest,
                                    **{k: v for k, v in info.items()
                                       if k in
                                       ("width", "height", "fps", "frames",
                                        "duration", "hasAudio")})
                                state.save()
                                result = {"ok": True, "media": medium}
                        self._send_json(result)
                    else:
                        self._send_json({"error": "Không tìm thấy"}, 404)
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


class QuietDisconnectServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that stays silent on client disconnects.

    Round 19: closing the browser tab mid-response raises
    ConnectionResetError/BrokenPipeError in wfile.write, and the
    default BaseServer.handle_error prints a traceback for every tab
    close. (The override belongs here, on the server: BaseRequest-
    Handler has no handle_error, so overriding it on the handler
    would never run.)
    Round 22: on Windows the same tab-close raises
    ConnectionAbortedError (WSAECONNABORTED), which is NOT a
    subclass of ConnectionResetError — both are ConnectionError
    siblings — so round 19's filter missed it and the traceback
    (at the _serve_media wfile.write loop) survived on Windows.
    Only disconnect errors are swallowed; every other handler error
    still prints its traceback.
    """

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError,
                            ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def run_server(project_dir: str | None, port: int = 8000,
               open_browser_flag: bool = False) -> None:
    state = State(project_dir)
    server = QuietDisconnectServer(("127.0.0.1", port),
                                   make_handler(state))
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
