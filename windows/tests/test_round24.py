"""Round 24 tests: honest-tool audit conversions + leftover hardening.

(A) Audit conversions: three tools leave the honest set because their
collections are empty BY DESIGN in this headless build (same precedent
as agent_terminals / app_vibeedit_automation_clients in round 22):
voice_clone_list (no cloning provider can ever exist here),
ui_dialog (the headless server has no window, so never an open
dialog), chat_status (port plugin manifests carry hooks, not an
agent.chat capability; registry plugins are macOS-only, never
executed). Every other honest tool stays honest, with the reason
recorded in the test (see STILL_HONEST_REASONS); the full honest set
is pinned by exact name so a future round cannot silently re-label a
tool without updating this list.

(B) Hardening:
1. hasAudio: an unprobed (or stale-True) media record for a streamless
   file used to fail the WHOLE export with FFmpeg "Stream specifier
   ':a' matches no streams". render now probes the actual file and
   falls back to anullsrc (main/overlay) or skips the item
   (extra-audio loop) when the file truly has no audio stream.
2. Cancel export: cancel_export_job now SIGKILLs the running FFmpeg
   process (round 22 only flipped the status); the worker removes
   the partial output and never publishes.
3. Import-merge DOM audit: the tester counted 3 import controls, but
   only ONE is visible — the file input and the submit button carry
   the visually-hidden class (1px, clipped) and exist only so the
   dropzone can open the picker programmatically. This test pins
   that fact instead of changing working UI (see PARITY.md round 24).
4. Required-arg errors: missing required args now raise ValueError
   naming the missing keys, not a bare KeyError ("'at'").
"""

import copy
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import MCPServer, TOOLS, TOOL_SCHEMAS, handle  # noqa: E402
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import (RenderCancel, RenderCancelled,  # noqa: E402
                                  probe_media, render)
from vibeedit_core.server import State  # noqa: E402


def _desc(name):
    return next(t["description"] for t in TOOLS if t["name"] == name)


def _honest_names():
    return sorted(t["name"] for t in TOOLS
                  if t["description"].startswith("Not available"))


# The complete honest set after round 24 (49 names). Each entry's
# reason for staying honest is in STILL_HONEST_REASONS below.
STILL_HONEST = [
    'vibeedit_acme_voice_fast',
    'vibeedit_agent_ask',
    'vibeedit_agent_detach',
    'vibeedit_agent_dismiss_changes',
    'vibeedit_agent_open',
    'vibeedit_agent_open_chat',
    'vibeedit_agent_open_claude',
    'vibeedit_agent_open_codex',
    'vibeedit_agent_open_shell',
    'vibeedit_agent_restart_tab',
    'vibeedit_agent_setup',
    'vibeedit_agent_setup_show',
    'vibeedit_agent_show_changes',
    'vibeedit_agent_toggle_dock',
    'vibeedit_agent_tools_install',
    'vibeedit_agent_undo_changes',
    'vibeedit_app_update',
    'vibeedit_app_vibeedit',
    'vibeedit_chat_attach',
    'vibeedit_chat_command',
    'vibeedit_chat_commands',
    'vibeedit_chat_detach',
    'vibeedit_chat_reset',
    'vibeedit_chat_send',
    'vibeedit_chat_stop',
    'vibeedit_chat_transcript',
    'vibeedit_clip_send_to_agent',
    'vibeedit_image_generate',
    'vibeedit_library_generate',
    'vibeedit_platforms_get',
    'vibeedit_playback_shuttle_back',
    'vibeedit_playback_shuttle_forward',
    'vibeedit_playback_stop',
    'vibeedit_playback_toggle',
    'vibeedit_plugins_setup',
    'vibeedit_show_settings',
    'vibeedit_source_toggle_playback',
    'vibeedit_timeline_header_compact',
    'vibeedit_ui_action',
    'vibeedit_ui_actions',
    'vibeedit_ui_respond',
    'vibeedit_ui_view',
    'vibeedit_view_compare',
    'vibeedit_view_fullscreen',
    'vibeedit_view_inspector_pane',
    'vibeedit_view_library_pane',
    'vibeedit_view_safe_area',
    'vibeedit_voice_clone_add',
    'vibeedit_voice_clone_remove',
]

