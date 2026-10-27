"""Phase 4 tests: OTIO import, karaoke, adjustment layers, beat grid,
ducking, tilt keyframes, new MCP tools. Real FFmpeg renders where the
claim is about rendering.

Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
"""

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.beats import detect_beats  # noqa: E402
from vibeedit_core.export_ops import export_otio, import_otio  # noqa: E402
from vibeedit_core.karaoke import build_ass  # noqa: E402
from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import render, probe_media  # noqa: E402


def gen_clip(path, seconds=3, freq=440):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def make_project(tmp):
    data = new_project("phase4", width=320, height=180, fps=(30, 1))
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


def mean_db(path, start, end):
    """Mean volume (dB) of an audio segment via volumedetect."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path, "-af",
         f"atrim=start={start}:end={end},volumedetect", "-vn", "-sn",
         "-dn", "-f", "null", "-"],
        capture_output=True, text=True, check=True)
    for line in out.stderr.splitlines():
        if "mean_volume" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0].strip())
    raise AssertionError("volumedetect produced no mean_volume")


def gen_bursts(path, burst_times, total=3.0, sr=11025):
    """WAV with short sine bursts at the given times, silence elsewhere."""
    frames = int(total * sr)
    data = [0.0] * frames
    for bt in burst_times:
        for i in range(int(0.1 * sr)):
            idx = int(bt * sr) + i
            if idx < frames:
                data[idx] = 0.8 * math.sin(2 * math.pi * 440 * i / sr)
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(sr)
        fh.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767))
            for v in data))


class TestOtioImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        gen_clip(os.path.join(self.tmp, "c2.mp4"))
        self.proj = make_project(self.tmp)
        self.i1 = add_clip(self.proj, "c1.mp4", "v1", 0, 90)
        self.i2 = add_clip(self.proj, "c2.mp4", "v1", 90, 90)
        self.proj.add_transition(self.i1["id"], self.i2["id"], "dissolve", 0.5)
        self.proj.add_marker("intro", 0)
        self.text = self.proj.add_text("t1", "Hello world", 0, 60)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_round_trip(self):
        otio = os.path.join(self.tmp, "timeline.otio")
        report = export_otio(self.proj.data, self.tmp, otio)
        self.assertEqual(report["clips"], 3)  # 2 video + 1 text
        self.assertEqual(report["transitions"], 1)
        dest = os.path.join(self.tmp, "imported")
        imported = import_otio(otio, dest)
        self.assertEqual(imported["clips"], 3)
        self.assertEqual(imported["transitions"], 1)
        self.assertEqual(imported["markers"], 1)
        self.assertEqual(imported["missing"], [])
        self.assertEqual(imported["warnings"], [])
        from vibeedit_core.project import load_project, find_project_file
        data = load_project(find_project_file(dest))
        clips = [i for t in data["tracks"] for i in t["items"]
                 if "media" in i]
        self.assertEqual(len(clips), 2)
        self.assertEqual(clips[0]["dur"], 90)
        self.assertEqual(clips[1]["at"], 90)
        self.assertEqual(len(data["transitions"]), 1)
        self.assertEqual(data["transitions"][0]["kind"], "dissolve")

    def test_round_trip_render_duration(self):
        otio = os.path.join(self.tmp, "timeline.otio")
        export_otio(self.proj.data, self.tmp, otio)
        dest = os.path.join(self.tmp, "imported2")
        import_otio(otio, dest)
        from vibeedit_core.project import load_project, find_project_file
        data = load_project(find_project_file(dest))
        out = os.path.join(dest, "render", "out.mp4")
        report = render(data, dest, out)
        # 6 s of clips minus 0.5 s transition = 5.5 s (text does not extend).
        self.assertAlmostEqual(report["duration"], 5.5, delta=0.15)
        self.assertAlmostEqual(duration(out), 5.5, delta=0.2)

    def test_missing_media_reported_not_dropped(self):
        otio = os.path.join(self.tmp, "timeline.otio")
        export_otio(self.proj.data, self.tmp, otio)
        os.remove(os.path.join(self.tmp, "c2.mp4"))
        dest = os.path.join(self.tmp, "imported3")
        imported = import_otio(otio, dest)
        self.assertEqual(imported["clips"], 3)
        self.assertTrue(any("c2.mp4" in m for m in imported["missing"]))


class TestKaraoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        self.proj = make_project(self.tmp)
        add_clip(self.proj, "c1.mp4", "v1", 0, 90)
        self.text = self.proj.add_text("t1", "Hello world", 0, 60)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_and_get(self):
        item = self.proj.add_karaoke(self.text["id"], [
            {"text": "Hello", "start": 0.0, "end": 1.0},
            {"text": "world", "start": 1.0, "end": 2.0}])
        self.assertEqual(len(item["karaoke"]["words"]), 2)
        self.assertEqual(self.proj.karaoke_get(self.text["id"])["words"][1]["text"],
                         "world")

    def test_mismatched_words_rejected(self):
        with self.assertRaises(ValueError):
            self.proj.add_karaoke(self.text["id"], [
                {"text": "Goodbye", "start": 0.0, "end": 1.0}])

    def test_ass_contains_k_tags(self):
        ass = build_ass([{"start_s": 0.0, "end_s": 2.0,
                          "words": [{"text": "Hello", "start": 0.0, "end": 1.0},
                                    {"text": "world", "start": 1.0, "end": 2.0}],
                          "size_frac": 0.1, "position_y": 0.8}], 320, 180)
        self.assertIn(r"{\k100}Hello", ass)
        self.assertIn(r"{\k100}world", ass)

    def test_karaoke_render(self):
        self.proj.add_karaoke(self.text["id"], [
            {"text": "Hello", "start": 0.0, "end": 1.0},
            {"text": "world", "start": 1.0, "end": 2.0}])
        out = os.path.join(self.tmp, "kara.mp4")
        report = render(self.proj.data, self.tmp, out)
        self.assertEqual(report["karaoke_items"], 1)
        self.assertAlmostEqual(duration(out), 3.0, delta=0.2)


class TestAdjustmentLayers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        self.proj = make_project(self.tmp)
        add_clip(self.proj, "c1.mp4", "v1", 0, 90)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_add_list_remove_and_overlap(self):
        layer = self.proj.add_adjustment(0, 45, preset="mono")
        self.assertEqual(len(self.proj.list_adjustments()), 1)
        with self.assertRaises(ValueError):
            self.proj.add_adjustment(30, 45, preset="vivid")
        self.proj.remove_adjustment(layer["id"])
        self.assertEqual(self.proj.list_adjustments(), [])

    def test_no_colour_rejected(self):
        with self.assertRaises(ValueError):
            self.proj.add_adjustment(0, 45)

    def test_adjustment_render_changes_colour(self):
        out_plain = os.path.join(self.tmp, "plain.mp4")
        render(self.proj.data, self.tmp, out_plain)
        self.proj.add_adjustment(0, 90, preset="mono")
        out_adj = os.path.join(self.tmp, "adj.mp4")
        report = render(self.proj.data, self.tmp, out_adj)
        self.assertEqual(report["adjustment_layers"], 1)
        self.assertAlmostEqual(duration(out_adj), 3.0, delta=0.2)
        # Mono output must differ measurably from the colour original:
        # extract a frame from each and compare mean saturation via
        # a simple channel-spread check on decoded pixels.
        from PIL import Image
        frames = []
        for src, dst in ((out_plain, "p.png"), (out_adj, "a.png")):
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "1",
                            "-i", src, "-frames:v", "1",
                            os.path.join(self.tmp, dst)],
                           capture_output=True, check=True)
            im = Image.open(os.path.join(self.tmp, dst)).convert("RGB")
            px = list(im.getdata())
            spread = sum(max(p) - min(p) for p in px) / len(px)
            frames.append(spread)
        self.assertGreater(frames[0], frames[1] + 5.0)


class TestBeats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detect_bursts(self):
        wav = os.path.join(self.tmp, "beats.wav")
        truth = [0.5, 1.0, 1.5, 2.0, 2.5]
        gen_bursts(wav, truth)
        beats = detect_beats(wav)
        self.assertEqual(len(beats), len(truth))
        for got, want in zip(beats, truth):
            self.assertAlmostEqual(got, want, delta=0.05)

    def test_silence_has_no_beats(self):
        wav = os.path.join(self.tmp, "silence.wav")
        gen_bursts(wav, [])
        self.assertEqual(detect_beats(wav), [])

    def test_project_beats_and_snap(self):
        wav = os.path.join(self.tmp, "beats.wav")
        gen_bursts(wav, [0.5, 1.0, 1.5])
        medium = self.proj_media(wav)
        proj = make_project(self.tmp)
        proj.data["media"].append(medium)
        grid = proj.detect_beats(medium["id"])
        self.assertEqual(len(grid["beats"]), 3)
        # Frame 20 (0.67 s) is nearest the 0.5 s beat = frame 15;
        # frame 25 (0.83 s) is nearest the ~1.0 s beat (frame 30,
        # ±1 frame for hop quantisation of the detector).
        self.assertEqual(proj.snap_frame(20), 15)
        self.assertIn(proj.snap_frame(25), (29, 30, 31))
        markers = proj.beats_to_markers()
        self.assertEqual(len(markers), 3)

    def proj_media(self, path):
        return {"id": "m-beats", "path": os.path.basename(path),
                "kind": "audio", "hasAudio": True}


class TestDucking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Dialogue: loud sine 0-2 s only (main track clip).
        gen_clip(os.path.join(self.tmp, "dlg.mp4"), seconds=2, freq=440)
        # Music: constant sine, 4 s.
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", "sine=frequency=880:duration=4",
             "-c:a", "aac", os.path.join(self.tmp, "music.m4a")],
            capture_output=True, check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _project(self, ducking):
        proj = make_project(self.tmp)
        dlg = add_clip(proj, "dlg.mp4", "v1", 0, 60)
        # Main video track needs a picture for the full 4 s: extend
        # with a second clip of the same media after the dialogue.
        info = probe_media(os.path.join(self.tmp, "music.m4a"))
        music = proj.add_media("music.m4a", kind="audio", **info)
        proj.add_clip(music["id"], "a2", 0, 0, 120)
        if ducking:
            proj.set_ducking(True, amount_db=12.0)
        return proj

    def test_sidechaincompress_lowers_music_during_dialogue(self):
        # Isolated mechanism check: music (constant) + sidechain
        # (bursts) through sidechaincompress; music level during a
        # burst must be lower than during silence.
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", "sine=frequency=880:duration=4",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
             "-filter_complex",
             "[0:a]atrim=0:4,asetpts=PTS-STARTPTS[m];"
             "[1:a]atrim=0:2,asetpts=PTS-STARTPTS,"
             "apad=whole_dur=4,aresample=48000[s];"
             "[m][s]sidechaincompress=threshold=0.02:ratio=10:"
             "attack=20:release=250[out]",
             "-map", "[out]", "-c:a", "aac",
             os.path.join(self.tmp, "ducked.m4a")],
            capture_output=True, check=True)
        during = mean_db(os.path.join(self.tmp, "ducked.m4a"), 0.5, 1.5)
        after = mean_db(os.path.join(self.tmp, "ducked.m4a"), 2.5, 3.5)
        self.assertGreater(after - during, 3.0)

    def test_full_render_with_ducking(self):
        proj = self._project(ducking=True)
        out = os.path.join(self.tmp, "duck.mp4")
        report = render(proj.data, self.tmp, out)
        self.assertTrue(report["ducking_applied"])
        self.assertAlmostEqual(duration(out), 4.0, delta=0.2)


class TestTilt(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        self.proj = make_project(self.tmp)
        self.clip = add_clip(self.proj, "c1.mp4", "v1", 0, 90)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tilt_validation(self):
        with self.assertRaises(ValueError):
            self.proj.add_keyframe(self.clip["id"], 0.0, "tilt", 200.0)
        self.proj.add_keyframe(self.clip["id"], 0.0, "tilt", 0.0)
        self.proj.add_keyframe(self.clip["id"], 3.0, "tilt", 45.0)

    def test_tilt_render(self):
        self.proj.add_keyframe(self.clip["id"], 0.0, "tilt", 0.0)
        self.proj.add_keyframe(self.clip["id"], 3.0, "tilt", 45.0)
        out = os.path.join(self.tmp, "tilt.mp4")
        report = render(self.proj.data, self.tmp, out)
        self.assertAlmostEqual(duration(out), 3.0, delta=0.2)
        # Rotated frame must differ from the unrotated original.
        plain = os.path.join(self.tmp, "plain.mp4")
        proj2 = make_project(self.tmp)
        add_clip(proj2, "c1.mp4", "v1", 0, 90)
        render(proj2.data, self.tmp, plain)
        hashes = []
        for src in (plain, out):
            h = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", "2", "-i", src,
                 "-frames:v", "1", "-f", "hash", "-hash", "md5", "-"],
                capture_output=True, text=True, check=True)
            hashes.append(h.stdout.strip())
        self.assertNotEqual(hashes[0], hashes[1])


class TestMcpPhase4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        self.proj = make_project(self.tmp)
        add_clip(self.proj, "c1.mp4", "v1", 0, 90)
        self.text = self.proj.add_text("t1", "Hello world", 0, 60)
        from vibeedit_core.project import save_project, PROJECT_FILENAME
        save_project(self.proj.data,
                     os.path.join(self.tmp, PROJECT_FILENAME))
        self.server = MCPServer(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tool_count(self):
        # Phase 7: 78 Phase 6 tools + 12 Phase 7 tools = 90.
        self.assertEqual(len(TOOLS), 472)  # Phase B1: 144 -> 472
        names = {t["name"] for t in TOOLS}
        for name in ("vibeedit_otio_import", "vibeedit_karaoke_add",
                     "vibeedit_karaoke_get", "vibeedit_karaoke_export_ass",
                     "vibeedit_adjustment_add", "vibeedit_adjustment_remove",
                     "vibeedit_adjustment_list", "vibeedit_beat_detect",
                     "vibeedit_beat_list", "vibeedit_beat_snap",
                     "vibeedit_beats_to_markers", "vibeedit_ducking_set",
                     "vibeedit_ducking_get", "vibeedit_project_stats",
                     "vibeedit_export_ducked", "vibeedit_clip_tilt"):
            self.assertIn(name, names)

    def test_karaoke_adjustment_ducking_stats_roundtrip(self):
        self.server.call("vibeedit_karaoke_add", {
            "item": self.text["id"],
            "words": [{"text": "Hello", "start": 0.0, "end": 1.0},
                      {"text": "world", "start": 1.0, "end": 2.0}]})
        got = self.server.call("vibeedit_karaoke_get",
                               {"item": self.text["id"]})
        self.assertEqual(len(got["words"]), 2)
        adj = self.server.call("vibeedit_adjustment_add",
                               {"at": 0, "dur": 45, "preset": "vivid"})
        listed = self.server.call("vibeedit_adjustment_list", {})
        self.assertEqual(len(listed["adjustments"]), 1)
        self.server.call("vibeedit_adjustment_remove",
                         {"item": adj["id"]})
        self.assertEqual(
            len(self.server.call("vibeedit_adjustment_list", {})["adjustments"]), 0)
        self.server.call("vibeedit_ducking_set",
                         {"enabled": True, "amount_db": 6.0})
        self.assertTrue(self.server.call("vibeedit_ducking_get", {})["enabled"])
        stats = self.server.call("vibeedit_project_stats", {})
        self.assertEqual(stats["karaoke_items"], 1)
        self.assertEqual(stats["items"], 2)
        tilt = self.server.call("vibeedit_clip_tilt", {
            "item": self.server.call("vibeedit_timeline_get", {}) and
            [i for t in self.server.project.data["tracks"]
             for i in t["items"] if "media" in i][0]["id"],
            "keyframes": [{"at": 0.0, "tilt": 0.0},
                          {"at": 3.0, "tilt": 30.0}]})
        self.assertTrue(any("tilt" in kf for kf in tilt["keyframes"]))


if __name__ == "__main__":
    unittest.main()
