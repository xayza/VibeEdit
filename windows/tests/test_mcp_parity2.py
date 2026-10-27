"""Phase B1 MCP parity tests: real wrappers + honest check-and-error
tools, plus the registry test. Every wrapper test changes or reads
real project data; every honest test asserts a structured error and
never a success with invented data. Temp data only.

Run from windows/: python3 -m unittest discover -s tests -v
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.mcp import TOOLS, MCPServer, handle  # noqa: E402
from vibeedit_core.project import Project, new_project, save_project  # noqa: E402
from vibeedit_core.render import probe_media  # noqa: E402


def make_server(tmp):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=320x180:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", os.path.join(tmp, "c1.mp4")],
        capture_output=True, check=True)
    proj = Project(new_project("b1", width=320, height=180,
                               fps=(30, 1)), tmp)
    medium = proj.add_media(
        "c1.mp4", kind="video",
        **probe_media(os.path.join(tmp, "c1.mp4")))
    clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
    text = proj.add_text("t1", "hello world", 0, 30)
    save_project(proj.data, os.path.join(tmp, "project.vibeedit.json"))
    return MCPServer(tmp), medium, clip, text


class B1Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server, self.medium, self.clip, self.text = make_server(
            self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestTimelineWrappers(B1Case):
    def test_split_move_delete_cut_range(self):
        s = self.server
        right = s.call("vibeedit_timeline_split",
                       {"item": self.clip["id"], "atFrame": 30})
        self.assertEqual(right["at"], 30)
        s.call("vibeedit_timeline_move",
               {"item": right["id"], "track": "v2", "at": 0})
        # Total counts every track's items, including the text item.
        self.assertEqual(s.call("vibeedit_timeline_clip_count", {})["total"], 3)
        s.call("vibeedit_timeline_delete", {"item": right["id"]})
        self.assertEqual(s.call("vibeedit_timeline_clip_count", {})["total"], 2)
        # Cut 10..20 out of the remaining 0..30 clip. delete() now
        # ripples (parallel magnetic change), so the 20..30 segment
        # shifts left to 10..20 instead of leaving a gap.
        out = s.call("vibeedit_timeline_cut_range",
                     {"start": 10, "end": 20})
        # One middle segment per track that overlaps the range
        # (the v1 clip and the t1 text item).
        self.assertEqual(len(out["deleted"]), 2)
        v1 = [i for i in s.call("vibeedit_clip_list", {"track": "v1"})["items"]]
        self.assertEqual([(i["at"], i["dur"]) for i in v1],
                         [(0, 10), (10, 10)])

    def test_close_gap_alias_select_zoom_snap(self):
        s = self.server
        s.call("vibeedit_timeline_split",
               {"item": self.clip["id"], "atFrame": 30})
        s.call("vibeedit_timeline_delete",
               {"item": s.call("vibeedit_clip_list", {})["items"][0]["id"]})
        # Remaining clip starts at 30: close_gap shifts it to 0.
        s.call("vibeedit_timeline_close_gap", {})
        items = s.call("vibeedit_clip_list", {"track": "v1"})["items"]
        self.assertEqual(items[0]["at"], 0)
        self.assertEqual(len(s.call("vibeedit_timeline_select_all", {})["selection"]), 2)
        self.assertEqual(s.call("vibeedit_timeline_deselect", {})["selection"], [])
        s.project.data["beatGrid"] = {"source": self.medium["id"],
                                      "beats": [1.0], "method": "test"}
        self.assertEqual(s.call("vibeedit_timeline_snap", {"frame": 15})["snapped"], 30)
        self.assertGreater(s.call("vibeedit_timeline_zoom_in", {})["zoom_px_per_s"], 50.0)
        # After close_gap the timeline is 30 frames = 1s, so fit = 1200.
        self.assertEqual(s.call("vibeedit_timeline_zoom_fit", {})["zoom_px_per_s"], 1200.0)
        self.assertLess(s.call("vibeedit_timeline_zoom_out", {})["zoom_px_per_s"], 1200.0)

    def test_move_items_changes_waveforms_sheet_lift(self):
        s = self.server
        right = s.call("vibeedit_timeline_split",
                       {"item": self.clip["id"], "atFrame": 30})
        moved = s.call("vibeedit_timeline_move_items",
                       {"items": [{"item": right["id"], "track": "v2", "at": 0}]})
        self.assertEqual(moved["moved"][0]["track"] if "track" in moved["moved"][0] else "v2", "v2")
        changes = s.call("vibeedit_timeline_changes", {})
        self.assertIn("can_undo", changes)
        waves = s.call("vibeedit_timeline_refresh_waveforms", {"buckets": 8})
        self.assertEqual(waves["waveforms"][self.medium["id"]], 8)
        self.assertIn("hello", s.call("vibeedit_timeline_sheet", {})["timeline"])
        lifted = s.call("vibeedit_timeline_lift", {"item": self.clip["id"]})
        self.assertTrue(lifted["clipboard"])
        pasted = s.call("vibeedit_clip_paste", {"track": "v1", "at": 0})
        self.assertEqual(pasted["at"], 0)


class TestClipSourcePlayheadLayers(B1Case):
    def test_clip_wrappers(self):
        s = self.server
        right = s.call("vibeedit_clip_cut",
                       {"item": self.clip["id"], "atFrame": 30})
        self.assertEqual(right["at"], 30)
        muted = s.call("vibeedit_clip_mute", {"item": self.clip["id"]})
        self.assertEqual(muted["volume"], -60.0)
        self.assertTrue(muted["muted"])
        self.assertEqual(s.call("vibeedit_clip_speed_up", {"item": self.clip["id"]})["speed"], 2.0)
        self.assertEqual(s.call("vibeedit_clip_speed_down", {"item": self.clip["id"]})["speed"], 1.0)
        self.assertEqual(s.call("vibeedit_clip_slow_down", {"item": self.clip["id"]})["speed"], 0.5)
        self.assertEqual(s.call("vibeedit_clip_speed_reset", {"item": self.clip["id"]})["speed"], 1.0)
        pasted = s.call("vibeedit_clip_paste",
                        {"item": self.clip["id"], "track": "v2", "at": 0})
        self.assertEqual(pasted["at"], 0)
        trans = s.call("vibeedit_clip_transition",
                       {"from": self.clip["id"], "to": right["id"],
                        "kind": "crossfade", "duration": 0.5})
        self.assertEqual(trans["kind"], "crossfade")
        kf = s.call("vibeedit_clip_keyframe",
                    {"item": self.clip["id"], "at": 0.5,
                     "property": "scale", "value": 1.5})
        self.assertTrue(any(k.get("scale") == 1.5 for k in kf["keyframes"]))
        # Unlink: link the clip to an audio item the way the
        # linked-audio system stores it, then unlink both sides.
        audio = s.call("vibeedit_media_place",
                       {"media": self.medium["id"], "track": "a1", "at": 0})
        _, clip_item = s.project.item(self.clip["id"])
        _, audio_item = s.project.item(audio["id"])
        clip_item["linked_audio"] = [audio["id"]]
        audio_item["linked_video"] = self.clip["id"]
        out = s.call("vibeedit_clip_unlink_audio", {"item": self.clip["id"]})
        self.assertEqual(out["unlinked"], [audio["id"]])
        self.assertNotIn("linked_audio", clip_item)
        self.assertNotIn("linked_video", audio_item)
        with self.assertRaises(ValueError):
            s.call("vibeedit_clip_unlink_audio", {"item": self.clip["id"]})

    def test_source_playhead_layers(self):
        s = self.server
        self.assertEqual(s.call("vibeedit_source_mark_in", {"frame": 5})["source_marks"]["in"], 5)
        self.assertEqual(s.call("vibeedit_source_mark_out", {"frame": 25})["source_marks"]["out"], 25)
        self.assertEqual(s.call("vibeedit_source_next_frame", {})["source_frame"], 1)
        self.assertEqual(s.call("vibeedit_source_previous_frame", {})["source_frame"], 0)
        self.assertEqual(s.call("vibeedit_source_show", {})["source_marks"]["in"], 5)
        self.assertEqual(s.call("vibeedit_source_close", {})["source_marks"], {})
        self.assertEqual(s.call("vibeedit_playhead_forward_second", {})["frame"], 30)
        self.assertEqual(s.call("vibeedit_playhead_next_frame", {})["frame"], 31)
        self.assertEqual(s.call("vibeedit_playhead_back_second", {})["frame"], 1)
        self.assertEqual(s.call("vibeedit_playhead_previous_frame", {})["frame"], 0)
        vid = s.call("vibeedit_layer_add_video", {"name": "ExtraV"})
        aud = s.call("vibeedit_layer_add_audio", {"name": "ExtraA"})
        txt = s.call("vibeedit_layer_add_text", {"name": "ExtraT"})
        adj = s.call("vibeedit_layer_add_adjustment", {"at": 0, "dur": 30, "preset": "vivid"})
        self.assertIn("id", adj)
        up = s.call("vibeedit_layer_up", {"track": aud["track"]["id"]})
        self.assertIn(aud["track"]["id"], up["order"])
        down = s.call("vibeedit_layer_down", {"track": aud["track"]["id"]})
        self.assertIn(aud["track"]["id"], down["order"])
        s.call("vibeedit_layer_delete", {"track": txt["track"]["id"]})
        added = s.call("vibeedit_layers_add", {"kind": "audio", "name": "L"})
        renamed = s.call("vibeedit_layers_set",
                         {"track": added["track"]["id"], "name": "Renamed"})
        self.assertEqual(renamed["name"], "Renamed")
        s.call("vibeedit_layer_delete", {"track": vid["track"]["id"]})


class TestCaptionsText(B1Case):
    def test_captions_and_line_style(self):
        s = self.server
        srt = s.call("vibeedit_captions_export", {"track": "t1"})["srt"]
        self.assertIn("hello world", srt)
        imported = s.call("vibeedit_captions_import",
                          {"track": "t1", "srt": "1\n00:00:02,000 --> 00:00:03,000\nsecond line\n"})
        self.assertEqual(imported["imported"], 1)
        found = s.call("vibeedit_captions_find", {"query": "second"})["items"]
        self.assertEqual(len(found), 1)
        changed = s.call("vibeedit_captions_replace",
                         {"query": "second", "replacement": "third"})
        self.assertEqual(len(changed["changed"]), 1)
        styled = s.call("vibeedit_captions_style",
                        {"item": self.text["id"], "preset": "title"})
        # TEXT_PRESETS expand into size/position, not a "preset" key.
        self.assertEqual(styled["textStyle"]["size"], 0.12)
        words = s.call("vibeedit_captions_words", {})["words"]
        self.assertTrue(any(w["word"] == "hello" for w in words))
        groups = s.call("vibeedit_captions_group", {})["groups"]
        self.assertIn("t1", groups)
        line = s.call("vibeedit_text_line_style",
                      {"item": self.text["id"], "line_style": "bold"})
        self.assertEqual(line["textStyle"]["lineStyle"], "bold")


class TestProjectExportPluginsJobs(B1Case):
    def test_project_wrappers(self):
        s = self.server
        self.assertEqual(s.call("vibeedit_project_folder", {})["folder"], self.tmp)
        history = s.call("vibeedit_project_history", {})
        self.assertEqual(history["rev"], s.project.rev)
        self.assertIn("hello", str(s.call("vibeedit_project_data", {})["project"]))
        s.call("vibeedit_project_set_data", {"key": "name", "value": "renamed-b1"})
        self.assertEqual(s.project.data["name"], "renamed-b1")
        credits = s.call("vibeedit_project_credits", {})
        self.assertEqual(credits["name"], "renamed-b1")
        with self.assertRaises(ValueError):
            s.call("vibeedit_project_set_data", {"key": "tracks", "value": []})
        # Recents: sibling .recent.json in the parent of the project.
        import json
        recents_path = os.path.join(os.path.dirname(self.tmp), ".recent.json")
        try:
            with open(recents_path, "w", encoding="utf-8") as fh:
                json.dump([self.tmp], fh)
            self.assertEqual(s.call("vibeedit_project_recents", {})["recent"], [self.tmp])
            self.assertEqual(s.call("vibeedit_project_show_recents", {})["recent"], [self.tmp])
        finally:
            if os.path.isfile(recents_path):
                os.remove(recents_path)
        derived = s.call("vibeedit_project_derive",
                          {"name": "b1-derived-" + os.path.basename(self.tmp)})
        self.assertTrue(os.path.isfile(derived["path"]))
        shutil.rmtree(os.path.dirname(derived["path"]), ignore_errors=True)
        imported = s.call("vibeedit_project_import_media",
                          {"path": os.path.join(self.tmp, "c1.mp4")})
        self.assertEqual(imported["kind"], "video")
        s.call("vibeedit_project_close", {})
        with self.assertRaises(RuntimeError):
            s.call("vibeedit_project_folder", {})

    def test_project_new(self):
        s = MCPServer(None)
        out = s.call("vibeedit_project_new",
                     {"directory": self.tmp, "name": "fresh-b1"})
        self.assertTrue(os.path.isfile(out["path"]))
        self.assertEqual(s.project.data["name"], "fresh-b1")

    def test_export_plugins_jobs_system(self):
        s = self.server
        chapters = s.call("vibeedit_export_chapters", {})
        self.assertEqual(chapters["chapters"], [])
        s.call("vibeedit_markers_add", {"text": "ch1", "at": 0})
        self.assertEqual(len(s.call("vibeedit_export_chapters", {})["chapters"]), 1)
        cover = s.call("vibeedit_export_cover", {})
        self.assertTrue(cover["cover"].endswith(".png"))
        self.assertIn("last_export", s.call("vibeedit_export_history", {}))
        with self.assertRaises(ValueError):
            s.call("vibeedit_export_link", {})
        with self.assertRaises(ValueError):
            s.call("vibeedit_export_open_output", {})
        with self.assertRaises(ValueError):
            s.call("vibeedit_export_reveal_output", {})
        self.assertTrue(s.call("vibeedit_export_dismiss_notice", {})["dismissed"])
        plugins = s.call("vibeedit_plugins_list", {})
        self.assertIn("plugins", plugins)
        self.assertEqual(s.call("vibeedit_plugins_reload", {})["plugins"], plugins["plugins"])
        validated = s.call("vibeedit_plugins_validate", {})
        self.assertIn("valid", validated)
        self.assertIn("plugins", s.call("vibeedit_plugins_hooks", {}))
        self.assertIn("plugins_dir", s.call("vibeedit_plugins_bundles", {}))
        self.assertIn("queued", s.call("vibeedit_jobs_status", {}))
        self.assertTrue(s.call("vibeedit_jobs_cancel", {})["cancelled"])
        self.assertIn("results", s.call("vibeedit_jobs_wait", {}))
        caps = s.call("vibeedit_capabilities_get", {})
        self.assertEqual(caps["capabilities"]["media.ocr"], "vision.text")
        schema = s.call("vibeedit_schema_get", {})
        self.assertEqual(schema["schema"], "vibeedit.project/1")
        version = s.call("vibeedit_app_version", {})
        self.assertEqual(version["version"], "0.1.0")
        storage = s.call("vibeedit_storage_get", {})
        self.assertIn("thumbs", storage)
        cleared = s.call("vibeedit_storage_clear", {})
        self.assertGreaterEqual(cleared["thumbs_removed"], 1)
        fonts = s.call("vibeedit_fonts_list", {})
        self.assertTrue(fonts["fonts"])
        cube = os.path.join(self.tmp, "test.cube")
        with open(cube, "w", encoding="utf-8") as fh:
            fh.write("LUT_3D_SIZE 2\n0 0 0\n1 1 1\n")
        lut = s.call("vibeedit_luts_import", {"path": cube})
        self.assertTrue(lut["lut"].endswith("test.cube"))
        self.assertTrue(s.call("vibeedit_batch_cancel", {})["cancelled"])
        self.assertIn("full", s.call("vibeedit_batch_presets", {})["presets"])
        with self.assertRaises(ValueError):
            s.call("vibeedit_batch_retry", {})


class TestReviewMediaAudio(B1Case):
    def test_review_gated_then_real(self):
        s = self.server
        for tool in ("vibeedit_review_compare", "vibeedit_review_coverage",
                     "vibeedit_review_layout", "vibeedit_review_measure",
                     "vibeedit_review_packet", "vibeedit_review_picture",
                     "vibeedit_review_shots", "vibeedit_review_sync",
                     "vibeedit_review_window"):
            with self.assertRaises(ValueError, msg=tool):
                s.call(tool, {})
        s.call("vibeedit_review_run", {})
        self.assertFalse(s.call("vibeedit_review_compare", {})["changed"])
        self.assertEqual(s.call("vibeedit_review_coverage", {})["media_used"], 1)
        self.assertIn("tracks", s.call("vibeedit_review_layout", {}))
        self.assertEqual(s.call("vibeedit_review_measure", {})["duration_frames"], 60)
        self.assertIn("review", s.call("vibeedit_review_packet", {}))
        self.assertEqual(len(s.call("vibeedit_review_picture", {})["main_clips"]), 1)
        self.assertEqual(len(s.call("vibeedit_review_shots", {})["shots"]), 1)
        self.assertIn("ducking", s.call("vibeedit_review_sync", {}))
        self.assertEqual(s.call("vibeedit_review_window", {})["end_frame"], 60)

    def test_media_audio_color_doctor_edl(self):
        s = self.server
        frame = s.call("vibeedit_media_frame", {"media": self.medium["id"]})
        self.assertTrue(frame["thumbnail"].endswith(".png"))
        frames = s.call("vibeedit_media_frames", {"media": self.medium["id"]})
        self.assertIn("metadata", frames)
        transcript = s.call("vibeedit_media_transcript", {})
        self.assertIn("hello world", transcript["text"])
        inv = s.call("vibeedit_media_inventory", {})["inventory"]
        self.assertEqual(inv[0]["clips_using"], 1)
        rng = s.call("vibeedit_media_resolve_range",
                     {"item": self.clip["id"]})
        self.assertEqual(rng["duration_frames"], 60)
        s.project.data["beatGrid"] = {"source": self.medium["id"],
                                      "beats": [0.5, 1.0], "method": "test"}
        self.assertEqual(s.call("vibeedit_beats_grid", {})["beats"], [0.5, 1.0])
        self.assertEqual(s.call("vibeedit_audio_beats", {})["beats"], [0.5, 1.0])
        energy = s.call("vibeedit_audio_energy", {"media": self.medium["id"]})
        self.assertGreater(energy["peak"], 0)
        loud = s.call("vibeedit_audio_loudness", {"media": self.medium["id"]})
        self.assertIn("input_i", loud["loudnorm"])
        measure = s.call("vibeedit_audio_measure", {"media": self.medium["id"]})
        self.assertIn("metadata", measure)
        mix = s.call("vibeedit_audio_mix_measure", {})
        self.assertIn("ducking", mix)
        with self.assertRaises(ValueError):
            s.call("vibeedit_color_measure", {"item": self.clip["id"]})
        s.call("vibeedit_clip_color_eq",
               {"item": self.clip["id"], "eq": {"brightness": 0.1}})
        colored = s.call("vibeedit_color_measure", {"item": self.clip["id"]})
        self.assertEqual(colored["eq"]["brightness"], 0.1)
        doctor = s.call("vibeedit_doctor_run", {})
        self.assertTrue(doctor["ok"])
        edl = os.path.join(self.tmp, "t.edl")
        with open(edl, "w", encoding="utf-8") as fh:
            fh.write("001  REEL1    V     C        00:00:00:00 00:00:01:00 00:00:00:00 00:00:01:00\n")
        parsed = s.call("vibeedit_edl_import", {"path": edl})
        self.assertEqual(parsed["events"][0]["source_out"], 30)
        placed = s.call("vibeedit_edl_import",
                        {"path": edl, "media_map": {"REEL1": self.medium["id"]},
                         "track": "v2"})
        self.assertEqual(len(placed["placed"]), 1)


class TestSelectsVariantsPlanWorkflowCheckpointRunLibrary(B1Case):
    def test_selects_variants_script_plan_workflow_checkpoint(self):
        s = self.server
        sel = s.call("vibeedit_selects_set",
                     {"name": "s1", "media": self.medium["id"],
                      "in": 0, "out": 30})["select"]
        self.assertEqual(len(s.call("vibeedit_selects_list", {})["selects"]), 1)
        placed = s.call("vibeedit_selects_place",
                        {"select": sel["id"], "track": "v2", "at": 0})
        self.assertEqual(placed["dur"], 30)
        s.call("vibeedit_variants_create", {"name": "v1"})
        self.assertEqual(len(s.call("vibeedit_variants_list", {})["variants"]), 1)
        diff = s.call("vibeedit_variants_diff", {"name": "v1"})
        self.assertEqual(diff["only_in_current"], [])
        script = s.call("vibeedit_script_check", {"text": "hello world and more"})
        self.assertEqual(script["coverage"], 1.0)
        check = s.call("vibeedit_plan_check",
                       {"ops": [{"op": "bogus"}, {"op": "delete", "item": "nope"}]})
        self.assertFalse(check["ok"])
        self.assertEqual(len(check["problems"]), 2)
        applied = s.call("vibeedit_plan_apply",
                         {"ops": [{"op": "set_text", "item": self.text["id"],
                                   "text": "via plan"}]})
        self.assertIn("results", applied)
        with self.assertRaises(ValueError):
            s.call("vibeedit_workflow_gates", {})
        s.call("vibeedit_workflow_set_gates", {"gates": {"require_review": True}})
        self.assertTrue(s.call("vibeedit_workflow_gates", {})["gates"]["require_review"])
        req = s.call("vibeedit_checkpoint_request", {})
        self.assertIsNotNone(req["checkpoint"])
        status = s.call("vibeedit_checkpoint_status", {})
        self.assertIsNotNone(status["backup"])
        self.assertIn("queued", s.call("vibeedit_run_status", {}))
        self.assertIn("batch_results", s.call("vibeedit_run_log", {}))
        self.assertIn("last_export", s.call("vibeedit_run_show", {}))
        self.assertTrue(s.call("vibeedit_run_stop", {})["cancelled"])

    def test_library_wrappers(self):
        s = self.server
        added = s.call("vibeedit_library_add",
                       {"item": self.clip["id"], "name": "libclip"})
        entry_id = added["entry"]["id"] if "entry" in added else added["id"]
        got = s.call("vibeedit_library_get", {"entry": entry_id})
        self.assertEqual(got["entry"]["id"], entry_id)
        self.assertEqual(s.call("vibeedit_library_stats", {})["count"], 1)
        self.assertEqual(s.call("vibeedit_library_preview", {"entry": entry_id})["entry"]["id"], entry_id)
        fav = s.call("vibeedit_library_favorite", {"entry": entry_id})
        self.assertTrue(fav["entry"]["favorite"])
        upd = s.call("vibeedit_library_update", {"entry": entry_id, "name": "renamed-lib"})
        self.assertEqual(upd["entry"]["name"], "renamed-lib")
        placed = s.call("vibeedit_library_apply",
                        {"entry": entry_id, "track": "v2", "at": 0})
        self.assertEqual(placed["at"], 0)
        moved = s.call("vibeedit_library_move", {"entry": entry_id, "to": 0})
        self.assertEqual(moved["order"], [entry_id])


HONEST_SAMPLE = [
    "vibeedit_agent_open", "vibeedit_agent_open_chat", "vibeedit_agent_open_claude",
    "vibeedit_agent_open_codex", "vibeedit_agent_open_shell", "vibeedit_agent_terminals",
    "vibeedit_agent_toggle_dock", "vibeedit_agent_ask", "vibeedit_agent_kit_check",
    "vibeedit_agent_kit_install", "vibeedit_agent_kit_update", "vibeedit_agent_kit_later",
    "vibeedit_agent_status", "vibeedit_agent_setup", "vibeedit_agent_setup_show",
    "vibeedit_agent_restart_tab", "vibeedit_agent_quick_edit", "vibeedit_agent_show_changes",
    "vibeedit_agent_dismiss_changes", "vibeedit_agent_undo_changes", "vibeedit_agent_detach",
    "vibeedit_agent_tools_install",
    "vibeedit_chat_send", "vibeedit_chat_command", "vibeedit_chat_commands",
    "vibeedit_chat_attach", "vibeedit_chat_detach", "vibeedit_chat_reset",
    "vibeedit_chat_status", "vibeedit_chat_transcript",
    "vibeedit_show_about", "vibeedit_show_commands", "vibeedit_show_shortcuts",
    "vibeedit_show_settings", "vibeedit_show_plugins", "vibeedit_show_review",
    "vibeedit_show_history", "vibeedit_show_sections", "vibeedit_show_batch",
    "vibeedit_show_export", "vibeedit_show_export_progress", "vibeedit_show_updates",
    "vibeedit_show_assets", "vibeedit_show_agent_kit", "vibeedit_show_doctor",
    "vibeedit_ui_action", "vibeedit_ui_dialog", "vibeedit_ui_view",
    "vibeedit_ui_select", "vibeedit_ui_seek", "vibeedit_ui_frame",
    "vibeedit_ui_frames", "vibeedit_ui_respond", "vibeedit_ui_actions",
    "vibeedit_playback_toggle", "vibeedit_playback_stop",
    "vibeedit_playback_shuttle_forward", "vibeedit_playback_shuttle_back",
    "vibeedit_view_fullscreen", "vibeedit_view_inspector_pane", "vibeedit_view_library_pane",
    "vibeedit_app_update", "vibeedit_app_update_later",
    "vibeedit_app_update_skip",
    "vibeedit_voice_clone_add", "vibeedit_voice_clone_list", "vibeedit_voice_clone_remove",
    # Round 3: generation (synthesize/speak/lines/use/fit/place) is
    # real now, so those names left this honest-error sample; only
    # cloning (no provider model) stays honest.
    "vibeedit_image_generate", "vibeedit_image_generate_list", "vibeedit_image_style",
    "vibeedit_image_disclose",
    "vibeedit_library_search", "vibeedit_library_generate", "vibeedit_library_brand_pose",
    "vibeedit_library_export_pack", "vibeedit_library_import_pack", "vibeedit_library_analyze",
    "vibeedit_media_ocr", "vibeedit_media_subjects", "vibeedit_media_describe",
    "vibeedit_media_description", "vibeedit_media_digest", "vibeedit_media_cuts",
    "vibeedit_media_sync", "vibeedit_media_speech_map", "vibeedit_media_strip",
    "vibeedit_media_proxy", "vibeedit_media_analysis", "vibeedit_media_analyze",
    "vibeedit_plugins_search",
    "vibeedit_plugins_setup", "vibeedit_plugins_set", "vibeedit_plugins_set_overlays",
    "vibeedit_plugins_overlays", "vibeedit_plugins_view", "vibeedit_plugins_view_event",
    "vibeedit_plugins_proposal", "vibeedit_plugins_replace",     "vibeedit_plugins_run", "vibeedit_plugins_invoke", "vibeedit_plugins_actions",
    "vibeedit_plugins_option", "vibeedit_plugins_options", "vibeedit_plugins_show_view",
    "vibeedit_clip_motion", "vibeedit_clip_backdrop", "vibeedit_clip_change_framing",
    "vibeedit_clip_send_to_agent",
    "vibeedit_music_replace", "vibeedit_narration_windows", "vibeedit_outcomes_import",
    "vibeedit_outcomes_map",
    "vibeedit_run_append", "vibeedit_run_checklist", "vibeedit_run_dismiss",
    "vibeedit_run_fix_issues", "vibeedit_run_follow", "vibeedit_run_toggle",
    "vibeedit_run_another_recipe",
    "vibeedit_acme_voice_fast", "vibeedit_speech_rate",
    "vibeedit_app_vibeedit", "vibeedit_app_vibeedit_automation_clients",
    "vibeedit_app_vibeedit_debug_log", "vibeedit_platforms_get", "vibeedit_context_get",
    "vibeedit_source_toggle_playback", "vibeedit_timeline_header_compact",
    "vibeedit_chat_stop", "vibeedit_view_compare", "vibeedit_view_safe_area",
    ]


class TestHonestTools(B1Case):
    def test_every_honest_tool_errors_structured(self):
        s = self.server
        names = {t["name"] for t in TOOLS}
        for name in HONEST_SAMPLE:
            self.assertIn(name, names, name)
            with self.assertRaises(ValueError, msg=name):
                s.call(name, {})
            try:
                s.call(name, {})
            except ValueError as exc:
                self.assertIn("NOT_AVAILABLE", str(exc), name)

    def test_honest_tool_via_jsonrpc_is_error(self):
        resp = handle(self.server, {"jsonrpc": "2.0", "id": 1,
                                    "method": "tools/call",
                                    "params": {"name": "vibeedit_agent_ask",
                                               "arguments": {}}})
        self.assertIn("error", resp)
        self.assertIn("NOT_AVAILABLE", resp["error"]["message"])


class TestRegistry(unittest.TestCase):
    def test_registry_count_no_dupes_descriptions(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(TOOLS), len(names))
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(len(TOOLS), 479)  # Round 4: 478 -> 479 (app_update_prepare)
        for tool in TOOLS:
            self.assertTrue(tool["description"], tool["name"])
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(honest), 132)  # Round 3: 138 -> 132, 6 voice tools became real


if __name__ == "__main__":
    unittest.main()
