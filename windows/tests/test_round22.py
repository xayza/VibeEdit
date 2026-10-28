"""Round 22: two more honest tools become real, and the honest list
is now fully covered with reasons re-checked against current code.

New tests live ONLY here (round-22 file). Old-test count bumps are
applied separately at the end of the round, after the count settles.

The two conversions are empty lists that are real ONLY because the
server by design cannot have elements, with descriptions stating
exactly that (see the brief's rule):
- agent_terminals: the original returns the dock's terminal choices,
  unavailable plugin terminals and open tabs (ProjectDocument+
  Terminals.swift). This headless server has no agent dock, registers
  no terminal choices and no terminal sessions, and its plugin
  manifests carry no terminal field (plugins._validate_manifest
  validates id/name/hooks/entry/actions/views only), so all three
  lists are always empty. Terminals run externally.
- app_vibeedit_automation_clients: the original lists clients of its
  Unix-socket automation server (UnixSocket.swift). This headless
  server has no Unix-socket automation server and no client registry
  (no socket code in vibeedit_core at all), so the list is always
  empty. HTTP MCP callers are not automation clients.

Guard-tuple trap (caught during this round): the handler chain for
these tools lives inside an `if name in (...)` guard tuple in
MCPServer.call; a handler whose name is missing from that tuple
silently falls through to "Unknown tool" even though the registry
description looks real. The bare-server calls below (and the global
test_no_orphan_tools) pin both names to reachable handlers.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402


def _desc(name):
    return next(t["description"] for t in TOOLS if t["name"] == name)


class TestRound22Terminals(unittest.TestCase):
    def test_returns_original_shape_all_empty(self):
        # No project open: the answer must not depend on project
        # state, because it reports server architecture, not data.
        result = MCPServer().call("vibeedit_agent_terminals", {})
        self.assertEqual(result, {"terminals": [], "unavailable": [],
                                  "tabs": []})

    def test_description_states_why_empty(self):
        desc = _desc("vibeedit_agent_terminals")
        self.assertFalse(desc.startswith("Not available"))
        self.assertIn("always empty", desc)
        self.assertIn("no agent dock", desc)
        self.assertIn("external terminal", desc)


class TestRound22AutomationClients(unittest.TestCase):
    def test_returns_empty_client_list(self):
        result = MCPServer().call(
            "vibeedit_app_vibeedit_automation_clients", {})
        self.assertEqual(result, {"clients": []})

    def test_description_states_no_socket_server(self):
        desc = _desc("vibeedit_app_vibeedit_automation_clients")
        self.assertFalse(desc.startswith("Not available"))
        self.assertIn("Unix-socket", desc)
        self.assertIn("always empty", desc)
        self.assertIn("not automation clients", desc)


class TestRound22StillHonest(unittest.TestCase):
    def test_all_remaining_honest_tools_raise(self):
        # All 52 remaining honest tools, with reasons re-checked
        # against current code (not copied) in this round:
        # - agent_open/open_claude/open_codex/open_shell: actions that
        #   open a tab in a managed terminal; no terminal is managed
        #   here and spawning one would be an out-of-scope side
        #   effect (terminals run externally).
        # - agent_open_chat/agent_ask/chat_*: in-app chat machinery;
        #   product decision (no in-app LLM chat) and no chat session
        #   exists server-side. chat_commands is not a static
        #   catalog to return: its commands cannot run without the
        #   session, so listing them would mislead.
        # - agent_detach/restart_tab: need a dock tab/session that
        #   does not exist here.
        # - agent_setup: privileged install into in-app tabs / Claude
        #   Code / Codex configs; the port never writes external CLI
        #   configs (kit_install covers only the app's own kit).
        # - agent_setup_show: a UIAction (showAgentSetup) that opens a
        #   setup view; no view exists in headless, and its checklist
        #   needs per-CLI kit-install status + starter-bundle
        #   membership, neither tracked.
        # - agent_show_changes/dismiss/undo_changes: show-changes is a
        #   UIAction opening a changes view (not a list tool), and no
        #   AgentChangeRecord exists; the backup file is pre-state
        #   only. timeline_undo is the undo path.
        # - agent_toggle_dock: a UIAction toggling dock visibility;
        #   no dock UI exists in headless (a stored flag nobody reads
        #   would be fake).
        # - agent_tools_install: mutates the external agent's
        #   environment; out of safe scope.
        # - app_update: self-replace of the running app is forbidden;
        #   check/download/prepare handoff are the real parts.
        # - app_vibeedit: no app-level automation client exists in
        #   headless (the app IS the server, not a client of itself).
        # - clip_send_to_agent: no agent session in headless.
        # - image_generate/library_generate: need an image-generation
        #   provider/model that is not wired.
        # - platforms_get: the spec exists but no platform-facts table
        #   exists in either tree; inventing limits would be fake.
        # - playback_*/source_toggle_playback: playback actions need a
        #   playback engine; none exists headless.
        # - plugins_setup: pure .py plugins declare no dependency
        #   recipe to set up.
        # - show_settings: no server-owned settings exist (Settings
        #   modal is project data + read-only info + browser
        #   localStorage); inventing keys would be fake.
        # - timeline_header_compact: a browser UI toggle; a stored
        #   flag nobody reads would be fake.
        # - ui_*: UI actions needing a live UI session; none exists
        #   headless.
        # - view_*: browser view toggles; a stored flag nobody reads
        #   would be fake.
        # - voice_clone_add/list/remove: cloning needs a provider
        #   model that does not exist; the list would be empty ONLY
        #   because cloning is unimplemented, which is exactly the
        #   fake-empty case (unlike terminals/automation clients,
        #   where the absence is architectural, not a missing
        #   feature). acme_voice_fast is a capability string with no
        #   acme provider behind it.
        server = MCPServer()
        for name in (
                "vibeedit_acme_voice_fast",
                "vibeedit_agent_ask",
                "vibeedit_agent_detach",
                "vibeedit_agent_dismiss_changes",
                "vibeedit_agent_open",
                "vibeedit_agent_open_chat",
                "vibeedit_agent_open_claude",
                "vibeedit_agent_open_codex",
                "vibeedit_agent_open_shell",
                "vibeedit_agent_restart_tab",
                "vibeedit_agent_setup",
                "vibeedit_agent_setup_show",
                "vibeedit_agent_show_changes",
                "vibeedit_agent_toggle_dock",
                "vibeedit_agent_tools_install",
                "vibeedit_agent_undo_changes",
                "vibeedit_app_update",
                "vibeedit_app_vibeedit",
                "vibeedit_chat_attach",
                "vibeedit_chat_command",
                "vibeedit_chat_commands",
                "vibeedit_chat_detach",
                "vibeedit_chat_reset",
                "vibeedit_chat_send",
                "vibeedit_chat_status",
                "vibeedit_chat_stop",
                "vibeedit_chat_transcript",
                "vibeedit_clip_send_to_agent",
                "vibeedit_image_generate",
                "vibeedit_library_generate",
                "vibeedit_platforms_get",
                "vibeedit_playback_shuttle_back",
                "vibeedit_playback_shuttle_forward",
                "vibeedit_playback_stop",
                "vibeedit_playback_toggle",
                "vibeedit_plugins_setup",
                "vibeedit_show_settings",
                "vibeedit_source_toggle_playback",
                "vibeedit_timeline_header_compact",
                "vibeedit_ui_action",
                "vibeedit_ui_actions",
                "vibeedit_ui_dialog",
                "vibeedit_ui_respond",
                "vibeedit_ui_view",
                "vibeedit_view_compare",
                "vibeedit_view_fullscreen",
                "vibeedit_view_inspector_pane",
                "vibeedit_view_library_pane",
                "vibeedit_view_safe_area",
                "vibeedit_voice_clone_add",
                "vibeedit_voice_clone_list",
                "vibeedit_voice_clone_remove"):
            with self.assertRaises(ValueError, msg=name):
                server.call(name, {})


class TestRound22RegistryCounts(unittest.TestCase):
    def test_counts(self):
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 479)
        self.assertEqual(len(honest), 52)
        self.assertEqual(len(TOOLS) - len(honest), 427)
        names = {t["name"] for t in TOOLS}
        for now_real in ("vibeedit_agent_terminals",
                         "vibeedit_app_vibeedit_automation_clients"):
            self.assertIn(now_real, names)
            self.assertNotIn(
                now_real, {t["name"] for t in honest}, now_real)


# ---------------------------------------------------------------------------
# Round 22 fix tests (appended after the audit part above). Each class covers
# one item from the Windows real-click test report, the zoompan-fps bug (#0),
# the rev-sync data-loss bug (P0), or the MCP supplements. Where a behaviour
# cannot be proven on a headless VM (browser-only state such as aria-pressed),
# the test asserts the server behaviour plus the exact client code that syncs
# it, and says so in the docstring.
# ---------------------------------------------------------------------------

import copy
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import redirect_stderr
from unittest import mock

from vibeedit_core.export_ops import export_otio, import_otio
from vibeedit_core.mcp import MCPServer, TOOLS, TOOL_SCHEMAS, handle as mcp_handle
from vibeedit_core.project import (PROJECT_FILENAME, Project, load_project,
                                   new_project, save_project)
from vibeedit_core.render import _attach_duration_check, probe_media, render
from vibeedit_core.server import (QuietDisconnectServer, State,
                                  agent_status_for, make_handler,
                                  mcp_client_command)

HERE = os.path.dirname(os.path.abspath(__file__))
WIN = os.path.dirname(HERE)
APP_JS = os.path.join(WIN, "static", "app.js")
INDEX_HTML = os.path.join(WIN, "static", "index.html")
STYLE_CSS = os.path.join(WIN, "static", "style.css")
RENDER_PY = os.path.join(WIN, "vibeedit_core", "render.py")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _ffmpeg_source(path, rate, duration=2.0, color="red"):
    """Synthetic video WITH an audio track (video-only sources hit an
    unrelated audio-concat failure on multi-clip renders, noted in the
    round-22 report as out-of-scope follow-up)."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i",
         f"color=c={color}:s=320x180:r={rate}:d={duration}",
         "-f", "lavfi", "-i", f"sine=frequency=440:d={duration}",
         "-shortest", "-c:v", "libx264", "-c:a", "aac", path],
        check=True)


