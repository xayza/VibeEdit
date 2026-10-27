"""Round 14: presentation first — the web UI must look like the original
app (slim top bar, tabbed Inspector, compact timeline with thumbnails,
waveforms, neon word chips and a red playhead, and a compact AGENT
dock with a one-line MCP status), using only synthetic test data.

Layout is copied from the original app's structure only. No content is
copied from any real editing session: no script lines, footage names,
or voiceover take names from screenshots appear in the app or tests.
"""

import os
import re
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = os.path.dirname(HERE)


def read(rel):
    with open(os.path.join(WINDOWS, rel), encoding="utf-8") as fh:
        return fh.read()


class TestRound14Presentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("static/index.html")
        cls.js = read("static/app.js")
        cls.css = read("static/style.css")

    def test_top_bar_is_slim(self):
        header = self.html.split("</header>")[0]
        # Project management moved into the welcome panel, not the bar.
        for ident in ("projectSelect", "btnProjectOpen", "projectNewName",
                      "btnProjectCreate"):
            self.assertNotIn(f'id="{ident}"', header, ident)
            self.assertIn(f'id="{ident}"', self.html, ident)
        for ident in ("projectName", "projectRev", "btnUndo", "btnRedo",
                      "btnExportReport", "btnExportDraft", "btnExportFull",
                      "btnWelcome"):
            self.assertIn(f'id="{ident}"', header, ident)

    def test_inspector_tabs_and_project_details(self):
        for tab in ("video", "audio", "text", "color", "speed"):
            self.assertIn(f'data-insp-tab="{tab}"', self.html, tab)
            self.assertIn(f'data-insp-pane="{tab}"', self.html, tab)
        for ident in ("detailsProject", "detailsName", "detailsPath",
                      "detailsFormat", "detailsFps", "detailsLength",
                      "detailsClips", "btnDetailsModify"):
            self.assertIn(f'id="{ident}"', self.html, ident)
        # Formerly always-visible extras are collapsed details now.
        self.assertIn('class="inspector-extra"', self.html)
        for ident in ("keyframeBox", "speedCurveForm", "brandForm",
                      "pluginForm"):
            self.assertIn(f'id="{ident}"', self.html, ident)

    def test_agent_dock_compact(self):
        for ident in ("agentStatusLine", "agentMcpCommand",
                      "btnAgentCopyMcp", "agentChat", "agentChatForm",
                      "agentChatInput", "agentProvider"):
            self.assertIn(f'id="{ident}"', self.html, ident)
        for tab in ("mcp", "ollama"):
            self.assertIn(f'data-agent-tab="{tab}"', self.html, tab)
        # The honest mechanism line stays, but no wall of text.
        self.assertIn("no in-app LLM generation connected yet", self.html)
        self.assertIn("/api/agent-status", self.js)
        self.assertIn("agent-log-row", self.js)

    def test_timeline_toolbar_and_content(self):
        for ident in ("tlSnap", "tlWaveforms", "tlFit", "tlTimecode"):
            self.assertIn(f'id="{ident}"', self.html, ident)
        self.assertIn("clip-thumb", self.js)
        self.assertIn("/api/thumbnail/", self.js)
        self.assertIn("tl-playhead", self.js)
        self.assertIn("role-${track.role}", self.js)
        # The old totalS formula always evaluated to 1 (ruler + lane
        # width broken for long projects); the fixed form is required.
        self.assertIn("Math.max(1, ...project.tracks.flatMap", self.js)
        self.assertNotIn("[1])[0]", self.js)
        self.assertIn(".clip-thumb", self.css)
        self.assertIn(".tl-playhead", self.css)
        # Neon restyle: kind colours replace the old role colours and
        # the orange chips (spec: video cyan, audio green, title pink,
        # caption chips purple; roles live on track-code chips now).
        self.assertIn("#8b5cf6", self.css)  # purple word chips / fx
        self.assertIn(".clip.video", self.css)
        self.assertIn("#06b6d4", self.css)  # cyan video clips
        self.assertIn(".clip.audio", self.css)
        self.assertIn("#10b981", self.css)  # green audio clips
        self.assertIn(".clip-title", self.css)
        self.assertIn("#ec4899", self.css)  # pink title cards
        self.assertIn(".track-code", self.css)
        self.assertIn("clip-narrow", self.js)
        self.assertIn("clip-fx", self.js)
        self.assertIn('marker.textContent = "⇄"', self.js)
        self.assertIn("fmtTc", self.js)

    def test_no_copied_session_content(self):
        # Layout only: nothing from any real editing session may leak
        # into the app (script lines, footage names, take names).
        for bad in ("DJI_", "di-choi-buon-lang"):
            for blob in (self.html, self.js, self.css):
                self.assertNotIn(bad, blob, bad)

    def test_forms_collapsed_not_removed(self):
        self.assertIn('class="form-advanced"', self.html)
        self.assertIn('class="source-range-wrap"', self.html)
        for ident in ("addIn", "addSpeed", "sourceIn", "sourceOut",
                      "btnSourceMarkIn", "btnSourceMarkOut",
                      "btnSourceInsert", "btnSourceOverwrite"):
            self.assertIn(f'id="{ident}"', self.html, ident)


