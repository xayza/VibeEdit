"""Round 21: agent_status as kit status (per the original spec) and a
real file-backed MCP debug log, plus the tools deliberately kept
honest after re-checking their reasons against current code.

New tests live ONLY here (round-21 file). Old-test count bumps are
applied separately at the end of the round, after the count settles.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402


class TestRound21AgentStatus(unittest.TestCase):
    def test_status_is_kit_data(self):
        # Original agent.status spec: the agent kit's folder, version
        # and skills (+ per-tab/per-CLI setup state, not tracked
        # here) — NOT a terminal session. So its headless content is
        # exactly agent_kit_check's data.
        server = MCPServer()
        status = server.call("vibeedit_agent_status", {})
        kit = server.call("vibeedit_agent_kit_check", {})
        self.assertEqual(status, kit)
        for key in ("kitFolder", "skills", "version"):
            self.assertIn(key, status, key)

    def test_status_description_states_limits(self):
        desc = next(t["description"] for t in TOOLS
                    if t["name"] == "vibeedit_agent_status")
        self.assertFalse(desc.startswith("Not available"))
        self.assertIn("agent_kit_check", desc)
        self.assertIn("not tracked", desc)


class TestRound21DebugLog(unittest.TestCase):
    def _server_with_log(self, tmp):
        path = os.path.join(tmp, "debug.log")
        os.environ["VIBEEDIT_DEBUG_LOG_PATH"] = path
        return MCPServer(), path

    def tearDown(self):
        os.environ.pop("VIBEEDIT_DEBUG_LOG_PATH", None)

    def test_calls_append_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, path = self._server_with_log(tmp)
            server.call("vibeedit_show_shortcuts", {})
            server.call("vibeedit_mcp_tools_list", {})
            result = server.call("vibeedit_app_vibeedit_debug_log", {})
            lines = result["lines"]
            self.assertEqual(result["path"], path)
            self.assertEqual(result["total"], 2)
            joined = "\n".join(lines)
            self.assertIn("vibeedit_show_shortcuts", joined)
            self.assertIn("vibeedit_mcp_tools_list", joined)
            # Debug-log reads themselves are not logged.
            self.assertNotIn("vibeedit_app_vibeedit_debug_log", joined)

    def test_arguments_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, path = self._server_with_log(tmp)
            server.call("vibeedit_agent_status", {})
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            # The distinctive value below was never an argument here;
            # this guards the no-args rule structurally: lines hold
            # only "ISO-time tool-name".
            for line in content.splitlines():
                parts = line.split(" ")
                self.assertEqual(len(parts), 2, line)
            self.assertNotIn("SECRET_MARKER_XYZ", content)

    def test_missing_file_is_empty_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, path = self._server_with_log(tmp)
            result = server.call("vibeedit_app_vibeedit_debug_log", {})
            self.assertEqual(result["lines"], [])
            self.assertEqual(result["total"], 0)
            self.assertIn("no log lines yet", result["note"])

    def test_lines_arg_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, path = self._server_with_log(tmp)
            with open(path, "w", encoding="utf-8") as fh:
                for i in range(10):
                    fh.write(f"2026-01-01T00:00:0{i}Z tool-{i}\n")
            result = server.call("vibeedit_app_vibeedit_debug_log",
                                 {"lines": 3})
            self.assertEqual(len(result["lines"]), 3)
            self.assertTrue(result["lines"][-1].endswith("tool-9"))
            self.assertEqual(result["total"], 10)
            for bad in (0, 1001, "three"):
                with self.assertRaises(ValueError, msg=str(bad)):
                    server.call("vibeedit_app_vibeedit_debug_log",
                                {"lines": bad})

    def test_byte_cap_trims(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, path = self._server_with_log(tmp)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("x" * (300 * 1024) + "\n")
            server._log_call("vibeedit_mcp_tools_list")
            self.assertLessEqual(os.path.getsize(path),
                                 MCPServer._DEBUG_LOG_MAX_BYTES)


class TestRound21StillHonest(unittest.TestCase):
    def test_kept_honest_tools_raise(self):
        # Re-checked against current code (not copied reasons):
        # - agent_setup: privileged install into in-app tabs / Claude
        #   Code / Codex configs; the port has no tabs and never
        #   writes external CLI configs (kit_install covers only the
        #   app's own kit folder).
        # - agent_setup_show: the setup card is the 2-step checklist
        #   (per-CLI kit-install status + starter-bundle membership);
        #   neither is tracked, and no enum state maps "unknown".
        # - agent_show_changes/dismiss/undo_changes: no
        #   AgentChangeRecord exists (author/label/changed IDs +
        #   notice lifecycle); the backup file is pre-state only,
        #   not a change record; timeline_undo is the undo path.
        # - app_vibeedit/automation_clients: no Unix-socket server
        #   and no client registry in this headless server.
        # - terminals/chat/playback/browser toggles: no terminal
        #   session, chat session, playback engine or browser session
        #   exists server-side (verified: no such machinery in
        #   vibeedit_core, no view flags in server.py).
        # - show_settings/platforms_get: re-verified in round 20 and
        #   unchanged (modal has no server-owned settings; the
        #   platforms spec exists but no facts table in either tree).
        server = MCPServer()
        for name in ("vibeedit_agent_setup",
                     "vibeedit_agent_setup_show",
                     "vibeedit_agent_show_changes",
                     "vibeedit_agent_dismiss_changes",
                     "vibeedit_agent_undo_changes",
                     "vibeedit_agent_open", "vibeedit_agent_open_chat",
                     # Round 22: agent_terminals left (now real).
                     "vibeedit_agent_ask",
                     "vibeedit_agent_restart_tab",
                     "vibeedit_agent_detach",
                     "vibeedit_agent_tools_install",
                     "vibeedit_chat_send", "vibeedit_chat_status",
                     "vibeedit_chat_transcript", "vibeedit_chat_stop",
                     "vibeedit_ui_action", "vibeedit_ui_dialog",
                     "vibeedit_ui_view", "vibeedit_ui_respond",
                     "vibeedit_ui_actions",
                     "vibeedit_playback_toggle", "vibeedit_playback_stop",
                     "vibeedit_source_toggle_playback",
                     "vibeedit_view_fullscreen",
                     "vibeedit_view_inspector_pane",
                     "vibeedit_view_library_pane",
                     "vibeedit_view_compare", "vibeedit_view_safe_area",
                     "vibeedit_timeline_header_compact",
                     "vibeedit_show_settings", "vibeedit_platforms_get",
                     "vibeedit_app_vibeedit",
                     # Round 22: automation_clients left (now real).
                     "vibeedit_voice_clone_add",
                     "vibeedit_image_generate",
                     "vibeedit_library_generate",
                     "vibeedit_app_update", "vibeedit_plugins_setup",
                     "vibeedit_clip_send_to_agent",
                     "vibeedit_acme_voice_fast"):
            with self.assertRaises(ValueError, msg=name):
                server.call(name, {})


class TestRound21RegistryCounts(unittest.TestCase):
    def test_counts(self):
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(honest), 52)
        self.assertEqual(len(TOOLS) - len(honest), 429)
        names = {t["name"] for t in TOOLS}
        for now_real in ("vibeedit_agent_status",
                         "vibeedit_app_vibeedit_debug_log"):
            self.assertIn(now_real, names)
            self.assertNotIn(
                now_real, {t["name"] for t in honest}, now_real)


if __name__ == "__main__":
    unittest.main()
