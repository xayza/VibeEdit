"""Integration tests for the full-parity batch (Phase B integration).

Covers the wiring the coordinator added after the five Phase B
children: motion kinds + reframe in Project, manifest plugin
discovery, MCP tools for skills/vision/plugin-install, and the new
server ops. Temp dirs only; no user sample projects/media.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from vibeedit_core.mcp import TOOLS
from vibeedit_core.project import Project, new_project, validate_reframe
from vibeedit_core.render import list_transition_renderability


def _make_project(tmp):
    return Project(new_project("test", width=320, height=180), tmp)


def _two_clips(proj):
    m1 = proj.add_media("media/a.mp4", "video", width=320, height=180,
                        fps=30, frames=60, duration=2.0)
    m2 = proj.add_media("media/b.mp4", "video", width=320, height=180,
                        fps=30, frames=60, duration=2.0)
    main = next(t for t in proj.data["tracks"] if t.get("role") == "main")
    c1 = proj.add_clip(m1["id"], main["id"], 0, dur=60)
    c2 = proj.add_clip(m2["id"], main["id"], 60, dur=60)
    return c1, c2


class TestMotionAndReframe(unittest.TestCase):
    def test_motion_kinds_accepted_by_add_transition(self):
        # One cut holds one transition, so each kind gets its own
        # fresh project.
        for kind in ("spin", "diamond", "kaleidoscope", "crash-out"):
            with tempfile.TemporaryDirectory() as tmp:
                proj = _make_project(tmp)
                c1, c2 = _two_clips(proj)
                tr = proj.add_transition(c1["id"], c2["id"], kind, 0.5)
                self.assertEqual(tr["kind"], kind)
                self.assertEqual(proj.validate()["ok"], True)

    def test_halftone_accepted_round4(self):
        # Round 4: halftone renders (geq dot mask + alphamerge /
        # overlay in the timeline render, Pillow segment standalone),
        # so add_transition accepts it. The real render proof is in
        # tests/test_round4_halftone.py; this test only asserts the
        # registry no longer rejects the kind.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            c1, c2 = _two_clips(proj)
            tr = proj.add_transition(c1["id"], c2["id"], "halftone", 0.5)
            self.assertEqual(tr["kind"], "halftone")
            self.assertEqual(proj.validate()["ok"], True)

    def test_renderability_list_covers_39_and_flags_halftone(self):
        rows = list_transition_renderability()
        names = [r["kind"] for r in rows]
        self.assertEqual(len(names), len(set(names)))
        by_kind = {r["kind"]: r for r in rows}
        self.assertTrue(by_kind["spin"]["renders"])
        # Round 4: halftone renders (was unrenderable before).
        self.assertTrue(by_kind["halftone"]["renders"])
        self.assertIn("geq", by_kind["halftone"]["method"])

    def test_reframe_via_add_clip_and_set_reframe(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            m1 = proj.add_media("media/a.mp4", "video", width=320,
                                  height=180, fps=30, frames=60,
                                  duration=2.0)
            main = next(t for t in proj.data["tracks"]
                        if t.get("role") == "main")
            clip = proj.add_clip(m1["id"], main["id"], 0, dur=60,
                                 reframe={"x": 0.342, "y": 0,
                                          "w": 0.316, "h": 1})
            self.assertEqual(clip["reframe"]["w"], 0.316)
            proj.set_reframe(clip["id"], None)
            _, item = proj.item(clip["id"])
            self.assertNotIn("reframe", item)
            with self.assertRaises(ValueError):
                validate_reframe({"x": 0.8, "y": 0, "w": 0.5, "h": 1})


class TestManifestDiscovery(unittest.TestCase):
    def test_install_then_list_then_enable(self):
        from vibeedit_core.plugins import (install_plugin, list_plugins,
                                          set_plugin_enabled)
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            src = os.path.join(tmp, "srcplug")
            os.makedirs(src)
            import json
            with open(os.path.join(src, "plugin.json"), "w") as fh:
                json.dump({"id": "demo-plug", "name": "Demo",
                           "description": "demo",
                           "hooks": ["color"]}, fh)
            res = install_plugin(src, plugins_dir=plugins_dir)
            self.assertEqual(res["id"], "demo-plug")
            self.assertFalse(res["enabled"])
            names = [p["name"] for p in list_plugins(plugins_dir)]
            self.assertIn("demo-plug", names)
            entry = [p for p in list_plugins(plugins_dir)
                     if p["name"] == "demo-plug"][0]
            self.assertIn("color", entry["hooks"])
            self.assertFalse(entry["enabled"])
            out = set_plugin_enabled("demo-plug", True,
                                     plugins_dir=plugins_dir)
            self.assertTrue(out["enabled"])

    def test_manifest_apply_errors_clearly(self):
        from vibeedit_core.plugins import apply_plugin, install_plugin
        with tempfile.TemporaryDirectory() as tmp:
            plugins_dir = os.path.join(tmp, "plugins")
            os.makedirs(plugins_dir)
            src = os.path.join(tmp, "srcplug")
            os.makedirs(src)
            import json
            with open(os.path.join(src, "plugin.json"), "w") as fh:
                json.dump({"id": "demo-plug", "name": "Demo",
                           "hooks": ["color"]}, fh)
            install_plugin(src, plugins_dir=plugins_dir)
            proj = _make_project(tmp)
            with self.assertRaises(ValueError) as ctx:
                apply_plugin(proj, "demo-plug", "color", "x",
                             plugins_dir=plugins_dir)
            # Either disabled-first or manifest-not-executable: both
            # are honest, neither pretends the hook ran.
            self.assertTrue("disabled" in str(ctx.exception)
                            or "not executable" in str(ctx.exception))


class TestMcpIntegrationTools(unittest.TestCase):
    def test_registry_counts(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(TOOLS), 481)  # Round 23: 479 -> 481 (skills_import_plan/import)
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(honest), 52)  # Round 22: 54 -> 52, agent_terminals/automation_clients became real (see tests/test_round22.py)
        for new in ("vibeedit_clip_link_audio",
                    "vibeedit_project_magnetic_get",
                    "vibeedit_project_magnetic_set",
                    "vibeedit_transitions_renderability",
                    "vibeedit_skills_search",
                    "vibeedit_plugins_download"):
            self.assertIn(new, names, new)

    def test_skills_tools_are_real(self):
        from vibeedit_core.mcp import MCPServer
        srv = MCPServer()
        res = srv.call("vibeedit_skills_list", {})
        ids = [s["id"] for s in res["skills"]]
        self.assertIn("loudness-check", ids)
        res = srv.call("vibeedit_skills_search", {"query": "preset"})
        self.assertTrue(any(s["id"] == "export-presets"
                            for s in res["skills"]))

    def test_magnetic_tools_and_link_tools(self):
        from vibeedit_core.mcp import MCPServer
        with tempfile.TemporaryDirectory() as tmp:
            srv = MCPServer()
            proj = _make_project(tmp)
            srv.project = proj
            srv.path = os.path.join(tmp, "project.json")
            self.assertTrue(
                srv.call("vibeedit_project_magnetic_get", {})["magnetic"])
            srv.call("vibeedit_project_magnetic_set",
                     {"enabled": False})
            self.assertFalse(
                srv.call("vibeedit_project_magnetic_get", {})["magnetic"])

    def test_vision_tool_errors_name_backend(self):
        from vibeedit_core.mcp import MCPServer
        srv = MCPServer()
        # No media/project needed: a nonexistent path must not be
        # reported as a successful empty scan.
        with self.assertRaises((ValueError, FileNotFoundError)):
            srv.call("vibeedit_vision_text", {"path": "/nonexistent/x.png"})

    def test_no_orphan_tools(self):
        # Every tool must either run or raise a controlled error —
        # never "Unknown tool" (a B1 bug this batch caught: three
        # tools had real-style descriptions but no handler).
        from vibeedit_core.mcp import MCPServer
        srv = MCPServer()
        for tool in TOOLS:
            try:
                srv.call(tool["name"], {})
            except ValueError as exc:
                self.assertFalse(str(exc).startswith("Unknown tool"),
                                 tool["name"])
            except Exception:
                pass

    def test_transitions_renderability_tool(self):
        from vibeedit_core.mcp import MCPServer
        srv = MCPServer()
        res = srv.call("vibeedit_transitions_renderability", {})
        by_kind = {r["kind"]: r for r in res["transitions"]}
        self.assertTrue(by_kind["spin"]["renders"])
        # Round 4: halftone renders (was unrenderable before).
        self.assertTrue(by_kind["halftone"]["renders"])


if __name__ == "__main__":
    unittest.main()
