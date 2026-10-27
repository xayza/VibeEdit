"""Phase 5 tests: Windows compat helpers are in test_windows_compat.py;
this file covers eq preset strength, main-track motion+opacity
combined rendering, karaoke by syllable, the agent-dock endpoint,
and the 12 new MCP tools. Real FFmpeg renders where the claim is
about rendering.

Run from windows/:  python3 -m unittest discover -s tests -v
"""

import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.karaoke import build_ass  # noqa: E402
from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.project import Project, new_project, eq_preset_filter  # noqa: E402
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
    data = new_project("phase5", width=320, height=180, fps=(30, 1))
    return Project(data, tmp)


def add_clip(proj, name, track, at, dur):
    info = probe_media(os.path.join(proj.folder, name))
    medium = proj.add_media(name, kind="video", **info)
    return proj.add_clip(medium["id"], track, at, 0, dur)


def frame_bytes(path, t):
    return subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(t), "-i", path,
         "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True).stdout


def frame_sat(path, t):
    raw = frame_bytes(path, t)
    n = len(raw) // 3
    total = 0.0
    for i in range(n):
        r, g, b = raw[3 * i], raw[3 * i + 1], raw[3 * i + 2]
        total += max(r, g, b) - min(r, g, b)
    return total / n


class TestEqPresetStrength(unittest.TestCase):
    def test_blend_values(self):
        # Task spec example: vivid at 0.5.
        self.assertEqual(
            eq_preset_filter("vivid", 0.5),
            "eq=brightness=0.01:contrast=1.075:saturation=1.125")
        self.assertEqual(eq_preset_filter("vivid", 1.0),
                         "eq=brightness=0.02:contrast=1.15:saturation=1.25")
        self.assertEqual(eq_preset_filter("vivid", 0.0), "")
        self.assertEqual(eq_preset_filter("none", 1.0), "")
        self.assertEqual(eq_preset_filter("mono", 0.5), "eq=saturation=0.5")

    def test_blend_validation(self):
        with self.assertRaises(ValueError):
            eq_preset_filter("neon", 0.5)
        with self.assertRaises(ValueError):
            eq_preset_filter("vivid", 1.5)
        with self.assertRaises(ValueError):
            eq_preset_filter("vivid", -0.1)

    def test_set_color_stores_preset_strength(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen_clip(os.path.join(tmp, "c1.mp4"))
            proj = make_project(tmp)
            clip = add_clip(proj, "c1.mp4", "v1", 0, 90)
            item = proj.set_color(clip["id"], preset="vivid",
                                  preset_strength=0.5)
            self.assertEqual(item["color"]["preset_strength"], 0.5)
            with self.assertRaises(ValueError):
                proj.set_color(clip["id"], preset_strength=2.0)

    def test_eq_strength_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            gen_clip(os.path.join(tmp, "c1.mp4"))
            sats = {}
            for label, strength in (("plain", None), ("s0", 0.0),
                                    ("s05", 0.5), ("s1", 1.0)):
                proj = make_project(tmp)
                clip = add_clip(proj, "c1.mp4", "v1", 0, 90)
                if strength is not None:
                    proj.set_color(clip["id"], preset="vivid",
                                   preset_strength=strength)
                out = os.path.join(tmp, f"eq-{label}.mp4")
                render(proj.data, tmp, out, preset="full")
                sats[label] = frame_sat(out, 1.0)
            # Strength 0 renders (nearly) identically to no preset.
            self.assertLess(abs(sats["s0"] - sats["plain"]), 1.0)
            # Strength blends monotonically toward the full preset.
            self.assertGreater(sats["s05"], sats["s0"])
            self.assertGreater(sats["s1"], sats["s05"])


class TestMotionOpacityCombined(unittest.TestCase):
    def test_combined_render_differs_from_each_alone(self):
        """Phase 5 fix: a main clip with motion (scale/x) AND
        opacity keyframes renders BOTH (previously motion was
        skipped). Frames at 2.5 s — inside the second opacity
        segment, where the old per-segment zoompan timing would
        have been wrong — must differ from motion-only,
        opacity-only and plain renders; duration stays exact and
        nothing is reported skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            gen_clip(os.path.join(tmp, "c1.mp4"))
            outs = {}
            for label, kfs in (
                    ("plain", []),
                    ("motion", [{"at": 0, "scale": 1.0, "x": 0.0},
                                {"at": 90, "scale": 2.0, "x": 1.0}]),
                    ("opacity", [{"at": 0, "opacity": 1.0},
                                 {"at": 45, "opacity": 0.5}]),
                    ("combined", [{"at": 0, "scale": 1.0, "x": 0.0,
                                   "opacity": 1.0},
                                  {"at": 45, "opacity": 0.5},
                                  {"at": 90, "scale": 2.0, "x": 1.0}])):
                proj = make_project(tmp)
                clip = add_clip(proj, "c1.mp4", "v1", 0, 90)
                if kfs:
                    proj.set_keyframes(clip["id"], kfs)
                out = os.path.join(tmp, f"mo-{label}.mp4")
                report = render(proj.data, tmp, out, preset="full")
                outs[label] = out
                if label == "combined":
                    self.assertEqual(report["duration"], 3.0)
                    self.assertFalse(
                        [s for s in report["skipped"]
                         if "motion" in s],
                        f"motion still skipped: {report['skipped']}")
            combined = frame_bytes(outs["combined"], 2.5)
            self.assertNotEqual(combined, frame_bytes(outs["motion"], 2.5))
            self.assertNotEqual(combined, frame_bytes(outs["opacity"], 2.5))
            self.assertNotEqual(combined, frame_bytes(outs["plain"], 2.5))


class TestKaraokeSyllables(unittest.TestCase):
    def _text_item(self, proj):
        return proj.add_text("t1", "hello world", 0, 90)

    def test_syllables_stored_and_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            item = self._text_item(proj)
            got = proj.add_karaoke(item["id"], [
                {"text": "hello", "start": 0.0, "end": 1.0,
                 "syllables": [{"text": "hel", "start": 0.0, "end": 0.5},
                               {"text": "lo", "start": 0.5, "end": 1.0}]},
                {"text": "world", "start": 1.0, "end": 2.0}])
            self.assertEqual(
                got["karaoke"]["words"][0]["syllables"][1]["text"], "lo")
            ass = build_ass([{"start_s": 0.0, "end_s": 3.0,
                              "words": got["karaoke"]["words"],
                              "size_frac": 0.062, "position_y": 0.8}],
                            320, 180)
            # One \k per syllable (50cs each), not one per word.
            self.assertIn("{\\k50}hel{\\k50}lo", ass)
            self.assertIn("{\\k100}world", ass)

    def test_syllable_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = make_project(tmp)
            item = self._text_item(proj)
            # Syllables must join to the word text.
            with self.assertRaises(ValueError):
                proj.add_karaoke(item["id"], [
                    {"text": "hello", "start": 0.0, "end": 1.0,
                     "syllables": [{"text": "he", "start": 0.0, "end": 0.5},
                                   {"text": "llo!", "start": 0.5, "end": 1.0}]},
                    {"text": "world", "start": 1.0, "end": 2.0}])
            # Syllables must lie inside the word range.
            with self.assertRaises(ValueError):
                proj.add_karaoke(item["id"], [
                    {"text": "hello", "start": 0.0, "end": 1.0,
                     "syllables": [{"text": "hel", "start": 0.0, "end": 0.5},
                                   {"text": "lo", "start": 0.5, "end": 1.5}]},
                    {"text": "world", "start": 1.0, "end": 2.0}])


class TestPhase5McpAndDock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = MCPServer()
        self.server.project = None
        data = new_project("phase5mcp", width=320, height=180, fps=(30, 1))
        from vibeedit_core.project import Project, save_project, PROJECT_FILENAME
        path = os.path.join(self.tmp, PROJECT_FILENAME)
        save_project(data, path)
        self.server.open(self.tmp)
        self.proj = self.server.project

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tool_count_is_78(self):
        # Phase 7: 78 Phase 6 tools + 12 Phase 7 tools = 90.
        self.assertEqual(len(TOOLS), 144)  # Code-gap batch 2: 123 -> 144
        names = [t["name"] for t in TOOLS]
        for expected in ("vibeedit_clip_color_preset_strength",
                         "vibeedit_tool_status",
                         "vibeedit_windows_check",
                         "vibeedit_karaoke_syllable_add",
                         "vibeedit_agent_dock_info",
                         "vibeedit_project_validate",
                         "vibeedit_track_list",
                         "vibeedit_clip_list",
                         "vibeedit_color_preset_list",
                         "vibeedit_mcp_tools_list",
                         "vibeedit_text_list",
                         "vibeedit_project_format"):
            self.assertIn(expected, names)

    def test_tool_status_and_windows_check(self):
        status = self.server.call("vibeedit_tool_status", {})
        self.assertTrue(status["ffmpeg"])
        self.assertTrue(status["ffprobe"])
        self.assertTrue(status["font"])
        checks = self.server.call("vibeedit_windows_check", {})
        self.assertTrue(checks["ok"])
        self.assertTrue(checks["file:run_vibeedit.bat"])
        self.assertTrue(checks["file:scripts/install_shortcuts.ps1"])

    def test_validate_track_clip_text_format(self):
        self.assertTrue(
            self.server.call("vibeedit_project_validate", {})["ok"])
        self.proj.data["tracks"][0]["items"].append(
            {"id": "bad-1", "media": "no-such-media", "at": 0, "dur": 30})
        result = self.server.call("vibeedit_project_validate", {})
        self.assertFalse(result["ok"])
        self.assertTrue(any("no-such-media" in e for e in result["errors"]))
        tracks = self.server.call("vibeedit_track_list", {})
        self.assertEqual(tracks["tracks"][0]["items"], 1)
        clips = self.server.call("vibeedit_clip_list", {})
        self.assertEqual(clips["items"][0]["id"], "bad-1")
        self.assertEqual(
            self.server.call("vibeedit_project_format", {})["format"]["width"],
            320)
        self.assertIn("vivid", self.server.call(
            "vibeedit_color_preset_list", {})["presets"])
        self.assertEqual(self.server.call(
            "vibeedit_mcp_tools_list", {})["count"], 144)  # Code-gap batch
        dock = self.server.call("vibeedit_agent_dock_info", {})
        self.assertEqual(dock["tool_count"], 144)  # Code-gap batch
        self.assertIn("mcp", dock["command"])
        text = self.proj.add_text("t1", "hi", 0, 30)
        listed = self.server.call("vibeedit_text_list", {})
        self.assertEqual(listed["items"][0]["id"], text["id"])

    def test_preset_strength_and_syllable_tools(self):
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        clip = add_clip(self.proj, "c1.mp4", "v1", 0, 90)
        got = self.server.call("vibeedit_clip_color_preset_strength",
                               {"item": clip["id"], "preset": "vivid",
                                "preset_strength": 0.5})
        self.assertEqual(got["color"]["preset_strength"], 0.5)
        text = self.proj.add_text("t1", "hello world", 0, 90)
        got = self.server.call("vibeedit_karaoke_syllable_add",
                               {"item": text["id"], "words": [
                                   {"text": "hello", "start": 0.0,
                                    "end": 1.0,
                                    "syllables": [
                                        {"text": "hel", "start": 0.0,
                                         "end": 0.5},
                                        {"text": "lo", "start": 0.5,
                                         "end": 1.0}]},
                                   {"text": "world", "start": 1.0,
                                    "end": 2.0}]})
        self.assertEqual(got["karaoke"]["words"][0]["syllables"][0]["text"],
                         "hel")

    def test_cli_color_preset_strength_flag(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "vibeedit.py"), "color", "--help"],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--preset-strength", proc.stdout)


class TestAgentDockEndpoint(unittest.TestCase):
    def test_mcp_tools_endpoint(self):
        from vibeedit_core.server import State, make_handler
        from http.server import ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                                        make_handler(state))
            thread = threading.Thread(target=httpd.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                conn = http.client.HTTPConnection("127.0.0.1", port,
                                                  timeout=10)
                conn.request("GET", "/")
                resp = conn.getresponse()
                self.assertEqual(resp.status, 200)
                resp.read()
                conn.request("GET", "/api/project")
                resp = conn.getresponse()
                self.assertEqual(resp.status, 200)
                json.loads(resp.read().decode("utf-8"))
                conn.request("GET", "/api/mcp-tools")
                resp = conn.getresponse()
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(data["count"], 144)  # Code-gap batch: 106 -> 123
                self.assertTrue(any(
                    t["name"] == "vibeedit_agent_dock_info"
                    for t in data["tools"]))
                conn.close()
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
