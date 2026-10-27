"""Finishing batch tests: aspect-ratio op, source-media endpoint with
Range support, no-page-scroll layout, Settings gear, VS Code launch
config and update scripts. No feature is faked: unknown media is a
404, an out-of-range format is a ValueError, a missing tool is
reported as "not found" by /api/info (never invented)."""
import json
import os
import re
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

from vibeedit_core.project import new_project, Project  # noqa: E402
from vibeedit_core.server import State, make_handler  # noqa: E402


def read(rel):
    with open(os.path.join(WINDOWS, rel), encoding="utf-8") as fh:
        return fh.read()


class TestSetFormat(unittest.TestCase):
    def test_valid_presets(self):
        proj = Project(new_project("t"), "/tmp")
        for w, h in ((1920, 1080), (1080, 1920), (1080, 1080),
                     (1080, 1350), (1080, 1440), (1440, 1080),
                     (1920, 810)):
            out = proj.set_format(w, h)
            self.assertEqual((out["width"], out["height"]), (w, h))
            self.assertEqual((proj.width, proj.height), (w, h))

    def test_invalid_rejected(self):
        proj = Project(new_project("t"), "/tmp")
        for w, h in ((100, 1080), (1920, 5000), (0, 0), ("x", 1080)):
            with self.assertRaises(ValueError):
                proj.set_format(w, h)
        # Failed attempts must not change the format.
        self.assertEqual((proj.width, proj.height), (1080, 1920))

    def test_server_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            out = state.apply({"op": "set_format", "width": 1920,
                               "height": 1080})
            self.assertEqual((out["width"], out["height"]), (1920, 1080))
            with self.assertRaises(ValueError):
                state.apply({"op": "set_format", "width": 10,
                             "height": 1080})


class TestMediaEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = State(cls.tmp.name)
        media_dir = os.path.join(cls.tmp.name, "media")
        with open(os.path.join(media_dir, "test.bin"), "wb") as fh:
            fh.write(b"0123456789ABCDEF")
        cls.medium = cls.state.project.add_media("media/test.bin",
                                                 kind="video")
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

    def _get(self, path, headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", headers=headers or {})
        return urllib.request.urlopen(req, timeout=10)

    def test_full_file(self):
        with self._get(f"/api/media/{self.medium['id']}") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.read(), b"0123456789ABCDEF")
            self.assertEqual(resp.headers.get("Accept-Ranges"), "bytes")

    def test_range_partial(self):
        with self._get(f"/api/media/{self.medium['id']}",
                       {"Range": "bytes=0-3"}) as resp:
            self.assertEqual(resp.status, 206)
            self.assertEqual(resp.read(), b"0123")
            self.assertEqual(resp.headers.get("Content-Range"),
                             "bytes 0-3/16")

    def test_unknown_id_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/media/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_traversal_404(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._get("/api/media/..%2Fsecret")
        self.assertEqual(ctx.exception.code, 404)

    def test_info_endpoint(self):
        with self._get("/api/info") as resp:
            data = json.loads(resp.read())
        self.assertIn("python", data)
        self.assertIn("ffmpeg", data)
        self.assertIn("ffprobe", data)
        self.assertIn("project_dir", data)
        self.assertTrue(data["python"])
        self.assertTrue(data["ffmpeg"])
        self.assertTrue(data["ffprobe"])


class TestFinishUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("static/index.html")
        cls.js = read("static/app.js")
        cls.css = read("static/style.css")

    def test_ratio_and_settings_markers(self):
        for marker in ("formatPreset", "settingsFormatPreset",
                       "settingsFormatWidth", "settingsFormatHeight",
                       "btnFormatCustom", "btnSettings", "settingsPanel",
                       "btnSettingsClose", "settingsProjectInfo",
                       "settingsEnvInfo", "previewImage",
                       "btnPreviewExport", "formatLabel"):
            self.assertIn(marker, self.html, marker)
        for preset in ("16:9", "9:16", "1:1", "4:5", "3:4", "4:3",
                       "21:9"):
            self.assertIn(preset, self.html, preset)
        self.assertIn("KHÔNG bị co giãn", self.html)

    def test_source_preview_logic_present(self):
        for marker in ("/api/media/", "previewMode", "sourceTimeForPlayhead",
                       "seekPreviewToPlayhead", "selectClipAndPreview",
                       "loadMediaPreview", "set_format"):
            self.assertIn(marker, self.js, marker)

    def test_no_page_scroll_layout(self):
        self.assertIn("height: 100vh", self.css)
        self.assertIn("overflow: hidden", self.css)
        self.assertIn(".settings-modal", self.css)
        self.assertIn("overflow-y: auto", self.css)

    def test_all_app_js_ids_still_present(self):
        ids = set(re.findall(r'\$\("([^"]+)"\)', self.js))
        ids |= set(re.findall(r'getElementById\("([^"]+)"\)', self.js))
        self.assertGreater(len(ids), 120,
                           "app.js should reference 120+ ids by now")
        missing = [i for i in ids if f'id="{i}"' not in self.html]
        self.assertEqual(missing, [],
                         f"ids used by app.js missing from HTML: {missing}")
        found = re.findall(r'id="([^"]+)"', self.html)
        dups = sorted({i for i in found if found.count(i) > 1})
        self.assertEqual(dups, [], f"duplicate ids: {dups}")

    def test_logo_intact(self):
        self.assertIn("data:image/png;base64", self.html)


class TestVscodeAndUpdate(unittest.TestCase):
    def test_launch_json(self):
        data = json.loads(read(".vscode/launch.json"))
        cfg = data["configurations"][0]
        self.assertEqual(cfg["name"], "VibeEdit")
        self.assertEqual(cfg["type"], "debugpy")
        self.assertEqual(cfg["request"], "launch")
        self.assertTrue(cfg["program"].endswith("vibeedit.py"))
        self.assertEqual(cfg["args"],
                         ["serve", "--port", "8000", "--open-browser"])
        self.assertEqual(cfg["cwd"], "${workspaceFolder}")
        self.assertEqual(cfg["console"], "integratedTerminal")

    def test_tasks_json(self):
        data = json.loads(read(".vscode/tasks.json"))
        labels = {t["label"] for t in data["tasks"]}
        self.assertIn("Run VibeEdit", labels)
        self.assertIn("Update & Run VibeEdit", labels)
        update = [t for t in data["tasks"]
                  if t["label"] == "Update & Run VibeEdit"][0]
        self.assertIn("update_and_run", update["command"])
        run = [t for t in data["tasks"]
               if t["label"] == "Run VibeEdit"][0]
        self.assertIn("vibeedit.py serve --port 8000 --open-browser",
                      run["command"])

    def test_update_scripts_pull_then_run_without_abort(self):
        for rel in ("update_and_run.bat", "update_and_run.ps1"):
            text = read(rel)
            self.assertIn("git pull --ff-only", text, rel)
            self.assertIn("serve --port 8000 --open-browser", text, rel)
            # Pull failure must warn and continue, never abort the run.
            self.assertIn("CANH BAO", text, rel)
            self.assertIn("Bo qua", text, rel)
            self.assertIn(".git", text, rel)


if __name__ == "__main__":
    unittest.main()
