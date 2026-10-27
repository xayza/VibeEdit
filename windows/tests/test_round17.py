"""Round 17: horizontal tool row + timeline ruler/lane shared origin.

Job 1: the vertical tool rail (Media, Audio, Text, ...) is now a
horizontal CapCut-style row above the workbench. Buttons, ids and
handlers are unchanged; only the layout moved.

Job 2: the timeline playhead used to be misaligned by exactly one
constant (label width + gap). The ruler sat at the timeline-wrap's
left edge while lane playheads/clips sat inside lanes that start
after the track-label column. The fix gives the ruler the same
origin as the lanes: ruler margin-left == label width + row gap.
These tests parse the REAL files and simulate the resulting pixel
math, so a regression that re-opens the offset fails here.
"""
import math
import re
import unittest
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"
HTML = (STATIC / "index.html").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")

RAIL_ORDER = [
    ("tab", "media"), ("tab", "audio"), ("tab", "text"),
    ("tab", "stickers"), ("tab", "effects"), ("tab", "transitions"),
    ("tab", "filters"), ("tab", "voice"), ("tab", "knowledge"),
    ("tab", "vision"), ("action", "timeline"), ("tab", "templates"),
]


def rule_body(css, selector):
    """First `{...}` body for an exact selector (not a descendant)."""
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, f"rule not found: {selector}"
    return m.group(1)


def px(body, prop):
    m = re.search(re.escape(prop) + r":\s*([\d.]+)px", body)
    assert m, f"{prop} not found in rule"
    return float(m.group(1))


