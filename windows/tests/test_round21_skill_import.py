"""Round 23 skill round (test file keeps the user's verbatim name):
folder-form skill store, skill import (plan/apply), kit_install
accepting .zip + nested folders, Claude Code sync, and the two new
MCP tools. The user's real zip
(C:\\Users\\daoho\\Downloads\\thanh-hai-learn-ai-2d-studio.zip) is
not on this machine, so the 5-skill acceptance case runs against a
synthetic zip with the same structure (plugin folder, one skill
with references/style-bible.md); the real-file step can only run on
the user's Windows after pull.

New tests live ONLY here. Old-test count bumps (479 -> 481,
427 -> 429, honest stays 52) are the count-maintenance exception.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core import skill_import  # noqa: E402
from vibeedit_core.mcp import MCPServer, TOOLS, handle  # noqa: E402
from vibeedit_core.skills import (  # noqa: E402
    export_skill, get_skill, list_skills, remove_skill, search_skills,
    set_skill_enabled)

# Shipped flat skills as of round 23 (counted on disk: 21, not the
# 23 the user remembered — the test asserts the real set).
SHIPPED_FLAT = [
    "audio-mix", "beat-cut", "captions-text", "color-grade",
    "edit-workflow", "effects", "export-presets", "footage-survey",
    "library", "loudness-check", "motion-graphics", "review-workflow",
    "review", "rough-cut", "self-learn", "setup", "stock-images",
    "style-study", "timeline-editing", "visual-plan", "voiceover",
]
SHIPPED_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "skills"))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def md(title, body="Nội dung skill."):
    return "# %s\n\n%s\n" % (title, body)


class StoreBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = os.path.join(self.tmp.name, "skills")
        os.makedirs(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def flat_store(self):
        write(os.path.join(self.store, "alpha.md"), md("Alpha"))
        write(os.path.join(self.store, "beta.md"), md("Beta"))

    def folder_store(self):
        base = os.path.join(self.store, "gamma")
        write(os.path.join(base, "SKILL.md"),
              md("Gamma", "Tài liệu hướng dẫn. Xem references/ref.md"))
        write(os.path.join(base, "references", "ref.md"), "Tài liệu tham khảo.")
        write(os.path.join(base, "kit", "kit.txt"), "kit data")


class TestFolderStore(StoreBase):
    def test_list_both_forms_and_kinds(self):
        self.flat_store()
        self.folder_store()
        # A proposals dir and a dir without SKILL.md are not skills.
        os.makedirs(os.path.join(self.store, "proposals"))
        write(os.path.join(self.store, "proposals", "draft.md"), md("Draft"))
        os.makedirs(os.path.join(self.store, "notaskill"))
        entries = {e["id"]: e for e in list_skills(self.store)}
        self.assertEqual(sorted(entries), ["alpha", "beta", "gamma"])
        self.assertEqual(entries["alpha"]["kind"], "flat")
        self.assertEqual(entries["gamma"]["kind"], "folder")
        self.assertEqual(entries["gamma"]["title"], "Gamma")
        self.assertTrue(entries["gamma"]["enabled"])

    def test_shipped_flat_skills_still_listed(self):
        entries = {e["id"]: e for e in list_skills(SHIPPED_DIR)}
        for skill_id in SHIPPED_FLAT:
            self.assertIn(skill_id, entries, skill_id)
            self.assertEqual(entries[skill_id]["kind"], "flat")

    def test_get_remove_export_both_forms(self):
        self.flat_store()
        self.folder_store()
        self.assertIn("Gamma", get_skill(self.store, "gamma"))
        self.assertIn("Alpha", get_skill(self.store, "alpha"))
        with self.assertRaises(FileNotFoundError):
            get_skill(self.store, "nope")
        with self.assertRaises(ValueError):
            get_skill(self.store, "../escape")
        out = os.path.join(self.tmp.name, "exp")
        res = export_skill(self.store, "gamma", out)
        self.assertTrue(os.path.isfile(os.path.join(out, "SKILL.md")))
        self.assertTrue(os.path.isfile(
            os.path.join(out, "references", "ref.md")))
        self.assertEqual(res["kind"], "folder")
        res = export_skill(self.store, "alpha", None)
        self.assertIn("Alpha", res["content"])
        remove_skill(self.store, "gamma", confirm=True)
        self.assertFalse(os.path.exists(os.path.join(self.store, "gamma")))
        remove_skill(self.store, "alpha", confirm=True)
        remove_skill(self.store, "beta", confirm=True)
        self.assertEqual(list_skills(self.store), [])
        with self.assertRaises(ValueError):
            remove_skill(self.store, "beta", confirm=False)

    def test_folder_wins_on_collision(self):
        write(os.path.join(self.store, "same.md"), md("Flat Same"))
        write(os.path.join(self.store, "same", "SKILL.md"), md("Folder Same"))
        entries = {e["id"]: e for e in list_skills(self.store)}
        self.assertEqual(list(entries), ["same"])
        self.assertEqual(entries["same"]["kind"], "folder")
        self.assertIn("Folder Same", get_skill(self.store, "same"))

    def test_search_and_enable_cover_folder_skills(self):
        self.folder_store()
        found = search_skills(self.store, "tài liệu")
        self.assertEqual([e["id"] for e in found], ["gamma"])
        set_skill_enabled(self.store, "gamma", False)
        entries = {e["id"]: e for e in list_skills(self.store)}
        self.assertFalse(entries["gamma"]["enabled"])
        set_skill_enabled(self.store, "gamma", True)
        self.assertTrue(list_skills(self.store)[0]["enabled"])


def plugin_folder(base):
    """Claude-plugin layout: <base>/skills/<id>/SKILL.md."""
    skills = [
        ("make-2d-video", "Make 2D Video", True),
        ("story-board", "Story Board", False),
        ("voice-direct", "Voice Direct", False),
    ]
    for skill_id, title, with_ref in skills:
        sub = os.path.join(base, "skills", skill_id)
        write(os.path.join(sub, "SKILL.md"),
              md(title, "Xem references/style-bible.md" if with_ref else "Body."))
        if with_ref:
            write(os.path.join(sub, "references", "style-bible.md"),
                  "# Style Bible\n\nQuy tắc phong cách.\n")
    return skills


def plugin_zip(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for skill_id, title, with_ref in [
                ("make-2d-video", "Make 2D Video", True),
                ("story-board", "Story Board", False),
                ("voice-direct", "Voice Direct", False),
                ("edit-assist", "Edit Assist", False),
                ("thumb-maker", "Thumb Maker", False)]:
            root = "thanh-hai-learn-ai-2d-studio/skills/%s" % skill_id
            zf.writestr(root + "/SKILL.md", md(title))
            if with_ref:
                zf.writestr(root + "/references/style-bible.md",
                            "# Style Bible\n\nQuy tắc phong cách.\n")


class TestPlanImport(StoreBase):
    def snapshot(self):
        snap = {}
        for dirpath, _dirs, names in os.walk(self.store):
            for name in names:
                full = os.path.join(dirpath, name)
                with open(full, "rb") as fh:
                    snap[os.path.relpath(full, self.store)] = \
                        hashlib.sha256(fh.read()).hexdigest()
        return snap

    def test_four_input_forms(self):
        # 1. single .md
        single = os.path.join(self.tmp.name, "solo.md")
        write(single, md("Solo"))
        plan = skill_import.plan_import(single, self.store)
        self.assertEqual([s["id"] for s in plan["skills"]], ["solo"])
        self.assertEqual(plan["skills"][0]["kind"], "flat")
        # 2. flat folder
        flat_dir = os.path.join(self.tmp.name, "flatdir")
        write(os.path.join(flat_dir, "one.md"), md("One"))
        write(os.path.join(flat_dir, "two.md"), md("Two"))
        plan = skill_import.plan_import(flat_dir, self.store)
        self.assertEqual([s["id"] for s in plan["skills"]], ["one", "two"])
        # 3. plugin folder
        plug = os.path.join(self.tmp.name, "plug")
        plugin_folder(plug)
        plan = skill_import.plan_import(plug, self.store)
        self.assertEqual([s["id"] for s in plan["skills"]],
                         ["make-2d-video", "story-board", "voice-direct"])
        self.assertTrue(all(s["kind"] == "folder"
                            for s in plan["skills"]))
        # 4. zip of a plugin
        zpath = os.path.join(self.tmp.name, "plug.zip")
        plugin_zip(zpath)
        plan = skill_import.plan_import(zpath, self.store)
        self.assertEqual(len(plan["skills"]), 5)
        self.assertIn("make-2d-video",
                      [s["id"] for s in plan["skills"]])

    def test_plan_writes_nothing(self):
        self.flat_store()
        before = self.snapshot()
        plug = os.path.join(self.tmp.name, "plug")
        plugin_folder(plug)
        skill_import.plan_import(plug, self.store)
        zpath = os.path.join(self.tmp.name, "plug.zip")
        plugin_zip(zpath)
        skill_import.plan_import(zpath, self.store)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(os.path.exists(
            os.path.join(self.store, "IMPORT_MANIFEST.json")))
        self.assertFalse(os.path.exists(
            os.path.join(self.tmp.name, "skills.json")))

    def test_zip_slip_and_unsafe_entries_skipped(self):
        zpath = os.path.join(self.tmp.name, "evil.zip")
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("good/SKILL.md", md("Good"))
            zf.writestr("../evil.md", md("Evil"))
            zf.writestr("/abs.md", md("Abs"))
            info = zipfile.ZipInfo("link/SKILL.md")
            info.external_attr = (0o120777 << 16)
            zf.writestr(info, md("Link"))
            zf.writestr("good/.git/config", "git")
        plan = skill_import.plan_import(zpath, self.store)
        self.assertEqual([s["id"] for s in plan["skills"]], ["good"])
        self.assertTrue(plan["warnings"])
        res = skill_import.apply_import(zpath, skills_dir=self.store)
        self.assertEqual(res["installed"], ["good"])
        self.assertFalse(os.path.exists(
            os.path.join(self.tmp.name, "evil.md")))
        self.assertFalse(os.path.exists(os.path.join("/", "abs.md")))

    def test_oversize_and_too_many_entries(self):
        big = os.path.join(self.tmp.name, "big.zip")
        with zipfile.ZipFile(big, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("big/SKILL.md", b"\0" * (51 * 1024 * 1024))
        with self.assertRaises(ValueError):
            skill_import.plan_import(big, self.store)
        many = os.path.join(self.tmp.name, "many.zip")
        with zipfile.ZipFile(many, "w") as zf:
            for i in range(2001):
                zf.writestr("f%04d.md" % i, md("F%d" % i))
        with self.assertRaises(ValueError):
            skill_import.plan_import(many, self.store)

    def test_bad_id_warns_and_skips(self):
        bad = os.path.join(self.tmp.name, "Bad Name!")
        write(os.path.join(bad, "SKILL.md"), md("Bad"))
        plan = skill_import.plan_import(bad, self.store)
        self.assertFalse(plan["skills"][0]["installable"])
        self.assertTrue(plan["skills"][0]["warnings"])
        res = skill_import.apply_import(bad, skills_dir=self.store)
        self.assertEqual(res["installed"], [])
        self.assertEqual(list_skills(self.store), [])

    def test_overwrite_and_only_filter(self):
        self.flat_store()
        src = os.path.join(self.tmp.name, "alpha.md")
        write(src, md("Alpha Mới"))
        res = skill_import.apply_import(src, skills_dir=self.store)
        self.assertEqual(res["installed"], [])
        self.assertEqual(res["skipped"][0]["id"], "alpha")
        self.assertIn("Alpha", get_skill(self.store, "alpha"))
        res = skill_import.apply_import(src, overwrite=True,
                                        skills_dir=self.store)
        self.assertEqual(res["installed"], ["alpha"])
        self.assertIn("Alpha Mới", get_skill(self.store, "alpha"))
        plug = os.path.join(self.tmp.name, "plug")
        plugin_folder(plug)
        res = skill_import.apply_import(
            plug, only=["story-board"], skills_dir=self.store)
        self.assertEqual(res["installed"], ["story-board"])
        self.assertEqual(sorted(e["id"] for e in list_skills(self.store)),
                         ["alpha", "beta", "story-board"])

    def test_no_exec_and_references_alive_and_verbatim(self):
        src = os.path.join(self.tmp.name, "evilskill")
        write(os.path.join(src, "SKILL.md"),
              md("Evil", "Xem references/style-bible.md"))
        write(os.path.join(src, "references", "style-bible.md"),
              "# Style Bible\n")
        write(os.path.join(src, "evil.py"),
              "open('MARKER_EXECUTED','w').write('x')\n")
        write(os.path.join(src, "references", "script.js"),
              "require('fs').writeFileSync('MARKER_JS','x');\n")
        marker = os.path.join(self.store, "MARKER_EXECUTED")
        res = skill_import.apply_import(src, skills_dir=self.store)
        self.assertEqual(res["installed"], ["evilskill"])
        self.assertFalse(os.path.exists(marker))
        installed = os.path.join(self.store, "evilskill")
        self.assertTrue(os.path.isfile(
            os.path.join(installed, "references", "style-bible.md")))
        # Copied as inert data, never executed.
        self.assertTrue(os.path.isfile(os.path.join(installed, "evil.py")))
        with open(os.path.join(src, "SKILL.md"), "rb") as fh:
            src_bytes = fh.read()
        with open(os.path.join(installed, "SKILL.md"), "rb") as fh:
            self.assertEqual(fh.read(), src_bytes)

    def test_no_auto_enable_and_manifest(self):
        self.flat_store()
        set_skill_enabled(self.store, "beta", False)
        state_path = os.path.join(self.tmp.name, "skills.json")
        with open(state_path, "rb") as fh:
            before = fh.read()
        plug = os.path.join(self.tmp.name, "plug")
        plugin_folder(plug)
        res = skill_import.apply_import(plug, skills_dir=self.store)
        self.assertEqual(len(res["installed"]), 3)
        with open(state_path, "rb") as fh:
            self.assertEqual(fh.read(), before)
        manifest_path = os.path.join(self.store, "IMPORT_MANIFEST.json")
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        entry = manifest["skills"]["make-2d-video"]
        self.assertEqual(entry["source"], os.path.abspath(plug))
        with open(os.path.join(plug, "skills", "make-2d-video",
                               "SKILL.md"), "rb") as fh:
            self.assertEqual(entry["sha256"],
                             hashlib.sha256(fh.read()).hexdigest())
        self.assertEqual(entry["kind"], "folder")

    def test_error_messages_and_missing_path(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            skill_import.plan_import(
                os.path.join(self.tmp.name, "nope.zip"), self.store)
        self.assertIn("Không tìm thấy", str(ctx.exception))
        txt = os.path.join(self.tmp.name, "note.txt")
        write(txt, "hello")
        with self.assertRaises(ValueError):
            skill_import.plan_import(txt, self.store)
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        with self.assertRaises(ValueError):
            skill_import.plan_import(empty, self.store)


class TestKitInstall(StoreBase):
    def test_zip_and_nested_folder_via_mcp(self):
        server = MCPServer()
        zpath = os.path.join(self.tmp.name, "kit.zip")
        plugin_zip(zpath)
        res = server.call("vibeedit_agent_kit_install",
                          {"path": zpath, "kit_dir": self.store})
        self.assertEqual(len(res["installed"]), 5)
        self.assertTrue(os.path.isfile(
            os.path.join(self.store, "make-2d-video.md")))
        # Nested folder form, direct function path (fresh kit dir:
        # the zip above already owns these ids in self.store).
        plug = os.path.join(self.tmp.name, "plug")
        plugin_folder(plug)
        fresh = os.path.join(self.tmp.name, "kit2")
        os.makedirs(fresh)
        from vibeedit_core.round8 import kit_install_skills
        res = kit_install_skills(plug, fresh)
        self.assertIn("story-board", res["installed"])
        # Existing ids are refused, never overwritten.
        res = kit_install_skills(plug, fresh)
        self.assertEqual(res["installed"], [])
        self.assertTrue(res["refused"])


class TestSyncClaude(StoreBase):
    def test_sync_flat_folder_hand_edited(self):
        self.flat_store()
        self.folder_store()
        target = os.path.join(self.tmp.name, "claude", "skills")
        res = skill_import.sync_claude(self.store, target)
        self.assertEqual(sorted(res["written"]),
                         ["alpha", "beta", "gamma"])
        self.assertIn("/reload-skills", res["note"])
        self.assertTrue(os.path.isfile(
            os.path.join(target, "alpha", "SKILL.md")))
        self.assertTrue(os.path.isfile(
            os.path.join(target, "gamma", "references", "ref.md")))
        # kit/ is VibeEdit-internal: not synced to Claude Code.
        self.assertFalse(os.path.exists(
            os.path.join(target, "gamma", "kit")))
        # Hand-edited destination is left alone without overwrite.
        hand = os.path.join(target, "alpha", "SKILL.md")
        write(hand, md("Alpha Tay"))
        res = skill_import.sync_claude(self.store, target)
        self.assertEqual(res["written"], [])
        self.assertEqual(res["skipped"][0]["id"], "alpha")
        res = skill_import.sync_claude(self.store, target, overwrite=True)
        self.assertIn("alpha", res["written"])
        with open(hand, encoding="utf-8") as fh:
            self.assertIn("Alpha", fh.read())


class TestMCPTools(StoreBase):
    def test_registry_counts_and_schemas(self):
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(honest), 52)
        self.assertEqual(len(TOOLS) - len(honest), 429)
        by_name = {t["name"]: t for t in TOOLS}
        for name in ("vibeedit_skills_import_plan",
                     "vibeedit_skills_import"):
            self.assertIn(name, by_name)
            schema = by_name[name]["inputSchema"]
            self.assertIn("path", schema["properties"])
            self.assertIn("path", schema["required"])

    def test_mcp_import_plan_and_apply(self):
        server = MCPServer()
        plug = os.path.join(self.tmp.name, "plug")
        plugin_folder(plug)
        plan = server.call("vibeedit_skills_import_plan",
                           {"path": plug, "skills_dir": self.store})
        self.assertEqual(len(plan["skills"]), 3)
        res = server.call("vibeedit_skills_import",
                          {"path": plug, "skills_dir": self.store,
                           "only": ["voice-direct"]})
        self.assertEqual(res["installed"], ["voice-direct"])
        self.assertTrue(os.path.isdir(
            os.path.join(self.store, "voice-direct")))

    def test_resources_list_and_read(self):
        server = MCPServer()
        listing = handle(server, {"jsonrpc": "2.0", "id": 1,
                                  "method": "resources/list"})
        uris = [r["uri"] for r in listing["result"]["resources"]]
        self.assertIn("vibeedit-skill://audio-mix", uris)
        read = handle(server, {"jsonrpc": "2.0", "id": 2,
                               "method": "resources/read",
                               "params": {"uri": "vibeedit-skill://audio-mix"}})
        self.assertTrue(read["result"]["contents"][0]["text"])
        bad = handle(server, {"jsonrpc": "2.0", "id": 3,
                              "method": "resources/read",
                              "params": {"uri": "unknown://x"}})
        self.assertEqual(bad["error"]["code"], -32603)
        # tools/list is untouched by the resources path.
        tools = handle(server, {"jsonrpc": "2.0", "id": 4,
                                "method": "tools/list"})
        self.assertEqual(len(tools["result"]["tools"]), 481)


class TestSyntheticUserZip(StoreBase):
    def test_five_skill_plugin_zip_like_user_file(self):
        zpath = os.path.join(self.tmp.name,
                             "thanh-hai-learn-ai-2d-studio.zip")
        plugin_zip(zpath)
        res = skill_import.apply_import(zpath, skills_dir=self.store)
        self.assertEqual(len(res["installed"]), 5)
        self.assertTrue(os.path.isfile(os.path.join(
            self.store, "make-2d-video", "references",
            "style-bible.md")))


class TestKnowledgeUI(unittest.TestCase):
    def test_new_ids_and_ops_present(self):
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "static", "index.html"),
                  encoding="utf-8") as fh:
            html = fh.read()
        for element_id in (
                "knowledgeSkillTable", "knowledgeSearch",
                "btnKnowledgeSearch", "btnKnowledgeSyncClaude",
                "knowledgeSyncResult", "knowledgeDetail",
                "knowledgeImportDetails", "knowledgeImportPath",
                "knowledgeImportOverwrite", "btnKnowledgeImportPreview",
                "knowledgeImportPreview", "btnKnowledgeImportInstall",
                "knowledgeImportResult"):
            self.assertIn('id="%s"' % element_id, html, element_id)
        self.assertIn("Nhập skill từ file (.md / .zip)", html)
        with open(os.path.join(os.path.dirname(__file__), "..",
                               "static", "app.js"), encoding="utf-8") as fh:
            js = fh.read()
        for token in ("skills_import_plan", "skills_import",
                      "skills_sync_claude", "renderMarkdown",
                      "data-skill-row", "data-import-skill"):
            self.assertIn(token, js, token)
        # Skill detail no longer prints raw JSON (lesson fallback may).
        self.assertNotIn("Skill ${id}: ${JSON.stringify", js)


if __name__ == "__main__":
    unittest.main()
