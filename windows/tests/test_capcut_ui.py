"""CapCut-style shell redesign tests.

Run from windows/:  python3 -m unittest discover -s tests -v

The redesign moves existing panels into tool tabs and a right Details
column; it must not rename, remove, or lose any element app.js uses,
must keep the logo data URI, and must keep every old panel reachable
in its new tab. No browser is involved: these checks read the served
files and the HTML structure directly.
"""

import os
import re
import unittest


def _read(rel):
    path = os.path.join(os.path.dirname(__file__), "..", rel)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _panel(html, name):
    """HTML of the tool panel with data-panel=name (up to next panel)."""
    parts = re.split(r'<section class="panel tool-panel" data-panel="([^"]+)"',
                     html)
    for i in range(1, len(parts), 2):
        if parts[i] == name:
            # Cut at the next tool panel or the end of the tool column.
            rest = parts[i + 1]
            nxt = rest.find('<section class="panel tool-panel"')
            return rest if nxt == -1 else rest[:nxt]
    raise AssertionError(f"tool panel missing: {name}")


class TestCapcutShell(unittest.TestCase):
    def test_every_app_js_id_still_in_html(self):
        js = _read("static/app.js")
        html = _read("static/index.html")
        for ident in sorted(set(re.findall(r'\$\("([^"]+)"\)', js))):
            self.assertIn(f'id="{ident}"', html,
                          f"app.js id {ident} missing from index.html")

    def test_logo_data_uri_intact(self):
        html = _read("static/index.html")
        self.assertIn("data:image/png;base64,", html)
        self.assertIn('class="brand-logo"', html)
        self.assertIn("onerror=", html)

    def test_top_toolbar_matches_screenshot_items(self):
        # SUPERSEDED (user decision 2026-10-27): the CapCut top icon
        # toolbar was removed in favour of the original-app shell.
        # The original has ONE far-left vertical rail, not a top row,
        # so the shell must NOT contain the CapCut toolbar anymore.
        html = _read("static/index.html")
        self.assertNotIn('class="tool-toolbar"', html)
        self.assertNotIn('class="tool-btn', html)
        # The original's top bar keeps project, rev, Export report,
        # Plugins, Review and Export — all still present.
        for marker in ("projectRev", "btnExportReport", "btnPlugins",
                       "btnReviewTop", "btnExportFull"):
            self.assertIn(marker, html, marker)

    def test_left_rail_matches_screenshot_menu(self):
        # Original-app rail (spec 01 section 1.3): Media, Audio, Text,
        # Stickers, Effects, Transitions, Filters, Voice, Timeline, More.
        html = _read("static/index.html")
        for label in ("Media", "Audio", "Text", "Stickers", "Effects",
                      "Transitions", "Filters", "Voice", "Timeline",
                      "More"):
            self.assertIn(f">{label}</button>", html,
                          f"rail item missing: {label}")
        # Rail only: the Media panel's "Create with these tools"
        # Generate card is a different element, not a rail item.
        import re as _re
        rail = _re.search(r'<nav class="tool-rail".*?</nav>', html,
                          _re.S).group(0)
        self.assertNotIn(">Subprojects</button>", rail)
        self.assertNotIn(">Generate</button>", rail)

    def test_shell_structure(self):
        html = _read("static/index.html")
        for marker in ('class="workbench"', 'class="tool-col"',
                       'class="centre-col"', 'class="details-col"',
                       'class="player-head"', 'class="timeline-wrap"',
                       'class="timeline-toolbar"',
                       'id="timelineEmptyHint"',
                       "Drag material here and start to create",
                       'class="import-dropzone"',
                       "Drag and drop videos, photos, and audio files here",
                       "No media? Create with these tools"):
            self.assertIn(marker, html, f"shell marker missing: {marker}")

    def test_old_panels_mapped_to_new_tabs(self):
        html = _read("static/index.html")
        mapping = {
            "media": ("uploadForm", "mediaList", "addClipForm",
                      "importDropzone"),
            "audio": ("beatForm", "duckingForm", "btnBeatsMarkers",
                      "btnSnap"),
            "text": ("addTextForm",),
            "transitions": ("transitionForm", "transitionList",
                            "btnTransitionPreview",
                            "transitionPreviewBox"),
            "captions": ("srtImportForm", "btnSrtExport", "karaokeForm",
                         "btnKaraokeAss"),
            "effects": ("adjustmentForm",),
            "templates": ("batchForm", "btnOtio", "exportNormalize",
                          "batchResult", "otioImportForm", "phase4Result"),
            "ai": ("agentDockCommand", "mcpTools", "btnReview",
                   "reviewResult"),
        }
        for panel, ids in mapping.items():
            body = _panel(html, panel)
            for ident in ids:
                self.assertIn(f'id="{ident}"', body,
                              f"{ident} not in tab {panel}")
        details = html.split('class="details-col"')[1].split(
            'class="timeline-wrap"')[0]
        for ident in ("inspectorEmpty", "inspectorForm", "keyframeBox",
                      "keyframeForm"):
            self.assertIn(f'id="{ident}"', details,
                          f"{ident} not in Details column")

    def test_no_fake_feature_tabs(self):
        """Stickers/Filters must not pretend to be tools we lack."""
        html = _read("static/index.html")
        stickers = _panel(html, "stickers")
        self.assertIn("not in VibeEdit yet", stickers)
        filters = _panel(html, "filters")
        self.assertIn("Details", filters)

    def test_teal_theme_and_legacy_selectors(self):
        css = _read("static/style.css")
        for snippet in ("#00c8d4", "#101014", "#1a1a1f",
                        ".tool-rail",
                        ".workbench", ".details-col", ".timeline-toolbar",
                        ".preview-wrap video", ".panel h3::before",
                        ".clip.selected", ".ruler .playhead::after",
                        "button:focus-visible",
                        "repeating-linear-gradient",
                        ".track-label", ".beat-tick"):
            self.assertIn(snippet, css, f"missing CSS rule: {snippet}")
        self.assertNotIn("@import", css)
        self.assertNotIn("fonts.googleapis", css)

    def test_shell_js_wiring(self):
        js = _read("static/app.js")
        for snippet in ("activateTab", 'data-tab', "importDropzone",
                        "tlUndo", "tlSplit", "focus-inspector"):
            self.assertIn(snippet, js, f"missing shell wiring: {snippet}")


if __name__ == "__main__":
    unittest.main()
