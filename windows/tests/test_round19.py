"""Round 19 tests: honest tools that became real, resizable panels,
icon-button tooltips, and the single import control.

New tests ONLY in this file (plus the count-maintenance updates in old
test files documented in the round-19 report, which follow the repo's
established "Round 15: 78 -> 76" practice: exact-count assertions and
honest-list removals for tools verified genuinely real, nothing else).

Run from windows/: python3 -m unittest tests.test_round19 tests.test_round18 -v
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import TOOLS, MCPServer  # noqa: E402
from vibeedit_core.project import Project, new_project, save_project  # noqa: E402
from vibeedit_core.render import probe_media  # noqa: E402

WIN = os.path.join(os.path.dirname(__file__), "..")
HTML = open(os.path.join(WIN, "static", "index.html"),
             encoding="utf-8").read()
CSS = open(os.path.join(WIN, "static", "style.css"),
            encoding="utf-8").read()
JS = open(os.path.join(WIN, "static", "app.js"), encoding="utf-8").read()

CONVERTED_17 = [
    "vibeedit_show_about", "vibeedit_show_commands",
    "vibeedit_show_plugins", "vibeedit_show_history",
    "vibeedit_show_sections", "vibeedit_show_batch",
    "vibeedit_show_export", "vibeedit_show_export_progress",
    "vibeedit_show_review", "vibeedit_show_doctor",
    "vibeedit_show_agent_kit", "vibeedit_show_updates",
    "vibeedit_show_assets", "vibeedit_agent_quick_edit",
    "vibeedit_ui_select", "vibeedit_ui_seek", "vibeedit_context_get",
]

STILL_HONEST = [
    # Round 24: voice_clone_list/ui_dialog/chat_status left (now real, empty-by-design).
    "vibeedit_voice_clone_add",
    "vibeedit_voice_clone_remove", "vibeedit_image_generate",
    "vibeedit_library_generate", "vibeedit_app_update",
    "vibeedit_chat_send", "vibeedit_chat_command",
    "vibeedit_agent_ask", "vibeedit_chat_stop",
    "vibeedit_plugins_setup", "vibeedit_clip_send_to_agent",
    "vibeedit_acme_voice_fast",
    # Round 20: ui_frame/ui_frames left (now real, FFmpeg timeline frames).
    "vibeedit_playback_toggle", "vibeedit_playback_stop",
    "vibeedit_view_compare", "vibeedit_view_safe_area",
    # Round 20: show_shortcuts left (now real, parsed from app.js).
    "vibeedit_show_settings",
    "vibeedit_ui_action",
    # Round 22: agent_terminals/automation_clients left (now real).
    "vibeedit_agent_open",
    "vibeedit_agent_toggle_dock", "vibeedit_app_vibeedit",
    # Round 21: debug_log left (now real, file-backed MCP log).
    "vibeedit_platforms_get",
    "vibeedit_timeline_header_compact",
    "vibeedit_source_toggle_playback",
]


def make_server(tmp):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=320x180:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", os.path.join(tmp, "c1.mp4")],
        capture_output=True, check=True)
    proj = Project(new_project("r19", width=320, height=180,
                               fps=(30, 1)), tmp)
    medium = proj.add_media(
        "c1.mp4", kind="video",
        **probe_media(os.path.join(tmp, "c1.mp4")))
    clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
    text = proj.add_text("t1", "hello world", 0, 30)
    save_project(proj.data, os.path.join(tmp, "project.vibeedit.json"))
    return MCPServer(tmp), medium, clip, text


class Round19Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server, self.medium, self.clip, self.text = make_server(
            self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestRound19RegistryCounts(unittest.TestCase):
    def test_total_and_split(self):
        honest = [t for t in TOOLS
                  if (t.get("description") or "").startswith(
                      "Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(honest), 49)  # Round 22: 54 -> 52; Round 24: 52 -> 49 (voice_clone_list/ui_dialog/chat_status empty-by-design)
        self.assertEqual(len(TOOLS) - len(honest), 432)  # Round 23: 479 -> 481 (skills_import_plan/import); Round 24: 429 -> 432 (voice_clone_list/ui_dialog/chat_status empty-by-design)

    def test_converted_descriptions_not_honest(self):
        by_name = {t["name"]: t["description"] for t in TOOLS}
        for name in CONVERTED_17:
            self.assertIn(name, by_name, name)
            self.assertFalse(
                by_name[name].startswith("Not available"), name)


class TestRound19ShowAliases(Round19Case):
    def test_aliases_equal_canonical(self):
        s = self.server
        pairs = [
            ("vibeedit_show_about", "vibeedit_app_version"),
            ("vibeedit_show_commands", "vibeedit_mcp_tools_list"),
            ("vibeedit_show_plugins", "vibeedit_plugins_list"),
            ("vibeedit_show_history", "vibeedit_project_history"),
            ("vibeedit_show_assets", "vibeedit_media_list"),
            ("vibeedit_show_batch", "vibeedit_batch_status"),
            ("vibeedit_show_export", "vibeedit_export_status"),
            ("vibeedit_show_export_progress", "vibeedit_export_status"),
            # NOTE: show_review is NOT in this equality list on purpose:
            # review_get mutates once (validate() adds a missing
            # adjustment track), so two consecutive calls differ by
            # design; its own test below covers it.
            ("vibeedit_show_doctor", "vibeedit_doctor_run"),
            ("vibeedit_show_agent_kit", "vibeedit_agent_kit_check"),
            ("vibeedit_show_updates", "vibeedit_app_update_check"),
        ]
        for alias, canonical in pairs:
            with self.subTest(alias=alias):
                self.assertEqual(s.call(alias, {}),
                                 s.call(canonical, {}))

    def test_show_commands_count(self):
        out = self.server.call("vibeedit_show_commands", {})
        self.assertEqual(out["count"], 481)
        self.assertEqual(len(out["tools"]), 481)

    def test_show_assets_lists_real_media(self):
        out = self.server.call("vibeedit_show_assets", {})
        self.assertEqual(len(out["media"]), 1)
        self.assertEqual(out["media"][0]["id"], self.medium["id"])

    def test_show_review_has_real_validation(self):
        s = self.server
        out = s.call("vibeedit_show_review", {})
        self.assertIn("validation", out)
        self.assertIn("stats", out)
        self.assertTrue(out["validation"]["ok"])
        # After the first call's one-time adjustment-track fixup,
        # the canonical tool is stable: two more calls agree.
        again1 = s.call("vibeedit_review_get", {})
        again2 = s.call("vibeedit_review_get", {})
        self.assertEqual(again1, again2)

    def test_show_doctor_reports_real_environment(self):
        out = self.server.call("vibeedit_show_doctor", {})
        self.assertIn("python", out)
        self.assertTrue(out["ffmpeg"] or "ffmpeg_error" in out)

    def test_show_agent_kit_status_shape(self):
        out = self.server.call("vibeedit_show_agent_kit", {})
        self.assertIn("kitFolder", out)
        self.assertIn("skills", out)

    def test_show_sections_are_markers(self):
        s = self.server
        s.call("vibeedit_markers_add", {"text": "sec-a", "at": 30})
        out = s.call("vibeedit_show_sections", {})
        self.assertEqual(out, s.call("vibeedit_markers_list", {}))
        self.assertTrue(any(m["text"] == "sec-a"
                            for m in out["markers"]))

    def test_quick_edit_applies_ops_for_real(self):
        s = self.server
        out = s.call("vibeedit_agent_quick_edit", {"ops": [
            {"op": "add_text", "track": "t1", "text": "quick",
             "at": 90, "dur": 30}]})
        self.assertEqual(len(out["results"]), 1)
        texts = s.call("vibeedit_text_list", {})["items"]
        self.assertTrue(any(t["text"] == "quick" for t in texts))


class TestRound19SessionTools(Round19Case):
    def test_ui_select_sets_and_reads(self):
        s = self.server
        self.assertEqual(s.call("vibeedit_ui_select", {})["selection"],
                         [])
        out = s.call("vibeedit_ui_select",
                     {"items": [self.clip["id"]]})
        self.assertEqual(out["selection"], [self.clip["id"]])
        out = s.call("vibeedit_ui_select",
                     {"items": [self.clip["id"], self.text["id"]]})
        self.assertEqual(out["selection"],
                         [self.clip["id"], self.text["id"]])
        self.assertEqual(s.call("vibeedit_ui_select", {})["selection"],
                         [self.clip["id"], self.text["id"]])
        s.call("vibeedit_timeline_deselect", {})
        self.assertEqual(s.call("vibeedit_ui_select", {})["selection"],
                         [])

    def test_ui_select_rejects_unknown(self):
        with self.assertRaises(ValueError):
            self.server.call("vibeedit_ui_select",
                             {"items": ["no-such-item"]})

    def test_ui_seek_absolute_and_steps(self):
        s = self.server
        self.assertEqual(s.call("vibeedit_ui_seek", {"frame": 42})
                         ["frame"], 42)
        # The existing step tools observe the same session playhead.
        self.assertEqual(s.call("vibeedit_playhead_next_frame", {})
                         ["frame"], 43)
        self.assertEqual(s.call("vibeedit_ui_seek", {"frame": -5})
                         ["frame"], 0)
        with self.assertRaises(ValueError):
            s.call("vibeedit_ui_seek", {})
        with self.assertRaises(ValueError):
            s.call("vibeedit_ui_seek", {"frame": "not-a-frame"})

    def test_context_get_snapshot_matches_reality(self):
        s = self.server
        s.call("vibeedit_markers_add", {"text": "ctx", "at": 10})
        s.call("vibeedit_ui_seek", {"frame": 25})
        s.call("vibeedit_ui_select", {"items": [self.clip["id"]]})
        ctx = s.call("vibeedit_context_get", {})
        self.assertEqual(ctx["name"], "r19")
        self.assertEqual(ctx["playhead_frame"], 25)
        self.assertEqual(ctx["selection"], [self.clip["id"]])
        self.assertEqual(ctx["items"], 2)  # 1 clip + 1 text item
        self.assertTrue(any(m["text"] == "ctx"
                            for m in ctx["markers"]))
        self.assertGreater(ctx["duration_seconds"], 0)


class TestRound19StillHonest(Round19Case):
    def test_must_stay_honest_tools_error(self):
        s = self.server
        for name in STILL_HONEST:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    s.call(name, {})
                try:
                    s.call(name, {})
                except ValueError as exc:
                    self.assertIn("NOT_AVAILABLE", str(exc))


if __name__ == "__main__":
    unittest.main()


# ---- Round 19 UI tests: resize handles, tooltip, single import ----

def _extract_function(src, name):
    """Extract one top-level function by brace matching."""
    start = src.index("function " + name)
    brace = src.index("{", start)
    depth = 0
    i = brace
    while True:
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return src[start:i + 1]


def _run_node_helpers():
    """Run the pure round-19 JS helpers in node, return parsed JSON."""
    import json
    fns = "\n".join(_extract_function(JS, n) for n in
                     ("clampSize", "validStored", "panelTemplate",
                      "tooltipPosition"))
    harness = fns + """
