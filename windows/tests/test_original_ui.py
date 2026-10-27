"""Original-app layout tests: the Windows UI must follow the structure
of the original BashCut editor (top bar, Voice panel, Inspector,
always-visible Agent dock, full timeline toolbar) without breaking
any existing app.js element id, and without claiming features that
do not exist (no in-app LLM generation, no voice cloning/recording).
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = os.path.dirname(HERE)


def read(rel):
    with open(os.path.join(WINDOWS, rel), encoding="utf-8") as fh:
        return fh.read()


class TestOriginalUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read("static/index.html")
        cls.js = read("static/app.js")
        cls.css = read("static/style.css")

    def test_all_app_js_ids_still_present(self):
        ids = set(re.findall(r'\$\("([^"]+)"\)', self.js))
        ids |= set(re.findall(r'getElementById\("([^"]+)"\)', self.js))
        self.assertGreater(len(ids), 90, "app.js should reference many ids")
        missing = [i for i in ids if f'id="{i}"' not in self.html]
        self.assertEqual(missing, [], f"ids used by app.js missing from HTML: {missing}")

    def test_no_duplicate_ids(self):
        found = re.findall(r'id="([^"]+)"', self.html)
        dups = sorted({i for i in found if found.count(i) > 1})
        self.assertEqual(dups, [], f"duplicate ids: {dups}")

    def test_logo_data_uri_intact(self):
        self.assertIn("data:image/png;base64", self.html)

    def test_top_bar_markers(self):
        for marker in ("projectRev", "Edited rev", "btnExportReport",
                       "Export report", "btnExportDraft", "btnExportFull"):
            self.assertIn(marker, self.html, marker)

    def test_voice_panel_markers(self):
        for marker in ("Voiceover", "voiceProvider", "voiceVoice",
                       "Clone voice", "voiceRefFile", "btnVoiceClone",
                       "btnVoiceGenerate", "btnVoiceRecord",
                       "voiceoverForm", "voiceMedia", "voiceAt",
                       "Import a voiceover take", "voiceList",
                       "not available"):
            self.assertIn(marker, self.html, marker)

    def test_inspector_tabs_markers(self):
        # Inspector sections map to the original's Video/Audio/Text/
        # Color/Speed tabs: position/scale (Video), volume/fades
        # (Audio), text (Text), LUT/preset (Color), speed (Speed).
        for marker in ("INSPECTOR", "inspSpeed", "inspVolume",
                       "inspText", "inspLut", "inspPreset",
                       "inspFadeIn", "inspFadeOut", "keyframeForm"):
            self.assertIn(marker, self.html, marker)

    def test_agent_dock_markers(self):
        for marker in ("AGENT", "agentDock", "agentChat", "agentChatForm",
                       "agentChatInput", "agentProvider",
                       "btnAgentWorkspace", "btnAgentContext",
                       "btnAgentSurvey", "btnAgentWriteVO",
                       "btnAgentReview",
                       "no in-app LLM generation connected yet",
                       "vibeedit.py mcp"):
            self.assertIn(marker, self.html, marker)

    def test_timeline_toolbar_functions(self):
        for marker in ("tlAdd", "tlUndo", "tlRedo", "tlSplit", "tlDelete",
                       "tlAddLayer", "Add Layer", "tlSections",
                       "Sections", "tlAskAgent", "Ask agent",
                       "timelineEmptyHint",
                       "Drag material here and start to create",
                       "zoom", "ruler", "tracks"):
            self.assertIn(marker, self.html, marker)

    def test_timeline_track_order_in_js(self):
        for role in ("captions", "overlay", "main", "background",
                     "dialogue", "voiceover", "music", "sfx"):
            self.assertIn(f'"{role}"', self.js, role)
        order = self.js.index('"captions"'), self.js.index('"overlay"')
        self.assertLess(order[0], order[1])

    def test_player_tabs_and_view_controls(self):
        for marker in ("playerTabTimeline", "playerTabSource",
                       "btnPreviewFit", "btnPreviewCompare",
                       "btnPreviewSafe", "safeAreaOverlay",
                       "btnPreviewPlay", "btnPreviewBack",
                       "playerSourceNote"):
            self.assertIn(marker, self.html, marker)

    def test_no_fake_claims(self):
        # The UI must never claim these work in-app.
        for bad in ("Claude is connected", "voice cloning is available",
                    "recording is available in VibeEdit"):
            self.assertNotIn(bad, self.html, bad)
            self.assertNotIn(bad, self.js, bad)
        # But the honest "not available" notes must exist.
        self.assertIn("not available", self.html)


if __name__ == "__main__":
    unittest.main()
