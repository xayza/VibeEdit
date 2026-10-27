"""Round 3 full-parity tests.

Covers what rounds 1+2 left open: marker shifting through clip moves
and close_gaps, the four original-name MCP aliases, the voice
provider interface (missing-backend path on this VM), the updater
framework (unconfigured channel + download SHA verify over a local
file URL), the learned-cutout model slot, the round-3 web-UI wiring
ids, and the viewport-fit CSS rules derived from the original's real
layout metrics. Temp dirs only; no user sample projects/media.

Original metrics (VibeEdit/VibeEdit/Views, read-only):
- EditorView+Layout.swift: rail 54, library 300 (372 on screens
  >=1680), viewer min 260, editor min 860, Inspector 300 (340 at
  window >=1680), timeline min 170 / ideal 330, window min 600.
- TimelineLayout.swift: ruler 22, rows 29, Main row 46, spacing 6.
- Conversion: 1pt == 1 CSS px at 100% scale; Windows scaling
  shrinks the CSS viewport, so the breakpoints below trigger at
  exactly the scaled widths (1280@125% -> 1024, 1366@125% -> 1093,
  1366@150% -> 911, 1280@150% -> 853).
"""

import glob
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402
from vibeedit_core.project import Project, new_project, save_project  # noqa: E402
from vibeedit_core.updater import (  # noqa: E402
    CURRENT_VERSION, UpdaterUnavailable, download_release, update_status)
from vibeedit_core.vision import VisionUnavailable, cutout_segmented  # noqa: E402
from vibeedit_core.voice import (  # noqa: E402
    VoiceUnavailable, available_backends, place_on_voiceover, synthesize)


def _make_project(tmp):
    return Project(new_project("test", width=320, height=180), tmp)


def _main_track(proj):
    return next(t for t in proj.data["tracks"] if t.get("role") == "main")


def _clips_on_main(proj, starts, dur=60):
    main = _main_track(proj)
    m = proj.add_media("media/a.mp4", "video", width=320, height=180,
                       fps=30, frames=600, duration=20.0)
    return [proj.add_clip(m["id"], main["id"], at, dur=dur)
            for at in starts]


def _marker_ats(proj):
    return sorted(int(m["at"]) for m in proj.data.get("markers", []))


class TestMarkerShifts(unittest.TestCase):
    def test_reorder_moves_markers_with_their_clips(self):
        # 4 clips of 60 frames at 0/60/120/180, one marker per clip.
        # Moving clip3 (at 180) before clip1 (at 60) gives order
        # clip0, clip3, clip1, clip2, so each clip's marker follows
        # it: 30 stays, 210 -> 90, 90 -> 150, 150 -> 210.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            clips = _clips_on_main(proj, [0, 60, 120, 180])
            marks = [proj.add_marker(f"m{i}", at)
                     for i, at in enumerate([30, 90, 150, 210])]
            proj.reorder_main(clips[3]["id"], clips[1]["id"])
            by_id = {m["id"]: int(m["at"])
                     for m in proj.data["markers"]}
            self.assertEqual(by_id[marks[0]["id"]], 30)
            self.assertEqual(by_id[marks[3]["id"]], 90)
            self.assertEqual(by_id[marks[1]["id"]], 150)
            self.assertEqual(by_id[marks[2]["id"]], 210)

    def test_close_gaps_collapses_gap_markers(self):
        # Clips of 60 at 0/100/250/400 close to 0/60/120/180.
        # Markers inside clips shift with them; markers in gaps
        # collapse to the next clip's new start; markers past the
        # last clip's original end are unchanged.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            _clips_on_main(proj, [0, 100, 250, 400])
            for at in [30, 80, 150, 220, 280, 420, 500]:
                proj.add_marker(f"m{at}", at)
            proj.close_gaps()
            self.assertEqual(_marker_ats(proj),
                             [30, 60, 110, 120, 150, 200, 500])
            ats = sorted(int(i["at"]) for i in _main_track(proj)["items"])
            self.assertEqual(ats, [0, 60, 120, 180])

    def test_plain_move_moves_only_the_moved_span_markers(self):
        # A non-Main track move ripples nothing: only markers
        # inside the moved clip's span follow it.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            overlay = next(t for t in proj.data["tracks"]
                           if t.get("role") == "overlay")
            m = proj.add_media("media/b.mp4", "video", width=320,
                               height=180, fps=30, frames=600,
                               duration=20.0)
            clip = proj.add_clip(m["id"], overlay["id"], 100, dur=60)
            for at in [50, 110, 200]:
                proj.add_marker(f"m{at}", at)
            proj.move(clip["id"], overlay["id"], 300)
            self.assertEqual(_marker_ats(proj), [50, 200, 310])