class TestRound14AgentStatus(unittest.TestCase):
    def test_touch_and_status_roundtrip(self):
        from vibeedit_core.mcp import MCPServer
        from vibeedit_core.server import agent_status_for

        tmp = tempfile.mkdtemp(prefix="ve-r14-")
        proj_file = os.path.join(tmp, "synthetic-project.json")
        with open(proj_file, "w", encoding="utf-8") as fh:
            fh.write("{}")
        self.assertFalse(agent_status_for(tmp)["connected"])
        srv = MCPServer()
        srv.path = proj_file
        srv._touch_agent_status()
        st = agent_status_for(tmp)
        self.assertTrue(st["connected"])
        self.assertLess(st["age_seconds"], 5)
        self.assertGreater(time.time() - st["last_seen"], -1)

    def test_mcp_counts_unchanged(self):
        from vibeedit_core.mcp import TOOLS

        real = sum(1 for t in TOOLS
                   if not t.get("description", "").startswith("Not available"))
        self.assertEqual((len(TOOLS), real, len(TOOLS) - real),
                         (479, 420, 59))  # Round 19: 403/76 -> 420/59


if __name__ == "__main__":
    unittest.main()


class TestRound14NeonLayout(unittest.TestCase):
    """Neon Nights layout: agent sidebar left, icon toolbar, CTA,
    3-col media grid, duration badges, Vietnamese labels."""

    @classmethod
    def setUpClass(cls):
        cls.html = read("static/index.html")
        cls.js = read("static/app.js")
        cls.css = read("static/style.css")

    def test_agent_sidebar_is_leftmost(self):
        self.assertIn('class="agent-col"', self.html)
        agent = self.html.index('id="agentDock"')
        self.assertLess(agent, self.html.index('class="tool-col"'))
        self.assertLess(agent, self.html.index('class="centre-col"'))
        # Inspector still sits between details-col and timeline-wrap.
        self.assertLess(self.html.index('class="details-col"'),
                        self.html.index('class="timeline-wrap"'))
        self.assertIn("AI AGENT", self.html)

    def test_topbar_is_icon_only_with_accessible_text(self):
        for ident in ("btnUndo", "btnRedo", "btnExportReport", "btnPlugins",
                      "btnReviewTop", "btnExportDraft", "btnSettings",
                      "btnExportPreset"):
            self.assertIn(f'id="{ident}"', self.html, ident)
        self.assertIn("icon-btn", self.html)
        self.assertIn("sr-only", self.html)
        # The long-text buttons are gone; their labels survive for
        # screen readers (and for the marker tests) in .sr-only spans.
        self.assertIn("Export report", self.html)
        self.assertIn("Export draft", self.html)
        # CTA: softened dark gradient cyan -> pink (round 16
        # harmony: still the strongest colour, but no longer harsh),
        # rounded, pushed to the right.
        self.assertIn("linear-gradient(90deg, #0e7490, #be185d)", self.css)
        self.assertIn("#btnExportFull { margin-left: auto; }", self.css)
        self.assertIn('class="primary cta"', self.html)

    def test_neon_palette_and_no_white_borders(self):
        for value in ("#09090b", "#16161a", "#18181b", "#27272a",
                      "#3f3f46", "#a1a1aa", "#06b6d4", "#ec4899",
                      "#8b5cf6", "#10b981"):
            self.assertIn(value, self.css, value)
        self.assertIn('"Inter"', self.css)
        for bad in ("solid #fff", "outline: 2px solid #fff",
                    "border-top-color: #fff", "#00c8d4", "#f59e0b"):
            self.assertNotIn(bad, self.css, bad)

    def test_media_grid_three_columns_and_duration_badge(self):
        self.assertIn("#mediaList { display: grid; grid-template-columns: repeat(3, 1fr);", self.css)
        self.assertIn("media-duration-badge", self.js)
        self.assertIn("media-duration-badge", self.css)
        self.assertIn("border-radius: 6px", self.css)  # rounded-md thumbs

    def test_tab_ids_have_direct_bindings(self):
        for ident in ("inspTabVideo", "inspTabAudio", "inspTabText",
                      "inspTabColor", "inspTabSpeed", "agentTabMcp",
                      "agentTabOllama"):
            self.assertIn(f'id="{ident}"', self.html, ident)
            self.assertIn(f'$("{ident}").addEventListener("click"',
                          self.js, ident)

    def test_vietnamese_labels_with_documented_english_terms(self):
        # Free-form labels are Vietnamese now...
        for text in ("track trống — bấm để hiện", "Ẩn track trống",
                     "Trống — dùng Add Layer", "Chưa có media.",
                     "Xem trước: bản xuất gần nhất", "Nhắn cho agent",
                     "Sao chép", "Mở Cài đặt", "Về đầu",
                     "Chế độ Source:", "Các nút timeline gọi lại"):
            blob = self.html + self.js
            self.assertIn(text, blob, text)
        # ...while the CTA and the technical terms the user used in
        # English (plus original-app labels) stay English by design.
        self.assertIn("Export video", self.html)
        self.assertIn("Edited rev", self.html)
        self.assertIn("AGENT", self.html)