const out = {
  clamp: [clampSize(100, 180, 480), clampSize(300, 180, 480),
          clampSize(500, 180, 480), clampSize("x", 180, 480),
          clampSize(NaN, 180, 480)],
  valid: [validStored(300, 180, 480), validStored(500, 180, 480),
          validStored("x", 180, 480)],
  panel: [panelTemplate(null, null, false),
          panelTemplate(320, null, false),
          panelTemplate(null, 400, false),
          panelTemplate(320, 400, false),
          panelTemplate(320, null, true),
          panelTemplate(null, null, true)],
  tip: [tooltipPosition({left: 100, top: 170, bottom: 200, width: 30},
                        80, 24, 1000, 800),
        tooltipPosition({left: 0, top: 100, bottom: 130, width: 30},
                        80, 24, 1000, 800),
        tooltipPosition({left: 990, top: 100, bottom: 130, width: 30},
                        80, 24, 1000, 800),
        tooltipPosition({left: 100, top: 760, bottom: 790, width: 30},
                        80, 24, 1000, 800)],
};
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(["node", "-e", harness], capture_output=True,
                          text=True, check=True)
    return json.loads(proc.stdout)


class TestRound19ResizeHandles(unittest.TestCase):
    def test_handles_exist_with_vietnamese_labels(self):
        for hid, label in (
                ("resizeTool", "cột công cụ"),
                ("resizeDetails", "cột chi tiết"),
                ("resizeTimeline", "timeline"),
                ("resizeAgent", "ngăn Agent")):
            m = re.search(r'<div[^>]*id="%s"[^>]*>' % hid, HTML)
            self.assertIsNotNone(m, hid)
            tag = m.group(0)
            self.assertIn('role="separator"', tag, hid)
            self.assertIn("aria-label=", tag, hid)
            self.assertIn(label, tag, hid)

    def test_handle_css_cursors_and_rules(self):
        self.assertIn("cursor: col-resize", CSS)
        self.assertIn("cursor: row-resize", CSS)
        self.assertIn("#resizeTool", CSS)
        self.assertIn("#resizeDetails", CSS)
        self.assertIn("#resizeAgent", CSS)
        self.assertIn(".resize-handle-h", CSS)
        self.assertIn("body.resizing", CSS)
        self.assertIn("user-select: none", CSS)

    def test_resize_js_wiring(self):
        for marker in ("vibeedit_panel_sizes", "pointerdown",
                       "pointermove", "pointerup", "dblclick",
                       "setPointerCapture", "stopPropagation",
                       "MutationObserver", "gridTemplateColumns",
                       "localStorage"):
            self.assertIn(marker, JS, marker)
        for limit in ("tool: [180, 480]", "details: [220, 520]",
                      "agent: [280, 520]", "0.6"):
            self.assertIn(limit, JS, limit)

    def test_locked_defaults_untouched(self):
        for locked in ("width: 280px;", "width: 340px;",
                       "width: 300px;",
                       "grid-template-columns: 280px minmax(0, 1fr) auto;",
                       "clamp(240px, 32vh, 340px)"):
            self.assertIn(locked, CSS, locked)

    def test_pure_resize_helpers_via_node(self):
        out = _run_node_helpers()
        self.assertEqual(out["clamp"], [180, 300, 480, None, None])
        self.assertEqual(out["valid"], [300, None, None])
        self.assertEqual(out["panel"], [
            "",
            "320px minmax(0, 1fr) auto",
            "280px minmax(0, 1fr) 400px",
            "320px minmax(0, 1fr) 400px",
            "320px minmax(0, 1fr)",
            "280px minmax(0, 1fr)",
        ])
        self.assertEqual(out["tip"], [
            {"left": 75, "top": 206, "below": True},
            {"left": 8, "top": 136, "below": True},
            {"left": 912, "top": 136, "below": True},
            {"left": 75, "top": 730, "below": False},
        ])