def _save(proj, tmp):
    save_project(proj.data, os.path.join(tmp, PROJECT_FILENAME))


def _disk(tmp):
    return load_project(os.path.join(tmp, PROJECT_FILENAME))


def _project_with_clip(tmp, rate, keyframes=None, project_fps=None):
    """Temp project dir + one main clip; returns (Project, clip, tmp).
    The media record carries real probe fields (fps as [num, den], frames,
    duration) exactly as a server upload would: Project.add_media alone
    leaves them empty, and the render then falls back to the project fps
    as the source rate, which hides the very fps mismatch under test."""
    src = os.path.join(tmp, "src.mp4")
    _ffmpeg_source(src, rate)
    proj = Project(new_project("r22"), tmp)
    if project_fps is not None:
        proj.data["format"]["fps"] = project_fps
    media = proj.add_media(src, "video")
    num, den = (int(x) for x in rate.split("/")) if "/" in rate \
        else (int(rate), 1)
    media["fps"] = [num, den]
    media["frames"] = int(round(2.0 * num / den))
    media["duration"] = 2.0
    clip = proj.add_clip(media["id"], "v1", 0, 0, 60, 1.0)
    if keyframes:
        proj.set_keyframes(clip["id"], keyframes)
    return proj, clip


class TestRound22RevSync(unittest.TestCase):
    """P0 data loss: web RAM copy overwrote an external MCP agent's edit
    (disk rev 107, 35 markers -> rev 107, 34 markers). After the fix both
    writers refresh from disk when it is newer, so the interleaved case
    keeps both edits and revs stay monotonic."""

    def _setup(self, tmp):
        proj = Project(new_project("sync"), tmp)
        proj.add_media(os.path.join(tmp, "x.mp4"), "video")
        _save(proj, tmp)
        return proj

    def test_reported_scenario_mcp_then_web(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._setup(tmp)
            state = State(tmp)
            mcp = MCPServer(tmp)
            clip = proj.add_clip(proj.data["media"][0]["id"], "v1", 0, 0, 30, 1.0)
            _save(proj, tmp)
            mcp.call("vibeedit_markers_add",
                     {"text": "agent mark", "at": 10})
            rev_after_mcp = _disk(tmp)["rev"]
            # Web edits AFTER the agent edit: refresh must reload first.
            state.apply({"op": "set_speed", "item": clip["id"],
                         "speed": 1.5})
            on_disk = _disk(tmp)
            markers = on_disk.get("markers", [])
            self.assertEqual(len(markers), 1)
            self.assertEqual(markers[0]["text"], "agent mark")
            item = next(i for t in on_disk["tracks"]
                        for i in t["items"] if i["id"] == clip["id"])
            self.assertEqual(item["speed"], 1.5)
            self.assertGreater(on_disk["rev"], rev_after_mcp)

    def test_reverse_direction_web_then_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._setup(tmp)
            state = State(tmp)
            mcp = MCPServer(tmp)
            clip = proj.add_clip(proj.data["media"][0]["id"], "v1", 0, 0, 30, 1.0)
            _save(proj, tmp)
            state.apply({"op": "set_speed", "item": clip["id"],
                         "speed": 2.0})
            mcp.call("vibeedit_markers_add", {"text": "m2", "at": 5})
            on_disk = _disk(tmp)
            self.assertEqual(len(on_disk.get("markers", [])), 1)
            item = next(i for t in on_disk["tracks"]
                        for i in t["items"] if i["id"] == clip["id"])
            self.assertEqual(item["speed"], 2.0)

    def test_no_refresh_when_disk_not_newer_keeps_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._setup(tmp)
            state = State(tmp)
            clip = proj.add_clip(proj.data["media"][0]["id"], "v1", 0, 0, 30, 1.0)
            _save(proj, tmp)
            state.apply({"op": "set_speed", "item": clip["id"],
                         "speed": 1.25})
            self.assertEqual(len(state.undo_stack), 1)
            # A plain read-only apply must not clear the stack.
            state.apply({"op": "magnetic_get"})
            self.assertEqual(len(state.undo_stack), 1)

    def test_refresh_clears_stale_undo_then_restores_merged_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._setup(tmp)
            state = State(tmp)
            mcp = MCPServer(tmp)
            clip = proj.add_clip(proj.data["media"][0]["id"], "v1", 0, 0, 30, 1.0)
            _save(proj, tmp)
            state.apply({"op": "set_speed", "item": clip["id"],
                         "speed": 1.25})
            mcp.call("vibeedit_markers_add", {"text": "ext", "at": 3})
            state.apply({"op": "set_speed", "item": clip["id"],
                         "speed": 1.5})
            # Stale pre-agent snapshot was cleared, so only one undo
            # entry exists and undoing restores the merged state.
            self.assertEqual(len(state.undo_stack), 1)
            # Same restore step the /api/undo route performs.
            state.project.restore(state.undo_stack.pop())
            self.assertEqual(len(state.project.data.get("markers", [])), 1)
            item = next(i for t in state.project.data["tracks"]
                        for i in t["items"] if i["id"] == clip["id"])
            self.assertEqual(item["speed"], 1.25)

    def test_refresh_failure_keeps_ram(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._setup(tmp)
            state = State(tmp)
            media = state.project.add_media(os.path.join(tmp, "x.mp4"),
                                            "video")
            clip = state.project.add_clip(media["id"], "v1", 0, 0, 30, 1.0)
            save_project(state.project.data, state.path)
            # Delete the file on disk: refresh must fail silently and
            # the edit must still succeed (file recreated on save).
            os.remove(os.path.join(tmp, PROJECT_FILENAME))
            state.apply({"op": "set_speed", "item": clip["id"],
                         "speed": 1.75})
            self.assertTrue(os.path.exists(
                os.path.join(tmp, PROJECT_FILENAME)))
            item = next(i for t in state.project.data["tracks"]
                        for i in t["items"] if i["id"] == clip["id"])
            self.assertEqual(item["speed"], 1.75)


class TestRound22ZoompanFps(unittest.TestCase):
    """Bug #0: a 59.94fps source with a scale keyframe doubled in length
    because zoompan re-timed frames at its own fps and ignored setpts.
    Evidence split, stated exactly:
    - The filter-order tests ARE the fail-before proof (old code returned
      zoompan with no preceding fps filter; new code starts with it).
    - The isolated filter experiment (120-frame 59.94fps input through
      trim+setpts+scale+crop+zoompan fps=29.97: 120 frames/4.004s without
      a preceding fps filter, 60 frames/2.002s with one) proves the
      mechanism at the filter level.
    - The full-render duration tests are NON-REGRESSION guards, not
      fail-before proofs: on small projects -shortest truncates the
      doubled video at the audio end, so old code passes them too
      (verified: old code gives 2.035s single-clip and 3.503s
      multi-clip+dissolve, both correct). Why -shortest did not
      truncate the user's 330s file is still open (see round-22 report:
      single render path, single -shortest site, so the user's exact
      export preset/command is needed to close it). The duration-check
      safety net is what would have caught that file."""

    def test_motion_filter_starts_with_fps_before_zoompan(self):
        src = _read(RENDER_PY)
        span = src[src.index("def _motion_filter"):src.index("def _tilt_filter")]
        ret = span[span.index("return (f\"fps="):]
        self.assertTrue(ret.startswith("return (f\"fps={fps_str},\""))
        self.assertIn("zoompan=", ret)
        # No trailing fps FILTER after zoompan (zoompan's own :fps=
        # parameter is fine; a separate ,fps= filter is the Phase-3 bug).
        self.assertNotIn("fps={fps_str}\",", ret.split("zoompan=")[1])

    def test_overlay_still_image_fps_before_zoompan(self):
        src = _read(RENDER_PY)
        zoom = src.index("zoompan=z='{_piecewise_expr(s_pts, 'on')}'")
        fps_before = src.rindex("ofilters.append(f\"fps={fps_str}\")", 0, zoom)
        self.assertLess(zoom - fps_before, 600)

    def test_full_render_5994_keyframed_matches_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _project_with_clip(
                tmp, "60000/1001", keyframes=[{"at": 0, "scale": 1.0},
                                              {"at": 59, "scale": 1.2}],
                project_fps=[30000, 1001])
            timeline = proj.duration_seconds()
            out = os.path.join(tmp, "out.mp4")
            rep = render(proj.data, tmp, out, preset="draft")
            file_s = float(probe_media(out).get("duration") or 0.0)
            self.assertAlmostEqual(file_s, timeline, delta=0.6)
            self.assertAlmostEqual(rep["duration"], timeline, delta=0.6)

    def test_full_render_30fps_keyframed_not_regressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _project_with_clip(
                tmp, "30", keyframes=[{"at": 0, "scale": 1.0},
                                      {"at": 59, "scale": 1.2}])
            timeline = proj.duration_seconds()
            out = os.path.join(tmp, "out.mp4")
            render(proj.data, tmp, out, preset="draft")
            file_s = float(probe_media(out).get("duration") or 0.0)
            self.assertAlmostEqual(file_s, timeline, delta=0.6)

    def test_duration_check_warns_on_breach_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "s.mp4")
            _ffmpeg_source(src, "30", duration=2.0)
            rep = {"duration": 2.0}
            _attach_duration_check(rep, src)
            self.assertIsNone(rep["duration_check"]["warning"])
            rep2 = {"duration": 10.0}
            _attach_duration_check(rep2, src)
            self.assertIn("differs", rep2["duration_check"]["warning"])
            self.assertGreater(abs(rep2["duration_check"]["diff_s"]), 1.0)
            rep3 = {"duration": 2.0}
            _attach_duration_check(rep3, os.path.join(tmp, "nope.mp4"))
            self.assertIsNone(rep3["duration_check"]["warning"])
            self.assertIn("error", rep3["duration_check"])


class TestRound22BackgroundExport(unittest.TestCase):
    """Bug #1: export ran synchronously under state.lock, so every other
    request queued behind a minutes-long render. The fake render stands
    in for a slow FFmpeg run to make the timing deterministic; what is
    under test is the lock-freedom, not FFmpeg speed."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = State(cls.tmp.name)
        cls.server = QuietDisconnectServer(("127.0.0.1", 0),
                                           make_handler(cls.state))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def _post(self, path, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    def _get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=10) as resp:
            return json.loads(resp.read())

    def test_get_project_fast_during_background_render(self):
        def slow_render(data, folder, out, preset=None, normalize_audio=False,
                        export_preset=None):
            time.sleep(2.5)
            return {"output": out, "duration": 1.0,
                    "width": 320, "height": 180}
        with mock.patch("vibeedit_core.server.render", slow_render):
            t0 = time.monotonic()
            started = self._post("/api/export", {"preset": "draft"})
            self.assertTrue(started["ok"])
            self.assertEqual(started["job"]["status"], "running")
            self.assertLess(time.monotonic() - t0, 2.0)
            t1 = time.monotonic()
            view = self._get("/api/project")
            elapsed = time.monotonic() - t1
            self.assertLess(elapsed, 2.0)
            self.assertIn("project", view)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                job = self._get("/api/export/status?job="
                                + started["job"]["id"])
                if job["job"]["status"] == "done":
                    break
                time.sleep(0.2)
            self.assertEqual(job["job"]["status"], "done")
            view = self._get("/api/project")
            self.assertTrue(view.get("last_export"))

    def test_cancel_never_publishes(self):
        done = threading.Event()

        def slow_render(data, folder, out, preset=None, normalize_audio=False,
                        export_preset=None):
            time.sleep(2.0)
            done.set()
            return {"output": out, "duration": 1.0,
                    "width": 320, "height": 180}
        with mock.patch("vibeedit_core.server.render", slow_render):
            out = os.path.join(self.tmp.name, "render", "cancelled.mp4")
            job = self.state.start_export_job(
                copy.deepcopy(self.state.project.data), self.tmp.name, out,
                preset="draft", normalize=False, export_preset=None)
            cancelled = self.state.cancel_export_job(job["id"])
            self.assertEqual(cancelled["status"], "cancelled")
            self.assertTrue(done.wait(timeout=10))
            self.assertIsNone(self.state.last_export)
            self.assertEqual(self.state.export_job(job["id"])["status"],
                             "cancelled")


class TestRound22MagneticUndoStatus(unittest.TestCase):
    """Bug #2 (Magnetic), bug #3 (double undo after Delete), bug #4
    (stale status). aria-pressed itself is browser state; the tests prove
    the server side plus the exact client sync code."""

    def test_magnetic_toggle_both_directions(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            self.assertTrue(state.project.magnetic_enabled)
            state.apply({"op": "magnetic_set", "enabled": False})
            self.assertFalse(state.project.magnetic_enabled)
            state.apply({"op": "magnetic_set", "enabled": True})
            self.assertTrue(state.project.magnetic_enabled)

    def test_magnetic_get_pushes_no_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            media = state.project.add_media(os.path.join(tmp, "x.mp4"),
                                            "video")
            clip = state.project.add_clip(media["id"], "v1", 0, 0, 30, 1.0)
            save_project(state.project.data, state.path)
            state.apply({"op": "delete", "item": clip["id"]})
            self.assertEqual(len(state.undo_stack), 1)
            state.apply({"op": "magnetic_get"})
            self.assertEqual(len(state.undo_stack), 1)
            # Same restore step the /api/undo route performs.
            state.project.restore(state.undo_stack.pop())
            ids = [i["id"] for t in state.project.data["tracks"]
                   for i in t["items"]]
            self.assertIn(clip["id"], ids)

    def test_load_syncs_magnetic_from_project_view(self):
        js = _read(APP_JS)
        # Single source of truth: load() reads data.magnetic (the server
        # view), and no live magnetic_get fetch remains in the load path.
        self.assertIn("data.magnetic !== undefined", js)
        self.assertIn("setAttribute(\"aria-pressed\"", js)
        live_fetches = [line for line in js.splitlines()
                        if "magnetic_get" in line
                        and not line.strip().startswith("//")]
        self.assertEqual(live_fetches, [])

    def test_status_overwritten_by_vision_knowledge_tab(self):
        js = _read(APP_JS)
        self.assertIn("Vision xong (", js)
        self.assertIn("— kết quả ở panel Vision.", js)
        self.assertIn("Xong — kết quả ở panel Knowledge.", js)
        self.assertIn("setStatus(\"Panel: \"", js)


class TestRound22Otio(unittest.TestCase):
    """Bug #5: export wrote project-relative media paths while the .otio
    file lives in render/, so import resolved nothing and stored broken
    records (reported as Missing: media/mp4)."""

    def test_roundtrip_resolves_real_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_proj = os.path.join(tmp, "src")
            os.makedirs(os.path.join(src_proj, "media"))
            src_file = os.path.join(src_proj, "media", "clip.mp4")
            _ffmpeg_source(src_file, "30")
            proj = Project(new_project("otio"), src_proj)
            media = proj.add_media(src_file, "video")
            proj.add_clip(media["id"], "v1", 0, 0, 60, 1.0)
            otio_path = os.path.join(src_proj, "render", "out.otio")
            os.makedirs(os.path.join(src_proj, "render"))
            export_otio(proj.data, src_proj, otio_path)
            dest = os.path.join(tmp, "dest")
            rep = import_otio(otio_path, dest)
            self.assertEqual(rep["missing"], [])
            data = load_project(os.path.join(dest, PROJECT_FILENAME))
            media_paths = [m["path"] for m in data["media"]]
            self.assertEqual(len(media_paths), 1)
            resolved = media_paths[0]
            if not os.path.isabs(resolved):
                resolved = os.path.join(dest, resolved)
            self.assertTrue(os.path.isfile(resolved))

    def test_missing_file_listed_verbatim_not_broken_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            src_proj = os.path.join(tmp, "src")
            os.makedirs(os.path.join(src_proj, "render"))
            proj = Project(new_project("otio"), src_proj)
            media = proj.add_media("media/gone.mp4", "video")
            proj.add_clip(media["id"], "v1", 0, 0, 60, 1.0)
            otio_path = os.path.join(src_proj, "render", "out.otio")
            export_otio(proj.data, src_proj, otio_path)
            dest = os.path.join(tmp, "dest")
            rep = import_otio(otio_path, dest)
            self.assertIn("media/gone.mp4", rep["missing"])
            data = load_project(os.path.join(dest, PROJECT_FILENAME))
            self.assertEqual(data["media"][0]["path"],
                             "media/gone.mp4")


class TestRound22TabClose(unittest.TestCase):
    """Bug #6: round 19 swallowed ConnectionResetError/BrokenPipeError but
    Windows tab-close raises sibling ConnectionAbortedError, so the
    traceback survived. Genuine errors must still print."""

    def _handle_error(self, exc):
        server = QuietDisconnectServer.__new__(QuietDisconnectServer)
        buf = io.StringIO()
        try:
            raise exc
        except type(exc):
            with redirect_stderr(buf):
                server.handle_error(None, None)
        return buf.getvalue()

    def test_disconnect_errors_silent(self):
        for exc in (ConnectionResetError("reset"),
                    BrokenPipeError("pipe"),
                    ConnectionAbortedError("aborted")):
            self.assertEqual(self._handle_error(exc), "")

    def test_other_errors_still_print(self):
        out = self._handle_error(ValueError("real bug"))
        self.assertIn("ValueError", out)


class TestRound22Notifications(unittest.TestCase):
    """MCP supplement (a): notifications must get NO response; only
    unknown methods WITH an id get an error."""

    def test_notification_gets_no_response(self):
        for req in ({"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "method": "notifications/cancelled",
                     "params": {}}):
            self.assertIsNone(mcp_handle(MCPServer(None), req))

    def test_unknown_method_with_id_gets_error(self):
        resp = mcp_handle(MCPServer(None),
                          {"jsonrpc": "2.0", "id": 7,
                           "method": "nope/unknown"})
        self.assertEqual(resp["error"]["code"], -32603)
        self.assertEqual(resp["id"], 7)

    def test_normal_call_unaffected(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(new_project("n"), tmp)
            _save(proj, tmp)
            resp = mcp_handle(MCPServer(tmp),
                              {"jsonrpc": "2.0", "id": 3,
                               "method": "tools/call",
                               "params": {"name": "vibeedit_markers_list",
                                          "arguments": {}}})
            self.assertEqual(resp["result"]["markers"], [])


class TestRound22InputSchema(unittest.TestCase):
    """MCP supplement (b): every tool carries an inputSchema derived from
    its handler code. Honest deviation, stated plainly: 209 tools have
    EMPTY properties because their handlers genuinely read no arguments
    (157 zero-arg real tools + 52 honest tools that raise before reading
    anything). Inventing a property for them would break the no-invention
    rule, which outranks the brief's shorthand 'every tool non-empty'."""

    def test_every_tool_has_schema_shape(self):
        self.assertEqual(len(TOOLS), 479)
        for tool in TOOLS:
            schema = tool.get("inputSchema")
            self.assertIsInstance(schema, dict, tool["name"])
            self.assertEqual(schema.get("type"), "object", tool["name"])
            self.assertIsInstance(schema.get("properties"), dict,
                                  tool["name"])
            self.assertIsInstance(schema.get("required"), list,
                                  tool["name"])
            self.assertTrue(set(schema["required"]) <=
                            set(schema["properties"]), tool["name"])

    def test_nonempty_and_empty_counts(self):
        nonempty = [t for t in TOOLS if t["inputSchema"]["properties"]]
        empty = [t for t in TOOLS if not t["inputSchema"]["properties"]]
        self.assertEqual(len(nonempty), 270)
        self.assertEqual(len(empty), 209)

    def test_markers_add_schema_exact(self):
        schema = next(t for t in TOOLS
                      if t["name"] == "vibeedit_markers_add")["inputSchema"]
        self.assertEqual(set(schema["properties"]), {"text", "at"})
        self.assertEqual(set(schema["required"]), {"text", "at"})
        self.assertEqual(schema["properties"]["text"]["type"], "string")
        self.assertEqual(schema["properties"]["at"]["type"], "integer")

    def test_alias_inherits_origin_schema(self):
        by_name = {t["name"]: t for t in TOOLS}
        self.assertEqual(by_name["vibeedit_agent_quick_edit"]["inputSchema"],
                         by_name["vibeedit_timeline_apply"]["inputSchema"])
        self.assertEqual(set(by_name["vibeedit_agent_quick_edit"]
                             ["inputSchema"]["properties"]), {"ops"})

    def test_spot_schemas(self):
        by_name = {t["name"]: t for t in TOOLS}
        self.assertEqual(by_name["vibeedit_project_get"]
                         ["inputSchema"]["properties"], {})
        self.assertIn("kind", by_name["vibeedit_clip_backdrop"]
                      ["inputSchema"]["required"])
        self.assertEqual(by_name["vibeedit_clip_backdrop"]
                         ["inputSchema"]["properties"]["blur"]["type"],
                         "number")
        self.assertEqual(by_name["vibeedit_ui_frames"]
                         ["inputSchema"]["properties"]["times"]["type"],
                         "array")

    def test_schema_driven_calls_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(new_project("s"), tmp)
            _save(proj, tmp)
            mcp = MCPServer(tmp)
            mcp.call("vibeedit_markers_add", {"text": "hi", "at": 1})
            listed = mcp.call("vibeedit_markers_list", {})
            markers = listed["markers"]
            self.assertEqual(len(markers), 1)
            self.assertEqual(markers[0]["text"], "hi")
            self.assertIsInstance(
                mcp.call("vibeedit_timeline_apply", {"ops": []}), dict)
            self.assertIn("project", mcp.call("vibeedit_project_get", {}))

    def test_required_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            _save(Project(new_project("s"), tmp), tmp)
            mcp = MCPServer(tmp)
            with self.assertRaises((KeyError, ValueError, TypeError)):
                mcp.call("vibeedit_markers_add", {})
            with self.assertRaises((KeyError, ValueError, TypeError)):
                mcp.call("vibeedit_markers_add", {"text": "only"})

    def test_honest_tools_have_empty_schema(self):
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(honest), 52)
        for tool in honest:
            self.assertEqual(tool["inputSchema"]["properties"], {},
                             tool["name"])


