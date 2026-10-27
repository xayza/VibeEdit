"""Phase 0 data safety: duplicate uploads, backup retention, live MCP count.

Run from windows/: python3 -m unittest discover -s tests -v
Temp test data only (tempfile); no user project or media is touched.
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vibeedit_core.project import (
    BACKUP_BASENAME, BACKUP_DIRNAME, new_project, prune_backups,
    save_project, unique_media_name, write_backup)
from vibeedit_core.server import State


def _temp_project():
    folder = tempfile.mkdtemp(prefix="vibeedit-phase0-")
    path = os.path.join(folder, "project.vibeedit.json")
    save_project(new_project("Phase0"), path)
    return folder, path


class TestUniqueMediaName(unittest.TestCase):
    def test_first_name_unchanged_and_second_gets_suffix(self):
        media_dir = tempfile.mkdtemp(prefix="vibeedit-media-")
        try:
            self.assertEqual(unique_media_name(media_dir, "clip.mp4"),
                             "clip.mp4")
            open(os.path.join(media_dir, "clip.mp4"), "wb").close()
            self.assertEqual(unique_media_name(media_dir, "clip.mp4"),
                             "clip-2.mp4")
            open(os.path.join(media_dir, "clip-2.mp4"), "wb").close()
            self.assertEqual(unique_media_name(media_dir, "clip.mp4"),
                             "clip-3.mp4")
        finally:
            shutil.rmtree(media_dir, ignore_errors=True)

    def test_no_extension_and_path_traversal_stripped(self):
        media_dir = tempfile.mkdtemp(prefix="vibeedit-media-")
        try:
            self.assertEqual(unique_media_name(media_dir, "audio"),
                             "audio")
            open(os.path.join(media_dir, "audio"), "wb").close()
            self.assertEqual(unique_media_name(media_dir, "audio"),
                             "audio-2")
            self.assertEqual(unique_media_name(media_dir, "../evil.mp4"),
                             "evil.mp4")
        finally:
            shutil.rmtree(media_dir, ignore_errors=True)

    def test_upload_twice_keeps_both_files_and_first_clip_points_old(self):
        # Mirrors the server upload handler: same original name twice,
        # stored under different names, first clip still references
        # the first file's content.
        folder, path = _temp_project()
        try:
            from vibeedit_core.project import Project, load_project
            media_dir = os.path.join(folder, "media")
            os.makedirs(media_dir, exist_ok=True)
            first = unique_media_name(media_dir, "clip.mp4")
            with open(os.path.join(media_dir, first), "wb") as fh:
                fh.write(b"FIRST")
            second = unique_media_name(media_dir, "clip.mp4")
            with open(os.path.join(media_dir, second), "wb") as fh:
                fh.write(b"SECOND")
            self.assertNotEqual(first, second)
            proj = Project(load_project(path), folder)
            m1 = proj.add_media(f"media/{first}", kind="video")
            m2 = proj.add_media(f"media/{second}", kind="video")
            clip = proj.add_clip(m1["id"], "v1", 0, 0, 30)
            self.assertEqual(proj.media(clip["media"])["path"],
                             f"media/{first}")
            with open(os.path.join(media_dir, first), "rb") as fh:
                self.assertEqual(fh.read(), b"FIRST")
            with open(os.path.join(media_dir, second), "rb") as fh:
                self.assertEqual(fh.read(), b"SECOND")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestBackupRetention(unittest.TestCase):
    def test_backup_writes_bak_and_timestamped_copy(self):
        folder, path = _temp_project()
        try:
            out = write_backup(path)
            self.assertIsNotNone(out)
            self.assertTrue(os.path.isfile(
                os.path.join(folder, BACKUP_BASENAME)))
            self.assertTrue(os.path.isfile(out["copy"]))
            with open(out["copy"], encoding="utf-8") as fh:
                self.assertEqual(json.load(fh)["name"], "Phase0")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_no_saved_file_means_no_backup(self):
        folder = tempfile.mkdtemp(prefix="vibeedit-phase0-")
        try:
            self.assertIsNone(write_backup(
                os.path.join(folder, "project.vibeedit.json")))
            self.assertFalse(os.path.exists(
                os.path.join(folder, BACKUP_DIRNAME)))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_prune_keeps_five_newest_plus_one_per_day(self):
        folder, path = _temp_project()
        try:
            backup_dir = os.path.join(folder, BACKUP_DIRNAME)
            os.makedirs(backup_dir, exist_ok=True)
            now = time.time()
            # 12 backups, one per day over the last 12 days (distinct
            # names, newest first). Retention keeps the 5 newest plus
            # one per day for the last 7 days: the 7 newest survive
            # (5 newest are inside the 7 daily ones), the 5 oldest go.
            for i in range(12):
                name = f"project-202601{i + 1:02d}-120000.json"
                target = os.path.join(backup_dir, name)
                with open(target, "w") as fh:
                    fh.write("{}")
                os.utime(target, (now - i * 86400, now - i * 86400))
            deleted = prune_backups(folder)
            remaining = os.listdir(backup_dir)
            self.assertEqual(len(remaining), 7)
            self.assertEqual(len(deleted), 5)
            self.assertIn("project-20260112-120000.json", deleted)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_autosave_creates_no_backup_but_first_save_does(self):
        folder = tempfile.mkdtemp(prefix="vibeedit-phase0-")
        try:
            state = State(folder)
            # State.save() is the autosave path; the FIRST call after
            # open creates exactly one backup, later calls none.
            state.save()
            backups = os.path.join(folder, BACKUP_DIRNAME)
            self.assertTrue(os.path.isdir(backups))
            self.assertEqual(len(os.listdir(backups)), 1)
            state.save()
            state.save()
            self.assertEqual(len(os.listdir(backups)), 1)
            self.assertTrue(os.path.isfile(
                os.path.join(folder, BACKUP_BASENAME)))
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_destructive_op_creates_backup_before_mutation(self):
        folder = tempfile.mkdtemp(prefix="vibeedit-phase0-")
        try:
            state = State(folder)
            state.save()  # consumes the first-save backup
            before = set(os.listdir(os.path.join(folder, BACKUP_DIRNAME)))
            # A clip must exist to delete: add media + clip, save,
            # then delete (destructive) and check a NEW backup holds
            # the pre-delete project (clip still present in it).
            medium = state.project.add_media("media/x.mp4", kind="video")
            clip = state.project.add_clip(medium["id"], "v1", 0, 0, 30)
            state.save()
            state.apply({"op": "delete", "item": clip["id"]})
            after = set(os.listdir(os.path.join(folder, BACKUP_DIRNAME)))
            new = after - before
            self.assertTrue(new, "delete must create a backup")
            newest = max(
                (os.path.join(folder, BACKUP_DIRNAME, n) for n in new),
                key=os.path.getmtime)
            with open(newest, encoding="utf-8") as fh:
                backed = json.load(fh)
            ids = [i["id"] for t in backed["tracks"] for i in t["items"]]
            self.assertIn(clip["id"], ids)
            # The live project no longer has the clip.
            live_ids = [i["id"] for t in state.project.data["tracks"]
                        for i in t["items"]]
            self.assertNotIn(clip["id"], live_ids)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_non_destructive_op_creates_no_extra_backup(self):
        folder = tempfile.mkdtemp(prefix="vibeedit-phase0-")
        try:
            state = State(folder)
            state.save()  # first-save backup
            count = len(os.listdir(os.path.join(folder, BACKUP_DIRNAME)))
            # Use a real non-destructive op: add a text item.
            state.apply({"op": "add_text", "track": "t1", "text": "hi",
                         "at": 0, "dur": 30})
            self.assertEqual(
                len(os.listdir(os.path.join(folder, BACKUP_DIRNAME))),
                count)
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestMultipartParser(unittest.TestCase):
    def test_filename_survives_content_type_header(self):
        # What a real browser sends: a Content-Type line after the
        # Content-Disposition line. The old parser collapsed the
        # filename to just the extension ('mp4').
        from vibeedit_core.server import _parse_multipart
        body = (b"--B\r\nContent-Disposition: form-data; name=\"file\"; "
                b"filename=\"clip.mp4\"\r\nContent-Type: video/mp4\r\n\r\n"
                b"DATA\r\n--B--\r\n")
        parts = _parse_multipart(body, b"B")
        self.assertEqual(parts["file"][0], "clip.mp4")
        self.assertEqual(parts["file"][1], b"DATA")

    def test_unicode_filename_kept(self):
        from vibeedit_core.server import _parse_multipart
        header = ("--B\r\nContent-Disposition: form-data; name=\"file\"; "
                  "filename=\"video của tôi.mp4\"\r\n\r\n")
        body = header.encode("utf-8") + b"DATA\r\n--B--\r\n"
        parts = _parse_multipart(body, b"B")
        self.assertEqual(parts["file"][0], "video của tôi.mp4")


class TestMcpBackup(unittest.TestCase):
    def test_destructive_mcp_tool_backs_up(self):
        from vibeedit_core.mcp import MCPServer
        folder, path = _temp_project()
        try:
            server = MCPServer(folder)
            server.call("vibeedit_project_save", {})
            backup_dir = os.path.join(folder, BACKUP_DIRNAME)
            before = (set(os.listdir(backup_dir))
                      if os.path.isdir(backup_dir) else set())
            track = server.call("vibeedit_track_add",
                                {"kind": "video", "role": "",
                                 "name": "Extra"})
            track_id = track["track"]["id"]
            server.call("vibeedit_track_remove", {"track": track_id})
            after = set(os.listdir(backup_dir))
            self.assertTrue(after - before,
                            "track_remove must create a backup")
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class TestNoHardcodedMcpCountInUi(unittest.TestCase):
    def test_static_files_carry_no_literal_tool_count(self):
        import re
        static_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static")
        for name in ("app.js", "index.html"):
            with open(os.path.join(static_dir, name),
                      encoding="utf-8") as fh:
                text = fh.read()
            self.assertIsNone(
                re.search(r"\b\d+ (MCP )?tools\b", text),
                f"{name} still hardcodes a tool count")
        with open(os.path.join(static_dir, "app.js"),
                  encoding="utf-8") as fh:
            app_js = fh.read()
        self.assertIn('/api/mcp-tools', app_js)
        self.assertIn('External agent (MCP) — ${data.count} tools', app_js)


if __name__ == "__main__":
    unittest.main()