class TestRound19IconTooltip(unittest.TestCase):
    def _icon_buttons(self):
        tags = re.findall(r'<button[^>]*class="[^"]*tl-icon-btn[^"]*"[^>]*>',
                          HTML)
        self.assertGreater(len(tags), 0, "no tl-icon-btn buttons found")
        return tags

    def test_every_icon_button_has_matching_hover_name(self):
        for tag in self._icon_buttons():
            tip = re.search(r'data-tip="([^"]+)"', tag)
            label = re.search(r'aria-label="([^"]+)"', tag)
            self.assertIsNotNone(tip, tag)
            self.assertIsNotNone(label, tag)
            self.assertEqual(tip.group(1), label.group(1), tag)
            self.assertNotIn("title=", tag, tag)

    def test_body_level_tooltip_wiring(self):
        for marker in ('id = "uiTooltip"', "document.body.appendChild",
                       "mouseover", "mouseout", "focusin", "focusout",
                       "pointerdown", "aria-label", "tooltipPosition"):
            self.assertIn(marker, JS, marker)
        self.assertNotIn('id="uiTooltip"', HTML,
                         "tooltip div must be JS-created on body, "
                         "not nested in an overflow container")
        self.assertIn(".ui-tooltip", CSS)
        self.assertIn("position: fixed", CSS)
        self.assertIn("z-index: 100", CSS)

    def test_clipped_css_rule_kept_verbatim(self):
        # Locked by test_round18: the ::after rule stays (inert, as
        # the toolbar's scroll container clips it); the JS tooltip
        # is what users actually see.
        self.assertIn(".tl-icon-btn[data-tip]:hover::after", CSS)
        self.assertIn("content: attr(data-tip)", CSS)


