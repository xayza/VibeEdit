"""Round 7: media.analyze pipeline for real (media_analyze,
media_analysis reading, media_speech_map, media_strip,
media_sync).

Original semantics (read-only, Swift tree): media.analyze
measures once and keeps the record by file content; media.analysis
derives cuts/shots/sound; speech-map splits 0.1 s RMS windows by
Otsu (silence left out; no separation -> spans null with a
reason); strip draws frames + levels + gaps + words as one PNG;
sync cross-correlates mono 8 kHz envelopes (below 0.4
correlation = no shared sound). Tests use synthetic clips in a
temp folder only, never a user sample.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), ".."))

from vibeedit_core.analysis import (  # noqa: E402
    content_key, otsu_calibrate)
from vibeedit_core.mcp import MCPServer  # noqa: E402
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)
from vibeedit_core.render import probe_media  # noqa: E402


def _run(args, path):
    subprocess.run(["ffmpeg", "-y", "-v", "error"] + args + [path],
                   capture_output=True, check=True)


def _make_av(path):
    """2 s, 320x180 30 fps green video + 440 Hz tone."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:d=2", "-f", "lavfi",
         "-i", "color=c=green:s=320x180:r=30:d=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", path], capture_output=True, check=True)


def _make_cut_clip(path):
    """2 s: 1 s pure red, then 1 s pure blue (one hard cut)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "color=c=red:s=320x180:r=30:d=1", "-f", "lavfi",
         "-i", "color=c=blue:s=320x180:r=30:d=1",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         path], capture_output=True, check=True)


def _make_tone(path, freq=440, seconds=6):
    _run(["-f", "lavfi", "-i",
          f"sine=frequency={freq}:d={seconds}", "-c:a", "aac"], path)


def _make_tone_gap_tone(path):
    """1 s tone, 1 s digital silence, 1 s tone (audio only)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:d=1", "-f", "lavfi",
         "-i", "anullsrc=r=48000:cl=mono:d=1", "-f", "lavfi",
         "-i", "sine=frequency=440:d=1",
         "-filter_complex",
         "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]",
         "-map", "[a]", "-c:a", "aac", path],
        capture_output=True, check=True)