# Why each remaining honest tool cannot become real with stdlib +
# FFmpeg + Pillow alone (grouped; every STILL_HONEST name appears).
STILL_HONEST_REASONS = {
    # No session/tab/dock exists in the headless server; these need a
    # live terminal tab or dock UI to act on.
    "session": ['vibeedit_agent_open', 'vibeedit_agent_open_chat',
                'vibeedit_agent_open_claude', 'vibeedit_agent_open_codex',
                'vibeedit_agent_open_shell', 'vibeedit_agent_restart_tab',
                'vibeedit_agent_toggle_dock', 'vibeedit_agent_detach',
                'vibeedit_clip_send_to_agent'],
    # In-app AI chat is a product decision AGAINST (user 2026-10-27:
    # the Agent dock is a connection point for an external agent);
    # chat agents additionally need a runnable agent.chat plugin,
    # which cannot exist here (see chat_status conversion).
    "chat": ['vibeedit_agent_ask', 'vibeedit_chat_send',
             'vibeedit_chat_command', 'vibeedit_chat_commands',
             'vibeedit_chat_attach', 'vibeedit_chat_detach',
             'vibeedit_chat_reset', 'vibeedit_chat_transcript',
             'vibeedit_chat_stop'],
    # Mutating the user's external agent environment (installing into
    # Claude/Codex configs, writing CLI setup) is unsafe by the
    # round-21 precedent; per-CLI setup state is not tracked.
    "external": ['vibeedit_agent_setup', 'vibeedit_agent_setup_show',
                 'vibeedit_agent_tools_install'],
    # No AgentChangeRecord exists; agent edits happen but are not
    # recorded as change objects, so a [] would falsely imply "no
    # changes made". Diff-vs-backup would be a different feature.
    "changes": ['vibeedit_agent_show_changes',
                'vibeedit_agent_dismiss_changes',
                'vibeedit_agent_undo_changes'],
    # No playback engine exists in the headless server (ui_frame
    # renders still frames; it is not playback).
    "playback": ['vibeedit_playback_toggle', 'vibeedit_playback_stop',
                 'vibeedit_playback_shuttle_forward',
                 'vibeedit_playback_shuttle_back',
                 'vibeedit_source_toggle_playback'],
    # Browser-only view state; a server-stored flag nobody reads
    # would be fake (round-20 rule).
    "browser": ['vibeedit_ui_action', 'vibeedit_ui_view',
                'vibeedit_ui_respond', 'vibeedit_ui_actions',
                'vibeedit_view_fullscreen', 'vibeedit_view_inspector_pane',
                'vibeedit_view_library_pane', 'vibeedit_view_compare',
                'vibeedit_view_safe_area',
                'vibeedit_timeline_header_compact'],
    # Needs an external provider/model that does not exist here.
    "provider": ['vibeedit_voice_clone_add', 'vibeedit_voice_clone_remove',
                 'vibeedit_image_generate', 'vibeedit_library_generate',
                 'vibeedit_acme_voice_fast', 'vibeedit_app_update',
                 'vibeedit_plugins_setup'],
    # Inventing the data would violate the no-fabrication rule: no
    # platform-facts table exists (platforms_get), no server-owned
    # settings store exists (show_settings), no app-level automation
    # client exists (app_vibeedit).
    "invented": ['vibeedit_platforms_get', 'vibeedit_show_settings',
                 'vibeedit_app_vibeedit'],
}


class TestRound24Audit(unittest.TestCase):
    def test_counts_481_432_49(self):
        real = [t for t in TOOLS
                if not t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(real), 432)
        self.assertEqual(len(_honest_names()), 49)

    def test_honest_set_exact_and_reasons_cover_it(self):
        self.assertEqual(_honest_names(), sorted(STILL_HONEST))
        covered = [n for group in STILL_HONEST_REASONS.values()
                   for n in group]
        self.assertEqual(sorted(covered), sorted(STILL_HONEST))

    def test_converted_tools_return_empty_by_design(self):
        # Bare server, no project: the answers report server
        # architecture, not project data (round-22 guard-tuple trap:
        # these names must be in the call() guard tuple or they fall
        # through to "Unknown tool").
        server = MCPServer()
        self.assertEqual(
            server.call("vibeedit_voice_clone_list", {}), {"clones": []})
        self.assertEqual(
            server.call("vibeedit_ui_dialog", {}), {"dialogs": []})
        self.assertEqual(
            server.call("vibeedit_chat_status", {}), {"agents": []})
        for name in ("vibeedit_voice_clone_list", "vibeedit_ui_dialog",
                     "vibeedit_chat_status"):
            desc = _desc(name)
            self.assertFalse(desc.startswith("Not available"))
            self.assertIn("always empty", desc)

    def test_remaining_honest_still_raise_not_available(self):
        server = MCPServer()
        for name in STILL_HONEST:
            with self.assertRaises(ValueError) as caught:
                server.call(name, {})
            self.assertIn("NOT_AVAILABLE", str(caught.exception))


