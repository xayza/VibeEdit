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
]


class MCPServer:
    def __init__(self, folder: str | None = None):
        self.folder = folder
        self.project: Project | None = None
        self.path: str | None = None
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
            return report
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
