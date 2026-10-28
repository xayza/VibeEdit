"""Round 13: end-to-end integration verification + server smoke + audit.

The user will only test on Windows once the app is truly complete, so
this round proves the whole main flow on the Linux VM with synthetic
test data only (never the user's sample projects/media) and prepares
the Windows checklist as a document — it does NOT ask the user to test
anything yet.

Composite project (320x180 @ 30 fps, all synthetic):
- Main: narrow red clip A (160x180, 60f) with a blur backdrop filling
  the fit bars, then blue clip B (320x180, 60f), dissolve 15f between
  them, freeze 30f appended after B.
- Overlay: green video 15..40 (trimmed end from 45) + a still image
  60..90 on the overlay track.
- Text: one caption 30..60 on the captions track.
- Audio: sine music on the music track + sine narration on the
  dialogue track, both covering the whole timeline.
Expected timeline: 60 + 60 + 30 - 15 (transition overlap) = 135
frames = 4.5 s. The test asserts the FFmpeg report AND the probed
output file agree on that duration/frame count, and that the file
carries both a video stream (320x180 H.264) and an audio stream.

Server smoke: start the real HTTP server in a thread on an ephemeral
port, GET / 200, /api/mcp-tools count 479, /api/info 200, shut it down
cleanly and prove the port can be rebound (no leaked listener).

Audit: MCP total/real/honest counted from the live registry with the
same definition used since round 4 (description starting with
"Not available" = honest check-and-error tool).

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from vibeedit_core.mcp import TOOLS  # noqa: E402
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import probe_media, render  # noqa: E402
from vibeedit_core.server import State, make_handler  # noqa: E402


def _color_clip(folder, name, color, frames, width=320, height=180):
    src = os.path.join(folder, name)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c={color}:size={width}x{height}:rate=30:"
                          f"duration={frames / 30.0}",
                    "-pix_fmt", "yuv420p", src],
                   capture_output=True, check=True)
    return name


def _sine(folder, name, freq, seconds):
    src = os.path.join(folder, name)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"sine=frequency={freq}:duration={seconds}",
                    "-c:a", "aac", src],
                   capture_output=True, check=True)
    return name


def _still(folder, name, color=(0, 0, 255)):
    path = os.path.join(folder, name)
    Image.new("RGB", (320, 180), color).save(path)
    return name


def _add_media(proj, folder, rel, kind):
    info = probe_media(os.path.join(folder, rel))
    return proj.add_media(rel, kind=kind, **info)


def _ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-count_frames",
                          "-print_format", "json", "-show_streams",
                          "-show_format", path],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _build_composite(tmp):
    proj = Project(new_project("round13", width=320, height=180,
                               fps=(30, 1)), tmp)
    a = _add_media(proj, tmp, _color_clip(tmp, "a.mp4", "red", 60,
                                          width=160), "video")
    b = _add_media(proj, tmp, _color_clip(tmp, "b.mp4", "blue", 60),
                   "video")
    ov = _add_media(proj, tmp, _color_clip(tmp, "ov.mp4", "green", 60),
                    "video")
    still = _add_media(proj, tmp, _still(tmp, "still.png"), "image")
    music = _add_media(proj, tmp, _sine(tmp, "music.m4a", 440, 6),
                       "audio")
    narr = _add_media(proj, tmp, _sine(tmp, "narr.m4a", 880, 6), "audio")
    clip_a = proj.add_clip(a["id"], "v1", 0, 0, 60)
    proj.set_backdrop(clip_a["id"], {"kind": "blur"})
    clip_b = proj.add_clip(b["id"], "v1", 60, 0, 60)
    proj.add_transition(clip_a["id"], clip_b["id"], "dissolve", 0.5)
    proj.freeze_clip(clip_b["id"], 30)
    ov_item = proj.add_clip(ov["id"], "v2", 15, 0, 30)
    proj.trim(ov_item["id"], "end", 40)
    proj.add_clip(still["id"], "v2", 60, 0, 30)
    proj.add_text("t1", "Round 13", 30, 30)
    proj.add_clip(music["id"], "a2", 0, 0, 135)
    proj.add_clip(narr["id"], "a1", 0, 0, 135)
    return proj


class TestRound13EndToEnd(unittest.TestCase):
    def test_composite_export_matches_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _build_composite(tmp)
            self.assertTrue(proj.validate()["ok"])
            out = os.path.join(tmp, "export.mp4")
            report = render(proj.data, tmp, out, preset="full")
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["transitions"], 1)
            self.assertEqual(report["text_overlays"], 1)
            self.assertEqual(report["overlay_clips"], 2)
            # 60 + 60 + 30 - 15 (dissolve overlap) = 135 frames.
            self.assertEqual(report["duration"], 4.5)
            self.assertTrue(os.path.isfile(out))
            probed = _ffprobe(out)
            video = [s for s in probed["streams"]
                     if s["codec_type"] == "video"]
            audio = [s for s in probed["streams"]
                     if s["codec_type"] == "audio"]
            self.assertEqual(len(video), 1)
            self.assertEqual(len(audio), 1)
            self.assertEqual(video[0]["codec_name"], "h264")
            self.assertEqual(int(video[0]["width"]), 320)
            self.assertEqual(int(video[0]["height"]), 180)
            self.assertEqual(int(video[0]["nb_read_frames"]), 135)
            self.assertAlmostEqual(float(probed["format"]["duration"]),
                                   report["duration"], places=1)
            # Freeze tail: the last second must still show the blue
            # main clip (freeze holds B's frame), not black.
            frame = os.path.join(tmp, "tail.png")
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "4.2",
                            "-i", out, "-frames:v", "1", frame],
                           capture_output=True, check=True)
            px = Image.open(frame).convert("RGB").getpixel((160, 90))
            self.assertTrue(px[2] > 150 and px[0] < 100,
                            f"freeze tail pixel not blue: {px}")

    def test_split_and_trim_keep_project_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(new_project("round13-cut", width=320,
                                       height=180, fps=(30, 1)), tmp)
            m = _add_media(proj, tmp, _color_clip(tmp, "c.mp4", "red",
                                                  90), "video")
            clip = proj.add_clip(m["id"], "v1", 0, 0, 90)
            # split() returns the right-half item dict, not a list.
            right = proj.split(clip["id"], 30)
            self.assertEqual(int(right["dur"]), 60)
            self.assertEqual(len(proj.track("v1")["items"]), 2)
            proj.trim(right["id"], "end", 75)
            self.assertTrue(proj.validate()["ok"])
            main = proj.track("v1")
            self.assertEqual(sum(i["dur"] for i in main["items"]), 75)


class TestRound13ServerSmoke(unittest.TestCase):
    def test_serve_endpoints_and_clean_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            server = ThreadingHTTPServer(("127.0.0.1", 0),
                                         make_handler(state))
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{port}"
                with urllib.request.urlopen(base + "/") as resp:
                    self.assertEqual(resp.status, 200)
                    home = resp.read().decode("utf-8", "replace")
                self.assertIn("compareWipe", home)
                with urllib.request.urlopen(base + "/api/mcp-tools") as resp:
                    tools = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(tools["count"], 481)
                self.assertEqual(len(tools["tools"]), 481)
                with urllib.request.urlopen(base + "/api/info") as resp:
                    self.assertEqual(resp.status, 200)
                    info = json.loads(resp.read().decode("utf-8"))
                self.assertIn("python", info)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            # Port must be free again: rebinding proves no leak.
            probe = ThreadingHTTPServer(("127.0.0.1", port),
                                        make_handler(state))
            probe.server_close()


class TestRound13Audit(unittest.TestCase):
    def test_mcp_count_and_split(self):
        honest = sum(1 for t in TOOLS
                     if t.get("description", "").startswith(
                         "Not available"))
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(honest, 52)  # Round 22: 54 -> 52
        self.assertEqual(len(TOOLS) - honest, 429)