class TestRound19SingleImport(unittest.TestCase):
    def test_dropzone_is_the_single_visible_control(self):
        m = re.search(r'<div[^>]*id="importDropzone"[^>]*>', HTML)
        self.assertIsNotNone(m)
        tag = m.group(0)
        self.assertIn('role="button"', tag)
        self.assertIn('tabindex="0"', tag)
        self.assertIn("Nhập", tag)

    def test_file_input_and_submit_hidden_not_removed(self):
        m = re.search(r'<input[^>]*id="uploadFile"[^>]*>', HTML)
        self.assertIsNotNone(m)
        self.assertIn('class="visually-hidden"', m.group(0))
        m = re.search(r'<button[^>]*type="submit"[^>]*>Tải media lên</button>',
                      HTML)
        self.assertIsNotNone(m, "submit button must stay in DOM")
        self.assertIn('class="visually-hidden"', m.group(0))
        hidden = re.search(r"\.visually-hidden \{([^}]*)\}", CSS)
        self.assertIsNotNone(hidden)
        self.assertNotIn("display: none", hidden.group(1),
                         "display:none would break programmatic clicks")

    def test_import_js_flows(self):
        for marker in ('getElementById("importDropzone")',
                       'getElementById("uploadFile")',
                       'getElementById("uploadForm")',
                       "input.click()", "keydown", '"Enter"',
                       '"change"', "requestSubmit", "dataTransfer",
                       "/api/media/upload"):
            self.assertIn(marker, JS, marker)

    def test_import_ids_and_add_clip_form_intact(self):
        for ident in ("importDropzone", "uploadForm", "uploadFile",
                      "mediaList", "mediaAddStatus", "addClipForm"):
            self.assertIn('id="%s"' % ident, HTML, ident)

    def test_english_subtitle_kept_by_locked_tests(self):
        # STOP decision: test_capcut_ui.py:90 and
        # test_round18.py:115 lock this English string, so the
        # Vietnamese subtitle change is NOT applied this round.
        self.assertIn("Drag and drop videos, photos, and audio files here",
                      HTML)


# ---- Round 19 fix batches: fps bug, real-click batch, review batch ----

import json  # noqa: E402
import threading  # noqa: E402
import urllib.request  # noqa: E402

from vibeedit_core.project import (  # noqa: E402
    migrate_fps_units, source_span_to_project_frames)
from vibeedit_core.render import render  # noqa: E402
from vibeedit_core.server import (  # noqa: E402
    State, make_handler, QuietDisconnectServer,
    _parse_multipart, _safe_upload_name, _find_media_by_sha256)


def _color_clip_60(folder, name, color, seconds, width=320, height=180):
    src = os.path.join(folder, name)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                    "-i", f"color=c={color}:size={width}x{height}:rate=60:"
                          f"duration={seconds}",
                    "-pix_fmt", "yuv420p", src],
                   capture_output=True, check=True)
    return name


def _ffprobe_duration_frames(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-count_frames",
                          "-print_format", "json", "-show_streams",
                          "-show_format", path],
                         capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    stream = next(s for s in data["streams"]
                  if s["codec_type"] == "video")
    return float(data["format"]["duration"]), int(stream["nb_read_frames"])


