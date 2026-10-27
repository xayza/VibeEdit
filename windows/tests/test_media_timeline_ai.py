"""Media grid + one-click add + timeline fit + Agent convenience +
original-app shell + desktop window (2026-10-27 batch)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = os.path.dirname(HERE)
sys.path.insert(0, WINDOWS)

from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.server import State, make_handler  # noqa: E402
from vibeedit_core.thumbnail import generate_thumbnail  # noqa: E402


def read(rel):
    with open(os.path.join(WINDOWS, rel), encoding="utf-8") as fh:
        return fh.read()


def make_video(path, seconds=1.0):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", f"color=c=red:s=160x90:d={seconds}",
         "-pix_fmt", "yuv420p", path], check=True)


class TestAddClipDurationFallback(unittest.TestCase):
    def test_duration_used_when_frames_missing(self):
        # The exact failure users hit: ffprobe records duration but no
        # nb_frames for some containers, and add_clip used to fail.
        proj = Project(new_project("t"), "/tmp")
        mid = proj.add_media("clip.mp4", kind="video", duration=2.0)["id"]
        clip = proj.add_clip(mid, "v1", 0, 0, None)
        self.assertGreater(clip["dur"], 0)

    def test_no_duration_no_frames_still_errors(self):
        proj = Project(new_project("t"), "/tmp")
        mid = proj.add_media("clip.mp4", kind="video")["id"]
        with self.assertRaises(ValueError):
            proj.add_clip(mid, "v1", 0, 0, None)


class TestThumbnail(unittest.TestCase):
    def test_video_thumbnail_is_valid_png(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "clip.mp4")
            make_video(src)
            out = generate_thumbnail(src, os.path.join(td, "t.png"), "video")
            with open(out, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")

    def test_audio_has_no_thumbnail(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                generate_thumbnail(os.path.join(td, "a.mp3"),
                                   os.path.join(td, "t.png"), "audio")

    def test_still_image_returned_as_is(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "pic.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                            "-i", "color=c=blue:s=32x32:d=0.1",
                            "-frames:v", "1", src], check=True)
            self.assertEqual(generate_thumbnail(src, os.path.join(td, "t.png"),
                                                "image"), src)


class TestThumbnailAndPluginEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = State(cls.tmp.name)
        media_dir = os.path.join(cls.tmp.name, "media")
        cls.video = os.path.join(media_dir, "clip.mp4")
        make_video(cls.video)
        cls.medium = cls.state.project.add_media("media/clip.mp4",
                                                 kind="video", frames=30,
                                                 duration=1.0)
        cls.state.project.add_text("t1", "hello world", 0, 30)
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(cls.state))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def _get(self, path):
        return urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}{path}", timeout=10)

    def _post(self, path, body):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(req, timeout=10)

    def test_thumbnail_video_png(self):
        with self._get(f"/api/thumbnail/{self.medium['id']}") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read(8), b"\x89PNG\r\n\x1a\n")

    def test_thumbnail_unknown_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/thumbnail/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_thumbnail_traversal_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/thumbnail/..%2Fsecret")
        self.assertEqual(ctx.exception.code, 404)

    def test_plugin_uppercases_text_item(self):
        item = next(it for t in self.state.project.data["tracks"]
                    for it in t["items"] if it.get("text") == "hello world")
        with self._post("/api/plugin", {"plugin": "uppercase_text",
                                        "item": item["id"]}) as resp:
            data = json.loads(resp.read())
        self.assertEqual(data["item"]["text"], "HELLO WORLD")

    def test_transcribe_unknown_media_errors(self):
        with self.assertRaises(urllib.error.HTTPError):
            self._post("/api/project", {"op": "transcribe",
                                        "media": "nope", "track": "t1",
                                        "model": "tiny"})


class TestShellAndUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("static/index.html")
        cls.js = read("static/app.js")
        cls.css = read("static/style.css")

    def test_original_shell_no_capcut_toolbar(self):
        # User decision 2026-10-27: original shell supersedes CapCut.
        self.assertNotIn('class="tool-toolbar"', self.html)
        for label in ("Media", "Audio", "Text", "Stickers", "Effects",
                      "Transitions", "Filters", "Voice", "Timeline",
                      "More"):
            self.assertIn(f">{label}</button>", self.html, label)
        for marker in ("projectRev", "btnExportReport", "btnPlugins",
                       "btnReviewTop", "btnExportFull", "agentDock",
                       "INSPECTOR", "btnSettings"):
            self.assertIn(marker, self.html, marker)

    def test_media_grid_and_one_click_add(self):
        for marker in ("media-card", "media-thumb", "media-added-badge",
                       "media-add-btn", "addMediaToTimeline",
                       "freePosition", "btnAddClipQuick", "mediaAddStatus",
                       "/api/thumbnail/", "dblclick"):
            self.assertIn(marker, self.js + self.html, marker)
        for marker in ("#mediaList", ".media-card", ".media-thumb"):
            self.assertIn(marker, self.css, marker)

    def test_timeline_no_vertical_scroll(self):
        self.assertIn("overflow-y: hidden", self.css)
        self.assertIn("min-height: 34px", self.css)

    def test_agent_dock_convenience(self):
        self.assertIn("width: 380px", self.css)
        self.assertIn("#agentChatForm", self.css)
        self.assertIn("margin-top: auto", self.css)
        for chip in ("Liệt kê clip", "Review", "Xuất bản nháp",
                     "Thống kê", "Hoàn tác", "data-agent-chip"):
            self.assertIn(chip, self.html + self.js, chip)

    def test_transcribe_and_plugin_wiring(self):
        for marker in ("transcribeForm", "transcribeMedia", "pluginForm",
                       "pluginSelect", "/api/plugin"):
            self.assertIn(marker, self.html + self.js, marker)

    def test_id_preservation(self):
        ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', self.html))
        used = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', self.js))
        missing = used - ids
        self.assertEqual(missing, set(), f"JS ids missing from HTML: {missing}")
        dupes = [i for i in ids if self.html.count(f'id="{i}"') > 1]
        self.assertEqual(dupes, [])


class TestDesktopApp(unittest.TestCase):
    def test_imports_without_pywebview(self):
        import desktop_app
        # pywebview is not installed on this Linux VM; the module must
        # still import and report that fact instead of crashing.
        self.assertIsNone(desktop_app.webview)
        self.assertTrue(callable(desktop_app.main))

    def test_desktop_bat_has_no_parenthesised_blocks(self):
        bat = read("run_vibeedit_desktop.bat")
        self.assertNotIn("(", bat)
        self.assertIn("desktop_app.py", bat)
        self.assertIn("python", bat)

    def test_desktop_readme_note(self):
        readme = read("README.md")
        self.assertIn("pywebview", readme)
        self.assertIn("run_vibeedit_desktop.bat", readme)


if __name__ == "__main__":
    unittest.main()
