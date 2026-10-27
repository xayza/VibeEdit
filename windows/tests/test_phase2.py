"""Phase 2 tests: transitions, keyframes, SRT, LUT/colour, MCP expansion.

Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
Media is generated with FFmpeg into temp folders; no network, no Swift.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.project import (Project, new_project,
                                   interpolate_keyframes, keyframe_points,
                                   validate_cube)
from vibeedit_core.render import render, probe_media
from vibeedit_core.mcp import MCPServer, TOOLS


def make_project():
    data = new_project("P2", width=320, height=180, fps=(30, 1))
    proj = Project(data, ".")
    proj.add_media("clip1.mp4", kind="video", fps=[30, 1], frames=90,
                   width=320, height=180, hasAudio=True)
    proj.add_media("clip2.mp4", kind="video", fps=[30, 1], frames=90,
                   width=320, height=180, hasAudio=True)
    return proj


def gen_clip(path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=320x180:rate=30:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class TestTransitions(unittest.TestCase):
    def setUp(self):
        self.proj = make_project()
        m1 = self.proj.data["media"][0]["id"]
        m2 = self.proj.data["media"][1]["id"]
        self.c1 = self.proj.add_clip(m1, "v1", 0, 0, 90)
        self.c2 = self.proj.add_clip(m2, "v1", 90, 0, 90)

    def test_valid_transition_stores_frames(self):
        trans = self.proj.add_transition(self.c1["id"], self.c2["id"],
                                         "dissolve", 0.5)
        self.assertEqual(trans["duration"], 15)  # 0.5s at 30fps
        self.assertEqual(trans["from"], self.c1["id"])

    def test_transition_validation(self):
        with self.assertRaises(ValueError):
            self.proj.add_transition(self.c1["id"], self.c2["id"],
                                     "explode", 0.5)
        with self.assertRaises(ValueError):
            self.proj.add_transition(self.c1["id"], self.c2["id"],
                                     "dissolve", 0.05)
        with self.assertRaises(ValueError):
            self.proj.add_transition(self.c1["id"], self.c2["id"],
                                     "dissolve", 2.5)
        with self.assertRaises(ValueError):
            self.proj.add_transition(self.c1["id"], self.c2["id"],
                                     "dissolve", 3.5)  # longer than a clip
        self.proj.add_transition(self.c1["id"], self.c2["id"], "wipe-left", 0.5)
        with self.assertRaises(ValueError):
            self.proj.add_transition(self.c1["id"], self.c2["id"],
                                     "dissolve", 0.5)  # duplicate cut

    def test_gap_blocks_transition(self):
        proj = make_project()
        m1 = proj.data["media"][0]["id"]
        m2 = proj.data["media"][1]["id"]
        a = proj.add_clip(m1, "v1", 0, 0, 90)
        b = proj.add_clip(m2, "v1", 120, 0, 90)  # 30-frame gap
        with self.assertRaises(ValueError):
            proj.add_transition(a["id"], b["id"], "dissolve", 0.5)


class TestKeyframes(unittest.TestCase):
    def test_linear_interpolation_and_clamping(self):
        points = [(0.0, 0.0), (2.0, 1.0)]
        self.assertAlmostEqual(interpolate_keyframes(points, 1.0), 0.5)
        self.assertEqual(interpolate_keyframes(points, -1.0), 0.0)
        self.assertEqual(interpolate_keyframes(points, 5.0), 1.0)
        self.assertIsNone(interpolate_keyframes([], 1.0))

    def test_set_keyframes_validation(self):
        proj = make_project()
        m1 = proj.data["media"][0]["id"]
        clip = proj.add_clip(m1, "v1", 0, 0, 90)
        with self.assertRaises(ValueError):
            proj.set_keyframes(clip["id"], [{"at": 999, "opacity": 0.5}])
        with self.assertRaises(ValueError):
            proj.set_keyframes(clip["id"], [{"at": 30, "opacity": 1.5}])
        with self.assertRaises(ValueError):
            proj.set_keyframes(clip["id"], [{"at": 30, "bogus": 1.0}])
        proj.set_keyframes(clip["id"], [{"at": 0, "opacity": 0.2},
                                        {"at": 60, "opacity": 0.9}])
        pts = keyframe_points(clip, "opacity", (30, 1))
        self.assertEqual(pts, [(0.0, 0.2), (2.0, 0.9)])

    def test_add_keyframe_merges_same_time(self):
        proj = make_project()
        m1 = proj.data["media"][0]["id"]
        clip = proj.add_clip(m1, "v1", 0, 0, 90)
        proj.add_keyframe(clip["id"], 1.0, "x", 0.25)
        proj.add_keyframe(clip["id"], 1.0, "y", 0.75)
        self.assertEqual(len(clip["keyframes"]), 1)
        self.assertEqual(clip["keyframes"][0]["x"], 0.25)
        self.assertEqual(clip["keyframes"][0]["y"], 0.75)


class TestSRT(unittest.TestCase):
    SRT = ("1\n00:00:01,000 --> 00:00:02,500\nHello world\n\n"
           "2\n00:00:03,000 --> 00:00:04,000\nSecond line\n")

    def test_import_export_round_trip(self):
        proj = make_project()
        items = proj.import_srt("t1", self.SRT)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["text"], "Hello world")
        self.assertEqual(items[0]["at"], 30)
        self.assertEqual(items[0]["dur"], 45)
        out = proj.export_srt("t1")
        self.assertIn("00:00:01,000 --> 00:00:02,500", out)
        self.assertIn("Hello world", out)
        self.assertIn("00:00:03,000 --> 00:00:04,000", out)

    def test_import_rejects_overlaps_and_bad_timecodes(self):
        proj = make_project()
        with self.assertRaises(ValueError):
            proj.import_srt("t1", "1\n00:00:01,000 --> 00:00:03,000\nA\n\n"
                                  "2\n00:00:02,000 --> 00:00:04,000\nB\n")
        with self.assertRaises(ValueError):
            proj.import_srt("t1", "1\nnot-a-timecode\nHello\n")
        # Nothing is added when validation fails part-way.
        self.assertEqual(len(proj.data["tracks"][2]["items"]), 0)

    def test_import_rejects_media_track(self):
        proj = make_project()
        with self.assertRaises(ValueError):
            proj.import_srt("v1", self.SRT)


class TestColor(unittest.TestCase):
    def test_invalid_lut_errors(self):
        proj = make_project()
        m1 = proj.data["media"][0]["id"]
        clip = proj.add_clip(m1, "v1", 0, 0, 90)
        with self.assertRaises(ValueError):
            proj.set_color(clip["id"], lut="/tmp/does-not-exist.cube")
        with self.assertRaises(ValueError):
            proj.set_color(clip["id"], preset="neon")
        tmp = tempfile.mkdtemp()
        try:
            bad = os.path.join(tmp, "bad.cube")
            with open(bad, "w") as fh:
                fh.write("this is not a lut\n")
            with self.assertRaises(ValueError):
                validate_cube(bad)
            good = os.path.join(tmp, "good.cube")
            with open(good, "w") as fh:
                fh.write('TITLE "t"\nLUT_3D_SIZE 2\n0 0 0\n0 0 1\n0 1 0\n'
                         '0 1 1\n1 0 0\n1 0 1\n1 1 0\n1 1 1\n')
            self.assertEqual(validate_cube(good), 2)
            item = proj.set_color(clip["id"], lut=good, preset="vivid")
            self.assertEqual(item["color"]["preset"], "vivid")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestMCPPhase2(unittest.TestCase):
    def test_tool_count_and_new_tools_call_real_code(self):
        names = [t["name"] for t in TOOLS]
        self.assertGreaterEqual(len(names), 19)
        for expected in ("vibeedit_media_place", "vibeedit_clip_trim",
                         "vibeedit_clip_split", "vibeedit_clip_move",
                         "vibeedit_clip_delete", "vibeedit_text_add",
                         "vibeedit_clip_speed", "vibeedit_transition_set",
                         "vibeedit_transition_remove", "vibeedit_srt_import",
                         "vibeedit_srt_export", "vibeedit_export_status",
                         "vibeedit_clip_keyframes", "vibeedit_clip_color"):
            self.assertIn(expected, names)
        tmp = tempfile.mkdtemp()
        try:
            server = MCPServer()
            server.call("vibeedit_project_create",
                        {"name": "mcp2", "directory": tmp})
            server.call("vibeedit_text_add",
                        {"track": "t1", "text": "Hi", "at": 0, "dur": 30})
            srt = server.call("vibeedit_srt_export", {"track": "t1"})
            self.assertIn("Hi", srt["srt"])
            imported = server.call("vibeedit_srt_import",
                                   {"track": "t1",
                                    "srt": "1\n00:00:02,000 --> 00:00:03,000\nYo\n"})
            self.assertEqual(imported["imported"], 1)
            status = server.call("vibeedit_export_status", {})
            self.assertIsNone(status["last_export"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestPhase2Renders(unittest.TestCase):
    def test_crossfade_render_duration(self):
        tmp = tempfile.mkdtemp()
        try:
            for name in ("clip1.mp4", "clip2.mp4"):
                gen_clip(os.path.join(tmp, name))
            data = new_project("XF", width=320, height=180, fps=(30, 1))
            proj = Project(data, tmp)
            for name in ("clip1.mp4", "clip2.mp4"):
                info = probe_media(os.path.join(tmp, name))
                proj.add_media(name, kind="video", **info)
            m1, m2 = proj.data["media"][0]["id"], proj.data["media"][1]["id"]
            c1 = proj.add_clip(m1, "v1", 0, 0, 90)
            c2 = proj.add_clip(m2, "v1", 90, 0, 90)
            proj.add_transition(c1["id"], c2["id"], "dissolve", 0.5)
            out = os.path.join(tmp, "xf.mp4")
            report = render(proj.data, tmp, out, preset="full")
            probe = ffprobe(out)
            video = [s for s in probe["streams"]
                     if s["codec_type"] == "video"][0]
            audio = [s for s in probe["streams"]
                     if s["codec_type"] == "audio"]
            self.assertEqual((int(video["width"]), int(video["height"])),
                             (320, 180))
            self.assertTrue(audio, "crossfade export must contain audio")
            # 3.0 + 3.0 - 0.5 transition = 5.5 s.
            self.assertAlmostEqual(float(probe["format"]["duration"]),
                                   5.5, delta=0.6)
            self.assertEqual(report["transitions"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_opacity_keyframe_overlay_render(self):
        tmp = tempfile.mkdtemp()
        try:
            for name in ("clip1.mp4", "clip2.mp4"):
                gen_clip(os.path.join(tmp, name))
            data = new_project("OP", width=320, height=180, fps=(30, 1))
            proj = Project(data, tmp)
            for name in ("clip1.mp4", "clip2.mp4"):
                info = probe_media(os.path.join(tmp, name))
                proj.add_media(name, kind="video", **info)
            m1, m2 = proj.data["media"][0]["id"], proj.data["media"][1]["id"]
            proj.add_clip(m1, "v1", 0, 0, 90)
            ov = proj.add_clip(m2, "v2", 0, 0, 90)
            proj.set_keyframes(ov["id"], [{"at": 0, "opacity": 0.2},
                                          {"at": 90, "opacity": 0.9}])
            out = os.path.join(tmp, "op.mp4")
            report = render(proj.data, tmp, out, preset="full")
            probe = ffprobe(out)
            self.assertAlmostEqual(float(probe["format"]["duration"]),
                                   3.0, delta=0.6)
            # Two opacity keyframes at the clip edges => one segment.
            self.assertEqual(report["overlay_clips"], 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_wipe_and_volume_keyframes_render(self):
        tmp = tempfile.mkdtemp()
        try:
            for name in ("clip1.mp4", "clip2.mp4"):
                gen_clip(os.path.join(tmp, name))
            data = new_project("WV", width=320, height=180, fps=(30, 1))
            proj = Project(data, tmp)
            for name in ("clip1.mp4", "clip2.mp4"):
                info = probe_media(os.path.join(tmp, name))
                proj.add_media(name, kind="video", **info)
            m1, m2 = proj.data["media"][0]["id"], proj.data["media"][1]["id"]
            c1 = proj.add_clip(m1, "v1", 0, 0, 90)
            c2 = proj.add_clip(m2, "v1", 90, 0, 90)
            proj.add_transition(c1["id"], c2["id"], "wipe-right", 0.5)
            proj.set_keyframes(c1["id"], [{"at": 0, "volume": -6.0},
                                          {"at": 90, "volume": 0.0}])
            out = os.path.join(tmp, "wv.mp4")
            render(proj.data, tmp, out, preset="full")
            probe = ffprobe(out)
            self.assertAlmostEqual(float(probe["format"]["duration"]),
                                   5.5, delta=0.6)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
