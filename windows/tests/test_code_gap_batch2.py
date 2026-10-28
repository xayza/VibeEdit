"""Code-gap batch 2 tests: timeline redo + tiny query tools, export
presets, speed curves, reverse, freeze, review workflow, library/brand,
plugin enable/disable, welcome recents, new transitions, new UI ids,
and the updated MCP count (144 -> 472, round 3 -> 478). Real FFmpeg renders for
reverse and one export preset.

Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.plugins import (  # noqa: E402
    list_plugins, load_plugin_state, set_plugin_enabled)
from vibeedit_core.project import (  # noqa: E402
    TRANSITION_XFADE, Project, new_project, save_project)
from vibeedit_core.render import (  # noqa: E402
    export_preset_info, render, probe_media)
from vibeedit_core.server import State  # noqa: E402


def gen_clip(path, seconds=2):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def make_project(tmp):
    return Project(new_project("gap2", width=320, height=180,
                                fps=(30, 1)), tmp)


def add_clip_project(tmp):
    gen_clip(os.path.join(tmp, "c1.mp4"))
    proj = make_project(tmp)
    info = probe_media(os.path.join(tmp, "c1.mp4"))
    medium = proj.add_media("c1.mp4", kind="video", **info)
    clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
    return proj, medium, clip


class TestRedoAndQueries(unittest.TestCase):
    def test_redo_restores_undone_state(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            path = os.path.join(tmp, "project.vibeedit.json")
            save_project(proj.data, path)
            server = MCPServer(tmp)
            server.call("vibeedit_project_backup", {})
            # Delete the clip, then undo (restores it, writes .redo),
            # then redo (restores the deleted state).
            server.project.delete(clip["id"])
            server._save()
            self.assertEqual(server.call("vibeedit_timeline_clip_count",
                                         {})["total"], 0)
            server.call("vibeedit_timeline_undo", {})
            self.assertEqual(server.call("vibeedit_timeline_clip_count",
                                         {})["total"], 1)
            self.assertTrue(os.path.isfile(path + ".redo"))
            server.call("vibeedit_timeline_redo", {})
            self.assertEqual(server.call("vibeedit_timeline_clip_count",
                                         {})["total"], 0)
            with self.assertRaises(RuntimeError):
                # A project with no .redo file cannot redo.
                tmp2 = tempfile.mkdtemp()
                proj2, _, _ = add_clip_project(tmp2)
                save_project(proj2.data,
                             os.path.join(tmp2, "project.vibeedit.json"))
                fresh = MCPServer(tmp2)
                fresh.call("vibeedit_timeline_redo", {})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_query_tools_return_real_data(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, medium, clip = add_clip_project(tmp)
            marker = proj.add_marker("Intro", 10)
            path = os.path.join(tmp, "project.vibeedit.json")
            save_project(proj.data, path)
            server = MCPServer(tmp)
            moved = server.call("vibeedit_marker_move",
                                {"marker": marker["id"], "at": 20})
            self.assertEqual(moved["at"], 20)
            self.assertEqual(server.call("vibeedit_media_get",
                                         {"media": medium["id"]})["media"]["id"],
                             medium["id"])
            self.assertEqual(server.call("vibeedit_track_get",
                                         {"track": "v1"})["track"]["id"], "v1")
            self.assertEqual(server.call("vibeedit_adjustments_list",
                                         {})["adjustments"], [])
            self.assertEqual(server.call("vibeedit_beats_list",
                                         {})["beats"], [])
            self.assertIn("enabled",
                          server.call("vibeedit_ducking_get", {}))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestExportPresets(unittest.TestCase):
    def test_preset_mapping_matches_original(self):
        info = export_preset_info("youtube1080", 320, 180)
        self.assertEqual((info["width"], info["height"]), (1920, 1080))
        self.assertEqual(info["bitrate"], 12000000)
        self.assertEqual(info["codec"], "libx264")
        self.assertEqual(info["ext"], "mp4")
        info = export_preset_info("youtube4k", 320, 180)
        self.assertEqual((info["width"], info["height"]), (3840, 2160))
        self.assertEqual(info["bitrate"], 45000000)
        info = export_preset_info("prores", 320, 180)
        self.assertEqual(info["codec"], "prores_ks")
        self.assertEqual(info["ext"], "mov")
        self.assertIsNone(info["bitrate"])
        info = export_preset_info("tiktok", 320, 180)
        self.assertEqual((info["width"], info["height"]), (1080, 1920))
        self.assertEqual(info["bitrate"], 8000000)
        with self.assertRaises(ValueError):
            export_preset_info("no-such-preset", 320, 180)

    def test_preset_render_uses_mapping(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, _ = add_clip_project(tmp)
            out = os.path.join(tmp, "preset.mp4")
            report = render(proj.data, tmp, out, preset="full",
                            export_preset="youtube1080")
            self.assertEqual(report["export_preset"], "youtube1080")
            self.assertEqual(report["video_codec"], "libx264")
            self.assertEqual(report["video_bitrate"], 12000000)
            self.assertEqual((report["width"], report["height"]),
                             (1920, 1080))
            probed = probe_media(out)
            self.assertEqual((probed["width"], probed["height"]),
                             (1920, 1080))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestSpeedReverseFreeze(unittest.TestCase):
    def test_speed_curve_splits_and_keeps_length(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            result = proj.apply_speed_curve(clip["id"], "montage")
            self.assertEqual(result["preset"], "montage")
            # Splits at the 3 interior control points -> 4 segments,
            # each at the curve value interpolated at its midpoint.
            self.assertEqual(len(result["segments"]), 4)
            for got, want in zip(result["speeds"], [1.75, 1.55, 1.55, 1.75]):
                self.assertAlmostEqual(got, want, places=2)
            # Total timeline length is preserved across the split.
            items = proj.track("v1")["items"]
            self.assertEqual(sum(int(i["dur"]) for i in items), 60)
            with self.assertRaises(ValueError):
                proj.apply_speed_curve(clip["id"], "no-such-curve")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reverse_flag_and_real_render(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            proj.set_reverse(clip["id"], True)
            _, item = proj.item(clip["id"])
            self.assertTrue(item["reverse"])
            out = os.path.join(tmp, "rev.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertTrue(os.path.isfile(out))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_freeze_appends_frame_hold(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            result = proj.freeze_clip(clip["id"], 30)
            self.assertEqual(result["dur"], 30)
            self.assertEqual(result["at"], 60)
            self.assertTrue(result["freeze"])
            out = os.path.join(tmp, "freeze.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestReviewLibraryBrand(unittest.TestCase):
    def test_review_run_accept_verify(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, _ = add_clip_project(tmp)
            run = proj.run_review()
            self.assertEqual(run["status"], "run")
            self.assertEqual(run["issue_count"], 0)
            rev_before = proj.rev
            accepted = proj.accept_review()
            self.assertEqual(accepted["accepted_rev"], rev_before)
            verified = proj.verify_review()
            self.assertFalse(verified["issue_count_changed"])
            # A fresh project with no review cannot accept/verify.
            fresh = make_project(tmp)
            with self.assertRaises(ValueError):
                fresh.accept_review()
            with self.assertRaises(ValueError):
                fresh.verify_review()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_library_and_brand_round_trip(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            entry = proj.library_add(clip["id"], "Hero clip")
            self.assertEqual(len(proj.library_list()), 1)
            placed = proj.library_place(entry["id"])
            self.assertEqual(placed["at"], 60)
            proj.library_remove(entry["id"])
            self.assertEqual(proj.library_list(), [])
            brand = proj.brand_set(["#FF0000", "#00FF00"], None)
            self.assertEqual(brand["colours"], ["#FF0000", "#00FF00"])
            with self.assertRaises(ValueError):
                proj.brand_set(["not-a-hex"], None)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPluginsAndRecents(unittest.TestCase):
    def test_plugin_disable_blocks_apply(self):
        tmp = tempfile.mkdtemp()
        try:
            from vibeedit_core.plugins import apply_plugin
            proj, _, _ = add_clip_project(tmp)
            text_item = proj.add_text("t1", "hello", 0, 10)
            state_before = load_plugin_state()
            self.assertNotIn("uppercase_text", state_before["disabled"])
            set_plugin_enabled("uppercase_text", False)
            listed = {p["name"]: p for p in list_plugins()
                      if p["name"] != "_errors"}
            self.assertFalse(listed["uppercase_text"]["enabled"])
            with self.assertRaises(ValueError):
                apply_plugin(proj, "uppercase_text", "transform_text",
                             text_item["id"])
            set_plugin_enabled("uppercase_text", True)
            listed = {p["name"]: p for p in list_plugins()
                      if p["name"] != "_errors"}
            self.assertTrue(listed["uppercase_text"]["enabled"])
            got = apply_plugin(proj, "uppercase_text", "transform_text",
                               text_item["id"])
            self.assertEqual(got["text"], "HELLO")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            # Restore the real plugin state on disk.
            try:
                set_plugin_enabled("uppercase_text", True)
            except Exception:
                pass

    def test_recent_list_and_remove(self):
        tmp = tempfile.mkdtemp()
        try:
            projects = os.path.join(tmp, "projects")
            state = State(os.path.join(projects, "default"))
            folder = os.path.join(projects, "proj1")
            os.makedirs(folder, exist_ok=True)
            save_project(new_project("p1"),
                         os.path.join(folder, "project.vibeedit.json"))
            state.record_recent(folder)
            self.assertEqual(len(state.recent_projects()), 1)
            self.assertEqual(state.recent_projects()[0]["folder"], "proj1")
            state.remove_recent("proj1")
            self.assertEqual(state.recent_projects(), [])
            # Removing the recent entry must not delete project files.
            self.assertTrue(os.path.isfile(
                os.path.join(folder, "project.vibeedit.json")))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestNewTransitionsAndUi(unittest.TestCase):
    def test_new_transition_kinds_present_and_renderable(self):
        for kind in ("shutter", "double-exposure", "seamless-zoom",
                     "infinite-zoom", "crash-zoom", "blur", "flash",
                     "blink", "roll", "roll-right"):
            self.assertIn(kind, TRANSITION_XFADE)
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            # Second clip + a shutter transition, rendered for real.
            clip2 = proj.add_clip(clip["media"], "v1", 60, 0, 60)
            proj.add_transition(clip["id"], clip2["id"], "shutter", 0.5)
            out = os.path.join(tmp, "trans.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            with self.assertRaises(ValueError):
                proj.add_transition(clip["id"], clip2["id"], "spin", 0.5)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_new_ui_ids_present_no_duplicates(self):
        html_path = os.path.join(os.path.dirname(__file__), "..",
                                 "static", "index.html")
        with open(html_path, encoding="utf-8") as fh:
            html = fh.read()
        for marker in ("welcomePanel", "btnWelcome", "welcomeRecent",
                       "btnWelcomeReveal", "btnWelcomeCopyPath",
                       "exportPresetSelect", "btnExportPreset",
                       "btnReviewRun", "btnReviewAccept", "btnReviewVerify",
                       "reviewWorkflowResult", "speedCurveForm",
                       "speedCurvePreset", "btnClipReverse", "btnClipFreeze",
                       "btnLibraryAdd", "libraryList", "brandForm",
                       "brandColours", "brandLogoMedia", "pluginList",
                       "btnPluginReload"):
            self.assertIn(f'id="{marker}"', html, marker)
        ids = re.findall(r'id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)), "duplicate ids")
        self.assertIn("data:image/png;base64,", html)
        js_path = os.path.join(os.path.dirname(__file__), "..",
                               "static", "app.js")
        with open(js_path, encoding="utf-8") as fh:
            js = fh.read()
        for ident in sorted(set(re.findall(r'\$\("([^"]+)"\)', js))):
            self.assertIn(f'id="{ident}"', html,
                          f"app.js id {ident} missing from index.html")

    def test_mcp_count_is_472(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(TOOLS), 481)  # Round 23: 479 -> 481 (skills_import_plan/import)
        self.assertEqual(len(names), len(set(names)))
        for name in ("vibeedit_timeline_redo", "vibeedit_adjustments_list",
                     "vibeedit_beats_list", "vibeedit_track_get",
                     "vibeedit_media_get", "vibeedit_speed_curve_apply",
                     "vibeedit_clip_reverse", "vibeedit_clip_freeze",
                     "vibeedit_review_run", "vibeedit_review_accept",
                     "vibeedit_review_verify", "vibeedit_library_add",
                     "vibeedit_library_list", "vibeedit_library_place",
                     "vibeedit_library_remove", "vibeedit_brand_set",
                     "vibeedit_brand_get", "vibeedit_export_preset",
                     "vibeedit_plugin_list", "vibeedit_plugin_enable",
                     "vibeedit_plugin_disable"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
