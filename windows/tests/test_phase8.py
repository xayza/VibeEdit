"""Phase 8 tests: overlay still images, transition preview stills,
review panel data, and MCP expansion 7 (90 -> 106 tools).

Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.export_ops import transition_preview  # noqa: E402
from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import render  # noqa: E402


def gen_clip(path, seconds=3):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def gen_still(path, color="red"):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c={color}:s=160x90",
         "-frames:v", "1", path], capture_output=True, check=True)


def make_project(tmp, clips=1):
    proj = Project(new_project("phase8", width=320, height=180,
                                fps=(30, 1)), tmp)
    os.makedirs(os.path.join(tmp, "media"), exist_ok=True)
    return proj


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def frame_pixel(path, x, y):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    return im.getpixel((x, y))


class TestOverlayStill(unittest.TestCase):
    def test_overlay_still_renders_and_is_visible(self):
        tmp = tempfile.mkdtemp()
        proj = make_project(tmp)
        gen_clip(os.path.join(tmp, "media", "main.mp4"))
        gen_still(os.path.join(tmp, "media", "still.png"), "red")
        main = proj.add_media("media/main.mp4", kind="video", width=320,
                              height=180, fps=[30, 1], frames=90,
                              duration=3.0, hasAudio=True)
        still = proj.add_media("media/still.png", kind="image", width=160,
                               height=90, fps=[30, 1], frames=1,
                               duration=0, hasAudio=False)
        proj.add_clip(main["id"], "v1", 0, 0, 90)
        item = proj.add_clip(still["id"], "v2", 30, 0, 60)
        proj.add_keyframe(item["id"], 0.0, "scale", 1.0)
        proj.add_keyframe(item["id"], 2.0, "scale", 1.5)
        out = os.path.join(tmp, "render", "out.mp4")
        report = render(proj.data, tmp, out, preset="full")
        self.assertEqual(report["overlay_clips"], 1)
        self.assertEqual(report["skipped"], [])
        self.assertAlmostEqual(float(
            ffprobe(out)["format"]["duration"]), 3.0, places=1)
        frame = os.path.join(tmp, "frame.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "2",
                        "-i", out, "-frames:v", "1", frame],
                       capture_output=True, check=True)
        r, g, b = frame_pixel(frame, 160, 90)
        self.assertGreater(r, 200)
        self.assertLess(g, 50)
        self.assertLess(b, 50)

    def test_overlay_still_without_keyframes_renders(self):
        tmp = tempfile.mkdtemp()
        proj = make_project(tmp)
        gen_clip(os.path.join(tmp, "media", "main.mp4"))
        gen_still(os.path.join(tmp, "media", "still.png"), "blue")
        main = proj.add_media("media/main.mp4", kind="video", width=320,
                              height=180, fps=[30, 1], frames=90,
                              duration=3.0, hasAudio=True)
        still = proj.add_media("media/still.png", kind="image", width=160,
                               height=90, fps=[30, 1], frames=1,
                               duration=0, hasAudio=False)
        proj.add_clip(main["id"], "v1", 0, 0, 90)
        proj.add_clip(still["id"], "v2", 0, 0, 90)
        out = os.path.join(tmp, "render", "out.mp4")
        report = render(proj.data, tmp, out, preset="full")
        self.assertEqual(report["overlay_clips"], 1)
        self.assertEqual(report["skipped"], [])


class TestTransitionPreview(unittest.TestCase):
    def test_preview_still_from_two_clips(self):
        tmp = tempfile.mkdtemp()
        proj = make_project(tmp)
        gen_clip(os.path.join(tmp, "media", "c1.mp4"))
        gen_clip(os.path.join(tmp, "media", "c2.mp4"))
        m1 = proj.add_media("media/c1.mp4", kind="video", width=320,
                            height=180, fps=[30, 1], frames=90,
                            duration=3.0, hasAudio=True)
        m2 = proj.add_media("media/c2.mp4", kind="video", width=320,
                            height=180, fps=[30, 1], frames=90,
                            duration=3.0, hasAudio=True)
        c1 = proj.add_clip(m1["id"], "v1", 0, 0, 90)
        c2 = proj.add_clip(m2["id"], "v1", 90, 0, 90)
        trans = proj.add_transition(c1["id"], c2["id"], "dissolve", 0.5)
        result = transition_preview(proj.data, tmp, trans["id"])
        self.assertTrue(os.path.isfile(result["image"]))
        self.assertTrue(os.path.isfile(result["video"]))
        self.assertEqual(result["kind"], "dissolve")
        from PIL import Image
        with Image.open(result["image"]) as im:
            size = im.size
        im = None
        self.assertEqual(size, (160, 90))

    def test_preview_unknown_transition_raises(self):
        tmp = tempfile.mkdtemp()
        proj = make_project(tmp)
        with self.assertRaises(ValueError):
            transition_preview(proj.data, tmp, "nope")


class TestReviewAndMcp(unittest.TestCase):
    def _server(self, tmp):
        proj = make_project(tmp)
        gen_clip(os.path.join(tmp, "media", "c1.mp4"))
        m = proj.add_media("media/c1.mp4", kind="video", width=320,
                           height=180, fps=[30, 1], frames=90,
                           duration=3.0, hasAudio=True)
        c1 = proj.add_clip(m["id"], "v1", 0, 0, 90)
        return proj, c1

    def test_review_data_is_real(self):
        tmp = tempfile.mkdtemp()
        proj, c1 = self._server(tmp)
        self.assertTrue(proj.validate()["ok"])
        stats = proj.project_stats()
        self.assertEqual(stats["clips"], 1)
        self.assertEqual(stats["transitions"], 0)

    def test_mcp_count_and_new_tools(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(TOOLS), 481)  # Round 23: 479 -> 481 (skills_import_plan/import)
        for name in ("vibeedit_transition_preview", "vibeedit_review_get",
                     "vibeedit_overlay_items", "vibeedit_clip_position_set",
                     "vibeedit_clip_scale_set", "vibeedit_clip_opacity_set",
                     "vibeedit_clip_fades_get", "vibeedit_clip_speed_get",
                     "vibeedit_marker_move", "vibeedit_beat_grid_get",
                     "vibeedit_ducking_toggle",
                     "vibeedit_clip_keyframes_clear",
                     "vibeedit_media_kind_list", "vibeedit_timeline_gaps",
                     "vibeedit_project_duration_frames",
                     "vibeedit_clip_at_time"):
            self.assertIn(name, names)

    def test_mcp_round_trip(self):
        tmp = tempfile.mkdtemp()
        proj, c1 = self._server(tmp)
        marker = proj.add_marker("Intro", 0)
        os.makedirs(os.path.join(tmp, "render"), exist_ok=True)
        from vibeedit_core.project import save_project, PROJECT_FILENAME
        save_project(proj.data, os.path.join(tmp, PROJECT_FILENAME))
        srv = MCPServer(tmp)
        self.assertEqual(
            srv.call("vibeedit_project_duration_frames", {})["frames"], 90)
        self.assertEqual(
            srv.call("vibeedit_clip_at_time", {"frame": 10})["clip"]["item"]["id"],
            c1["id"])
        self.assertIsNone(
            srv.call("vibeedit_clip_at_time", {"frame": 500})["clip"])
        self.assertEqual(
            srv.call("vibeedit_timeline_gaps", {})["gaps"], [])
        self.assertEqual(
            srv.call("vibeedit_clip_speed_get", {"item": c1["id"]})["speed"], 1.0)
        srv.call("vibeedit_clip_scale_set",
                 {"item": c1["id"], "at": 1.0, "scale": 1.5})
        self.assertEqual(
            srv.call("vibeedit_keyframes_get", {"item": c1["id"]})["keyframes"][0]["scale"],
            1.5)
        srv.call("vibeedit_clip_keyframes_clear", {"item": c1["id"]})
        self.assertEqual(
            srv.call("vibeedit_keyframes_get", {"item": c1["id"]})["keyframes"], [])
        srv.call("vibeedit_marker_move", {"marker": marker["id"], "at": 45})
        self.assertEqual(
            srv.call("vibeedit_markers_list", {})["markers"][0]["at"], 45)
        self.assertEqual(
            srv.call("vibeedit_media_kind_list", {"kind": "video"})["media"][0]["id"],
            proj.data["media"][0]["id"])
        review = srv.call("vibeedit_review_get", {})
        self.assertTrue(review["validation"]["ok"])
        self.assertEqual(review["stats"]["clips"], 1)
        overlays = srv.call("vibeedit_overlay_items", {})
        self.assertEqual(overlays["overlay_items"], [])

    def test_ui_ids_for_review_and_preview(self):
        with open(os.path.join(os.path.dirname(__file__), "..",
                            "static", "index.html"),
                    encoding="utf-8") as fh:
            html = fh.read()
        for ident in ("btnReview", "reviewResult", "btnTransitionPreview",
                      "transitionPreviewImg", "transitionPreviewBox"):
            self.assertIn(f'id="{ident}"', html)
        with open(os.path.join(os.path.dirname(__file__), "..",
                      "static", "app.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("/api/review", js)
        self.assertIn("/api/transition-preview", js)

    def test_ui_polish_phase8(self):
        # Phase 8 beautification: every id app.js uses must still
        # exist in index.html, the logo data URI must be intact,
        # and the stylesheet must carry the polished treatment
        # (centred preview stage, panel section bars, timeline
        # selection highlight, ruler ticks, focus states).
        import re
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "static", "app.js"),
                  encoding="utf-8") as fh:
            js = fh.read()
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "static", "index.html"),
                  encoding="utf-8") as fh:
            html = fh.read()
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "static", "style.css"),
                  encoding="utf-8") as fh:
            css = fh.read()
        for ident in sorted(set(re.findall(r'\$\("([^"]+)"\)', js))):
            self.assertIn(f'id="{ident}"', html,
                          f"app.js id {ident} missing from index.html")
        self.assertIn("data:image/png;base64,", html)
        for snippet in (".preview-wrap video", ".panel h3::before",
                        ".clip.selected", ".ruler .playhead::after",
                        "button:focus-visible",
                        "repeating-linear-gradient",
                        ".track-label", ".beat-tick"):
            self.assertIn(snippet, css, f"missing polish rule {snippet}")


if __name__ == "__main__":
    unittest.main()