def _ffmpeg(*args, check=True):
    return subprocess.run(["ffmpeg", "-y", "-v", "error", *args],
                          capture_output=True, check=check)


def _mean_volume(path):
    proc = subprocess.run(["ffmpeg", "-v", "info", "-i", path,
                           "-af", "volumedetect", "-f", "null", "-"],
                          capture_output=True, text=True)
    for line in proc.stderr.splitlines():
        if "mean_volume" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0])
    return None


def _video(tmp, name, with_audio):
    if with_audio:
        _ffmpeg("-f", "lavfi", "-i",
                "testsrc=duration=2:size=320x180:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", os.path.join(tmp, name))
    else:
        _ffmpeg("-f", "lavfi", "-i",
                "testsrc=duration=2:size=320x180:rate=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                os.path.join(tmp, name))


class TestRound24HasAudio(unittest.TestCase):
    def test_unprobed_silent_main_renders(self):
        # The reported failure: no hasAudio key -> old code defaulted
        # to True -> [0:a] on a streamless file -> whole export died
        # with "Stream specifier ':a' matches no streams".
        tmp = tempfile.mkdtemp()
        _video(tmp, "silent.mp4", False)
        proj = Project(new_project("t1", width=320, height=180,
                                   fps=(30, 1)), tmp)
        medium = proj.add_media("silent.mp4", kind="video")
        self.assertNotIn("hasAudio", medium)
        proj.add_clip(medium["id"], "v1", 0, 0, 60)
        out = os.path.join(tmp, "o1.mp4")
        report = render(proj.data, tmp, out, preset="draft")
        self.assertEqual(report["duration"], 2.0)
        self.assertTrue(os.path.isfile(out))
        # Silence fallback, not invented audio: anullsrc floor.
        self.assertLessEqual(_mean_volume(out), -85)

    def test_unprobed_with_audio_uses_real_audio(self):
        tmp = tempfile.mkdtemp()
        _video(tmp, "loud.mp4", True)
        proj = Project(new_project("t2", width=320, height=180,
                                   fps=(30, 1)), tmp)
        medium = proj.add_media("loud.mp4", kind="video")
        proj.add_clip(medium["id"], "v1", 0, 0, 60)
        out = os.path.join(tmp, "o2.mp4")
        render(proj.data, tmp, out, preset="draft")
        self.assertGreater(_mean_volume(out), -60)

    def test_probed_paths_unchanged(self):
        # Normal path (probed True) keeps real audio; a record that
        # says False keeps silence even when the file has audio —
        # the probe only ever silences audio that isn't there.
        tmp = tempfile.mkdtemp()
        _video(tmp, "loud.mp4", True)
        proj = Project(new_project("t3", width=320, height=180,
                                   fps=(30, 1)), tmp)
        medium = proj.add_media(
            "loud.mp4", kind="video",
            **probe_media(os.path.join(tmp, "loud.mp4")))
        self.assertTrue(medium["hasAudio"])
        proj.add_clip(medium["id"], "v1", 0, 0, 60)
        out = os.path.join(tmp, "o3.mp4")
        render(proj.data, tmp, out, preset="draft")
        self.assertGreater(_mean_volume(out), -60)

        proj = Project(new_project("t4", width=320, height=180,
                                   fps=(30, 1)), tmp)
        medium = proj.add_media("loud.mp4", kind="video", hasAudio=False)
        proj.add_clip(medium["id"], "v1", 0, 0, 60)
        out = os.path.join(tmp, "o4.mp4")
        render(proj.data, tmp, out, preset="draft")
        self.assertLessEqual(_mean_volume(out), -85)

    def test_streamless_on_music_track_renders(self):
        # The extra-audio loop used to emit [i:a] unconditionally,
        # so a streamless file on an audio track died the same way.
        tmp = tempfile.mkdtemp()
        _video(tmp, "silent.mp4", False)
        proj = Project(new_project("t5", width=320, height=180,
                                   fps=(30, 1)), tmp)
        medium = proj.add_media("silent.mp4", kind="video")
        proj.add_clip(medium["id"], "v1", 0, 0, 60)
        proj.data["tracks"].append(
            {"id": "a1", "kind": "audio", "role": "music", "items": [
                {"id": "i-music", "media": medium["id"],
                 "at": 0, "dur": 60, "in": 0}]})
        out = os.path.join(tmp, "o5.mp4")
        report = render(proj.data, tmp, out, preset="draft")
        self.assertEqual(report["duration"], 2.0)


def _slow_project(tmp, src):
    """1080p 30s project: ~36s uncancelled on this VM, so a cancel
    that lands in seconds proves the process actually stopped. The
    source file is generated once per test class and copied in."""
    import shutil
    shutil.copyfile(src, os.path.join(tmp, "big.mp4"))
    proj = Project(new_project("slow", width=1920, height=1080,
                               fps=(30, 1)), tmp)
    medium = proj.add_media("big.mp4", kind="video", hasAudio=False)
    proj.add_clip(medium["id"], "v1", 0, 0, 900)
    return proj


def _wait_for(path, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.isfile(path):
            return True
        time.sleep(0.2)
    return False


class TestRound24CancelExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.class_tmp = tempfile.mkdtemp()
        _ffmpeg("-f", "lavfi", "-i",
                "testsrc=duration=30:size=1920x1080:rate=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                os.path.join(cls.class_tmp, "big.mp4"))

    def test_render_cancel_kills_ffmpeg(self):
        tmp = tempfile.mkdtemp()
        proj = _slow_project(tmp, os.path.join(self.class_tmp,
                                               "big.mp4"))
        out = os.path.join(tmp, "cancel-direct.mp4")
        token = RenderCancel()
        outcome = {}

        def _run():
            try:
                render(proj.data, tmp, out, preset="full", cancel=token)
                outcome["raised"] = None
            except BaseException as exc:  # noqa: BLE001 - captured
                outcome["raised"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        self.assertTrue(_wait_for(out),
                        "FFmpeg never started writing output")
        proc = token._proc
        self.assertIsNotNone(proc)
        self.assertIsNone(proc.poll(), "FFmpeg already exited pre-cancel")
        token.request()
        thread.join(timeout=15)
        self.assertFalse(thread.is_alive(),
                         "render thread still running 15s after cancel "
                         "(uncancelled render takes ~36s)")
        self.assertIsInstance(outcome.get("raised"), RenderCancelled)
        self.assertTrue(token.killed)
        self.assertEqual(token.returncode, -9)
        self.assertEqual(proc.poll(), -9)

    def test_job_cancel_kills_ffmpeg_and_cleans_up(self):
        tmp = tempfile.mkdtemp()
        proj = _slow_project(tmp, os.path.join(self.class_tmp,
                                               "big.mp4"))
        state = State(tmp)
        out = os.path.join(tmp, "cancel-job.mp4")
        job = state.start_export_job(copy.deepcopy(proj.data), tmp, out,
                                     "full", False, None)
        self.assertEqual(job["status"], "running")
        self.assertTrue(_wait_for(out),
                        "FFmpeg never started writing output")
        token = state.export_tokens[job["id"]]
        self.assertIsNone(token._proc.poll(),
                          "FFmpeg already exited pre-cancel")
        response = state.cancel_export_job(job["id"])
        self.assertEqual(response["status"], "cancelled")
        deadline = time.time() + 15
        cleaned = False
        while time.time() < deadline:
            if (not os.path.isfile(out)
                    and token._proc.poll() == -9):
                cleaned = True
                break
            time.sleep(0.2)
        self.assertTrue(
            cleaned,
            "partial output still present or FFmpeg still alive 15s "
            "after cancel (uncancelled render takes ~36s)")
        self.assertTrue(token.killed)
        self.assertEqual(state.export_job(job["id"])["status"], "cancelled")
        self.assertTrue(state.export_job(job["id"]).get("killed"))
        self.assertIsNone(state.last_export,
                          "cancelled job must never publish")
        self.assertFalse(os.path.isfile(out))

    def test_job_success_still_publishes(self):
        # The Popen final-FFmpeg path must not break normal exports.
        tmp = tempfile.mkdtemp()
        _video(tmp, "silent.mp4", False)
        proj = Project(new_project("ok", width=320, height=180,
                                   fps=(30, 1)), tmp)
        medium = proj.add_media("silent.mp4", kind="video")
        proj.add_clip(medium["id"], "v1", 0, 0, 60)
        state = State(tmp)
        out = os.path.join(tmp, "ok.mp4")
        job = state.start_export_job(copy.deepcopy(proj.data), tmp, out,
                                     "draft", False, None)
        deadline = time.time() + 60
        final = None
        while time.time() < deadline:
            final = state.export_job(job["id"])
            if final["status"] in ("done", "error"):
                break
            time.sleep(0.2)
        self.assertEqual(final["status"], "done", final.get("error"))
        self.assertEqual(state.last_export, out)
        self.assertTrue(os.path.isfile(out))


class TestRound24ImportDomAudit(unittest.TestCase):
    """The tester counted 3 import controls. The DOM has 3 import
    NODES but only ONE visible control: the file input and the
    submit button carry .visually-hidden (1px, clipped) and exist
    only so the dropzone can open the picker programmatically
    (a display:none input cannot be .click()ed). No label, no
    "Choose File" text, no second visible control exists."""

    def _read(self, name):
        root = os.path.join(os.path.dirname(__file__), "..", "static")
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            return fh.read()

    def test_exactly_one_visible_import_control(self):
        html = self._read("index.html")
        css = self._read("style.css")
        # The hidden class really hides: 1px box, clipped out.
        hidden_rule = re.search(
            r"\.visually-hidden \{([^}]*)\}", css).group(1)
        self.assertIn("width: 1px", hidden_rule)
        self.assertIn("clip: rect(0 0 0 0)", hidden_rule)
        # Dropzone: the one visible control, no hidden class.
        zone = re.search(
            r'<div class="([^"]*)" id="importDropzone"', html).group(1)
        self.assertNotIn("visually-hidden", zone)
        # File input + submit button: present (ids kept) but hidden.
        file_input = re.search(
            r'<input type="file" id="uploadFile" class="([^"]*)"', html)
        self.assertIsNotNone(file_input)
        self.assertIn("visually-hidden", file_input.group(1))
        submit = re.search(
            r'<button type="submit" class="([^"]*)">Tải media lên</button>',
            html)
        self.assertIsNotNone(submit)
        self.assertIn("visually-hidden", submit.group(1))
        # No other picker affordance: no label, no Choose File text.
        self.assertNotIn('for="uploadFile"', html)
        self.assertNotIn("Choose File", html)
        # All import ids kept.
        for element_id in ("importDropzone", "uploadForm", "uploadFile",
                           "mediaList", "mediaAddStatus"):
            self.assertIn(f'id="{element_id}"', html)
        # Locked English subtext verbatim (test_capcut_ui:90,
        # test_round18:115).
        self.assertIn(
            "Drag and drop videos, photos, and audio files here", html)


class TestRound24RequiredArgs(unittest.TestCase):
    def test_missing_args_raise_value_error_naming_keys(self):
        server = MCPServer()
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_markers_add", {})
        self.assertEqual(
            str(caught.exception),
            "vibeedit_markers_add: missing required argument(s): at, text")
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_markers_add", {"text": "x"})
        self.assertIn("at", str(caught.exception))
        self.assertNotIn("text", str(caught.exception).split(": ")[-1])
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_agent_kit_install", {})
        self.assertIn("path", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_project_open", {})
        self.assertIn("path", str(caught.exception))

    def test_non_dict_arguments_raise_value_error(self):
        server = MCPServer()
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_markers_add", ["at"])  # type: ignore
        self.assertIn("must be an object", str(caught.exception))

    def test_via_handle_surfaces_clean_message(self):
        server = MCPServer()
        response = handle(server, {"jsonrpc": "2.0", "id": 7,
                                   "method": "tools/call",
                                   "params": {"name": "vibeedit_markers_add",
                                              "arguments": {}}})
        self.assertEqual(response["error"]["code"], -32603)
        self.assertEqual(
            response["error"]["message"],
            "vibeedit_markers_add: missing required argument(s): at, text")
        response = handle(server, {"jsonrpc": "2.0", "id": 8,
                                   "method": "tools/call",
                                   "params": {}})
        self.assertEqual(response["error"]["code"], -32603)
        self.assertIn("params.name", response["error"]["message"])

    def test_unknown_tool_error_unchanged(self):
        server = MCPServer()
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_no_such_tool", {})
        self.assertIn("Unknown tool", str(caught.exception))

    def test_valid_markers_add_still_works(self):
        tmp = tempfile.mkdtemp()
        server = MCPServer()
        server.call("vibeedit_project_new",
                    {"name": "r24", "directory": tmp})
        result = server.call("vibeedit_markers_add",
                             {"at": 0, "text": "hello"})
        self.assertEqual(result["text"], "hello")
        self.assertTrue(result["id"].startswith("mk-"))

    def test_plugins_install_source_not_schema_required(self):
        # Round 24 follow-up: the registry path takes registry_plugin
        # instead of source, so the schema cannot require source; the
        # round-15 registry test (no source arg) is the regression.
        schema = TOOL_SCHEMAS["vibeedit_plugins_install"]
        self.assertEqual(schema["required"], [])

    def test_plugins_install_neither_arg_is_valueerror(self):
        # ...but neither source nor registry_plugin still fails as a
        # clear ValueError, never a bare KeyError.
        server = MCPServer()
        with self.assertRaises(ValueError) as caught:
            server.call("vibeedit_plugins_install", {})
        self.assertIn("registry_plugin", str(caught.exception))
        self.assertIn("source", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
