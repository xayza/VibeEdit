"""Round 6: media_cuts for real.

Original semantics (CommandCatalog+Media.swift, media.cuts, .edit):
"Correct the cut list of an analysed media: add cuts or remove
candidates at source seconds (a removal matches within one sample
interval; removing an added cut takes it back). Shots and
statistics in media.analysis follow. Corrections live in the
record and are dropped when the file is measured again. Returns
the corrected cuts."

This build measures with FFmpeg's scene filter (threshold, default
0.4 — a different scale from the original's minScore, never claimed
equal) and stores the record on the media entry. Tests use a
synthetic clip with one real hard cut (red 1s -> blue 1s), never a
user sample.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))

from vibeedit_core.cuts import (  # noqa: E402
    apply_cut_corrections, detect_cuts)
from vibeedit_core.mcp import MCPServer  # noqa: E402
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)
from vibeedit_core.render import probe_media  # noqa: E402


def _make_cut_clip(path):
    """2s clip, 320x180, 30fps: 1s pure red, then 1s pure blue."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "color=c=red:s=320x180:r=30:d=1",
         "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=1",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         path],
        capture_output=True, check=True)


def _make_tone(path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:d=1",
         "-c:a", "aac", path],
        capture_output=True, check=True)


def _make_server(tmp, clip_path):
    proj = Project(new_project("r6cuts", width=320, height=180,
                               fps=(30, 1)), tmp)
    medium = proj.add_media(os.path.basename(clip_path), kind="video",
                            **probe_media(clip_path))
    save_project(proj.data, os.path.join(tmp, "project.vibeedit.json"))
    return MCPServer(tmp), medium


class TestApplyCutCorrections(unittest.TestCase):
    def test_add_and_remove_roundtrip(self):
        res = apply_cut_corrections([1.0], [1.0], add="0.5")
        self.assertEqual(res["cuts"], [0.5, 1.0])
        self.assertEqual(res["added"], [0.5])
        res = apply_cut_corrections([1.0], [0.5, 1.0], remove="0.5")
        self.assertEqual(res["cuts"], [1.0])
        self.assertEqual(res["removed"], [0.5])

    def test_removal_matches_within_one_frame_only(self):
        # 30fps -> one frame is ~0.033s; 0.03 matches, 0.2 does not.
        res = apply_cut_corrections([1.0], [1.0], remove="1.03",
                                    tolerance=1.0 / 30)
        self.assertEqual(res["cuts"], [])
        res = apply_cut_corrections([1.0], [1.0], remove="1.2",
                                    tolerance=1.0 / 30)
        self.assertEqual(res["cuts"], [1.0])
        self.assertEqual(res["removed_unmatched"], [1.2])

    def test_clear_drops_earlier_corrections_first(self):
        res = apply_cut_corrections([1.0], [0.5, 1.0], clear=True)
        self.assertEqual(res["cuts"], [1.0])
        res = apply_cut_corrections([1.0], [0.5, 1.0], clear=True,
                                    add="0.25")
        self.assertEqual(res["cuts"], [0.25, 1.0])

    def test_add_beyond_duration_rejected(self):
        with self.assertRaises(ValueError):
            apply_cut_corrections([1.0], [1.0], add="9.0", duration=2.0)

    def test_bad_entries_rejected(self):
        with self.assertRaises(ValueError):
            apply_cut_corrections([1.0], [1.0], add="soon")
        with self.assertRaises(ValueError):
            apply_cut_corrections([1.0], [1.0], remove="-1")


class TestDetectCuts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clip = os.path.join(self.tmp, "cut.mp4")
        _make_cut_clip(self.clip)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hard_cut_found_once(self):
        det = detect_cuts(self.clip)
        self.assertEqual(len(det["cuts"]), 1,
                         f"expected exactly one cut, got {det}")
        self.assertAlmostEqual(det["cuts"][0], 1.0, delta=0.1)
        self.assertEqual(det["threshold"], 0.4)

    def test_audio_only_has_no_picture_to_cut(self):
        tone = os.path.join(self.tmp, "tone.m4a")
        _make_tone(tone)
        with self.assertRaises(ValueError):
            detect_cuts(tone)

    def test_missing_file_and_bad_threshold(self):
        with self.assertRaises(FileNotFoundError):
            detect_cuts(os.path.join(self.tmp, "nope.mp4"))
        with self.assertRaises(ValueError):
            detect_cuts(self.clip, threshold=1.5)


class TestMediaCutsTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clip = os.path.join(self.tmp, "cut.mp4")
        _make_cut_clip(self.clip)
        self.server, self.medium = _make_server(self.tmp, self.clip)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detect_then_correct_then_remeasure(self):
        mid = self.medium["id"]
        first = self.server.call("vibeedit_media_cuts", {"media": mid})
        self.assertEqual(len(first["cuts"]), 1)
        self.assertAlmostEqual(first["cuts"][0], 1.0, delta=0.1)
        # First use measures (no record existed yet) and the
        # corrected list starts as the detected list.
        self.assertTrue(first["remeasured"])
        self.assertEqual(first["detected"], first["cuts"])
        added = self.server.call("vibeedit_media_cuts",
                                 {"media": mid, "add": "0.5"})
        self.assertEqual(added["cuts"], [0.5, first["cuts"][0]])
        self.assertFalse(added["remeasured"])
        removed = self.server.call("vibeedit_media_cuts",
                                   {"media": mid, "remove": "0.5"})
        self.assertEqual(removed["cuts"], first["cuts"])
        remeasured = self.server.call(
            "vibeedit_media_cuts", {"media": mid, "remeasure": True})
        self.assertTrue(remeasured["remeasured"])
        self.assertEqual(remeasured["cuts"], first["cuts"])

    def test_corrections_persist_and_analysis_follows(self):
        mid = self.medium["id"]
        self.server.call("vibeedit_media_cuts", {"media": mid})
        self.server.call("vibeedit_media_cuts",
                         {"media": mid, "add": "0.5"})
        reopened = MCPServer(self.tmp)
        analysis = reopened.call("vibeedit_media_analysis",
                                 {"media": mid})
        self.assertIn(0.5, analysis["analysis_cuts"])
        self.assertEqual(len(analysis["analysis_cuts_detected"]), 1)

    def test_needs_media(self):
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_media_cuts", {})


if __name__ == "__main__":
    unittest.main()
