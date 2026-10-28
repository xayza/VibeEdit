"""Round 20: shortcut map derived from app.js, timeline frames from a
real FFmpeg render, and the tools deliberately kept honest.

New tests live ONLY here (round-20 file). Old-test count bumps are
applied separately at the end of the round, after the count settles.
"""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import (  # noqa: E402
    MCPServer, TOOLS, shortcuts_from_app_js)
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)
from vibeedit_core.render import probe_media  # noqa: E402

WINDOWS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(WINDOWS_DIR, "static", "app.js")

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:  # pragma: no cover
    HAS_PILLOW = False


def _color_clip(folder, name, color, seconds=1, rate=30):
    src = os.path.join(folder, name)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c={color}:size=320x180:rate={rate}:"
                          f"duration={seconds}",
                    "-pix_fmt", "yuv420p", src],
                   capture_output=True, check=True)
    return name


def _red_dominant(pixel):
    r, g, b = pixel
    return r > 200 and g < 80 and b < 80


def _blue_dominant(pixel):
    r, g, b = pixel
    return b > 200 and r < 80 and g < 80


class TestRound20Shortcuts(unittest.TestCase):
    def test_map_has_pinned_shortcuts(self):
        result = shortcuts_from_app_js(APP_JS)
        self.assertGreaterEqual(result["listeners"], 5)
        by_keys = {s["keys"]: s["action"] for s in result["shortcuts"]}
        pinned = {
            "Ctrl+S": "POST /api/save",
            "Ctrl+Z": "POST /api/undo",
            "Ctrl+Shift+Z": "POST /api/redo",
            "Ctrl+Y": "POST /api/redo",
            "Ctrl+K": "splitAtPlayhead()",
            "Ctrl+Shift+K": "splitAllAtPlayhead()",
            "Ctrl+N": "openCreateProject()",
            "Ctrl+O": "openSavedProject()",
            "Ctrl+E": "open rail tab effects",
            "Ctrl+T": "open rail tab text",
            "Ctrl+R": "click inspTabSpeed",
            "Alt+Shift+C": "click btnExportFull",
            "Shift+Z": "toggleTimelineZoom()",
            "Shift+A": "stepPlayhead()",
            "Shift+B": "openSpeedCurve()",
            "Shift+Backspace": "click tlCloseGaps",
            "Delete": "click btnDelete",
            "Space": "click btnPreviewPlay",
            "S": "click tlMagnetic",
            "I": "markSource()",
            "O": "markSource()",
            "E": "placeSource()",
            "Q": "placeSource()",
            "Escape": "applyAgentCollapsePref()",
            "J": "stepPlayhead()",
            "K": "pause preview",
            "L": "playPreviewFromKey()",
            "ArrowLeft": "stepPlayhead()",
            "ArrowRight": "stepPlayhead()",
            "A": "stepPlayhead()",
        }
        for keys, action in pinned.items():
            self.assertIn(keys, by_keys, f"missing shortcut {keys}")
            self.assertEqual(by_keys[keys], action, keys)
        self.assertEqual(len(result["shortcuts"]), 30)

    def test_unbound_keys_absent(self):
        result = shortcuts_from_app_js(APP_JS)
        keys = {s["keys"] for s in result["shortcuts"]}
        # Deliberately unbound (round-18 comment block): the parser
        # reads listener bodies only, so comment text can never leak in.
        for unbound in ("Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+A",
                        "Ctrl+Shift+S", "Ctrl+Shift+F", "Ctrl+G",
                        "Ctrl+Shift+G", "V", "C", "Shift+P", "Shift+X"):
            self.assertNotIn(unbound, keys, unbound)

    def test_derivation_by_mutation(self):
        # Proof the map comes from the live file, not a hand-kept
        # table: deleting one branch from a COPY removes exactly that
        # shortcut, and deleting the S branch removes S only.
        with open(APP_JS, encoding="utf-8") as fh:
            src = fh.read()
        with tempfile.TemporaryDirectory() as tmp:
            mutated = os.path.join(tmp, "app.js")
            cut = src.replace(
                'else if (key === "k" && !shift) { e.preventDefault(); '
                'splitAtPlayhead(); }', "")
            self.assertNotEqual(cut, src)
            with open(mutated, "w", encoding="utf-8") as fh:
                fh.write(cut)
            keys = {s["keys"]
                    for s in shortcuts_from_app_js(mutated)["shortcuts"]}
            self.assertNotIn("Ctrl+K", keys)
            self.assertIn("Ctrl+Shift+K", keys)
            cut2 = src.replace(
                'if (e.key === "s" || e.key === "S") {', 'if (false) {')
            self.assertNotEqual(cut2, src)
            with open(mutated, "w", encoding="utf-8") as fh:
                fh.write(cut2)
            keys2 = {s["keys"]
                     for s in shortcuts_from_app_js(mutated)["shortcuts"]}
            self.assertNotIn("S", keys2)
            self.assertIn("Ctrl+S", keys2)

    def test_missing_file_raises(self):
        with self.assertRaises(ValueError):
            shortcuts_from_app_js(os.path.join(tempfile.gettempdir(),
                                               "no-such-app.js"))

    def test_via_mcp_tool(self):
        server = MCPServer()
        result = server.call("vibeedit_show_shortcuts", {})
        keys = {s["keys"] for s in result["shortcuts"]}
        self.assertIn("Ctrl+K", keys)
        self.assertIn("Space", keys)
        self.assertNotIn("Ctrl+C", keys)


