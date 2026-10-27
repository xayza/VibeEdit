"""Code-gap batch tests: per-parameter eq colour, Source In/Out insert,
Compare + project switcher markers, close-gaps, track rename/remove,
and the 17 new MCP tools (106 -> 123). Real FFmpeg render for eq.

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
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)
from vibeedit_core.render import _color_filters, render, probe_media  # noqa: E402
from vibeedit_core.server import State  # noqa: E402


def gen_clip(path, seconds=2):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def frame_mean(path, seconds=1.0):
    png = path + ".png"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(seconds), "-i", path,
         "-frames:v", "1", png], capture_output=True, check=True)
    from PIL import Image, ImageStat
    with Image.open(png) as im:
        return ImageStat.Stat(im.convert("RGB")).mean


def make_project(tmp):
    return Project(new_project("gap", width=320, height=180,
                                fps=(30, 1)), tmp)


def add_clip_project(tmp):
    gen_clip(os.path.join(tmp, "c1.mp4"))
    proj = make_project(tmp)
    info = probe_media(os.path.join(tmp, "c1.mp4"))
    medium = proj.add_media("c1.mp4", kind="video", **info)
    clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
    return proj, medium, clip


class TestEqColour(unittest.TestCase):
    def test_eq_stored_and_rendered(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            proj.set_color(clip["id"], eq={"brightness": 0.2,
                                           "contrast": 1.5})
            _, item = proj.item(clip["id"])
            self.assertEqual(item["color"]["eq"]["brightness"], 0.2)
            filters = _color_filters(item)
            self.assertTrue(any("brightness=0.2" in f and "contrast=1.5" in f
                                for f in filters))

        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_eq_validation(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            with self.assertRaises(ValueError):
                proj.set_color(clip["id"], eq={"hue": 1})
            with self.assertRaises(ValueError):
                proj.set_color(clip["id"], eq={"brightness": 5})
            with self.assertRaises(ValueError):
                proj.set_color(clip["id"], eq={})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_eq_clear(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            proj.set_color(clip["id"], eq={"saturation": 0.5})
            proj.set_color(clip["id"], clear_eq=True, clear_lut=True)
            _, item = proj.item(clip["id"])
            self.assertNotIn("eq", item.get("color") or {})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_eq_real_render_brightens(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, clip = add_clip_project(tmp)
            out_plain = os.path.join(tmp, "plain.mp4")
            render(proj.data, tmp, out_plain, preset="draft")
            proj.set_color(clip["id"], eq={"brightness": 0.5})
            out_bright = os.path.join(tmp, "bright.mp4")
            render(proj.data, tmp, out_bright, preset="draft")
            self.assertGreater(sum(frame_mean(out_bright)),
                               sum(frame_mean(out_plain)))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestCloseGapsAndTracks(unittest.TestCase):
    def test_close_gaps(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, medium, _ = add_clip_project(tmp)
            proj.add_clip(medium["id"], "v1", 90, 0, 30)
            result = proj.close_gaps("v1")
            _, second = proj.item(
                [i for i in proj.track("v1")["items"] if i["at"] == 60][0]["id"])
            self.assertEqual(second["at"], 60)
            self.assertIn(second["id"], result["moved"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_rename_and_remove_track(self):
        tmp = tempfile.mkdtemp()
        try:
            proj = make_project(tmp)
            track = proj.add_track("video", "overlay", "Layer X")
            proj.rename_track(track["id"], "Layer Y")
            self.assertEqual(proj.track(track["id"])["name"], "Layer Y")
            with self.assertRaises(ValueError):
                proj.remove_track("v1")  # Main is protected
            proj.remove_track(track["id"])
            self.assertNotIn(track["id"],
                             [t["id"] for t in proj.data["tracks"]])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_remove_populated_track_refused(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, _, _ = add_clip_project(tmp)
            with self.assertRaises(ValueError):
                proj.remove_track("v1")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestServerOpsAndProjects(unittest.TestCase):
    def test_source_insert_and_close_gaps_via_state(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_clip(os.path.join(tmp, "c1.mp4"))
            state = State(tmp)
            proj = state.project
            info = probe_media(os.path.join(tmp, "c1.mp4"))
            medium = proj.add_media("c1.mp4", kind="video", **info)
            state.save()
            result = state.apply({"op": "source_insert",
                                  "media": medium["id"], "in": 0,
                                  "out": 30, "at": 0})
            self.assertEqual(result["dur"], 30)
            result = state.apply({"op": "close_gaps", "track": "v1"})
            self.assertEqual(result["track"], "v1")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_projects_list_and_open(self):
        root = tempfile.mkdtemp()
        try:
            first = os.path.join(root, "first")
            os.makedirs(os.path.join(first, "media"))
            state = State(first)
            second = os.path.join(root, "second")
            os.makedirs(os.path.join(second, "media"))
            save_project(new_project("Second"),
                         os.path.join(second, "project.vibeedit.json"))
            names = [p["folder"] for p in state.list_projects()]
            self.assertIn("second", names)
            opened = state.open_project("second")
            self.assertEqual(opened["name"], "Second")
            self.assertEqual(state.project.data["name"], "Second")
            with self.assertRaises((ValueError, FileNotFoundError)):
                state.open_project("../outside")
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)


class TestOverwrite(unittest.TestCase):
    def test_overwrite_trims_and_splits(self):
        tmp = tempfile.mkdtemp()
        try:
            proj, medium, first = add_clip_project(tmp)
            # A long clip spanning the overwrite range, plus one inside it.
            proj.add_clip(medium["id"], "v1", 120, 0, 30)
            result = proj.overwrite_insert(medium["id"], 0, 30, 30)
            items = sorted(proj.track("v1")["items"], key=lambda i: i["at"])
            self.assertEqual(result["at"], 30)
            self.assertEqual(result["dur"], 30)
            # Original 0..60 clip is trimmed to 0..30; the new clip sits
            # at 30..60; the 120..150 clip is untouched.
            self.assertEqual([i["at"] for i in items], [0, 30, 120])
            self.assertEqual([i["dur"] for i in items], [30, 30, 30])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestNewMcpTools(unittest.TestCase):
    def test_tool_count_is_123(self):
        self.assertEqual(len(TOOLS), 479)  # Round 4: 478 -> 479 (app_update_prepare)
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        for expected in ("vibeedit_clip_color_eq",
                         "vibeedit_clip_color_eq_get",
                         "vibeedit_source_insert", "vibeedit_close_gaps",
                         "vibeedit_project_list", "vibeedit_track_rename",
                         "vibeedit_track_remove", "vibeedit_beat_nearest",
                         "vibeedit_marker_at_time",
                         "vibeedit_clip_overlap_check",
                         "vibeedit_media_usage",
                         "vibeedit_project_search_text",
                         "vibeedit_track_duration",
                         "vibeedit_clip_text_get",
                         "vibeedit_clip_color_reset",
                         "vibeedit_timeline_clip_count",
                         "vibeedit_source_overwrite"):
            self.assertIn(expected, names)

    def test_new_tools_execute(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_clip(os.path.join(tmp, "c1.mp4"))
            proj, medium, clip = add_clip_project(tmp)
            path = os.path.join(tmp, "project.vibeedit.json")
            save_project(proj.data, path)
            server = MCPServer(tmp)
            server.call("vibeedit_clip_color_eq",
                        {"item": clip["id"],
                         "eq": {"brightness": 0.1}})
            got = server.call("vibeedit_clip_color_eq_get",
                              {"item": clip["id"]})
            self.assertEqual(got["eq"]["brightness"], 0.1)
            usage = server.call("vibeedit_media_usage",
                                {"media": medium["id"]})
            self.assertEqual(len(usage["clips"]), 1)
            check = server.call("vibeedit_clip_overlap_check",
                                {"track": "v1", "at": 0, "dur": 10})
            self.assertFalse(check["free"])
            counts = server.call("vibeedit_timeline_clip_count", {})
            self.assertEqual(counts["total"], 1)
            dur = server.call("vibeedit_track_duration", {"track": "v1"})
            self.assertEqual(dur["end_frame"], 60)
            server.call("vibeedit_clip_color_reset", {"item": clip["id"]})
            got = server.call("vibeedit_clip_color_eq_get",
                              {"item": clip["id"]})
            self.assertEqual(got["eq"], {})
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestNewUiIds(unittest.TestCase):
    def test_new_ids_present_no_duplicates(self):
        html_path = os.path.join(os.path.dirname(__file__), "..",
                                 "static", "index.html")
        with open(html_path, encoding="utf-8") as fh:
            html = fh.read()
        for new_id in ("inspEqBrightness", "inspEqContrast",
                       "inspEqSaturation", "inspEqGamma", "btnColorReset",
                       "sourceMedia", "sourceIn", "sourceOut",
                       "btnSourceMarkIn", "btnSourceMarkOut",
                       "btnSourceInsert", "btnSourceOverwrite",
                       "sourceRangeStatus",
                       "btnPreviewCompareMode", "tlCloseGaps",
                       "compareWrap", "previewCompareSource",
                       "previewCompareExport",
                       "projectSelect", "btnProjectOpen",
                       "projectNewName", "btnProjectCreate"):
            self.assertIn(f'id="{new_id}"', html, new_id)
        ids = re.findall(r'id="([^"]+)"', html)
        dupes = [i for i in set(ids) if ids.count(i) > 1]
        self.assertEqual(dupes, [])
        self.assertIn("data:image", html)  # logo data URI intact


if __name__ == "__main__":
    unittest.main()
