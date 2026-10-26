"""CapCut-style web UI server for the VibeEdit Windows MVP.

Layout (mirroring the CapCut desktop layout the user already knows
from ADIT): preview on top, editor/inspector panel below it, and a
multi-track timeline strip at the bottom. Preview plays the latest
export only — it is not a live GPU timeline render (Phase 1 limit,
documented in windows/README.md).

Stdlib only (http.server). Endpoints:
  GET  /api/project            project JSON + timeline text
  POST /api/project            {"op": ...} edit operation (see project.py)
  POST /api/undo  /api/redo     snapshot history (server session)
  POST /api/export             {"preset": "draft"|"full"}
  GET  /api/preview             latest export file, if any
  POST /api/media/upload       multipart file -> project media/
  GET  /  /static/*            the web UI
"""

from __future__ import annotations

import copy
import json
import mimetypes
import os
import shutil
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .project import (Project, load_project, save_project, new_project,
                      find_project_file, PROJECT_FILENAME)
from .render import render, probe_media

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "static")
DEFAULT_PROJECT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "projects", "default")


class State:
    def __init__(self, project_dir: str | None):
        self.lock = threading.Lock()
        self.project_dir = project_dir or DEFAULT_PROJECT_DIR
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.last_export: str | None = None
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
            if parsed.path == "/api/project":
                with state.lock:
                    self._send_json(self._project_view())
            elif parsed.path == "/api/preview":
                if state.last_export and os.path.isfile(state.last_export):
                    self._serve_file(state.last_export)
                else:
                    self._send_json({"error": "No export yet"}, 404)
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
                                        state.project_dir, out, preset=preset)
                        state.last_export = out
                        self._send_json({"ok": True, "report": report})
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


def run_server(project_dir: str | None, port: int = 8000) -> None:
    state = State(project_dir)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))
    print(f"VibeEdit Windows MVP running at http://127.0.0.1:{port}/")
    print(f"Project folder: {state.project_dir}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nVibeEdit stopped.")
