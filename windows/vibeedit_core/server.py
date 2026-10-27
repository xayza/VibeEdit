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
                      find_project_file, PROJECT_FILENAME)
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

    def save(self) -> None:
        save_project(self.project.data, self.path)

    def apply(self, op: dict) -> dict:
        proj = self.project
        if op.get("op") == "srt_export":
            return {"srt": proj.export_srt(op.get("track", "t1"))}
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
                                        op.get("preset_strength"))
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
    """Minimal multipart/form-data parser (stdlib only)."""
    parts: dict[str, tuple[str, bytes]] = {}
    for chunk in body.split(b"--" + boundary):
        if b"Content-Disposition" not in chunk:
            continue
        head, _, payload = chunk.partition(b"\r\n\r\n")
        payload = payload.rsplit(b"\r\n", 1)[0]
        name = None
        filename = None
        for piece in head.decode(errors="replace").split(";"):
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
            elif parsed.path.startswith("/api/media/"):
                self._serve_media(parsed.path[len("/api/media/"):])
            elif parsed.path == "/api/project":
                with state.lock:
                    self._send_json(self._project_view())
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
                    elif parsed.path == "/api/export":
                        body = self._read_json()
                        preset = body.get("preset", "full")
                        out = os.path.join(state.project_dir, "render",
                                           f"export-{preset}.mp4")
                        report = render(state.project.data,
                                        state.project_dir, out, preset=preset,
                                        normalize_audio=bool(body.get("normalize", False)))
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
                        safe = os.path.basename(filename) or "upload.bin"
                        dest = os.path.join(state.project_dir, "media", safe)
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