@unittest.skipUnless(HAS_PILLOW, "Pillow required for pixel checks")
class TestRound20TimelineFrames(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _color_clip(self.tmp, "red.mp4", "red")
        _color_clip(self.tmp, "blue.mp4", "blue")
        proj = Project(new_project("fr", width=320, height=180,
                                   fps=(30, 1)), self.tmp)
        m1 = proj.add_media("red.mp4", kind="video",
                            **probe_media(os.path.join(self.tmp,
                                                       "red.mp4")))
        m2 = proj.add_media("blue.mp4", kind="video",
                            **probe_media(os.path.join(self.tmp,
                                                       "blue.mp4")))
        proj.add_clip(m1["id"], "v1", 0, 0, 30)
        proj.add_clip(m2["id"], "v1", 30, 0, 30)
        save_project(proj.data,
                     os.path.join(self.tmp, "project.vibeedit.json"))
        self.server = MCPServer(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pixel(self, frame):
        raw = base64.b64decode(frame["png_base64"])
        self.assertEqual(raw[:8], b"\x89PNG\r\n\x1a\n")
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        w, h = img.size
        self.assertEqual((w, h), (frame["width"], frame["height"]))
        return img.getpixel((w // 2, h // 2))

    def test_frame_colors_by_time(self):
        # Draft preset halves 320x180 -> 160x90; colors must be the
        # TIMELINE composition at that time, not a media first frame.
        early = self.server.call("vibeedit_ui_frame", {"time": 0.5})
        late = self.server.call("vibeedit_ui_frame", {"time": 1.5})
        self.assertEqual(early["preset"], "draft")
        self.assertEqual((early["frame"]["width"],
                          early["frame"]["height"]), (160, 90))
        self.assertTrue(_red_dominant(self._pixel(early["frame"])))
        self.assertTrue(_blue_dominant(self._pixel(late["frame"])))

    def test_frame_uses_playhead_by_default(self):
        self.server.call("vibeedit_ui_seek", {"frame": 45})
        frame = self.server.call("vibeedit_ui_frame", {})["frame"]
        self.assertTrue(_blue_dominant(self._pixel(frame)))

    def test_frames_times_and_count(self):
        multi = self.server.call("vibeedit_ui_frames",
                                 {"times": [0.5, 1.5]})
        self.assertEqual([f["time"] for f in multi["frames"]], [0.5, 1.5])
        self.assertTrue(_red_dominant(self._pixel(multi["frames"][0])))
        self.assertTrue(_blue_dominant(self._pixel(multi["frames"][1])))
        counted = self.server.call("vibeedit_ui_frames", {"count": 2})
        self.assertEqual([f["time"] for f in counted["frames"]],
                         [0.5, 1.5])

    def test_frame_time_validation(self):
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_ui_frame", {"time": 5})
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_ui_frame", {"time": "abc"})
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_ui_frames", {"count": 0})

    def test_empty_timeline_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Project(new_project("empty", width=320, height=180,
                                       fps=(30, 1)), tmp)
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            with self.assertRaises(ValueError):
                server.call("vibeedit_ui_frame", {"time": 0})


class TestRound20StillHonest(unittest.TestCase):
    def test_kept_honest_tools_raise(self):
        # Deliberate keeps, with the precise reason each stays honest:
        # show_settings (no server-owned settings exist; the modal
        # shows project format, read-only info and browser-local
        # storage, so inventing keys nobody consumes would be fake),
        # platforms_get (no platform-facts table in either tree;
        # presets carry only width/height/bitrate, and maxSeconds /
        # LUFS / safe areas / text limits would be invented),
        # plus structural keeps (browser toggles, in-app chat,
        # provider/model tools, updater self-replace, plugin setup).
        server = MCPServer()
        for name in ("vibeedit_show_settings", "vibeedit_platforms_get",
                     "vibeedit_view_compare", "vibeedit_view_safe_area",
                     "vibeedit_ui_action", "vibeedit_agent_ask",
                     "vibeedit_chat_send", "vibeedit_voice_clone_add",
                     "vibeedit_image_generate", "vibeedit_app_update",
                     "vibeedit_plugins_setup",
                     "vibeedit_clip_send_to_agent"):
            with self.assertRaises(ValueError, msg=name):
                server.call(name, {})


class TestRound20RegistryCounts(unittest.TestCase):
    def test_counts(self):
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(honest), 52)  # Round 22: 54 -> 52
        self.assertEqual(len(TOOLS) - len(honest), 429)  # Round 23: 479 -> 481 (skills_import_plan/import)
        names = {t["name"] for t in TOOLS}
        for now_real in ("vibeedit_show_shortcuts", "vibeedit_ui_frame",
                         "vibeedit_ui_frames"):
            self.assertIn(now_real, names)
            self.assertNotIn(
                now_real, {t["name"] for t in honest}, now_real)


if __name__ == "__main__":
    unittest.main()
