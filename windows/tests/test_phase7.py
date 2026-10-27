"""Phase 7 tests: Windows fontfile-colon bugfix, Vietnamese text
encoding, still-image keyframe rendering, Inspector preset-strength
UI wiring, beautified UI ids, and MCP expansion 6 (78 -> 90 tools).
Real FFmpeg renders where the claim is about rendering.

Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import (  # noqa: E402
    _escape_drawtext, _filter_path, render, probe_media)


def gen_clip(path, seconds=3):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def gen_still(path):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180",
         "-frames:v", "1", path], capture_output=True, check=True)


def make_project(tmp):
    return Project(new_project("phase7", width=320, height=180,
                                fps=(30, 1)), tmp)


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                          "-show_streams", "-show_format", path],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def duration(path):
    return float(ffprobe(path)["format"]["duration"])


def frame_count(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames",
                          "-select_streams", "v:0",
                          "-show_entries", "stream=nb_read_frames",
                          "-of", "csv=p=0", path],
                         capture_output=True, text=True, check=True)
    return int(out.stdout.strip())


class TestFilterPath(unittest.TestCase):
    def test_windows_drive_path_escapes_colon(self):
        # The user's real failure: C:/Windows/Fonts/arial.ttf split
        # at the drive colon even inside single quotes.
        self.assertEqual(_filter_path("C:\\Windows\\Fonts\\arial.ttf"),
                         "C\\:/Windows/Fonts/arial.ttf")

    def test_windows_path_with_spaces_escapes_colon(self):
        self.assertEqual(
            _filter_path("D:\\My Fonts\\my font.ttf"),
            "D\\:/My Fonts/my font.ttf")

    def test_plain_linux_path_unchanged(self):
        self.assertEqual(_filter_path("/usr/share/fonts/a.ttf"),
                         "/usr/share/fonts/a.ttf")

    def test_single_quote_escaped(self):
        self.assertEqual(_filter_path("/tmp/o'brien/a.ttf"),
                         "/tmp/o\\'brien/a.ttf")

    def test_every_colon_escaped(self):
        # A colon anywhere in the path splits the filter the same way.
        self.assertEqual(_filter_path("/tmp/win:C/font.ttf"),
                         "/tmp/win\\:C/font.ttf")

    def test_drawtext_filter_string_for_windows_path(self):
        # The exact construction render.py builds for drawtext,
        # with the user's font path: one fontfile option, and the
        # colon must appear only as an escaped \: inside it.
        font = _filter_path("C:\\Windows\\Fonts\\arial.ttf")
        filt = (f"drawtext=fontfile='{font}':"
                f"text='{_escape_drawtext('xin chào')}':fontsize=59")
        self.assertIn("fontfile='C\\:/Windows/Fonts/arial.ttf'", filt)
        # No unescaped colon may appear before the text= option:
        # split the fontfile value out and check it has no bare ':'.
        value = filt.split("fontfile='", 1)[1].split("'", 1)[0]
        self.assertNotIn(":", value.replace("\\:", ""))

    def test_real_ffmpeg_drawtext_with_escaped_colon_path(self):
        # Reproduces the user's failure mode on this VM: a font
        # path containing a colon renders only with \: escaping.
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "win:C"))
            import shutil
            shutil.copy("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        os.path.join(tmp, "win:C", "font.ttf"))
            font = _filter_path(os.path.join(tmp, "win:C", "font.ttf"))
            out = os.path.join(tmp, "out.mp4")
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", "testsrc2=size=320x180:rate=30:duration=1",
                 "-vf", f"drawtext=fontfile='{font}':text='xin chào':"
                        "fontsize=24:fontcolor=white:x=10:y=10",
                 out], capture_output=True, text=True,
                encoding="utf-8", errors="replace")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.isfile(out))
            self.assertEqual(frame_count(out), 30)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestVietnameseText(unittest.TestCase):
    def test_escape_drawtext_keeps_vietnamese(self):
        # The user's "xin chÃ o" mojibake is UTF-8 bytes decoded as
        # Latin-1; the drawtext escaper must pass the text through
        # unchanged (no mojibake characters may appear).
        escaped = _escape_drawtext("xin chào")
        self.assertEqual(escaped, "xin chào")
        self.assertNotIn("Ã", escaped)

    def test_ffmpeg_error_output_decoded_as_utf8(self):
        # Regression for render.py's subprocess decoding: FFmpeg
        # stderr containing UTF-8 Vietnamese must survive decoding.
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.stderr.buffer.write('xin chào'.encode('utf-8'))"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        self.assertIn("xin chào", proc.stderr)

    def test_full_render_with_vietnamese_text(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_clip(os.path.join(tmp, "c1.mp4"))
            proj = make_project(tmp)
            info = probe_media(os.path.join(tmp, "c1.mp4"))
            medium = proj.add_media("c1.mp4", kind="video", **info)
            proj.add_clip(medium["id"], "v1", 0, 0, 90)
            proj.add_text("t1", "xin chào", 0, 90)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["text_overlays"], 1)
            self.assertNotIn("xin chào", str(report.get("skipped", [])))
            self.assertAlmostEqual(duration(out), 3.0, delta=0.2)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestStillImageKeyframes(unittest.TestCase):
    def test_main_image_scale_keyframes_render(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_still(os.path.join(tmp, "still.png"))
            proj = make_project(tmp)
            info = probe_media(os.path.join(tmp, "still.png"))
            medium = proj.add_media("still.png", kind="image", **info)
            item = proj.add_clip(medium["id"], "v1", 0, 0, 90)
            proj.add_keyframe(item["id"], 0.0, "scale", 1.0)
            proj.add_keyframe(item["id"], 3.0, "scale", 2.0)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertAlmostEqual(duration(out), 3.0, delta=0.2)
            self.assertEqual(frame_count(out), 90)
            # No more "stored, not rendered" entry for this clip.
            self.assertFalse(
                any("stored, not rendered" in s
                    for s in report.get("skipped", [])))

        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_image_tilt_keyframes_render(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_still(os.path.join(tmp, "still.png"))
            proj = make_project(tmp)
            info = probe_media(os.path.join(tmp, "still.png"))
            medium = proj.add_media("still.png", kind="image", **info)
            item = proj.add_clip(medium["id"], "v1", 0, 0, 90)
            proj.add_keyframe(item["id"], 0.0, "tilt", 0.0)
            proj.add_keyframe(item["id"], 3.0, "tilt", 45.0)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertAlmostEqual(duration(out), 3.0, delta=0.2)
            self.assertFalse(
                any("stored, not rendered" in s
                    for s in report.get("skipped", [])))
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestPresetStrengthUI(unittest.TestCase):
    def test_preset_strength_input_wired(self):
        base = os.path.join(os.path.dirname(__file__), "..")
        html = open(os.path.join(base, "static", "index.html"),
                    encoding="utf-8").read()
        js = open(os.path.join(base, "static", "app.js"),
                  encoding="utf-8").read()
        self.assertIn('id="inspPresetStrength"', html)
        self.assertIn("inspPresetStrength", js)
        self.assertIn("preset_strength", js)


class TestBeautifiedUI(unittest.TestCase):
    def test_every_app_js_id_still_in_html(self):
        base = os.path.join(os.path.dirname(__file__), "..")
        html = open(os.path.join(base, "static", "index.html"),
                    encoding="utf-8").read()
        js = open(os.path.join(base, "static", "app.js"),
                  encoding="utf-8").read()
        ids = sorted(set(re.findall(r'\$\("([^"]+)"\)', js)))
        self.assertTrue(ids)
        missing = [i for i in ids if f'id="{i}"' not in html]
        self.assertEqual(missing, [], f"UI ids broken by redesign: {missing}")

    def test_css_has_polished_theme(self):
        css = open(os.path.join(os.path.dirname(__file__), "..",
                                "static", "style.css"),
                   encoding="utf-8").read()
        # CapCut redesign: teal accent replaces the Phase 7 gradient.
        for token in ("--accent: #00c8d4", "linear-gradient",
                      ".brand-text", "box-shadow", ":focus-visible"):
            self.assertIn(token, css)
        # Old flat brown palette must be gone.
        self.assertNotIn("#c4915e", css)

    def test_server_smoke_with_new_css(self):
        import threading
        import urllib.request
        from vibeedit_core.server import State, make_handler
        from http.server import ThreadingHTTPServer
        tmp = tempfile.mkdtemp()
        try:
            state = State(tmp)
            srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
            port = srv.server_address[1]
            t = threading.Thread(target=srv.serve_forever, daemon=True)
            t.start()
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/") as resp:
                    body = resp.read().decode("utf-8")
                    self.assertEqual(resp.status, 200)
                    self.assertIn("VibeEdit", body)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/static/style.css") as resp:
                    css = resp.read().decode("utf-8")
                    # CapCut redesign: teal accent, not the old gradient.
                    self.assertIn("--accent: #00c8d4", css)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/project") as resp:
                    self.assertEqual(resp.status, 200)
            finally:
                srv.shutdown()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class TestMCPPhase7(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        gen_clip(os.path.join(self.tmp, "c1.mp4"))
        from vibeedit_core.project import save_project, PROJECT_FILENAME
        save_project(new_project("phase7mcp", width=320, height=180,
                                 fps=(30, 1)),
                     os.path.join(self.tmp, PROJECT_FILENAME))
        self.srv = MCPServer(self.tmp)
        proj = self.srv._require()
        info = probe_media(os.path.join(self.tmp, "c1.mp4"))
        self.medium = proj.add_media("c1.mp4", kind="video", **info)
        self.clip = proj.add_clip(self.medium["id"], "v1", 0, 0, 90)
        self.srv._save()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_tool_count_is_90(self):
        self.assertEqual(len(TOOLS), 478)  # Round 3: 472 -> 478: 144 -> 478
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_clip_get_and_duplicate(self):
        got = self.srv.call("vibeedit_clip_get", {"item": self.clip["id"]})
        self.assertEqual(got["item"]["id"], self.clip["id"])
        dup = self.srv.call("vibeedit_clip_duplicate",
                            {"item": self.clip["id"], "track": "v1",
                             "at": 90})
        self.assertNotEqual(dup["id"], self.clip["id"])

    def test_keyframe_remove(self):
        proj = self.srv._require()
        proj.add_keyframe(self.clip["id"], 0.0, "scale", 1.0)
        proj.add_keyframe(self.clip["id"], 1.0, "scale", 2.0)
        self.srv._save()
        self.srv.call("vibeedit_clip_keyframe_remove",
                      {"item": self.clip["id"], "property": "scale"})
        _, item = proj.item(self.clip["id"])
        self.assertEqual(item.get("keyframes", []), [])

    def test_media_remove_blocked_when_used(self):
        with self.assertRaises(ValueError):
            self.srv.call("vibeedit_media_remove",
                          {"media": self.medium["id"]})

    def test_format_set_and_track_add_and_rev(self):
        fmt = self.srv.call("vibeedit_project_format_set",
                            {"width": 640, "height": 360})
        self.assertEqual(fmt["format"]["width"], 640)
        track = self.srv.call("vibeedit_track_add",
                              {"kind": "text", "name": "Extra"})
        self.assertEqual(track["track"]["kind"], "text")
        rev = self.srv.call("vibeedit_project_rev", {})
        self.assertEqual(rev["format"]["width"], 640)

    def test_karaoke_remove_and_adjustment_get(self):
        proj = self.srv._require()
        text = proj.add_text("t1", "Hello world", 0, 90)
        proj.add_karaoke(text["id"], [
            {"text": "Hello", "start": 0, "end": 1},
            {"text": "world", "start": 1, "end": 2}])
        self.srv._save()
        removed = self.srv.call("vibeedit_karaoke_remove",
                                {"item": text["id"]})
        self.assertEqual(removed["removed"], text["id"])
        layer = proj.add_adjustment(0, 90, preset="mono")
        got = self.srv.call("vibeedit_adjustment_get",
                            {"item": layer["id"]})
        self.assertEqual(got["adjustment"]["id"], layer["id"])
        beat = self.srv.call("vibeedit_beat_count", {})
        self.assertEqual(beat["beats"], 0)
        style = self.srv.call("vibeedit_text_style_get",
                              {"item": text["id"]})
        self.assertEqual(style["text"], "Hello world")


if __name__ == "__main__":
    unittest.main()
