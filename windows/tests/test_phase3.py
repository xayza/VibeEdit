"""Phase 3 tests: new transitions, main-track keyframes, LUT
strength, OTIO, batch, plugins, new MCP tools. Real FFmpeg renders
where the claim is about rendering.

Run from windows/:  python3 -m unittest discover -s tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.export_ops import (  # noqa: E402
    batch_export, duplicate_project, export_otio, media_metadata)
from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.plugins import load_plugins, apply_plugin  # noqa: E402
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import render, probe_media  # noqa: E402


def gen_clip(path, seconds=3):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def make_project(tmp):
    data = new_project("phase3", width=320, height=180, fps=(30, 1))
    return Project(data, tmp)


def add_clip(proj, name, track, at, dur):
    info = probe_media(os.path.join(proj.folder, name))
    medium = proj.add_media(name, kind="video", **info)
    return proj.add_clip(medium["id"], track, at, 0, dur)


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def duration(path):
    return float(ffprobe(path)["format"]["duration"])


class TestPhase3Transitions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        gen_clip(os.path.join(self.tmp, "c2.mp4"))
        self.proj = make_project(self.tmp)
        self.i1 = add_clip(self.proj, "c1.mp4", "v1", 0, 90)
        self.i2 = add_clip(self.proj, "c2.mp4", "v1", 90, 90)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_kinds_accepted(self):
        for kind in ("whip-left", "whip", "iris-open", "iris-close",
                     "zoom-in", "glitch", "fadeblack", "smooth-left",
                     "cover-left", "reveal-right", "diag-tl", "hblur",
                     "fadegrays", "squeezeh", "vert-open", "horz-open",
                     "circlecrop", "distance", "wipe-tl"):
            self.proj.data["transitions"] = []
            t = self.proj.add_transition(self.i1["id"], self.i2["id"],
                                         kind, 0.5)
            self.assertEqual(t["kind"], kind)

    def test_unknown_kind_rejected_never_dissolve(self):
        for kind in ("shrink-ray", "warp-drive"):
            with self.assertRaises(ValueError):
                self.proj.add_transition(self.i1["id"], self.i2["id"],
                                         kind, 0.5)
        self.assertEqual(self.proj.data["transitions"], [])

    def test_whip_render_duration(self):
        self.proj.add_transition(self.i1["id"], self.i2["id"],
                                 "whip-left", 0.5)
        out = os.path.join(self.tmp, "whip.mp4")
        report = render(self.proj.data, self.tmp, out, preset="full")
        self.assertEqual(report["transitions"], 1)
        self.assertAlmostEqual(duration(out), 5.5, delta=0.6)

    def test_zoom_render_duration(self):
        self.proj.add_transition(self.i1["id"], self.i2["id"],
                                 "zoom-in", 0.5)
        out = os.path.join(self.tmp, "zoom.mp4")
        render(self.proj.data, self.tmp, out, preset="full")
        self.assertAlmostEqual(duration(out), 5.5, delta=0.6)


class TestMainTrackKeyframes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        self.proj = make_project(self.tmp)
        self.item = add_clip(self.proj, "c1.mp4", "v1", 0, 90)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _render(self, name):
        out = os.path.join(self.tmp, name)
        report = render(self.proj.data, self.tmp, out, preset="full")
        self.assertAlmostEqual(duration(out), 3.0, delta=0.6)
        return report

    def test_scale_keyframes_render(self):
        self.proj.set_keyframes(self.item["id"], [
            {"at": 0, "scale": 1.0}, {"at": 90, "scale": 1.5}])
        report = self._render("scale.mp4")
        self.assertFalse([s for s in report["skipped"]
                          if "motion" in s or "opacity" in s])

    def test_position_keyframes_render(self):
        self.proj.set_keyframes(self.item["id"], [
            {"at": 0, "x": 0.0}, {"at": 90, "x": 1.0}])
        self._render("pos.mp4")

    def test_opacity_keyframes_render(self):
        self.proj.set_keyframes(self.item["id"], [
            {"at": 0, "opacity": 0.2}, {"at": 90, "opacity": 0.9}])
        self._render("op.mp4")

    def test_volume_keyframes_render(self):
        self.proj.set_keyframes(self.item["id"], [
            {"at": 0, "volume": -6.0}, {"at": 90, "volume": 0.0}])
        self._render("vol.mp4")

    def test_motion_plus_opacity_reports_skip(self):
        self.proj.set_keyframes(self.item["id"], [
            {"at": 0, "scale": 1.0, "opacity": 0.2},
            {"at": 90, "scale": 1.5, "opacity": 0.9}])
        report = self._render("both.mp4")
        self.assertTrue(any("motion" in s for s in report["skipped"]))


class TestLutStrength(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"), seconds=2)
        self.proj = make_project(self.tmp)
        self.item = add_clip(self.proj, "c1.mp4", "v1", 0, 60)
        red = ("LUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n"
               + "1 0 0\n" * 8)
        self.lut = os.path.join(self.tmp, "red.cube")
        with open(self.lut, "w") as fh:
            fh.write(red)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _vavg(self, path):
        # FFmpeg 8 signalstats only exposes its stats as frame
        # metadata; metadata=print dumps them (lavfi.signalstats.*).
        out = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-vf",
                              "signalstats,metadata=print:file=-",
                              "-f", "null", "-"],
                             capture_output=True, text=True, timeout=120)
        # metadata=print writes to stdout (file=-), not stderr.
        lines = [ln for ln in (out.stdout + out.stderr).splitlines()
                 if "lavfi.signalstats.VAVG=" in ln]
        self.assertTrue(lines, "no signalstats output")
        return float(lines[-1].split("=")[1])

    def test_strength_0_near_original_and_1_differs(self):
        self.proj.set_color(self.item["id"], lut=self.lut, strength=0.0)
        out0 = os.path.join(self.tmp, "s0.mp4")
        render(self.proj.data, self.tmp, out0, preset="full")
        self.proj.set_color(self.item["id"], lut=self.lut, strength=1.0)
        out1 = os.path.join(self.tmp, "s1.mp4")
        render(self.proj.data, self.tmp, out1, preset="full")
        # set_color(None) does not clear an existing colour, so clear
        # the dict directly for a true no-LUT reference render.
        self.item["color"] = {}
        out_ref = os.path.join(self.tmp, "ref.mp4")
        render(self.proj.data, self.tmp, out_ref, preset="full")
        m0, m1, mref = (self._vavg(out0), self._vavg(out1),
                        self._vavg(out_ref))
        self.assertAlmostEqual(m0, mref, delta=20.0)
        self.assertGreater(abs(m1 - mref), 30.0)

    def test_strength_validation(self):
        with self.assertRaises(ValueError):
            self.proj.set_color(self.item["id"], strength=1.5)
        with self.assertRaises(ValueError):
            self.proj.set_color(self.item["id"], strength=-0.1)


class TestOtioAndBatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        gen_clip(os.path.join(self.tmp, "c2.mp4"))
        self.proj = make_project(self.tmp)
        self.i1 = add_clip(self.proj, "c1.mp4", "v1", 0, 90)
        self.i2 = add_clip(self.proj, "c2.mp4", "v1", 90, 90)
        self.proj.add_marker("intro", 0)
        self.proj.add_transition(self.i1["id"], self.i2["id"],
                                 "dissolve", 0.5)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_otio_structure(self):
        out = os.path.join(self.tmp, "timeline.otio")
        report = export_otio(self.proj.data, self.tmp, out)
        with open(out, encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["OTIO_SCHEMA"], "Timeline.1")
        # OTIO Timeline.tracks is a Stack whose children are Tracks.
        self.assertEqual(doc["tracks"]["OTIO_SCHEMA"], "Stack.1")
        stack = doc["tracks"]["children"]
        self.assertTrue(any(t["OTIO_SCHEMA"] == "Track.1" for t in stack))
        clips = [c for t in stack for c in t["children"]
                 if c["OTIO_SCHEMA"] == "Clip.1"]
        self.assertEqual(len(clips), 2)
        self.assertEqual(clips[0]["source_range"]["start_time"]["value"], 0)
        self.assertEqual(clips[0]["source_range"]["duration"]["value"], 90)
        trans = [c for t in stack for c in t["children"]
                 if c["OTIO_SCHEMA"] == "Transition.1"]
        self.assertEqual(len(trans), 1)
        self.assertEqual(trans[0]["transition_type"], "SMPTE_Dissolve")
        # Markers live on the Stack (Timeline.tracks) in this export.
        markers = [c for c in doc["tracks"].get("markers", [])
                   if c["OTIO_SCHEMA"] == "Marker.1"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(report["clips"], 2)
        self.assertEqual(report["transitions"], 1)

    def test_batch_success_and_failure(self):
        good = os.path.join(self.tmp, "good")
        os.makedirs(os.path.join(good, "media"))
        shutil.copy(os.path.join(self.tmp, "c1.mp4"),
                    os.path.join(good, "media", "c1.mp4"))
        proj2 = Project(new_project("good", width=320, height=180,
                                    fps=(30, 1)), good)
        info = probe_media(os.path.join(good, "media", "c1.mp4"))
        m2 = proj2.add_media("media/c1.mp4", kind="video", **info)
        proj2.add_clip(m2["id"], "v1", 0, 0, 60)
        from vibeedit_core.project import save_project
        save_project(proj2.data,
                     os.path.join(good, "project.vibeedit.json"))
        results = batch_export([good, os.path.join(self.tmp, "missing")],
                               preset="draft")
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0]["ok"])
        self.assertFalse(results[1]["ok"])
        self.assertIn("error", results[1])

    def test_duplicate_and_metadata(self):
        from vibeedit_core.project import save_project, load_project
        save_project(self.proj.data,
                     os.path.join(self.tmp, "project.vibeedit.json"))
        dest = os.path.join(self.tmp, "copy")
        # duplicate_project returns the new project FILE path.
        path = duplicate_project(self.tmp, dest, "phase3copy")
        self.assertTrue(os.path.isfile(path))
        proj2 = Project(load_project(path), dest)
        self.assertEqual(proj2.data["name"], "phase3copy")
        self.assertNotEqual(proj2.data["id"], self.proj.data["id"])
        media_id = self.proj.data["media"][0]["id"]
        meta = media_metadata(self.proj.data, self.tmp, media_id)
        self.assertTrue(meta["probed"])
        self.assertIn("width", meta)


class TestPluginsAndMcp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.proj = make_project(self.tmp)
        self.text = self.proj.add_text("t1", "hello", 0, 30)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plugin_list_and_run(self):
        plugins = load_plugins()
        self.assertIn("uppercase_text", plugins)
        self.assertIn("vivid_color", plugins)
        item = apply_plugin(self.proj, "uppercase_text",
                            "transform_text", self.text["id"])
        self.assertEqual(item["text"], "HELLO")
        with self.assertRaises(KeyError):
            apply_plugin(self.proj, "nope", "transform_text",
                         self.text["id"])

    def test_mcp_total_and_new_tools(self):
        self.assertGreaterEqual(len(TOOLS), 38)
        names = {t["name"] for t in TOOLS}
        for name in ("vibeedit_markers_add", "vibeedit_transitions_list",
                     "vibeedit_keyframes_get", "vibeedit_clip_color_get",
                     "vibeedit_batch_queue", "vibeedit_batch_run",
                     "vibeedit_batch_status", "vibeedit_otio_export",
                     "vibeedit_project_duplicate", "vibeedit_media_metadata",
                     "vibeedit_export_normalized", "vibeedit_project_info"):
            self.assertIn(name, names)

    def test_mcp_marker_and_info_roundtrip(self):
        server = MCPServer()
        server.call("vibeedit_project_create",
                    {"name": "mcp3", "directory": self.tmp})
        out = server.call("vibeedit_markers_add",
                          {"text": "here", "at": 15})
        self.assertEqual(out["text"], "here")
        info = server.call("vibeedit_project_info", {})
        self.assertEqual(info["markers"], 1)
        self.assertEqual(info["name"], "mcp3")


if __name__ == "__main__":
    unittest.main()