class TestRound19FpsConversion(unittest.TestCase):
    def test_user_numbers_6797_frames(self):
        # The user's measured case: 6797 frames of 59.94fps footage
        # in a 29.97fps project. Frames-only conversion gives 3398
        # project frames (113.38s); the probe duration path below
        # gives 3400 (113.45s). Both are within 2 frames of each
        # other — and nothing like the old 6797 (226.79s).
        self.assertEqual(
            source_span_to_project_frames(6797, [60000, 1001],
                                          [30000, 1001]),
            3398)
        self.assertEqual(
            source_span_to_project_frames(1800, 60, 30), 900)

    def test_add_clip_default_converts(self):
        proj = Project(new_project("fps", width=320, height=180,
                                   fps=(30, 1)), "/tmp")
        med = proj.add_media("m.mp4", kind="video", frames=1800,
                             fps=[60, 1], duration=30.0)
        clip = proj.add_clip(med["id"], "v1", 0, 0, None)
        self.assertEqual(clip["dur"], 900)
        self.assertAlmostEqual(proj.duration_seconds(), 30.0, places=2)

    def test_add_clip_default_prefers_duration(self):
        proj = Project(new_project("fps", width=320, height=180,
                                   fps=(30000, 1001)), "/tmp")
        med = proj.add_media("m.mp4", kind="video", frames=6797,
                             fps=[60000, 1001], duration=113.45)
        clip = proj.add_clip(med["id"], "v1", 0, 0, None)
        self.assertEqual(clip["dur"], 3400)

    def test_overwrite_insert_converts(self):
        proj = Project(new_project("fps", width=320, height=180,
                                   fps=(30, 1)), "/tmp")
        med = proj.add_media("m.mp4", kind="video", frames=1800,
                             fps=[60, 1], duration=30.0)
        item = proj.overwrite_insert(med["id"], 0, 600, 0)
        self.assertEqual(item["dur"], 300)
        self.assertEqual(item["in"], 0)

    def test_mcp_source_insert_converts(self):
        with tempfile.TemporaryDirectory() as tmp:
            _color_clip_60(tmp, "c60.mp4", "red", 2)
            proj = Project(new_project("fps", width=320, height=180,
                                       fps=(30, 1)), tmp)
            med = proj.add_media("c60.mp4", kind="video",
                                 **probe_media(
                                     os.path.join(tmp, "c60.mp4")))
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            result = server.call("vibeedit_source_insert",
                                 {"media": med["id"], "in": 0,
                                  "out": 60})
            item = result["item"] if "item" in result else result
            self.assertEqual(item["dur"], 30)

    def test_migrate_converts_once_and_skips_unknown_fps(self):
        data = new_project("old", width=320, height=180, fps=(30, 1))
        data.pop("fps_units")
        data["media"] = [
            {"id": "m1", "kind": "video", "path": "media/a.mp4",
             "frames": 1800, "fps": [60, 1], "duration": 30.0},
            {"id": "m2", "kind": "video", "path": "media/b.mp4"},
        ]
        data["tracks"][0]["items"] = [
            {"id": "c1", "media": "m1", "in": 0, "dur": 1800, "at": 0,
             "speed": 1.0},
            {"id": "c2", "media": "m2", "in": 0, "dur": 90, "at": 0,
             "speed": 1.0},
        ]
        result = migrate_fps_units(data)
        self.assertEqual(result["converted"], 1)
        self.assertEqual(result["skipped"], ["c2"])
        self.assertEqual(data["tracks"][0]["items"][0]["dur"], 900)
        self.assertEqual(data["tracks"][0]["items"][1]["dur"], 90)
        self.assertEqual(data["fps_units"], "project")
        self.assertEqual(migrate_fps_units(data)["converted"], 0)

    def test_migrate_reflows_stacked_at_not_gaps(self):
        # Parent check on the round-19 migration: the user's stacked
        # project (two 6797-frame 59.94fps clips in a 29.97fps
        # project) must come out gapless at ~226.9s, not 340s with a
        # phantom gap. A deliberately gapped clip keeps its `at`.
        data = new_project("old", width=320, height=180,
                           fps=(30000, 1001))
        data.pop("fps_units")
        data["media"] = [
            {"id": "m1", "kind": "video", "path": "media/a.mp4",
             "frames": 6797, "fps": [60000, 1001], "duration": 113.45},
        ]
        data["tracks"][0]["items"] = [
            {"id": "c1", "media": "m1", "in": 0, "dur": 6797, "at": 0,
             "speed": 1.0},
            {"id": "c2", "media": "m1", "in": 0, "dur": 6797, "at": 6797,
             "speed": 1.0},
            {"id": "c3", "media": "m1", "in": 0, "dur": 6797, "at": 20000,
             "speed": 1.0},
        ]
        result = migrate_fps_units(data)
        items = data["tracks"][0]["items"]
        self.assertEqual(result["converted"], 3)
        self.assertEqual(result["at_fixed"], 1)
        self.assertEqual(items[0]["dur"], 3398)
        self.assertEqual(items[1]["at"], 3398)
        self.assertEqual(items[1]["dur"], 3398)
        self.assertEqual(items[1]["at"],
                         items[0]["at"] + items[0]["dur"])
        self.assertEqual(items[2]["at"], 20000)
        self.assertEqual(migrate_fps_units(data)["converted"], 0)

    def test_validate_warns_on_unknown_video_fps(self):
        proj = Project(new_project("v", width=320, height=180,
                                   fps=(30, 1)), "/tmp")
        med = proj.add_media("b.mp4", kind="video")
        proj.add_clip(med["id"], "v1", 0, 0, 30)
        self.assertTrue(proj.validate()["warnings"])
        proj2 = Project(new_project("v", width=320, height=180,
                                    fps=(30, 1)), "/tmp")
        med2 = proj2.add_media("a.mp4", kind="video", fps=[30, 1])
        proj2.add_clip(med2["id"], "v1", 0, 0, 30)
        self.assertEqual(proj2.validate()["warnings"], [])

    def test_render_length_matches_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            _color_clip_60(tmp, "c60.mp4", "red", 2)
            proj = Project(new_project("fps", width=320, height=180,
                                       fps=(30, 1)), tmp)
            med = proj.add_media("c60.mp4", kind="video",
                                 **probe_media(
                                     os.path.join(tmp, "c60.mp4")))
            clip = proj.add_clip(med["id"], "v1", 0, 0, None)
            self.assertEqual(clip["dur"], 60)
            self.assertAlmostEqual(proj.duration_seconds(), 2.0,
                                   places=2)
            out = os.path.join(tmp, "export.mp4")
            render(proj.data, tmp, out, preset="full")
            dur, frames = _ffprobe_duration_frames(out)
            self.assertAlmostEqual(dur, 2.0, delta=0.1)
            self.assertAlmostEqual(frames, 60, delta=2)