class TestRound22CopyCommand(unittest.TestCase):
    """MCP supplement (c): the Agent dock copy button must copy the REAL
    command (absolute .venv python + script + project folder), never the
    'python windows\\vibeedit.py mcp <project-folder>' template."""

    def test_command_uses_absolute_paths_no_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(new_project("c"), tmp)
            _save(proj, tmp)
            cmd = mcp_client_command(tmp)
            self.assertTrue(os.path.isabs(cmd["command"]))
            self.assertTrue(os.path.isabs(cmd["args"][0]))
            self.assertTrue(cmd["args"][0].endswith("vibeedit.py"))
            self.assertEqual(cmd["args"][1], "mcp")
            self.assertEqual(cmd["args"][2], os.path.abspath(tmp))
            self.assertNotIn("<project-folder>", cmd["command_line"])
            self.assertIn("vibeedit.py", cmd["command_line"])

    def test_agent_status_carries_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            _save(Project(new_project("c"), tmp), tmp)
            status = agent_status_for(tmp)
            self.assertIn("mcp_command", status)
            self.assertIn("mcp_client", status)
            self.assertNotIn("<project-folder>", status["mcp_command"] or "")

    def test_client_fills_command_from_status(self):
        js = _read(APP_JS)
        self.assertIn("d.mcp_command", js)
        self.assertIn("agentMcpCommand", js)
        self.assertIn("agentDockCommand", js)

    def test_gitignore_covers_runtime_dirs(self):
        content = _read(os.path.join(WIN, ".gitignore"))
        for entry in (".venv/", "__pycache__/", "projects/", "*.pyc"):
            self.assertIn(entry, content)


