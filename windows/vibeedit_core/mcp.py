"""Minimal stdio MCP-style JSON-RPC server for the VibeEdit Windows MVP.

This is a real, working subset — not a mock: every tool call goes
through the same Project operations as the CLI and the web UI, and
every edit is saved to the project file. Tool names mirror the
original BashCut MCP tools (``bashcut_<group>_<command>``) with the
``vibeedit_`` prefix; the full original catalog has 249 tools, of
which Phase 1 implements the core timeline/project subset below.
The rest are documented as Phase 2 in VibeEdit/docs/windows-port.md.

Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout.
Supported methods: ``initialize``, ``ping``, ``tools/list``,
``tools/call``. The server is single-project: start it with a project
folder (``python -m vibeedit_core.mcp <folder>`` or via the CLI
``vibeedit mcp``), and ``project open`` switches folders.
"""

from __future__ import annotations

import json
import sys

from .project import (Project, load_project, save_project, find_project_file,
                      PROJECT_FILENAME)

TOOLS = [
    {"name": "vibeedit_project_get",
     "description": "Read the whole open project document."},
    {"name": "vibeedit_project_create",
     "description": "Create a project folder and open it."},
    {"name": "vibeedit_project_open",
     "description": "Open a project.vibeedit.json file or its folder."},
    {"name": "vibeedit_project_save",
     "description": "Save the open project to disk."},
    {"name": "vibeedit_timeline_get",
     "description": "Read the timeline as text (like the original timeline get)."},
    {"name": "vibeedit_timeline_apply",
     "description": "Apply timeline operations: add_clip, add_text, trim, "
                    "split, move, delete, set_speed, set_fade."},
    {"name": "vibeedit_timeline_undo",
     "description": "Undo the last applied edit (one step, from the backup file)."},
    {"name": "vibeedit_media_list",
     "description": "List the project's media entries."},
    {"name": "vibeedit_export_start",
     "description": "Start an FFmpeg export (draft or full). Synchronous in Phase 1."},
    # Phase 2 tools — each calls a real Project operation below.
    {"name": "vibeedit_media_place",
     "description": "Place a media entry as a clip on a track."},
    {"name": "vibeedit_clip_trim",
     "description": "Trim a clip edge to a timeline frame."},
    {"name": "vibeedit_clip_split",
     "description": "Split a clip at a timeline frame."},
    {"name": "vibeedit_clip_move",
     "description": "Move a clip to another track and/or start frame."},
    {"name": "vibeedit_clip_delete",
     "description": "Delete a clip or text item."},
    {"name": "vibeedit_text_add",
     "description": "Add a text item to a text track."},
    {"name": "vibeedit_clip_speed",
     "description": "Set a clip's playback speed."},
    {"name": "vibeedit_transition_set",
     "description": "Set a transition between two consecutive main-track clips."},
    {"name": "vibeedit_transition_remove",
     "description": "Remove a transition by id."},
    {"name": "vibeedit_srt_import",
     "description": "Import SRT text onto a text track."},
    {"name": "vibeedit_srt_export",
     "description": "Export a text track as SRT text."},
    {"name": "vibeedit_export_status",
     "description": "Report the last export started by this server, if any."},
    {"name": "vibeedit_clip_keyframes",
     "description": "Replace a clip's keyframes (or add one keyframe)."},
    {"name": "vibeedit_clip_color",
     "description": "Set a clip's LUT file and/or colour preset."},
]