class TestRound19RealClickBatch(unittest.TestCase):
    def test_post_helper_is_top_level_and_covers_round3(self):
        self.assertIn("async function post(body) {", JS)
        self.assertNotIn("const post =", JS)
        for op in ("skills_list", "skills_get", "skills_disable",
                   "skills_enable", "skills_remove", "skills_save",
                   "skills_propose", "knowledge", "plugin_install",
                   "plugin_download", "magnetic_set"):
            self.assertIn(f'post({{ op: "{op}"', JS)

    def test_magnetic_status_vietnamese(self):
        self.assertIn("Đã bật Magnetic Main.", JS)
        self.assertIn("Đã tắt Magnetic Main.", JS)

    def test_back_button_seeks_zero(self):
        idx = JS.index('if (backBtn) backBtn.addEventListener("click"')
        region = JS[idx:idx + 500]
        self.assertIn("playheadFrame = 0;", region)
        self.assertNotIn("found.item.at", region)

    def test_undo_redo_status_with_rev(self):
        self.assertIn("Đã hoàn tác. (Edited rev", JS)
        self.assertIn("Đã làm lại. (Edited rev", JS)

    def test_sections_toggle_state(self):
        self.assertIn("__showSections", JS)
        self.assertIn("section-tick", JS)
        self.assertIn("Đã bật Sections", JS)
        self.assertIn("Đã tắt Sections.", JS)
        idx = JS.index("tlSections")
        region = JS[idx:idx + 1200]
        self.assertIn('setAttribute("aria-pressed"', region)

    def test_waveforms_status_kept(self):
        self.assertIn("Đã tải lại sóng âm.", JS)

    def test_voice_precheck_and_clone_feedback(self):
        self.assertIn('op: "voice_check"', JS)
        self.assertIn("Chưa có backend giọng nói", JS)
        start = JS.index("btnVoiceClone")
        end = JS.index("btnVoiceGenerate")
        region = JS[start:end]
        self.assertIn("setStatus(", region)

    def test_rename_enter_and_named_status(self):
        self.assertIn("Đã đổi tên project thành", JS)
        idx = JS.index('$("projectName").addEventListener("keydown"')
        self.assertIn('e.target.blur()', JS[idx:idx + 200])

    def test_beats_zero_status_and_mapping(self):
        self.assertIn("không tìm thấy nhịp nào", JS)
        self.assertIn("nếu đã chạy mà vẫn trống", JS)

    def test_ducking_handler_status_and_persist(self):
        self.assertIn("duckingForm", JS)
        self.assertIn("Đã lưu ducking.", JS)
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            state.apply({"op": "ducking_set", "enabled": True,
                         "amount_db": 6})
            self.assertTrue(state.project.ducking_get()["enabled"])
            reloaded = State(tmp)
            self.assertTrue(reloaded.project.ducking_get()["enabled"])

    def test_rename_persists_on_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            state.apply({"op": "set_project", "name": "TenMoi"})
            self.assertEqual(State(tmp).project.data["name"], "TenMoi")

    def test_ollama_honesty_kept(self):
        self.assertIn("Ollama chưa kết nối trong app", JS)

    def test_disconnect_server_seam(self):
        import io
        import contextlib
        with tempfile.TemporaryDirectory() as tmp:
            srv = QuietDisconnectServer(("127.0.0.1", 0),
                                        make_handler(State(tmp)))
            err = io.StringIO()
            try:
                raise ConnectionResetError("closed")
            except ConnectionResetError:
                with contextlib.redirect_stderr(err):
                    srv.handle_error(None, None)
            self.assertEqual(err.getvalue(), "")
            err2 = io.StringIO()
            try:
                raise ValueError("boom")
            except ValueError:
                with contextlib.redirect_stderr(err2):
                    srv.handle_error(None, None)
            self.assertIn("ValueError", err2.getvalue())
            srv.server_close()

    def test_beat_detect_runs_real_detector(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", "sine=frequency=440:duration=2",
                            "-c:a", "aac", os.path.join(tmp, "t.m4a")],
                           capture_output=True, check=True)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", "anullsrc=r=48000:cl=stereo",
                            "-t", "2", "-c:a", "aac",
                            os.path.join(tmp, "s.m4a")],
                           capture_output=True, check=True)
            proj = Project(new_project("b", width=320, height=180,
                                       fps=(30, 1)), tmp)
            med = proj.add_media("t.m4a", kind="audio",
                                 **probe_media(os.path.join(tmp, "t.m4a")))
            # The detector runs (no raise, beats key present) on tone.
            grid = proj.detect_beats(med["id"])
            self.assertIn("beats", grid)
            # Silence detects to an empty grid — and only then does
            # beats_to_markers raise the message the UI now maps to
            # a clear instruction instead of showing it raw.
            sil = proj.add_media("s.m4a", kind="audio",
                                 **probe_media(os.path.join(tmp, "s.m4a")))
            grid2 = proj.detect_beats(sil["id"])
            self.assertEqual(grid2["beats"], [])
            with self.assertRaises(ValueError) as cm:
                proj.beats_to_markers()
            self.assertIn("No beat grid detected yet", str(cm.exception))