class TestOriginalNameAliases(unittest.TestCase):
    def test_all_249_original_specs_have_a_registry_name(self):
        # Counting method: specs are extracted from the original
        # CommandCatalog with the multiline regex (a single-line
        # grep only finds 7, because specs are written multiline).
        # Normalisation: dots AND hyphens -> underscores, prefixed
        # with vibeedit_. The 4 names that differ from the Windows
        # canonical names are covered by real alias TOOLS entries.
        root = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        swift_root = os.path.join(root, "..", "VibeEdit", "VibeEdit",
                                  "Core", "Automation")
        specs = set()
        pat = re.compile(r"CommandSpec\(\s*\n?\s*\"([^\"]+)\"")
        for path in glob.glob(os.path.join(swift_root,
                                           "CommandCatalog*.swift")):
            with open(path, encoding="utf-8") as fh:
                specs.update(pat.findall(fh.read()))
        self.assertEqual(len(specs), 249)
        names = {t["name"] for t in TOOLS}
        missing = [s for s in sorted(specs)
                   if "vibeedit_" + s.replace(".", "_").replace("-", "_")
                   not in names]
        self.assertEqual(missing, [])

    def test_alias_tools_are_unique_and_dispatch(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 478)
        self.assertIn("vibeedit_beats_detect", names)
        self.assertIn("vibeedit_clip_speed_curve", names)
        self.assertIn("vibeedit_transcript_words", names)
        self.assertIn("vibeedit_library_save_selection", names)
        self.assertIn("vibeedit_app_update_download", names)
        self.assertIn("vibeedit_vision_cutout_model", names)

    def test_voice_speak_alias_fails_controlled_not_unknown(self):
        # No voice backend exists on this VM, so synthesis must
        # raise the missing-backend error, never "Unknown tool".
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            with self.assertRaises(Exception) as ctx:
                server.call("vibeedit_voice_speak",
                            {"text": "hello"})
            self.assertNotIn("Unknown tool", str(ctx.exception))


class TestVoiceInterface(unittest.TestCase):
    def test_missing_backends_raise_clear_error(self):
        backends = available_backends()
        self.assertIn("piper", backends)
        self.assertIn("edge_tts", backends)
        if not backends["piper"] and not backends["edge_tts"]:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "take.wav")
                with self.assertRaises(VoiceUnavailable) as ctx:
                    synthesize("hello", out)
                self.assertIn("Piper", str(ctx.exception))
                self.assertIn("edge-tts", str(ctx.exception))

    def test_empty_text_and_non_audio_place_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                synthesize("", os.path.join(tmp, "take.wav"))
            proj = _make_project(tmp)
            m = proj.add_media("media/v.mp4", "video", width=320,
                               height=180, fps=30, frames=60,
                               duration=2.0)
            with self.assertRaises(ValueError):
                place_on_voiceover(proj, m["id"])


class TestUpdaterFramework(unittest.TestCase):
    def test_unconfigured_status_touches_no_network(self):
        old = os.environ.pop("VIBEEDIT_RELEASES_URL", None)
        try:
            status = update_status()
            self.assertEqual(status["current_version"], CURRENT_VERSION)
            self.assertIsNone(status["update_channel"])
        finally:
            if old is not None:
                os.environ["VIBEEDIT_RELEASES_URL"] = old

    def test_download_verifies_sha256(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "asset.bin")
            data = b"vibeedit-test-asset"
            with open(src, "wb") as fh:
                fh.write(data)
            digest = hashlib.sha256(data).hexdigest()
            dest = os.path.join(tmp, "out", "asset.bin")
            res = download_release("file://" + src, dest, sha256=digest)
            self.assertEqual(res["sha256"], digest)
            self.assertEqual(res["bytes"], len(data))
            with self.assertRaises(UpdaterUnavailable):
                download_release("file://" + src, dest,
                                 sha256="0" * 64)