def _make_quiet_loud(path):
    """1.5 s quiet tone (0.1) then 1.5 s loud tone (1.0)."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:d=1.5", "-f", "lavfi",
         "-i", "sine=frequency=440:d=1.5",
         "-filter_complex",
         "[0:a]volume=0.1[q];[1:a]volume=1.0[l];"
         "[q][l]concat=n=2:v=0:a=1[a]",
         "-map", "[a]", "-c:a", "aac", path],
        capture_output=True, check=True)


def _make_server(tmp, clip_path, kind="video"):
    proj = Project(new_project("r7", width=320, height=180,
                               fps=(30, 1)), tmp)
    medium = proj.add_media(os.path.basename(clip_path), kind=kind,
                            **probe_media(clip_path))
    save_project(proj.data, os.path.join(tmp, "project.vibeedit.json"))
    return MCPServer(tmp), medium, proj


class TestAnalyze(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r7-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_analyze_measures_reuses_and_forces(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        first = server.call("vibeedit_media_analyze",
                            {"media": medium["id"]})
        entry = first["results"][0]
        self.assertFalse(entry["reused"])
        self.assertTrue(entry["measured"])
        self.assertTrue(entry["hasPicture"])
        self.assertTrue(entry["hasSound"])
        self.assertEqual(entry["transcriptWords"], 0)
        self.assertIn("faster-whisper", entry["transcriptReason"])
        second = server.call("vibeedit_media_analyze",
                             {"media": medium["id"]})
        self.assertTrue(second["results"][0]["reused"])
        self.assertEqual(second["results"][0]["key"], entry["key"])
        forced = server.call("vibeedit_media_analyze",
                             {"media": medium["id"], "force": True})
        self.assertFalse(forced["results"][0]["reused"])

    def test_analyze_default_measures_all_media(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        cut = os.path.join(self.tmp, "cut.mp4")
        _make_cut_clip(cut)
        server, _m, proj = _make_server(self.tmp, clip)
        proj.add_media(os.path.basename(cut), kind="video",
                       **probe_media(cut))
        save_project(proj.data, os.path.join(
            self.tmp, "project.vibeedit.json"))
        server = MCPServer(self.tmp)
        result = server.call("vibeedit_media_analyze", {})
        self.assertEqual(len(result["results"]), 2)

    def test_analyze_persists_across_reopen(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        first = server.call("vibeedit_media_analyze",
                            {"media": medium["id"]})
        reopened = MCPServer(self.tmp)
        read = reopened.call("vibeedit_media_analysis",
                             {"media": medium["id"]})
        self.assertEqual(read["analysis_record"]["key"],
                         first["results"][0]["key"])
        self.assertIsNotNone(read["analysis_record"]["picture"])
        self.assertIsNotNone(read["analysis_record"]["sound"])

    def test_cut_candidate_at_exact_frame(self):
        clip = os.path.join(self.tmp, "cut.mp4")
        _make_cut_clip(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        read = server.call("vibeedit_media_analysis",
                           {"media": medium["id"]})
        cuts = read["analysis_record"]["picture"]["cuts"]
        self.assertEqual(len(cuts), 1)
        self.assertEqual(cuts[0]["frame"], 30)
        self.assertAlmostEqual(cuts[0]["seconds"], 1.0, delta=0.05)
        self.assertGreaterEqual(cuts[0]["score"], 0.04)
        shots = read["analysis_record"]["picture"]["shots"]
        self.assertEqual(len(shots), 2)
        self.assertAlmostEqual(shots[0]["seconds"], 1.0, delta=0.05)

    def test_analysis_sound_summary_and_curve(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        read = server.call("vibeedit_media_analysis",
                           {"media": medium["id"], "curve": True})
        sound = read["analysis_record"]["sound"]
        self.assertIn("floorDb", sound)
        self.assertIn("medianDb", sound)
        self.assertIn("loudDb", sound)
        self.assertIn("peakDb", sound)
        self.assertIn("activeShare", sound)
        self.assertIn("curve", sound)
        self.assertGreater(len(sound["curve"]), 0)

    def test_analysis_needs_media(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, _m, _p = _make_server(self.tmp, clip)
        with self.assertRaises(ValueError):
            server.call("vibeedit_media_analysis", {})

    def test_content_key_stable_on_rename_changed_on_edit(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        renamed = os.path.join(self.tmp, "renamed.mp4")
        shutil.copyfile(clip, renamed)
        self.assertEqual(content_key(clip), content_key(renamed))
        with open(renamed, "ab") as handle:
            handle.write(b"\x00" * 4096)
        self.assertNotEqual(content_key(clip), content_key(renamed))


class TestOtsu(unittest.TestCase):
    def test_bimodal_calibrates_constant_does_not(self):
        levels = [-50.0] * 10 + [-10.0] * 10
        cal = otsu_calibrate(levels)
        self.assertIsNotNone(cal)
        self.assertGreater(cal["speechDb"] - cal["floorDb"], 6)
        self.assertIsNone(otsu_calibrate([-20.0] * 30))
        self.assertIsNone(otsu_calibrate([-20.0] * 5 + [-10.0] * 4))


class TestSpeechMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r7-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_threshold_forces_spans_over_silence_gap(self):
        clip = os.path.join(self.tmp, "gap.m4a")
        _make_tone_gap_tone(clip)
        server, medium, _proj = _make_server(self.tmp, clip,
                                             kind="audio")
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        # Encoded silence decodes to digital silence plus quiet
        # edge windows, so Otsu splits tone from silence cleanly
        # on its own: spans over the two tone seconds, gap over
        # the silent second. (A file whose classes genuinely do
        # not separate is covered by test_none_when_classes_close
        # below, via a minSeparationDb the classes cannot meet.)
        plain = server.call("vibeedit_media_speech_map",
                            {"media": medium["id"]})
        self.assertEqual(plain["calibration"]["separation"], "clear")
        spans = [(s["start"], s["end"]) for s in plain["spans"]]
        self.assertEqual(len(spans), 2)
        self.assertAlmostEqual(spans[0][1], 1.0, delta=0.15)
        self.assertAlmostEqual(spans[1][0], 2.0, delta=0.15)
        gaps = [(g["start"], g["end"]) for g in plain["gaps"]]
        self.assertTrue(any(abs(g[0] - 1.0) < 0.15
                            and abs(g[1] - 2.0) < 0.15
                            for g in gaps))
        forced = server.call("vibeedit_media_speech_map",
                             {"media": medium["id"],
                              "thresholdDb": -50})
        self.assertEqual(forced["calibration"]["separation"], "given")
        spans = [(s["start"], s["end"]) for s in forced["spans"]]
        self.assertEqual(len(spans), 2)
        self.assertAlmostEqual(spans[0][0], 0.0, delta=0.15)
        self.assertAlmostEqual(spans[0][1], 1.0, delta=0.15)
        self.assertAlmostEqual(spans[1][0], 2.0, delta=0.15)

    def test_none_when_classes_close(self):
        clip = os.path.join(self.tmp, "ql.m4a")
        _make_quiet_loud(clip)
        server, medium, _proj = _make_server(self.tmp, clip,
                                             kind="audio")
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        # The quiet/loud classes are ~20 dB apart; a
        # minSeparationDb of 60 dB is one they cannot meet, so
        # separation must be none with spans/gaps null and a
        # reason -- never made-up silences.
        result = server.call("vibeedit_media_speech_map",
                             {"media": medium["id"],
                              "minSeparationDb": 60})
        self.assertEqual(result["calibration"]["separation"], "none")
        self.assertIsNone(result["spans"])
        self.assertIsNone(result["gaps"])
        self.assertIn("reason", result)

    def test_otsu_separates_quiet_from_loud(self):
        clip = os.path.join(self.tmp, "ql.m4a")
        _make_quiet_loud(clip)
        server, medium, _proj = _make_server(self.tmp, clip,
                                             kind="audio")
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        result = server.call("vibeedit_media_speech_map",
                             {"media": medium["id"]})
        self.assertIn(result["calibration"]["separation"],
                      ("clear", "weak"))
        spans = result["spans"]
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0]["start"], 1.5, delta=0.25)
        self.assertAlmostEqual(spans[0]["end"], 3.0, delta=0.25)

    def test_speech_map_rejects_video_without_audio(self):
        clip = os.path.join(self.tmp, "cut.mp4")
        _make_cut_clip(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        with self.assertRaises(ValueError):
            server.call("vibeedit_media_speech_map",
                        {"media": medium["id"]})


class TestStrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r7-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_strip_png_real_after_analyze(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        result = server.call("vibeedit_media_strip",
                             {"media": medium["id"]})
        self.assertEqual(result["levels"], "analysis")
        self.assertEqual(len(result["frames"]), 8)
        self.assertIsNotNone(result["path"])
        self.assertTrue(os.path.isfile(result["path"]))
        self.assertEqual(result["width"], 1600)
        from PIL import Image
        with Image.open(result["path"]) as image:
            self.assertEqual(image.width, 1600)
            self.assertGreater(image.height, 100)

    def test_strip_measures_levels_without_record(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        result = server.call("vibeedit_media_strip",
                             {"media": medium["id"], "count": 4,
                              "width": 800})
        self.assertEqual(result["levels"], "measured")
        self.assertEqual(len(result["frames"]), 4)
        self.assertTrue(os.path.isfile(result["path"]))

    def test_strip_audio_has_data_but_no_png(self):
        clip = os.path.join(self.tmp, "gap.m4a")
        _make_tone_gap_tone(clip)
        server, medium, _proj = _make_server(self.tmp, clip,
                                             kind="audio")
        server.call("vibeedit_media_analyze",
                    {"media": medium["id"]})
        result = server.call("vibeedit_media_strip",
                             {"media": medium["id"]})
        self.assertEqual(result["frames"], [])
        self.assertIsNone(result["path"])
        self.assertIsNotNone(result["pngReason"])

    def test_strip_rejects_bad_args(self):
        clip = os.path.join(self.tmp, "av.mp4")
        _make_av(clip)
        server, medium, _proj = _make_server(self.tmp, clip)
        for args in ({"media": medium["id"], "from": 1.5, "to": 1.0},
                     {"media": medium["id"], "count": 0},
                     {"media": medium["id"], "count": 25},
                     {"media": medium["id"], "width": 100}):
            with self.assertRaises(ValueError):
                server.call("vibeedit_media_strip", args)


class TestSync(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r7-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _two_media(self):
        a = os.path.join(self.tmp, "a.m4a")
        b = os.path.join(self.tmp, "b.m4a")
        _make_tone(a, 440, 6)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", a,
             "-af", "adelay=500:all=1", "-c:a", "aac", b],
            capture_output=True, check=True)
        server, first, proj = _make_server(self.tmp, a, kind="audio")
        second = proj.add_media(os.path.basename(b), kind="audio",
                                **probe_media(b))
        save_project(proj.data, os.path.join(
            self.tmp, "project.vibeedit.json"))
        return MCPServer(self.tmp), first, second, proj

    def test_known_half_second_offset(self):
        server, first, second, _proj = self._two_media()
        result = server.call("vibeedit_media_sync",
                             {"media": first["id"],
                              "to": second["id"]})
        self.assertAlmostEqual(result["offsetSeconds"], 0.5,
                               delta=0.02)
        self.assertGreaterEqual(result["correlation"], 0.9)
        self.assertTrue(result["sharedSound"])
        self.assertTrue(result["steady"])
        self.assertEqual(len(result["halves"]), 2)

    def test_sync_maps_clip_in_point(self):
        server, first, second, proj = self._two_media()
        item = proj.add_clip(first["id"], "v1", at=0, in_frame=30)
        save_project(proj.data, os.path.join(
            self.tmp, "project.vibeedit.json"))
        server = MCPServer(self.tmp)
        result = server.call("vibeedit_media_sync",
                             {"media": first["id"],
                              "to": second["id"],
                              "item": item["id"]})
        # In-point 30 frames at 30 fps = 1.0 s in the first file;
        # +0.5 s offset = 1.5 s (frame 45) in the second.
        self.assertAlmostEqual(result["item"]["mediaInSeconds"],
                               1.0, delta=0.02)
        self.assertAlmostEqual(result["item"]["toSeconds"], 1.5,
                               delta=0.03)
        self.assertEqual(result["item"]["toFrame"], 45)

    def test_sync_no_shared_sound_below_threshold(self):
        a = os.path.join(self.tmp, "a.m4a")
        c = os.path.join(self.tmp, "c.m4a")
        _make_tone(a, 440, 6)
        _make_tone(c, 880, 6)
        server, first, proj = _make_server(self.tmp, a, kind="audio")
        second = proj.add_media(os.path.basename(c), kind="audio",
                                **probe_media(c))
        save_project(proj.data, os.path.join(
            self.tmp, "project.vibeedit.json"))
        server = MCPServer(self.tmp)
        result = server.call("vibeedit_media_sync",
                             {"media": first["id"],
                              "to": second["id"]})
        self.assertLess(result["correlation"], 0.4)
        self.assertFalse(result["sharedSound"])

    def test_sync_needs_three_seconds(self):
        a = os.path.join(self.tmp, "a.m4a")
        b = os.path.join(self.tmp, "b.m4a")
        _make_tone(a, 440, 1)
        _make_tone(b, 440, 1)
        server, first, proj = _make_server(self.tmp, a, kind="audio")
        second = proj.add_media(os.path.basename(b), kind="audio",
                                **probe_media(b))
        save_project(proj.data, os.path.join(
            self.tmp, "project.vibeedit.json"))
        server = MCPServer(self.tmp)
        with self.assertRaises(ValueError):
            server.call("vibeedit_media_sync",
                        {"media": first["id"], "to": second["id"]})


if __name__ == "__main__":
    unittest.main()