def _multipart_body(boundary, filename, payload):
    return (b"--" + boundary +
            b'\r\nContent-Disposition: form-data; name="file"; filename="' +
            filename + b'"\r\nContent-Type: video/mp4\r\n\r\n' +
            payload + b"\r\n--" + boundary + b"--\r\n")


class TestRound19UploadDedupe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state = State(self.tmp)
        self.httpd = QuietDisconnectServer(
            ("127.0.0.1", 0), make_handler(self.state))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True)
        self.thread.start()
        _color_clip_60(self.tmp, "up.mp4", "red", 1)
        with open(os.path.join(self.tmp, "up.mp4"), "rb") as fh:
            self.payload = fh.read()
        _color_clip_60(self.tmp, "up2.mp4", "blue", 1)
        with open(os.path.join(self.tmp, "up2.mp4"), "rb") as fh:
            self.payload2 = fh.read()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _upload(self, filename, payload):
        body = _multipart_body(b"B", filename.encode(), payload)
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/media/upload",
            data=body, method="POST",
            headers={"Content-Type": "multipart/form-data; boundary=B"})
        with urllib.request.urlopen(req) as res:
            return json.loads(res.read())

    def test_same_file_twice_reuses_one_id(self):
        first = self._upload("clip-tay.mp4", self.payload)
        second = self._upload("clip-tay.mp4", self.payload)
        self.assertEqual(first["media"]["id"], second["media"]["id"])
        self.assertTrue(second.get("reused"))
        self.assertEqual(len(self.state.project.data["media"]), 1)

    def test_different_file_same_name_gets_name2(self):
        first = self._upload("clip-tay.mp4", self.payload)
        second = self._upload("clip-tay.mp4", self.payload2)
        self.assertNotEqual(first["media"]["id"], second["media"]["id"])
        self.assertFalse(second.get("reused"))
        self.assertTrue(second["media"]["path"].endswith("-2.mp4"))

    def test_stored_name_keeps_mp4_extension(self):
        data = self._upload("clip-tay.mp4", self.payload)
        self.assertTrue(data["media"]["path"].endswith(".mp4"))
        self.assertNotEqual(data["media"]["path"], "media/mp4")

    def test_parser_crlf_and_lf_and_safe_names(self):
        crlf = (b'--B\r\nContent-Disposition: form-data; name="file"; '
                b'filename="clip-tay.mp4"\r\nContent-Type: video/mp4\r\n'
                b'\r\nPAYLOAD\r\n--B--\r\n')
        self.assertEqual(_parse_multipart(crlf, b"B")["file"],
                         ("clip-tay.mp4", b"PAYLOAD"))
        lf = (b'--B\nContent-Disposition: form-data; name="file"; '
              b'filename="clip-tay.mp4"\nContent-Type: video/mp4\n'
              b'\nPAYLOAD\n--B--\n')
        self.assertEqual(_parse_multipart(lf, b"B")["file"],
                         ("clip-tay.mp4", b"PAYLOAD"))
        self.assertEqual(_safe_upload_name(
            "C:\\Users\\daoho\\Downloads\\clip.mp4"), "clip.mp4")
        self.assertEqual(_safe_upload_name(""), "upload.bin")

    def test_find_by_sha256_backfills(self):
        medium = self.state.project.add_media(
            "media/up.mp4", kind="video")
        shutil.copy(os.path.join(self.tmp, "up.mp4"),
                    os.path.join(self.tmp, "media", "up.mp4"))
        import hashlib
        digest = hashlib.sha256(self.payload).hexdigest()
        found = _find_media_by_sha256(self.state.project, self.tmp,
                                      digest)
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], medium["id"])
        self.assertEqual(found["sha256"], digest)


