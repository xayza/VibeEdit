"""Round 5: honest-tool conversions.

Covers the 11 tools that left the honest set in round 5:
app_update_later / app_update_skip (real defer/skip state in
updater.json), library_search, plugins_search, plugins_run /
plugins_invoke (declared-hook execution via apply_plugin),
media_ocr / media_subjects (aliases of the already-real
vision_text / vision_faces), vision_cutout (description fix —
its handler was already real), media_analysis / media_analyze
(ffprobe-based analysis via media_metadata).

Updater state tests patch vibeedit_core.updater.__file__ into a
temp dir so the real updater.json next to the module is never
touched; the module reads its state path from __file__ at call
time, so the patch is sufficient.
"""

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core import updater  # noqa: E402
from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)
from vibeedit_core.render import probe_media  # noqa: E402

HERE = os.path.dirname(__file__)
PLUGINS_SRC = os.path.join(HERE, "..", "plugins", "uppercase_text.py")


def _parse_z(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


class TestUpdaterDeferSkip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patch = mock.patch.object(
            updater, "__file__", os.path.join(self.tmp, "updater.py"))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _state_file(self):
        return os.path.join(self.tmp, "updater.json")

    def test_defer_stores_version_and_remind_after(self):
        res = updater.defer_update("9.9.9", remind_in_days=3)
        rec = res["deferred"]
        self.assertEqual(rec["version"], "9.9.9")
        delta = _parse_z(rec["remind_after"]) - _parse_z(rec["deferred_at"])
        self.assertEqual(delta, datetime.timedelta(days=3))
        with open(self._state_file(), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["deferred"], rec)

    def test_defer_default_seven_days_and_rejects_empty(self):
        rec = updater.defer_update("1.2.3")["deferred"]
        delta = _parse_z(rec["remind_after"]) - _parse_z(rec["deferred_at"])
        self.assertEqual(delta, datetime.timedelta(days=7))
        with self.assertRaises(ValueError):
            updater.defer_update("")
        with self.assertRaises(ValueError):
            updater.defer_update("1.0", remind_in_days=-1)

    def test_skip_appends_and_deduplicates(self):
        self.assertEqual(updater.skip_update("2.0.0")["skipped_versions"],
                         ["2.0.0"])
        self.assertEqual(updater.skip_update("2.0.0")["skipped_versions"],
                         ["2.0.0"])
        self.assertEqual(updater.skip_update("2.1.0")["skipped_versions"],
                         ["2.0.0", "2.1.0"])
        with self.assertRaises(ValueError):
            updater.skip_update("  ")

    def test_defer_skip_preserve_releases_url(self):
        with open(self._state_file(), "w", encoding="utf-8") as fh:
            json.dump({"releases_url": "https://example.invalid/rel"},
                      fh)
        updater.defer_update("3.0.0", remind_in_days=1)
        updater.skip_update("2.9.0")
        with open(self._state_file(), encoding="utf-8") as fh:
            state = json.load(fh)
        self.assertEqual(state["releases_url"],
                         "https://example.invalid/rel")
        self.assertEqual(state["deferred"]["version"], "3.0.0")
        self.assertEqual(state["skipped_versions"], ["2.9.0"])

    def test_corrupt_state_file_is_tolerated(self):
        with open(self._state_file(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        res = updater.skip_update("4.0.0")
        self.assertEqual(res["skipped_versions"], ["4.0.0"])

    def test_update_status_reports_defer_skip(self):
        with mock.patch.object(updater, "get_channel", lambda: None):
            updater.defer_update("5.0.0", remind_in_days=2)
            updater.skip_update("4.9.0")
            status = updater.update_status()
        self.assertEqual(status["deferred"]["version"], "5.0.0")
        self.assertEqual(status["skipped_versions"], ["4.9.0"])
        self.assertIn("no updater configured", status["status"])


def _make_server(tmp):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=320x180:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", os.path.join(tmp, "c1.mp4")],
        capture_output=True, check=True)
    proj = Project(new_project("r5", width=320, height=180,
                               fps=(30, 1)), tmp)
    medium = proj.add_media(
        "c1.mp4", kind="video",
        **probe_media(os.path.join(tmp, "c1.mp4")))
    clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
    text = proj.add_text("t1", "hello world", 0, 30)
    save_project(proj.data, os.path.join(tmp, "project.vibeedit.json"))
    return MCPServer(tmp), medium, clip, text


class TestRound5McpTools(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server, self.medium, self.clip, self.text = _make_server(
            self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_registry_counts_round5(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(TOOLS), 479)
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        # Round 5: 132 -> 120 (12 tools became real, listed below).
        self.assertEqual(len(honest), 78)  # Round 9: 85 -> 78, 7 tools became real (see tests/test_round9.py)

    def test_app_update_later_skip_via_mcp(self):
        with mock.patch.object(
                updater, "__file__",
                os.path.join(self.tmp, "updater.py")):
            later = self.server.call("vibeedit_app_update_later",
                                     {"version": "9.9.9",
                                      "remind_in_days": 2})
            self.assertEqual(later["deferred"]["version"], "9.9.9")
            skipped = self.server.call("vibeedit_app_update_skip",
                                       {"version": "9.8.0"})
            self.assertIn("9.8.0", skipped["skipped_versions"])
            with self.assertRaises(ValueError):
                self.server.call("vibeedit_app_update_later", {})
            with self.assertRaises(ValueError):
                self.server.call("vibeedit_app_update_skip", {})

    def test_library_search(self):
        srv = self.server
        entry = srv.call("vibeedit_library_add",
                         {"item": self.text["id"], "name": "greeting"})
        found = srv.call("vibeedit_library_search", {"query": "greet"})
        self.assertTrue(any(e["id"] == entry["id"]
                            for e in found["items"]))
        self.assertEqual(found["count"], 1)
        self.assertEqual(
            srv.call("vibeedit_library_search",
                     {"query": "zzz-no-match"})["count"], 0)
        all_items = srv.call("vibeedit_library_search", {})
        self.assertGreaterEqual(all_items["count"], 1)

    def _temp_plugins(self):
        plugs = os.path.join(self.tmp, "plugs")
        os.makedirs(plugs, exist_ok=True)
        shutil.copy(PLUGINS_SRC, os.path.join(plugs, "uppercase_text.py"))
        return plugs

    def test_plugins_search_and_run(self):
        plugs = self._temp_plugins()
        found = self.server.call("vibeedit_plugins_search",
                                 {"query": "upper",
                                  "plugins_dir": plugs})
        self.assertTrue(any(p["name"] == "uppercase_text"
                            for p in found["plugins"]))
        self.assertEqual(self.server.call(
            "vibeedit_plugins_search",
            {"query": "zzz-no-match", "plugins_dir": plugs})["count"], 0)
        res = self.server.call("vibeedit_plugins_run",
                               {"plugin": "uppercase_text",
                                "hook": "transform_text",
                                "item": self.text["id"],
                                "plugins_dir": plugs})
        self.assertEqual(res["item"]["text"], "HELLO WORLD")
        # Invoke is the same documented path, not a second executor.
        res2 = self.server.call("vibeedit_plugins_invoke",
                                {"plugin": "uppercase_text",
                                 "hook": "transform_text",
                                 "item": self.text["id"],
                                 "plugins_dir": plugs})
        self.assertEqual(res2["item"]["text"], "HELLO WORLD")

    def test_plugins_run_refuses_disabled_and_unknown(self):
        plugs = self._temp_plugins()
        with open(os.path.join(self.tmp, "plugins.json"), "w",
                  encoding="utf-8") as fh:
            json.dump({"disabled": ["uppercase_text"]}, fh)
        with self.assertRaises(ValueError) as ctx:
            self.server.call("vibeedit_plugins_run",
                             {"plugin": "uppercase_text",
                              "hook": "transform_text",
                              "item": self.text["id"],
                              "plugins_dir": plugs})
        self.assertIn("disabled", str(ctx.exception))
        with self.assertRaises(Exception):
            self.server.call("vibeedit_plugins_run",
                             {"plugin": "no-such-plugin",
                              "hook": "transform_text",
                              "item": self.text["id"],
                              "plugins_dir": plugs})
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_plugins_run",
                             {"plugin": "uppercase_text"})

    def test_media_ocr_subjects_are_vision_aliases(self):
        # Routing proof: with no media/path the call reaches the
        # vision handler's argument error, NOT the honest fallback.
        for name in ("vibeedit_media_ocr", "vibeedit_media_subjects",
                     "vibeedit_vision_cutout"):
            with self.assertRaises(ValueError) as ctx:
                self.server.call(name, {})
            self.assertIn("vision tool needs", str(ctx.exception))
            self.assertNotIn("NOT_AVAILABLE", str(ctx.exception))
        descs = {t["name"]: t["description"] for t in TOOLS}
        for name in ("vibeedit_media_ocr", "vibeedit_media_subjects",
                     "vibeedit_vision_cutout"):
            self.assertFalse(descs[name].startswith("Not available"),
                             name)

    def test_media_proxy(self):
        res = self.server.call("vibeedit_media_proxy",
                               {"media": self.medium["id"], "width": 160})
        self.assertTrue(os.path.isfile(res["path"]))
        self.assertEqual(res["width"], 160)
        self.assertEqual(res["height"], 90)
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_media_proxy", {})

    def test_media_analysis_via_ffprobe(self):
        # Round 7: media_analysis still reads stored metadata +
        # live ffprobe; media_analyze now measures for real and
        # returns the job shape (each media with its key and
        # whether it was reused), not the metadata shape.
        res = self.server.call("vibeedit_media_analysis",
                               {"media": self.medium["id"]})
        self.assertTrue(res.get("probed"))
        self.assertEqual(res.get("width"), 320)
        analyzed = self.server.call("vibeedit_media_analyze",
                                    {"media": self.medium["id"]})
        self.assertEqual(len(analyzed["results"]), 1)
        self.assertEqual(analyzed["results"][0]["media"],
                         self.medium["id"])
        self.assertIn("key", analyzed["results"][0])
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_media_analysis", {})


if __name__ == "__main__":
    unittest.main()