def media_block(css, query):
    start = css.find(query)
    assert start != -1, f"media query not found: {query}"
    open_brace = css.find("{", start)
    depth = 0
    for i in range(open_brace, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                return css[open_brace + 1:i]
    raise AssertionError("unbalanced media block")


class TestHorizontalToolRow(unittest.TestCase):
    def test_rail_sits_above_workbench_not_inside_tool_col(self):
        nav = HTML.find('<nav class="tool-rail"')
        workbench = HTML.find('<div class="workbench">')
        tool_col = HTML.find('<div class="tool-col">')
        self.assertGreater(nav, -1)
        self.assertLess(nav, workbench)
        self.assertLess(workbench, tool_col)
        tool_col_block = HTML[tool_col:tool_col + 400]
        self.assertNotIn("tool-rail", tool_col_block)

    def test_all_rail_buttons_kept_in_order(self):
        nav = HTML[HTML.find('<nav class="tool-rail"'):HTML.find("</nav>", HTML.find('<nav class="tool-rail"'))]
        found = re.findall(r'data-(tab|action)="([^"]+)"', nav)
        self.assertEqual(found, RAIL_ORDER)

    def test_rail_is_horizontal_and_scrollable(self):
        rail = rule_body(CSS, ".tool-rail")
        self.assertIn("flex-direction: row", rail)
        self.assertIn("overflow-x: auto", rail)
        btn = rule_body(CSS, ".rail-btn")
        self.assertIn("white-space: nowrap", btn)
        self.assertIn("flex-shrink: 0", btn)

    def test_tool_col_is_panels_only_width(self):
        # Was 356px = 76px rail + 280px panels; rail moved out, so 280px.
        self.assertEqual(px(rule_body(CSS, ".tool-col"), "width"), 280)

    def test_rail_wiring_unchanged(self):
        self.assertIn('b.closest(".tool-rail")', JS)
        self.assertIn('document.querySelectorAll("[data-tab]")', JS)
        ids = set(re.findall(r'\$\("([A-Za-z0-9_-]+)"\)', JS))
        ids |= set(re.findall(r'getElementById\("([A-Za-z0-9_-]+)"\)', JS))
        for i in ids:
            self.assertIn(f'id="{i}"', HTML, f"missing id {i}")

    def test_collapse_hides_panels_column_only(self):
        collapsed = rule_body(CSS, ".tool-col.tool-col-collapsed")
        self.assertIn("display: none", collapsed)
        # The rail lives outside tool-col (test 1), so collapsing the
        # panels column can no longer hide the tool switcher itself.

    def test_agent_column_untouched_by_round_17(self):
        agent = rule_body(CSS, ".agent-col")
        self.assertEqual(px(agent, "width"), 340)


class TestRulerLaneSharedOrigin(unittest.TestCase):
    def _origins(self, css):
        label_w = px(rule_body(css, ".track-label"), "width")
        gap = px(rule_body(css, ".track-row"), "gap")
        margin = px(rule_body(css, ".ruler"), "margin-left")
        return label_w, gap, margin

    def test_default_origin_matches(self):
        label_w, gap, margin = self._origins(CSS)
        self.assertEqual(label_w, 128)
        self.assertEqual(gap, 10)
        self.assertEqual(margin, label_w + gap)  # 138: the old offset, now closed

    def test_narrow_breakpoint_origin_matches(self):
        block = media_block(CSS, "@media (max-width: 720px)")
        label_w = px(rule_body(block, ".track-label"), "width")
        margin = px(rule_body(block, ".ruler"), "margin-left")
        gap = px(rule_body(CSS, ".track-row"), "gap")  # gap is breakpoint-independent
        self.assertEqual(label_w, 84)
        self.assertEqual(gap, 10)
        self.assertEqual(margin, label_w + gap)  # 94
        self.assertNotIn("width: 60px", rule_body(block, ".tool-rail"))

    def test_tick_lane_playhead_clip_align(self):
        # Absolute x of each element for time T, from the real CSS:
        # wrap padding-left + origin + 1px border + T * pxPerSec.
        wrap = rule_body(CSS, ".timeline-wrap")
        pad = float(re.search(r"padding:\s*\d+px\s+(\d+)px", wrap).group(1))
        label_w, gap, margin = self._origins(CSS)
        border = 1.0
        for pps in (60, 100):
            for t in (0, 8.44, 60, 229.9):
                tick = pad + margin + border + t * pps
                lane_ph = pad + label_w + gap + border + t * pps
                clip = pad + label_w + gap + border + t * pps
                self.assertAlmostEqual(tick, lane_ph, places=6)
                self.assertAlmostEqual(tick, clip, places=6)
        # Before the fix the ruler had no margin, so the same math
        # gives a constant 138px gap — the exact complaint in the
        # user's screenshot. The margin above is what closes it.
        self.assertEqual(label_w + gap, 138)

    def test_ruler_click_lands_on_the_tick(self):
        wrap = rule_body(CSS, ".timeline-wrap")
        pad = float(re.search(r"padding:\s*\d+px\s+(\d+)px", wrap).group(1))
        _, _, margin = self._origins(CSS)
        border = 1.0
        for fps in (30, 29.97):
            for pps in (60, 100):
                for t in (0, 8.44, 60, 229.9):
                    # Border-box left of the ruler (what getBoundingClientRect
                    # returns) plus the tick's offset inside it.
                    rect_left = pad + margin
                    client_x = rect_left + border + t * pps
                    frames = round(((client_x - rect_left) / pps) * fps)
                    self.assertLessEqual(abs(frames / fps - t), 1.0 / fps + 1e-9)

    def test_js_uses_one_scale_with_no_hidden_offset(self):
        # Ruler playhead, ruler ticks, beat ticks, lane playhead and
        # clip left must all be the same t * pxPerSec scale.
        self.assertRegex(JS, r'left:\$\{\(playheadFrame / fps\(\)\) \* pxPerSec\}px')
        self.assertRegex(JS, r'left:\$\{sec \* pxPerSec\}px')
        self.assertRegex(JS, r'left:\$\{b \* pxPerSec\}px')
        self.assertRegex(JS, r'ph\.style\.left = \(playheadFrame / fps\(\)\) \* pxPerSec')
        self.assertRegex(JS, r'el\.style\.left = \(item\.at / fps\(\)\) \* pxPerSec')
        # The only additive constant among timeline x-positions is the
        # transition marker's -9, which centres its 18px icon on a clip
        # join; it is not a playhead, tick or clip origin.
        self.assertRegex(JS, r'marker\.style\.left = \(\(from\.at \+ from\.dur\) / fps\(\)\) \* pxPerSec - 9')
        # The ruler click handler measures from the ruler's own rect,
        # so it inherits the corrected origin automatically.
        click = JS[JS.find('$("ruler").addEventListener("click"'):]
        self.assertIn("getBoundingClientRect()", click[:400])
        self.assertIn("e.clientX - rect.left", click[:400])


if __name__ == "__main__":
    unittest.main()