class TestRound19ReviewBatch(unittest.TestCase):
    def test_a1_poster_via_existing_media_no_new_endpoint(self):
        self.assertIn("frame đầu của clip đầu tiên", JS)
        self.assertIn("/api/media/", JS)
        # The report's suggested /api/thumb/first does NOT exist and
        # was not invented; /api/thumbnail (the real endpoint) is a
        # different path and is allowed to appear.
        self.assertNotIn("/api/thumb/first", JS)
        self.assertNotIn("/api/thumb/first", HTML)

    def test_a2_drawer_toggles_and_x_buttons(self):
        self.assertIn('id="btnAgentClose"', HTML)
        self.assertIn('id="btnDetailsClose"', HTML)
        self.assertIn('setAttribute("aria-pressed"', JS)
        self.assertIn("syncInspectorDrawer", JS)
        self.assertIn("@media (max-width: 1100px)", CSS)
        self.assertIn(".details-col.open", CSS)
        # Both topbar toggles live outside the <details> overflow menu.
        self.assertLess(HTML.index("</details>"),
                        HTML.index("btnAgentToggleTop"))
        self.assertLess(HTML.index("</details>"),
                        HTML.index("btnInspectorToggle"))

    def test_a3_honest_quick_command_labels(self):
        form = HTML[HTML.index('id="agentChatForm"'):
                    HTML.index("</form>", HTML.index('id="agentChatForm"'))]
        self.assertIn("Nhập lệnh nhanh (help để xem danh sách)", form)
        self.assertIn("lệnh nhanh — chưa phải AI", HTML)
        self.assertIn(">Chạy<", form)
        self.assertNotIn(">Gửi<", form)

    def test_b_beautification_locked_values_kept(self):
        self.assertIn(".clip { border-radius: 6px", CSS)
        self.assertIn("rgba(255, 255, 255, .06)", CSS)
        self.assertIn("#14141a", CSS)
        self.assertIn("#17171e", CSS)
        self.assertIn("#22222a", CSS)
        self.assertIn("linear-gradient(to bottom, #ef4444", CSS)
        self.assertIn("#ef4444", CSS)
        self.assertIn("font-size: 11px; text-transform: uppercase;"
                      " letter-spacing: .08em; color: #8a8579", CSS)
        self.assertIn("flex: 0 0 48px", CSS)
        self.assertIn("data:image/png;base64", HTML)
        toolbar = HTML[HTML.index('class="timeline-toolbar"'):
                        HTML.index("</div>", HTML.index(
                            'class="timeline-toolbar"'))]
        for glyph in ("✂", "🗑", "⚙", "⬚"):
            self.assertNotIn(glyph, toolbar)

    def test_c_details_and_indicators(self):
        self.assertIn("mediaBaseName(m)", JS)
        self.assertIn("mediaDurationLabel", JS)
        self.assertIn('${m.width}×${m.height}', JS)
        self.assertIn('$("previewLabel").hidden = true;', JS)
        self.assertIn('id="zoomOut"', HTML)
        self.assertIn('id="zoomIn"', HTML)
        self.assertIn("function setZoom(v)", JS)
        self.assertIn("Math.max(10, Math.min(200", JS)
        self.assertIn('$("timelineText").title', JS)
        self.assertIn("#timelineText { max-width: 480px", CSS)
        idx = JS.index("btnDetailsModify")
        self.assertIn('btnSettings', JS[idx:idx + 300])
        self.assertIn('id="saveDot"', HTML)
        self.assertIn('id="saveLabel"', HTML)
        self.assertIn("function setSaveState", JS)
        save_idx = JS.index('api("/api/save"')
        self.assertIn('setSaveState("saved")',
                      JS[save_idx:save_idx + 300])
        self.assertIn("is-empty", JS)
        self.assertIn(".track-lane.is-empty { min-height: 28px", CSS)

    def test_d_virtualized_ruler(self):
        import json as _json
        fn = _extract_function(JS, "visibleTickRange")
        harness = fn + """
const out = {
  start: visibleTickRange(0, 1280, 60, 3600),
  scrolled: visibleTickRange(108000, 1280, 60, 3600),
  slow: visibleTickRange(0, 1280, 10, 3600),
};
console.log(JSON.stringify(out));
"""
        proc = subprocess.run(["node", "-e", harness], capture_output=True,
                              text=True, check=True)
        res = _json.loads(proc.stdout)
        start = res["start"]
        self.assertEqual(start["firstSec"], 0)
        # ~22 labelled seconds + ~42 half-second minors at 60 px/s.
        self.assertLessEqual(start["lastSec"] - start["firstSec"], 25)
        self.assertEqual(start["minorStep"], 0.5)
        self.assertEqual(res["scrolled"]["firstSec"], 1800)
        self.assertEqual(res["slow"]["minorStep"], 1)
        self.assertNotIn(
            "for (let sec = 0; sec <= Math.ceil(totalSecs); sec++)", JS)
        self.assertIn("renderRuler()", JS)
        self.assertIn("requestAnimationFrame", JS)


class TestRound19RegistryFinal(unittest.TestCase):
    def test_counts_still_479_420_59(self):
        real = [t for t in TOOLS
                if not t["description"].startswith("Not available")]
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(real), 432)  # Round 23: 479 -> 481 (skills_import_plan/import); Round 24: 429 -> 432 (voice_clone_list/ui_dialog/chat_status empty-by-design)
        self.assertEqual(len(honest), 49)  # Round 22: 54 -> 52; Round 24: 52 -> 49 (voice_clone_list/ui_dialog/chat_status empty-by-design)
