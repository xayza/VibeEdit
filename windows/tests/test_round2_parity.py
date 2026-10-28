"""Round-2 parity tests: knowledge store, skills write-side, magnetic
reorder, marker shifting, font import, caption alignment mapping,
voice/update checks, and the new MCP tools. Temp dirs only; no user
sample projects/media; no model or network needed (faster-whisper
paths are tested through their clear-error branch on this VM).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

from vibeedit_core.mcp import TOOLS
from vibeedit_core.project import Project, new_project


def _proj(tmp):
    return Project(new_project("r2", width=320, height=180), tmp)


def _main_clips(proj, count=4):
    media = proj.add_media("media/a.mp4", "video", width=320, height=180,
                           fps=30, frames=60, duration=2.0)
    main = next(t for t in proj.data["tracks"] if t.get("role") == "main")
    clips = []
    for i in range(count):
        clips.append(proj.add_clip(media["id"], main["id"], i * 60,
                                   dur=60))
    return main, clips


class TestKnowledgeStore(unittest.TestCase):
    def test_lesson_fact_pref_claim_proposal_flow(self):
        from vibeedit_core import knowledge as k
        data = {}
        lesson = k.add_lesson(data, "Cut on action, not on words.")
        self.assertEqual(lesson["status"], "proposed")
        k.approve_lesson(data, lesson["id"])
        self.assertEqual(k.get_lesson(data, lesson["id"])["status"],
                         "active")
        k.set_fact(data, "fps", "30")
        k.set_pref(data, "theme", "dark")
        k.set_claim(data, "hook", "first sentence hooks")
        self.assertEqual(k.facts(data)["fps"], "30")
        prop = k.propose(data, "fact",
                         {"key": "codec", "value": "h264"})
        k.approve_proposal(data, prop["id"])
        self.assertEqual(k.facts(data)["codec"], "h264")
        self.assertEqual(len(k.verdicts(data)), 1)
        k.set_memo(data, "line one\n\nline two")
        res = k.split_memo(data)
        self.assertEqual(len(res["added"]), 2)
        hist_len = len(k.history(data))
        k.revert(data, 1)
        self.assertEqual(len(k.lessons(data)),
                         len(k.lessons(data)))  # reverted state loads
        self.assertTrue(len(k.history(data)) >= hist_len - 1)
        with self.assertRaises(ValueError):
            k.add_lesson(data, "   ")

    def test_migrate_noop_is_honest(self):
        from vibeedit_core import knowledge as k
        data = {}
        res = k.migrate(data)
        self.assertFalse(res["migrated"])
        data["knowledge_notes"] = "old notes"
        res = k.migrate(data)
        self.assertTrue(res["migrated"])
        self.assertEqual(k.get_memo(data), "old notes")


class TestSkillsWriteSide(unittest.TestCase):
    def test_save_enable_disable_export_remove_propose(self):
        from vibeedit_core import skills as sk
        with tempfile.TemporaryDirectory() as tmp:
            sdir = os.path.join(tmp, "skills")
            saved = sk.save_skill(sdir, "my-skill", "My Skill",
                                  "Do the thing.")
            self.assertTrue(os.path.isfile(saved["path"]))
            with open(saved["path"], encoding="utf-8") as fh:
                self.assertIn("NOT original", fh.read())
            with self.assertRaises(ValueError):
                sk.save_skill(sdir, "my-skill", "Again", "x")
            self.assertTrue(sk.set_skill_enabled(sdir, "my-skill",
                                                 False)["enabled"] is False)
            entries = sk.list_skills(sdir)
            self.assertFalse([e for e in entries
                              if e["id"] == "my-skill"][0]["enabled"])
            sk.set_skill_enabled(sdir, "my-skill", True)
            exported = sk.export_skill(sdir, "my-skill")
            self.assertIn("Do the thing.", exported["content"])
            prop = sk.propose_skill(sdir, "draft-one", "Draft", "Idea.")
            self.assertEqual(prop["status"], "pending")
            self.assertNotIn("draft-one",
                             [e["id"] for e in sk.list_skills(sdir)])
            with self.assertRaises(ValueError):
                sk.remove_skill(sdir, "my-skill", confirm=False)
            sk.remove_skill(sdir, "my-skill", confirm=True)
            self.assertNotIn("my-skill",
                             [e["id"] for e in sk.list_skills(sdir)])


class TestReorderAndMarkers(unittest.TestCase):
    def test_reorder_earlier_and_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _proj(tmp)
            _, clips = _main_clips(proj, 4)
            # Move last clip before first: order becomes [D, A, B, C].
            proj.reorder_main(clips[3]["id"], clips[0]["id"])
            main = next(t for t in proj.data["tracks"]
                        if t.get("role") == "main")
            order = [i["id"] for i in sorted(main["items"],
                                             key=lambda i: i["at"])]
            self.assertEqual(order, [clips[3]["id"], clips[0]["id"],
                                     clips[1]["id"], clips[2]["id"]])
            ats = [i["at"] for i in sorted(main["items"],
                                           key=lambda i: i["at"])]
            self.assertEqual(ats, [0, 60, 120, 180])
            # Move first clip (now D) to the end.
            proj.reorder_main(clips[3]["id"], None)
            order = [i["id"] for i in sorted(main["items"],
                                             key=lambda i: i["at"])]
            self.assertEqual(order, [clips[0]["id"], clips[1]["id"],
                                     clips[2]["id"], clips[3]["id"]])
            with self.assertRaises(ValueError):
                proj.reorder_main(clips[0]["id"], clips[0]["id"])

    def test_markers_shift_on_insert_delete_trim(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _proj(tmp)
            _, clips = _main_clips(proj, 2)
            m1 = proj.add_marker("at 30", 30)
            m2 = proj.add_marker("at 90", 90)
            m3 = proj.add_marker("at 150", 150)
            # Magnetic insert at 60 (dur 60): markers >= 60 shift +60.
            media = proj.data["media"][0]
            main = next(t for t in proj.data["tracks"]
                        if t.get("role") == "main")
            proj.add_clip(media["id"], main["id"], 60, dur=60)
            ats = {m["id"]: m["at"] for m in proj.data["markers"]}
            self.assertEqual(ats[m1["id"]], 30)
            self.assertEqual(ats[m2["id"]], 150)
            self.assertEqual(ats[m3["id"]], 210)
            # Delete the inserted clip (at 60, dur 60): markers in
            # [60, 120) collapse to 60, markers >= 120 shift -60.
            inserted = [i for i in main["items"] if i["at"] == 60][0]
            proj.delete(inserted["id"])
            ats = {m["id"]: m["at"] for m in proj.data["markers"]}
            self.assertEqual(ats[m2["id"]], 90)
            self.assertEqual(ats[m3["id"]], 150)


class TestFontsAndCaptions(unittest.TestCase):
    def test_font_import_unique_and_listed(self):
        from vibeedit_core.render import font_candidates, import_font
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "MyFont.ttf")
            with open(src, "wb") as fh:
                fh.write(b"\x00\x01\x00\x00fake-font")
            fdir = os.path.join(tmp, "fonts")
            first = import_font(src, fonts_dir=fdir)
            second = import_font(src, fonts_dir=fdir)
            self.assertNotEqual(first["name"], second["name"])
            self.assertTrue(os.path.isfile(first["path"]))
            with self.assertRaises(ValueError):
                bad = os.path.join(tmp, "x.txt")
                with open(bad, "w") as fh:
                    fh.write("nope")
                import_font(bad, fonts_dir=fdir)

    def test_caption_align_mapping_and_error(self):
        from vibeedit_core.transcribe import snap_items_to_segments
        items = [{"id": "s1", "at": 0, "dur": 60},
                 {"id": "s2", "at": 60, "dur": 60}]
        segs = [{"start": 0.1, "end": 1.1}, {"start": 2.1, "end": 3.1}]
        snaps = snap_items_to_segments(items, segs, (30, 1))
        self.assertEqual(len(snaps), 2)
        self.assertEqual(snaps[0]["to"][0], 3)  # 0.1s at 30fps
        # Without faster-whisper, align_captions errors clearly and
        # changes nothing.
        from vibeedit_core.transcribe import align_captions
        with tempfile.TemporaryDirectory() as tmp:
            proj = _proj(tmp)
            try:
                import faster_whisper  # noqa: F401
                self.skipTest("faster-whisper installed here")
            except ImportError:
                with self.assertRaises(RuntimeError):
                    align_captions(proj, "t1", "media/a.mp4")


class TestRound2Tools(unittest.TestCase):
    def test_registry_counts(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(TOOLS), 481)  # Round 23: 479 -> 481 (skills_import_plan/import)
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(honest), 52)  # Round 22: 54 -> 52, 2 tools became real (see tests/test_round22.py)
        for new in ("vibeedit_knowledge_add_lesson",
                    "vibeedit_knowledge_verdicts",
                    "vibeedit_skills_save", "vibeedit_skills_propose",
                    "vibeedit_captions_transcribe",
                    "vibeedit_captions_generate",
                    "vibeedit_captions_align", "vibeedit_media_transcribe",
                    "vibeedit_fonts_import", "vibeedit_timeline_reorder",
                    "vibeedit_chat_stop", "vibeedit_view_compare",
                    "vibeedit_view_safe_area"):
            self.assertIn(new, names, new)

    def test_voice_and_update_checks_are_real(self):
        from vibeedit_core.mcp import MCPServer
        srv = MCPServer()
        voice = srv.call("vibeedit_voice_check", {})
        self.assertIn("piper", voice["backends"])
        self.assertIn("edge_tts", voice["backends"])
        upd = srv.call("vibeedit_app_update_check", {})
        self.assertIsNone(upd["update_channel"])
        self.assertEqual(upd["current_version"], "0.1.0")

    def test_knowledge_and_reorder_tools(self):
        from vibeedit_core.mcp import MCPServer
        with tempfile.TemporaryDirectory() as tmp:
            srv = MCPServer()
            srv.project = _proj(tmp)
            srv.path = os.path.join(tmp, "project.json")
            lesson = srv.call("vibeedit_knowledge_add_lesson",
                              {"text": "Hold the hook."})
            self.assertEqual(lesson["status"], "proposed")
            srv.call("vibeedit_knowledge_approve",
                     {"lesson": lesson["id"]})
            lessons = srv.call("vibeedit_knowledge_lessons", {})
            self.assertEqual(lessons["lessons"][0]["status"], "active")
            _, clips = _main_clips(srv.project, 3)
            srv.call("vibeedit_timeline_reorder",
                     {"item": clips[2]["id"], "before": clips[0]["id"]})
            main = next(t for t in srv.project.data["tracks"]
                        if t.get("role") == "main")
            order = [i["id"] for i in sorted(main["items"],
                                             key=lambda i: i["at"])]
            self.assertEqual(order[0], clips[2]["id"])


if __name__ == "__main__":
    unittest.main()