class MCPServer:
    def __init__(self, folder: str | None = None):
        self.folder = folder
        self.project: Project | None = None
        self.path: str | None = None
        self.last_export: dict | None = None
        if folder:
            self.open(folder)

    def open(self, path: str) -> dict:
        import os
        found = path
        if os.path.isdir(path):
            found = find_project_file(path)
            if not found:
                raise FileNotFoundError(f"No project file in folder: {path}")
        data = load_project(found)
        self.project = Project(data, os.path.dirname(os.path.abspath(found)))
        self.path = found
        return {"path": found, "name": data.get("name"), "rev": data.get("rev")}

    def _require(self) -> Project:
        if self.project is None:
            raise RuntimeError("No project open; call vibeedit_project_open first")
        return self.project

    def _save(self) -> None:
        assert self.project is not None and self.path is not None
        save_project(self.project.data, self.path)

    def call(self, name: str, args: dict) -> dict:
        if name == "vibeedit_project_get":
            proj = self._require()
            return {"project": proj.data}
        if name == "vibeedit_project_open":
            return self.open(args["path"])
        if name == "vibeedit_project_save":
            self._save()
            return {"saved": self.path, "rev": self._require().rev}
        if name == "vibeedit_timeline_get":
            return {"timeline": self._require().timeline_text()}
        if name == "vibeedit_media_list":
            return {"media": self._require().data["media"]}
        if name == "vibeedit_timeline_undo":
            import os
            if self.path is None:
                raise RuntimeError("No project open")
            bak = self.path + ".bak"
            if not os.path.isfile(bak):
                raise RuntimeError("Nothing to undo (no backup file)")
            data = load_project(bak)
            assert self.project is not None
            self.project.restore(data)
            self._save()
            return {"rev": self.project.rev}
        if name == "vibeedit_project_create":
            from .project import new_project
            import os
            folder = os.path.join(args.get("directory", "projects"),
                                  args["name"])
            os.makedirs(os.path.join(folder, "media"), exist_ok=True)
            os.makedirs(os.path.join(folder, "render"), exist_ok=True)
            data = new_project(args["name"])
            path = os.path.join(folder, PROJECT_FILENAME)
            save_project(data, path)
            return self.open(folder)
        if name == "vibeedit_timeline_apply":
            proj = self._require()
            results = []
            for op in args.get("ops", []):
                kind = op["op"]
                if kind == "add_clip":
                    results.append(proj.add_clip(
                        op["media"], op["track"], int(op["at"]),
                        int(op.get("in", 0)),
                        int(op["dur"]) if op.get("dur") is not None else None,
                        float(op.get("speed", 1.0))))
                elif kind == "add_text":
                    results.append(proj.add_text(
                        op["track"], op["text"], int(op["at"]), int(op["dur"])))
                elif kind == "trim":
                    results.append(proj.trim(op["item"], op["edge"],
                                             int(op["toFrame"])))
                elif kind == "split":
                    results.append(proj.split(op["item"], int(op["atFrame"])))
                elif kind == "move":
                    results.append(proj.move(op["item"], op["track"],
                                             int(op["at"])))
                elif kind == "delete":
                    proj.delete(op["item"])
                    results.append({"deleted": op["item"]})
                elif kind == "set_speed":
                    results.append(proj.set_speed(op["item"], float(op["speed"])))
                elif kind == "set_fade":
                    results.append(proj.set_fade(
                        op["item"], op.get("fadeIn"), op.get("fadeOut")))
                elif kind == "set_volume":
                    results.append(proj.set_volume(op["item"],
                                                   float(op["volume"])))
                elif kind == "set_text":
                    results.append(proj.set_text(op["item"], op["text"]))
                elif kind == "set_keyframes":
                    results.append(proj.set_keyframes(op["item"],
                                                      op["keyframes"]))
                elif kind == "set_color":
                    results.append(proj.set_color(op["item"], op.get("lut"),
                                                  op.get("preset")))
                elif kind == "add_transition":
                    results.append(proj.add_transition(
                        op["from"], op["to"], op["kind"],
                        float(op["duration"])))
                elif kind == "remove_transition":
                    proj.remove_transition(op["transition"])
                    results.append({"deleted": op["transition"]})
                else:
                    raise ValueError(f"Unknown operation: {kind}")
            self._save()
            return {"rev": proj.rev, "results": results}
        if name == "vibeedit_export_start":
            from .render import render
            import os
            proj = self._require()
            preset = args.get("preset", "full")
            out = os.path.join(proj.folder, "render",
                               f"export-{preset}.mp4")
            report = render(proj.data, proj.folder, out, preset=preset)
            self.last_export = report
            return report
        if name == "vibeedit_export_status":
            return {"last_export": self.last_export}
        if name == "vibeedit_media_place":
            proj = self._require()
            result = proj.add_clip(args["media"], args["track"],
                                   int(args["at"]), int(args.get("in", 0)),
                                   int(args["dur"]) if args.get("dur") is not None else None,
                                   float(args.get("speed", 1.0)))
            self._save()
            return result
        if name == "vibeedit_clip_trim":
            proj = self._require()
            result = proj.trim(args["item"], args["edge"], int(args["toFrame"]))
            self._save()
            return result
        if name == "vibeedit_clip_split":
            proj = self._require()
            result = proj.split(args["item"], int(args["atFrame"]))
            self._save()
            return result
        if name == "vibeedit_clip_move":
            proj = self._require()
            result = proj.move(args["item"], args["track"], int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_clip_delete":
            proj = self._require()
            proj.delete(args["item"])
            self._save()
            return {"deleted": args["item"]}
        if name == "vibeedit_text_add":
            proj = self._require()
            result = proj.add_text(args["track"], args["text"],
                                   int(args["at"]), int(args["dur"]))
            self._save()
            return result
        if name == "vibeedit_clip_speed":
            proj = self._require()
            result = proj.set_speed(args["item"], float(args["speed"]))
            self._save()
            return result
        if name == "vibeedit_transition_set":
            proj = self._require()
            result = proj.add_transition(args["from"], args["to"],
                                         args["kind"], float(args["duration"]))
            self._save()
            return result
        if name == "vibeedit_transition_remove":
            proj = self._require()
            proj.remove_transition(args["transition"])
            self._save()
            return {"deleted": args["transition"]}
        if name == "vibeedit_srt_import":
            proj = self._require()
            result = proj.import_srt(args.get("track", "t1"), args["srt"])
            self._save()
            return {"imported": len(result)}
        if name == "vibeedit_srt_export":
            proj = self._require()
            return {"srt": proj.export_srt(args.get("track", "t1"))}
        if name == "vibeedit_clip_keyframes":
            proj = self._require()
            if "keyframes" in args:
                result = proj.set_keyframes(args["item"], args["keyframes"])
            else:
                result = proj.add_keyframe(args["item"], float(args["at"]),
                                           args["property"],
                                           float(args["value"]))
            self._save()
            return result
        if name == "vibeedit_clip_color":
            proj = self._require()
            result = proj.set_color(args["item"], args.get("lut"),
                                    args.get("preset"))
            self._save()
            return result
        raise ValueError(f"Unknown tool: {name}")


def handle(server: MCPServer, request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")
    try:
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "vibeedit-mcp", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params", {})
            result = server.call(params["name"], params.get("arguments", {}))
        else:
            raise ValueError(f"Unknown method: {method}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:  # noqa: BLE001 - surfaced to the MCP client
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32603, "message": str(exc)}}


def serve(folder: str | None = None) -> None:
    server = MCPServer(folder)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(handle(server, request)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve(sys.argv[1] if len(sys.argv) > 1 else None)
