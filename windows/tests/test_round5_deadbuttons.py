"""Round 5, task 2: dead-button scan of the web UI.

Static scan (no browser): every <button> in static/index.html and every
element with an onclick handler must either

  * have a wired handler that calls a real server endpoint / project op
    (or a real local UI action: tab switch, scroll-to-panel, play/pause,
    preview toggle, mirror-click of another wired button), or
  * be explicitly marked unavailable WITH a specific reason
    (data-unavailable attribute, or label/title containing a reason such
    as "chua co" / "not available" plus the missing piece).

A button that clicks and does nothing, or that only prints a vague
"not available" without a reason, or that calls an endpoint/op that does
not exist in vibeedit_core/, fails this test.

Also covered here (round-5 fixes + round-4 regressions):
  * every tool panel must be reachable via a data-tab button;
  * every /api/* URL and every project op used by app.js must exist in
    server.py / project.py (no invented endpoints);
  * the round-4 Compare [hidden] rule must still hide compareWrap;
  * the round-4 voice-record button must still point at the real
    POST /api/voiceover/record endpoint;
  * the round-5 fixes: btnPlugins scrolls to the real Details panel
    (not a status-only "no panel" message), playerTabSource shows a real
    source preview (it used to hide the whole preview-wrap, which also
    hid its own "not available" note), and btnAgentWriteVO is labelled
    unavailable with its specific reason.

Run from windows/: python3 -m unittest tests.test_round5_deadbuttons -v
"""

import os
import re
import subprocess
import unittest

BASE = os.path.join(os.path.dirname(__file__), "..")


def _read(rel):
    path = os.path.join(BASE, rel)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _var_map(js):
    """Map JS variable name -> set of element ids for `$("id")` lookups.

    One name is reused for different elements in different IIFEs
    (e.g. fitBtn = btnPreviewFit in one wiring block and
    btnSettingsFit in another; vm = btnVisionCutoutModel and later
    voiceMedia), so a name maps to a SET, never a single id.
    """
    mapping = {}
    for var, ident in re.findall(
            r'(\w+)\s*=\s*(?:document\.getElementById\()?\$?\("([^"]+)"\)',
            js):
        mapping.setdefault(var, set()).add(ident)
    return mapping


def _wired_ids(js):
    """Element ids that have a click/submit listener (direct or via var)."""
    wired = set()
    var_map = _var_map(js)
    # Direct: $("id").addEventListener("click"|"submit", ...)
    for ident in re.findall(
            r'\$\("([^"]+)"\)\.addEventListener\("(?:click|submit)"', js):
        wired.add(ident)
    for ident in re.findall(
            r'getElementById\("([^"]+)"\)\.addEventListener\("(?:click|submit)"',
            js):
        wired.add(ident)
    # Via variable: const btn = $("id"); btn.addEventListener("click", ...)
    for var in re.findall(r'(\w+)\.addEventListener\("(?:click|submit)"', js):
        if var in var_map:
            wired.update(var_map[var])
    # Via the agent-dock helper: agentBtn("id", fn)
    for ident in re.findall(r'agentBtn\("([^"]+)"', js):
        wired.add(ident)
    # Via the timeline mirror map: { tlUndo: "btnUndo", ... } + .click()
    for mirror, real in re.findall(r'(\w+):\s*"(btn\w+)"', js):
        if real in wired:
            wired.add(mirror)
    return wired


def _button_attrs(tag):
    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', tag))
    return attrs