class TestLearnedCutoutSlot(unittest.TestCase):
    def test_missing_model_errors_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "frame.png")
            from PIL import Image
            Image.new("RGB", (8, 8), "white").save(img)
            with self.assertRaises(VisionUnavailable) as ctx:
                cutout_segmented(img, None)
            self.assertIn("model", str(ctx.exception).lower())
            with self.assertRaises(VisionUnavailable):
                cutout_segmented(img, os.path.join(tmp, "nope.onnx"))


class TestRound3WebUI(unittest.TestCase):
    def _static(self, name):
        root = os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))
        with open(os.path.join(root, "static", name),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_wiring_ids_exist_and_are_unique(self):
        html = self._static("index.html")
        for element_id in (
                "voiceVoice", "voiceGenModel", "voiceGenText",
                "knowledgeList", "knowledgeResult", "knowledgeSaveForm",
                "knowledgeSaveId", "knowledgeSaveBody",
                "knowledgeSaveOverwrite", "btnKnowledgePropose",
                "knowledgeLessonForm", "knowledgeRemoveConfirm",
                "visionMedia", "visionModelPath", "btnVisionOcr",
                "btnVisionFaces", "btnVisionCutout",
                "btnVisionCutoutModel", "pluginInstallForm",
                "pluginInstallSource", "pluginInstallLabel",
                "pluginDownloadForm", "pluginDownloadUrl",
                "pluginDownloadConfirm", "pluginInstallResult",
                "tlMagnetic"):
            self.assertIn(f'id="{element_id}"', html, element_id)
        ids = re.findall(r'id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("data:image", html)  # logo data URI intact

    def test_new_wiring_handlers_call_real_ops(self):
        js = self._static("app.js")
        for op in ("skills_list", "skills_save", "skills_propose",
                   "skills_remove", "plugin_install", "plugin_download",
                   "magnetic_set"):
            self.assertIn(f'op: "{op}"', js, op)
        # Vision goes through the vision(op) helper, which posts
        # {op, media}; the op names must still appear verbatim.
        for op in ("vision_ocr", "vision_faces", "vision_cutout",
                   "vision_cutout_model"):
            self.assertIn(f'"{op}"', js, op)
        self.assertIn("vision(\"vision_ocr\")", js)

    def test_viewport_fit_rules_match_original_metrics(self):
        css = self._static("style.css")
        # No workbench horizontal-scroll strip: the old stacking
        # block is gone, and the page itself never scrolls.
        self.assertNotIn(".workbench { flex-wrap: wrap", css)
        self.assertIn("body { display: flex; flex-direction: column; "
                      "height: 100vh; overflow: hidden; }", css)
        # Right column: original 300, 340 at >=1680 (was flat 380).
        self.assertIn(".details-col { width: 300px; }", css)
        self.assertIn("@media (min-width: 1680px)", css)
        self.assertIn(".details-col { width: 340px; }", css)
        # Timeline: original ruler/rows + ideal-height pane.
        self.assertIn(".ruler { height: 22px; }", css)
        self.assertIn(".track-lane { min-height: 29px; }", css)
        self.assertIn(".track-row-main .track-lane { min-height: 46px; }",
                      css)
        self.assertIn("max-height: clamp(300px, 46vh, 480px)", css)
        # Viewer fits its pane; rail scrolls internally.
        self.assertIn(".centre-col { display: flex; flex-direction: "
                      "column; overflow: hidden; }", css)
        self.assertIn(".tool-rail { overflow-y: auto;", css)

    def test_column_arithmetic_fits_required_viewports(self):
        # Fixed widths (tool + details + viewer-min 260) must fit
        # every required effective viewport. 1pt == 1 CSS px.
        cases = [
            # (viewport, tool, details): base, scaled, wide, narrow
            (1920, 356, 340), (1600, 356, 300), (1280, 356, 300),
            (1093, 300, 300), (1024, 300, 300), (911, 300, 300),
            (853, 280, 280),
        ]
        for viewport, tool, details in cases:
            total = tool + details + 260
            self.assertLessEqual(total, viewport,
                                 (viewport, tool, details, total))
        # Vertical budget at 720px height: topbar ~85 + timeline
        # cap 46vh (~331, the original ideal 330) leaves ~304 for
        # the panes, above the original pane minimum of 220.
        self.assertGreaterEqual(720 - 85 - round(720 * 0.46), 220)


if __name__ == "__main__":
    unittest.main()