class TestRound22ExportBarWelcomeBatchOverlap(unittest.TestCase):
    """UI finish items: export job bar + cancel, welcome path open,
    batch empty-folder note, overlap flash on the conflicting clip."""

    def test_export_job_bar_markup_and_css(self):
        html = _read(INDEX_HTML)
        css = _read(STYLE_CSS)
        self.assertIn('id="exportJobBar"', html)
        self.assertIn('id="exportProgressText"', html)
        self.assertIn('id="btnExportCancel"', html)
        self.assertIn(".export-job-bar", css)
        self.assertIn("#exportJobBar[hidden]", css)
        js = _read(APP_JS)
        self.assertIn("/api/export/cancel", js)

    def test_welcome_path_open(self):
        html = _read(INDEX_HTML)
        js = _read(APP_JS)
        self.assertIn('id="welcomePath"', html)
        self.assertIn('id="btnWelcomeOpenPath"', html)
        self.assertIn("welcomePath", js)
        self.assertIn("/api/project/open", js)

    def test_batch_empty_note_and_overlap_flash(self):
        js = _read(APP_JS)
        self.assertIn("Chưa nhập thư mục phụ — sẽ chỉ xuất project hiện tại.",
                      js)
        self.assertIn("dataset.item", js)
        self.assertIn("overlaps (\\S+) on track", js)
        self.assertIn(".clip-flash", _read(STYLE_CSS))

    def test_project_picker_opens_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            other = os.path.join(tmp, "second")
            os.makedirs(other, exist_ok=True)
            proj = Project(new_project("second"), other)
            save_project(proj.data, os.path.join(other, PROJECT_FILENAME))
            state.open_project(os.path.abspath(other))
            self.assertEqual(state.project_dir, os.path.abspath(other))
            self.assertEqual(state.project.data["name"], "second")


if __name__ == "__main__":
    unittest.main()