class TestDeadButtons(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = _read("static/index.html")
        cls.js = _read("static/app.js")
        cls.css = _read("static/style.css")
        cls.server = _read("vibeedit_core/server.py")
        cls.project = _read("vibeedit_core/project.py")
        cls.core = cls.server + "\n" + cls.project
        cls.wired = _wired_ids(cls.js)
        # Generic delegated handlers (one registration covers many buttons).
        cls.has_tab_handler = bool(re.search(
            r'querySelectorAll\("\[data-tab\]"\)', cls.js))
        cls.has_action_handler = bool(re.search(
            r'querySelectorAll\(\'\[data-action=', cls.js))
        cls.has_chip_handler = bool(re.search(
            r'querySelectorAll\("\[data-agent-chip\]"\)', cls.js))
        cls.submit_forms = _submit_forms(cls.js)

    def _form_of(self, button_start):
        """Id of the <form> enclosing a button position, or None."""
        before = self.html[:button_start]
        opens = list(re.finditer(r'<form[^>]*id="([^"]+)"', before))
        if not opens:
            return None
        # The last opened form is the enclosing one unless a </form>
        # intervenes after it.
        last = opens[-1]
        if "</form>" in before[last.end():]:
            return None
        return last.group(1)

    def _is_marked_unavailable(self, tag, text):
        if "data-unavailable=" in tag:
            return True
        hay = (tag + " " + text).lower()
        # A reason, not just the bare words: "chua co" / "not available"
        # must come with what is missing (ai / model / llm / clone...).
        if "chưa có" in hay or "chua co" in hay or "not available" in hay:
            return any(word in hay for word in (
                "ai", "llm", "kịch bản", "script", "model", "clone",
                "provider", "connected", "nối"))
        return False

    def test_no_onclick_attributes(self):
        onclicks = re.findall(r'onclick="[^"]*"', self.html)
        self.assertEqual(
            onclicks, [],
            "onclick attributes bypass the handler scan; wire via app.js: "
            + str(onclicks))

    def test_every_button_wired_or_marked_unavailable(self):
        dead = []
        for match in re.finditer(r'<button([^>]*)>(.*?)</button>',
                                 self.html, re.S):
            tag, raw_text = match.group(1), match.group(2)
            text = re.sub(r"\s+", " ", raw_text).strip()
            attrs = _button_attrs(tag)
            ident = attrs.get("id")
            # Submit buttons are wired through their form's handler.
            if attrs.get("type") == "submit":
                form = self._form_of(match.start())
                if form and form in self.submit_forms:
                    continue
                dead.append(f"submit button {text!r} (form={form}) "
                            "has no submit handler in app.js")
                continue
            # Delegated handlers cover these families wholesale.
            if "data-tab" in attrs and self.has_tab_handler:
                continue
            if "data-action" in attrs and self.has_action_handler:
                continue
            if "data-agent-chip" in attrs and self.has_chip_handler:
                continue
            if ident and ident in self.wired:
                continue
            if self._is_marked_unavailable(tag, text):
                continue
            dead.append(f"button id={ident} text={text!r} attrs={tag}")
        self.assertEqual(dead, [], "dead buttons found: " + "; ".join(dead))

    def test_every_form_has_submit_handler(self):
        orphan = []
        for form in re.findall(r'<form[^>]*id="([^"]+)"', self.html):
            if form not in self.submit_forms:
                orphan.append(form)
        self.assertEqual(orphan, [],
                         "forms with no submit handler in app.js: "
                         + ", ".join(orphan))

    def test_every_tool_panel_reachable(self):
        panels = set(re.findall(r'data-panel="([^"]+)"', self.html))
        tabs = set(re.findall(r'data-tab="([^"]+)"', self.html))
        self.assertEqual(panels - tabs, set(),
                         "tool panels no button can open: "
                         + ", ".join(sorted(panels - tabs)))

    def test_dynamic_buttons_have_handlers(self):
        # Buttons rendered by app.js itself (not present in index.html).
        for attr in ("data-tr", "data-kf", "data-library-place",
                     "data-library-remove", "data-plugin-toggle",
                     "data-welcome-open", "data-welcome-remove",
                     "data-add-media"):
            self.assertIn(attr, self.js,
                          f"dynamic button family {attr} missing from app.js")
            self.assertRegex(
                self.js,
                r'querySelectorAll\("[^"]*' + re.escape(attr) +
                r'[^"]*"\)\.forEach\(\(b\) => b\.addEventListener\("click"',
                f"dynamic buttons {attr} have no click handler")

    def test_js_endpoints_exist_in_server(self):
        raw = set(re.findall(r'"/api/([^"]*)"', self.js))
        missing = []
        for ep in raw:
            path = "/api/" + ep.split("?")[0].split("${")[0]
            if path.endswith("/"):
                pass  # prefix form, e.g. /api/media/
            elif path not in self.server:
                # Template forms: /api/thumbnail/<id> -> prefix check.
                prefix = path.rsplit("/", 1)[0] + "/"
                if prefix not in self.server and path + "/" not in self.server:
                    missing.append(path)
        self.assertEqual(missing, [],
                         "app.js calls endpoints missing from server.py: "
                         + ", ".join(sorted(missing)))

    def test_js_ops_exist_in_core(self):
        ops = set(re.findall(r'op:\s*"([^"]+)"', self.js))
        ops |= set(re.findall(r'vision\("([^"]+)"', self.js))
        # Ternary op selection: op: overwrite ? "source_overwrite"
        # : "source_insert" — both strings are real server ops.
        for name in ("source_insert", "source_overwrite"):
            if f'"{name}"' in self.js:
                ops.add(name)
        missing = [op for op in sorted(ops) if op not in self.core]
        self.assertEqual(missing, [],
                         "app.js calls project ops missing from core: "
                         + ", ".join(missing))

    def test_no_duplicate_ids(self):
        ids = re.findall(r'id="([^"]+)"', self.html)
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        self.assertEqual(dupes, [], f"duplicate ids: {dupes}")

    def test_compare_hidden_rule_still_holds(self):
        self.assertIn('id="compareWrap" hidden', self.html)
        rule = re.search(r'#compareWrap\[hidden\]\s*\{([^}]*)\}', self.css)
        self.assertIsNotNone(rule, "#compareWrap[hidden] rule missing")
        self.assertIn("display: none", rule.group(1))
        self.assertIn("compareWipeAt", self.js)
        self.assertIn("compareWireSync", self.js)

    def test_voice_record_still_points_at_real_endpoint(self):
        self.assertIn('id="btnVoiceRecord"', self.html)
        self.assertNotIn('id="btnVoiceRecord" disabled', self.html)
        self.assertIn("/api/voiceover/record", self.js)
        self.assertIn('fetch("/api/voiceover/record"', self.js)
        self.assertIn("getUserMedia", self.js)
        self.assertIn("MediaRecorder", self.js)
        self.assertIn("/api/voiceover/record", self.server)

    def test_round5_plugins_button_wired_to_real_panel(self):
        # The old handler was status-only and claimed no plugin panel
        # exists; the Details column DOES contain the Plugins panel.
        self.assertNotIn("Chưa có panel cài đặt plugin", self.js)
        self.assertIn('class="details-col"', self.html)
        self.assertIn('id="pluginForm"', self.html)
        self.assertIn('id="pluginList"', self.html)
        handler = self.js[self.js.index('const btnPlugins ='):][:900]
        self.assertIn(".details-col", handler)
        self.assertIn("scrollIntoView", handler)

    def test_round5_source_tab_shows_real_source(self):
        # The old handler set wrap.hidden = true, hiding the preview
        # AND the note inside it. The new one must keep the wrap
        # visible and show a real source preview.
        start = self.js.index('const tabTl = $("playerTabTimeline")')
        block = self.js[start:start + 1600]
        self.assertIn("showSourcePreview", block)
        self.assertNotIn("wrap.hidden = true", block)
        self.assertNotIn("Source view is not available yet", self.html)

    def test_round5_write_vo_labelled_unavailable_with_reason(self):
        match = re.search(
            r'<button[^>]*id="btnAgentWriteVO"[^>]*>(.*?)</button>',
            self.html, re.S)
        self.assertIsNotNone(match, "btnAgentWriteVO missing")
        tag = self.html[match.start():match.end()]
        self.assertIn("data-unavailable=", tag)
        self.assertIn("chưa có", tag)
        self.assertIn("AI", tag)

    def test_app_js_syntax(self):
        import shutil
        if shutil.which("node") is None:
            self.skipTest("node not installed on this machine")
        proc = subprocess.run(
            ["node", "--check", os.path.join(BASE, "static", "app.js")],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


def _submit_forms(js):
    """Form ids with a submit listener (direct or via a variable)."""
    forms = set()
    var_map = _var_map(js)
    for ident in re.findall(
            r'\$\("([^"]+)"\)\.addEventListener\("submit"', js):
        forms.add(ident)
    for var in re.findall(r'(\w+)\.addEventListener\("submit"', js):
        if var in var_map:
            forms.update(var_map[var])
    return forms


if __name__ == "__main__":
    unittest.main()
