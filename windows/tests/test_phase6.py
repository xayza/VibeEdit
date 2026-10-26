"""Phase 6 tests: GitHub Actions Windows workflow, exe easy-run
behaviour (serve --open-browser + frozen no-arg default), and the
12 new MCP tools. No exe is built here and no browser is opened:
browser opening is tested through a mock, and the workflow is
validated by parsing its YAML (it can only run on GitHub).

Run from windows/:  python3 -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import yaml  # noqa: E402
import vibeedit  # noqa: E402
from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.project import (Project, new_project, save_project,  # noqa: E402
                                  PROJECT_FILENAME)
from vibeedit_core.render import probe_media  # noqa: E402
from vibeedit_core.server import open_browser  # noqa: E402


def gen_clip(path, seconds=3):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


class TestFrozenDefaultAndOpenBrowser(unittest.TestCase):
    def test_frozen_no_args_defaults_to_serve_open_browser(self):
        self.assertEqual(
            vibeedit._effective_argv([], True),
            ["serve", "--open-browser", "--port", "8000"])

    def test_unfrozen_no_args_stays_empty(self):
        self.assertEqual(vibeedit._effective_argv([], False), [])

    def test_explicit_args_unchanged_when_frozen(self):
        self.assertEqual(
            vibeedit._effective_argv(["open", "x"], True), ["open", "x"])

    def test_open_browser_success_and_failure(self):
        real_open = webbrowser.open
        try:
            webbrowser.open = lambda url: True
            self.assertTrue(open_browser("http://127.0.0.1:8000/"))
            webbrowser.open = lambda url: (_ for _ in ()).throw(
                RuntimeError("no browser"))
            self.assertFalse(open_browser("http://127.0.0.1:8000/"))
        finally:
            webbrowser.open = real_open

    def test_serve_plumbing_passes_open_browser_flag(self):
        import vibeedit_core.server as server_mod
        seen = {}
        real_run = server_mod.run_server
        try:
            server_mod.run_server = lambda *a, **k: seen.update(
                {"args": a, "kwargs": k})
            vibeedit._serve(types.SimpleNamespace(
                project=None, port=8123, open_browser=True))
            self.assertEqual(seen["args"], (None, 8123))
            self.assertTrue(seen["kwargs"]["open_browser_flag"])
        finally:
            server_mod.run_server = real_run

    def test_serve_parser_accepts_open_browser(self):
        # main() with a mocked run_server must not reject the flag.
        import vibeedit_core.server as server_mod
        real_run = server_mod.run_server
        try:
            server_mod.run_server = lambda *a, **k: None
            self.assertEqual(
                vibeedit.main(["serve", "--port", "8123",
                               "--open-browser"]), 0)
        finally:
            server_mod.run_server = real_run


class TestWorkflowYaml(unittest.TestCase):
    def test_workflow_parses_and_has_required_steps(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..",
                            ".github", "workflows", "build-windows.yml")
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh)
        self.assertEqual(doc["jobs"]["build"]["runs-on"], "windows-latest")
        triggers = doc[True] if True in doc else doc.get("on", {})
        # PyYAML parses the `on` key as boolean True.
        self.assertIn("workflow_dispatch", triggers)
        self.assertIn("windows/**", triggers["push"]["paths"])
        text = open(path, encoding="utf-8").read()
        for needle in ("actions/checkout@v4", "actions/setup-python@v5",
                       "windows\\build_windows.bat",
                       "ffmpeg-release-essentials.zip",
                       "VibeEdit.exe' --help", "actions/upload-artifact@v4",
                       "name: VibeEdit-Windows",
                       "windows/dist/VibeEdit"):
            self.assertIn(needle, text)


class TestPhase6Mcp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        data = new_project("phase6", width=320, height=180, fps=(30, 1))
        save_project(data, os.path.join(self.tmp, PROJECT_FILENAME))
        self.server = MCPServer(self.tmp)
        proj = self.server.project
        info = probe_media(os.path.join(self.tmp, "c1.mp4"))
        self.medium = proj.add_media("c1.mp4", kind="video", **info)
        self.clip = proj.add_clip(self.medium["id"], "v1", 0, 0, 90)
        proj.set_color(self.clip["id"], preset="vivid")
        proj.set_keyframes(self.clip["id"], [{"at": 0, "scale": 1.0},
                                             {"at": 90, "scale": 2.0}])
        proj.set_fade(self.clip["id"], fade_in=0.5)
        self.server._save()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tool_count_and_names(self):
        self.assertEqual(len(TOOLS), 90)
        names = {t["name"] for t in TOOLS}
        self.assertEqual(len(names), 90)
        for name in ("vibeedit_clip_copy",
                     "vibeedit_clip_paste_cross_project",
                     "vibeedit_text_preset_list",
                     "vibeedit_text_preset_apply",
                     "vibeedit_export_preset_list",
                     "vibeedit_timeline_duration",
                     "vibeedit_media_duration",
                     "vibeedit_project_backup",
                     "vibeedit_project_rename",
                     "vibeedit_clip_volume",
                     "vibeedit_text_set",
                     "vibeedit_media_add"):
            self.assertIn(name, names)

    def test_clip_copy_preserves_color_keyframes_fade(self):
        copy = self.server.call(
            "vibeedit_clip_copy",
            {"item": self.clip["id"], "track": "v2", "at": 0})
        self.assertNotEqual(copy["id"], self.clip["id"])
        self.assertEqual(copy["media"], self.medium["id"])
        self.assertEqual(copy["color"]["preset"], "vivid")
        self.assertEqual(len(copy["keyframes"]), 2)
        self.assertEqual(copy["fadeIn"], 0.5)

    def test_cross_project_paste_reports_missing_media(self):
        dest = os.path.join(self.tmp, "destproj")
        os.makedirs(dest)
        save_project(new_project("dest", width=320, height=180,
                                 fps=(30, 1)),
                     os.path.join(dest, PROJECT_FILENAME))
        pasted = self.server.call(
            "vibeedit_clip_paste_cross_project",
            {"item": self.clip["id"], "dest": dest,
             "track": "v1", "at": 0})
        self.assertIn("media_warning", pasted)
        self.assertEqual(pasted["media"], self.medium["id"])
        # The destination project file now holds the pasted clip.
        from vibeedit_core.project import load_project
        dest_data = load_project(os.path.join(dest, PROJECT_FILENAME))
        self.assertEqual(len(dest_data["tracks"][0]["items"]), 1)

    def test_text_presets_and_apply(self):
        presets = self.server.call("vibeedit_text_preset_list", {})
        self.assertIn("title", presets["presets"])
        text = self.server.project.add_text("t1", "hi", 0, 30)
        self.server._save()
        styled = self.server.call(
            "vibeedit_text_preset_apply",
            {"item": text["id"], "preset": "title"})
        self.assertEqual(styled["textStyle"]["size"], 0.12)
        renamed = self.server.call("vibeedit_text_set",
                                   {"item": text["id"], "text": "hello"})
        self.assertEqual(renamed["text"], "hello")

    def test_export_presets_duration_media_and_misc(self):
        presets = self.server.call("vibeedit_export_preset_list", {})
        self.assertEqual(presets["presets"]["full"]["crf"], "20")
        self.assertEqual(presets["presets"]["draft"]["width"], 160)
        dur = self.server.call("vibeedit_timeline_duration", {})
        self.assertEqual(dur["frames"], 90)
        self.assertAlmostEqual(dur["seconds"], 3.0)
        media = self.server.call("vibeedit_media_duration",
                                 {"media": self.medium["id"]})
        self.assertTrue(media["probed"])
        self.assertAlmostEqual(media["duration"], 3.0, places=1)
        backup = self.server.call("vibeedit_project_backup", {})
        self.assertTrue(os.path.isfile(backup["backup"]))
        renamed = self.server.call("vibeedit_project_rename",
                                   {"name": "renamed"})
        self.assertEqual(renamed["name"], "renamed")
        vol = self.server.call("vibeedit_clip_volume",
                               {"item": self.clip["id"], "volume": -3.0})
        self.assertEqual(vol["volume"], -3.0)
        added = self.server.call("vibeedit_media_add",
                                 {"path": "missing.mp4"})
        self.assertIn("warning", added)
        added2 = self.server.call("vibeedit_media_add", {"path": "c1.mp4"})
        self.assertNotIn("warning", added2)


if __name__ == "__main__":
    unittest.main()