class TestRound14PreviewSync(unittest.TestCase):
    """Two-way playhead <-> preview sync, verified for real: the pure
    mapping functions are extracted verbatim from app.js and executed
    under Node, and the waveform backend is run on synthetic audio."""

    def test_mapping_both_directions_within_one_frame(self):
        import json
        import subprocess
        js = read("static/app.js")
        start = js.index("// __PREVIEW_SYNC_MAP_START__")
        end = js.index("// __PREVIEW_SYNC_MAP_END__")
        src = js[start:end]
        vectors = [
            # (fn, args, expected)
            ("timelineToSourceSeconds", [2.0, 1.0, 0.5, 1, 10], 1.5),
            ("timelineToSourceSeconds", [2.0, 1.0, 0.5, 2, 10], 2.5),
            ("timelineToSourceSeconds", [0.5, 1.0, 0.5, 1, 10], 0.5),
            ("timelineToSourceSeconds", [20.0, 1.0, 0.5, 1, 10], 10.0),
            ("timelineToSourceSeconds", [2.0, 1.0, 0.5, 1, None], 1.5),
            ("sourceToTimelineSeconds", [1.5, 1.0, 0.5, 1, 2.0], 2.0),
            ("sourceToTimelineSeconds", [2.5, 1.0, 0.5, 2, 2.0], 2.0),
            ("sourceToTimelineSeconds", [0.2, 1.0, 0.5, 1, 2.0], 1.0),
            ("sourceToTimelineSeconds", [9.0, 1.0, 0.5, 1, 2.0], 3.0),
        ]
        script = src + "\n" + "\n".join(
            f"console.log(JSON.stringify({fn}({', '.join('null' if a is None else repr(a) for a in args)})));"
            for fn, args, _ in vectors)
        out = subprocess.run(["node", "-e", script], capture_output=True,
                             text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        got = [json.loads(line) for line in out.stdout.splitlines()]
        for (_, _, expected), value in zip(vectors, got):
            self.assertAlmostEqual(value, expected, places=9)
        # Roundtrip: timeline -> source -> timeline stays within
        # one frame at 30 fps (the user's sync tolerance).
        rt = src + "\n" + (
            "let worst = 0;"
            "for (let t = 1.0; t <= 3.0; t += 0.01) {"
            "  const s = timelineToSourceSeconds(t, 1.0, 0.5, 1, 10);"
            "  const back = sourceToTimelineSeconds(s, 1.0, 0.5, 1, 2.0);"
            "  worst = Math.max(worst, Math.abs(back - t) * 30);"
            "}"
            "console.log(worst);")
        out = subprocess.run(["node", "-e", rt], capture_output=True,
                             text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertLess(float(out.stdout.strip()), 1.0)

    def test_sync_wiring_present(self):
        js = read("static/app.js")
        html = read("static/index.html")
        for marker in ('addEventListener("timeupdate"',
                       'addEventListener("seeked"',
                       'addEventListener("loadedmetadata"',
                       "renderPreviewCaption", "updatePreviewEmpty",
                       "sourceToTimelineSeconds",
                       "previewCaption", "previewEmpty", "preview-stage"):
            self.assertIn(marker, js + html, marker)
        # Caption overlay uses the item's own text/karaoke + position.
        self.assertIn("item.karaoke.words", js)
        self.assertIn("positionX", js)
        self.assertIn("positionY", js)
        # load() and showSourcePreview() re-seek after any change.
        self.assertIn("seekPreviewToPlayhead();", js)

    def test_waveform_spans_full_file(self):
        # Synthetic 3 s mono WAV, stdlib only: 1 s tone, 1 s silence,
        # 1 s tone. Peaks must show energy-silence-energy across the
        # whole file, proving buckets cover the full duration.
        import math
        import struct
        import wave
        from vibeedit_core.waveform import waveform_peaks
        rate = 22050
        frames = []
        for sec in range(3):
            for i in range(rate):
                v = 0.0 if sec == 1 else math.sin(2 * math.pi * 440 * i / rate)
                frames.append(int(v * 12000))
        tmp = tempfile.mktemp(suffix=".wav")
        with wave.open(tmp, "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(rate)
            fh.writeframes(struct.pack(f"<{len(frames)}h", *frames))
        peaks = waveform_peaks(tmp, buckets=30)
        self.assertEqual(len(peaks), 30)
        first = sum(peaks[0:10]) / 10
        middle = sum(peaks[10:20]) / 10
        last = sum(peaks[20:30]) / 10
        self.assertGreater(first, 0.3)
        self.assertLess(middle, 0.05)
        self.assertGreater(last, 0.3)
        os.unlink(tmp)
