"""Round 4 milestone 1: in-app voiceover recording, Compare masked
wipe, and manifest plugin code execution.

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

Milestone 1 covers round-4 tasks 1-3 only. Halftone (task 4),
updater run flow (task 5) and docs (task 6) are later milestones
and are NOT asserted here, so this file stays green while they
are still in progress.
"""

import json
import math
import os
import re
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer

WINDOWS = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, WINDOWS)

from vibeedit_core.plugins import (  # noqa: E402
    apply_plugin, load_plugins, set_plugin_enabled)
from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.server import State, make_handler  # noqa: E402
from vibeedit_core.voice import place_on_voiceover  # noqa: E402


def _make_wav(path: str, seconds: float = 1.0) -> bytes:
    """A real 8 kHz mono sine WAV, built with stdlib wave only."""
    frames = int(8000 * seconds)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * 440 * i / 8000))
            wf.writeframes(struct.pack("<h", sample))
    with open(path, "rb") as fh:
        return fh.read()


def _multipart(filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "----round4testboundary"
    head = (f"--{boundary}\r\nContent-Disposition: form-data; "
            f"name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + payload + tail, boundary


class RecordEndpointTest(unittest.TestCase):
    """Task 1 server side: POST /api/voiceover/record."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.state = State(cls.tmp.name)
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), make_handler(cls.state))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever,
                                      daemon=True)
        cls.thread.start()
        cls.wav = _make_wav(os.path.join(cls.tmp.name, "take.wav"))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def _post_record(self, filename, payload):
        body, boundary = _multipart(filename, payload)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/voiceover/record",
            data=body,
            headers={"Content-Type":
                     f"multipart/form-data; boundary={boundary}"})
        return urllib.request.urlopen(req, timeout=10)

    def test_record_accepts_real_audio_and_registers_take(self):
        with self._post_record("take.wav", self.wav) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read())
        self.assertTrue(data["ok"])
        medium = data["media"]
        self.assertEqual(medium["kind"], "audio")
        stored = os.path.join(self.state.project_dir, medium["path"])
        self.assertTrue(os.path.isfile(stored))
        self.assertGreater(os.path.getsize(stored), 0)
        # The registered take is real project media: the existing
        # voiceover path places it on the Voiceover track (created
        # when the project has none) exactly like an imported take.
        place_on_voiceover(self.state.project, medium["id"])
        voiceover = next(t for t in self.state.project.data["tracks"]
                         if t.get("role") == "voiceover")
        self.assertEqual(len(voiceover["items"]), 1)

    def test_record_duplicate_name_never_overwrites(self):
        with self._post_record("dup.wav", self.wav) as resp:
            first = json.loads(resp.read())["media"]["path"]
        with self._post_record("dup.wav", self.wav) as resp:
            second = json.loads(resp.read())["media"]["path"]
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.isfile(
            os.path.join(self.state.project_dir, first)))
        self.assertTrue(os.path.isfile(
            os.path.join(self.state.project_dir, second)))

    def test_record_rejects_non_audio(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post_record("notes.txt", b"hello")
        self.assertEqual(ctx.exception.code, 400)

    def test_record_rejects_empty_payload(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post_record("empty.wav", b"")
        self.assertEqual(ctx.exception.code, 400)


def _manifest_plugin_dir(tmp: str, entry_ok: bool = True,
                         malformed: bool = False) -> str:
    folder = os.path.join(tmp, "plugins")
    sub = os.path.join(folder, "manifest_upper")
    os.makedirs(sub, exist_ok=True)
    if malformed:
        with open(os.path.join(sub, "plugin.json"), "w",
                  encoding="utf-8") as fh:
            fh.write("{not json")
        return folder
    manifest = {"id": "manifest_upper", "name": "Manifest Upper",
                "hooks": ["transform_text"]}
    if entry_ok:
        manifest["entry"] = "main.py"
        with open(os.path.join(sub, "main.py"), "w",
                  encoding="utf-8") as fh:
            fh.write(
                "def _upper(project, item_id):\n"
                "    _track, item = project.item(item_id)\n"
                "    item['text'] = item.get('text', '').upper()\n"
                "    return item\n"
                "\n"
                "def register():\n"
                "    return {'name': 'manifest_upper', "
                "'transform_text': _upper}\n")
    with open(os.path.join(sub, "plugin.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh)
    return folder


class ManifestExecutionTest(unittest.TestCase):
    """Task 3: manifest-declared plugins really execute."""

    def test_manifest_plugin_executes_and_changes_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _manifest_plugin_dir(tmp)
            plugins = load_plugins(folder)
            self.assertIn("manifest_upper", plugins)
            self.assertEqual(plugins["manifest_upper"].get("manifest_entry"),
                             "main.py")
            proj = Project(new_project("t"), tmp)
            item = proj.add_text("t1", "hello world", 0, 30)
            result = apply_plugin(proj, "manifest_upper",
                                  "transform_text", item["id"],
                                  plugins_dir=folder)
            self.assertEqual(result["text"], "HELLO WORLD")

    def test_disabled_manifest_plugin_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _manifest_plugin_dir(tmp)
            set_plugin_enabled("manifest_upper", False,
                               plugins_dir=folder)
            proj = Project(new_project("t"), tmp)
            item = proj.add_text("t1", "hello world", 0, 30)
            with self.assertRaises(ValueError):
                apply_plugin(proj, "manifest_upper", "transform_text",
                             item["id"], plugins_dir=folder)

    def test_malformed_manifest_errors_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _manifest_plugin_dir(tmp, malformed=True)
            plugins = load_plugins(folder)
            self.assertNotIn("manifest_upper", plugins)
            self.assertTrue(plugins["_errors"])

    def test_manifest_without_entry_is_not_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _manifest_plugin_dir(tmp, entry_ok=False)
            plugins = load_plugins(folder)
            self.assertIn("manifest_upper", plugins)
            self.assertNotIn("manifest_entry", plugins["manifest_upper"])
            proj = Project(new_project("t"), tmp)
            item = proj.add_text("t1", "hello world", 0, 30)
            with self.assertRaises(ValueError):
                apply_plugin(proj, "manifest_upper", "transform_text",
                             item["id"], plugins_dir=folder)


class Round4UiWiringTest(unittest.TestCase):
    """Tasks 1 + 2 UI side: controls exist, call the real
    endpoint / real wipe code, and no id is duplicated."""

    @classmethod
    def setUpClass(cls):
        static = os.path.join(WINDOWS, "static")
        with open(os.path.join(static, "index.html"),
                  encoding="utf-8") as fh:
            cls.html = fh.read()
        with open(os.path.join(static, "app.js"),
                  encoding="utf-8") as fh:
            cls.js = fh.read()
        with open(os.path.join(static, "style.css"),
                  encoding="utf-8") as fh:
            cls.css = fh.read()

    def test_no_duplicate_ids(self):
        ids = re.findall(r'id="([^"]+)"', self.html)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dupes, [])

    def test_recording_controls_exist_and_call_real_endpoint(self):
        for element_id in ("btnVoiceRecord", "btnVoiceRecordStop",
                           "voiceRecordStatus", "voiceRecordPreview"):
            self.assertIn(f'id="{element_id}"', self.html)
        # Record button is enabled (round 3 had it disabled).
        self.assertNotIn('id="btnVoiceRecord" disabled', self.html)
        self.assertIn("/api/voiceover/record", self.js)
        self.assertIn("getUserMedia", self.js)
        self.assertIn("MediaRecorder", self.js)
        self.assertIn("voiceMedia", self.js)

    def test_compare_wipe_controls_exist(self):
        for element_id in ("compareWrap", "compareDivider",
                           "compareRange", "previewCompareSource",
                           "previewCompareExport", "btnPreviewCompare"):
            self.assertIn(f'id="{element_id}"', self.html)
        self.assertIn("compareWipeAt", self.js)
        self.assertIn("compareWireSync", self.js)
        self.assertIn("pointerdown", self.js)
        # Honest sync wording: time-sync, not sample-accurate lock.
        self.assertIn("time-sync", self.js)
        self.assertIn(".compare-wipe", self.css)
        self.assertIn("clip-path", self.css)
        # The [hidden] rule must beat the flex rule, or Compare
        # would stay visible after being switched off.
        self.assertIn("#compareWrap[hidden]", self.css)


if __name__ == "__main__":
    unittest.main()
