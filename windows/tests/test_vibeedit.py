"""Unit + render tests for the VibeEdit Windows MVP.

Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
Media is generated with FFmpeg (testsrc2 + sine tone) into a temp
folder; no real user footage, no network, no Swift toolchain needed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.project import (Project, new_project, load_project,
                                   save_project, frames_to_seconds,
                                   LEGACY_SCHEMA)
from vibeedit_core.render import render, probe_media


def make_project():
    data = new_project("Test", width=320, height=180, fps=(30, 1))
    return Project(data, ".")


class TestProjectOps(unittest.TestCase):
    def setUp(self):
        self.proj = make_project()
        self.proj.add_media("clip1.mp4", kind="video",
                            fps=[30, 1], frames=90, width=320, height=180,
                            hasAudio=True)
        self.proj.add_media("clip2.mp4", kind="video",
                            fps=[30, 1], frames=90, width=320, height=180,
                            hasAudio=True)

    def test_add_trim_split_move_delete(self):
        clip = self.proj.add_clip("m-0001-xxxxxx" if False else
                                  self.proj.data["media"][0]["id"],
                                  "v1", 0, 0, 90)
        self.assertEqual(clip["dur"], 90)
        # Overlap on the same track is rejected.
        with self.assertRaises(ValueError):
            self.proj.add_clip(self.proj.data["media"][1]["id"], "v1", 45, 0, 30)
        trimmed = self.proj.trim(clip["id"], "end", 60)
        self.assertEqual(trimmed["dur"], 60)
        right = self.proj.split(clip["id"], 30)
        self.assertEqual(clip["dur"], 30)
        self.assertEqual(right["at"], 30)
        self.assertEqual(right["dur"], 30)
        self.assertNotEqual(right["id"], clip["id"])
        moved = self.proj.move(right["id"], "v2", 0)
        self.assertEqual(moved["at"], 0)
        self.proj.delete(right["id"])
        with self.assertRaises(KeyError):
            self.proj.item(right["id"])

    def test_text_and_speed(self):
        text = self.proj.add_text("t1", "Hello VibeEdit", 0, 60)
        self.assertEqual(text["text"], "Hello VibeEdit")
        clip = self.proj.add_clip(self.proj.data["media"][0]["id"],
                                  "v1", 0, 0, 60, speed=2.0)
        self.assertEqual(clip["speed"], 2.0)
        self.assertEqual(frames_to_seconds(60, (30, 1)), 2.0)

    def test_save_load_preserves_unknown_fields_and_legacy_schema(self):
        self.proj.data["futureField"] = {"kept": True}
        self.proj.data["schema"] = LEGACY_SCHEMA
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "project.vibeedit.json")
            save_project(self.proj.data, path)
            loaded = load_project(path)
            self.assertEqual(loaded["futureField"], {"kept": True})
            self.assertEqual(loaded["schema"], LEGACY_SCHEMA)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_undo_snapshot(self):
        before = self.proj.snapshot()
        self.proj.add_text("t1", "x", 0, 30)
        self.assertEqual(len(self.proj.data["tracks"][2]["items"]), 1)
        self.proj.restore(before)
        self.assertEqual(len(self.proj.data["tracks"][2]["items"]), 0)


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class TestRender(unittest.TestCase):
    def test_two_clips_text_speed_export(self):
        tmp = tempfile.mkdtemp()
        try:
            # Two generated clips: video + tone audio, 3 s each.
            for name in ("clip1.mp4", "clip2.mp4"):
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "lavfi",
                     "-i", "testsrc2=size=320x180:rate=30:duration=3",
                     "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                     "-c:v", "libx264", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-shortest",
                     os.path.join(tmp, name)],
                    capture_output=True, check=True)
            data = new_project("RenderTest", width=320, height=180, fps=(30, 1))
            proj = Project(data, tmp)
            for name in ("clip1.mp4", "clip2.mp4"):
                info = probe_media(os.path.join(tmp, name))
                proj.add_media(name, kind="video", **info)
            m1, m2 = proj.data["media"][0]["id"], proj.data["media"][1]["id"]
            proj.add_clip(m1, "v1", 0, 0, 90, speed=1.0)
            # Second clip at 2x speed: 90 source frames play in 45 timeline
            # frames, so place it right after the first clip's 90 frames.
            proj.add_clip(m2, "v1", 90, 0, 45, speed=2.0)
            proj.add_text("t1", "VibeEdit", 0, 60)
            out = os.path.join(tmp, "export.mp4")
            report = render(proj.data, tmp, out, preset="full")
            self.assertTrue(os.path.isfile(out))
            self.assertGreater(os.path.getsize(out), 10000)
            probe = ffprobe(out)
            video = [s for s in probe["streams"]
                     if s["codec_type"] == "video"][0]
            audio = [s for s in probe["streams"]
                     if s["codec_type"] == "audio"]
            self.assertEqual((int(video["width"]), int(video["height"])),
                             (320, 180))
            self.assertTrue(audio, "export must contain an audio stream")
            duration = float(probe["format"]["duration"])
            # 3.0 s + 45 frames at 30 fps (1.5 s) = 4.5 s, allow encoder slack.
            self.assertAlmostEqual(duration, 4.5, delta=0.6)
            self.assertEqual(report["text_overlays"], 1)
            self.assertEqual(report["segments"], 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
