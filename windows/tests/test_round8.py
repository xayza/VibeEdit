"""Round 8: state/workflow + local-data tools.

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

Every test uses temp data only: temp project folders, temp plugin
folders, temp kit folders, synthetic media built with stdlib wave
or FFmpeg lavfi. Nothing here touches a user project or media.
"""

import json
import math
import os
import shutil
import struct
import sys
import tempfile
import unittest
import wave

WINDOWS = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, WINDOWS)

from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402
from vibeedit_core.plugins import (  # noqa: E402
    apply_plugin, apply_plugin_proposal, get_plugin_view,
    install_plugin, list_plugin_actions, list_plugin_overlays,
    plugin_view_event, replace_plugin, set_plugin_enabled,
    set_plugin_overlays)
from vibeedit_core.project import (  # noqa: E402
    Project, new_project, save_project)
from vibeedit_core.round8 import (  # noqa: E402
    MOTION_PRESETS, apply_motion, brand_pose_image, change_framing,
    describe_media, export_pack, image_disclose, image_style,
    import_outcomes, kit_check, kit_install_skills,
    map_outcomes, media_description, media_digest, music_replace,
    narration_windows, run_checklist, append_run_entry, speech_rate)


def _make_project(tmp, width=320, height=180):
    data = new_project("round8", width=width, height=height)
    proj = Project(data, tmp)
    save_project(data, os.path.join(tmp, "project.vibeedit.json"))
    return proj


def _make_wav(path, seconds=2.0, freq=440.0):
    frames = int(8000 * seconds)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * freq * i / 8000))
            wf.writeframes(struct.pack("<h", sample))
    return path


def _make_server(tmp):
    proj = _make_project(tmp)
    return MCPServer(tmp), proj


class MotionTest(unittest.TestCase):
    def test_preset_zoom_in_becomes_scale_keyframes(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("clip.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            result = apply_motion(proj, clip["id"], preset="zoom-in")
            self.assertEqual(result["preset"], "zoom-in")
            keys = result["keyframes"]
            self.assertEqual(keys[0]["scale"], 1)
            self.assertEqual(keys[-1]["scale"], 1.12)
            self.assertEqual(keys[0]["at"], 0)
            self.assertEqual(keys[-1]["at"], 60)

    def test_preset_pan_left_maps_to_x_fractions(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("clip.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            result = apply_motion(proj, clip["id"], preset="pan-left")
            keys = result["keyframes"]
            self.assertAlmostEqual(keys[0]["x"], 0.55)
            self.assertAlmostEqual(keys[-1]["x"], 0.45)

    def test_none_clears_and_unknown_and_focus_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("clip.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            apply_motion(proj, clip["id"], preset="zoom-in")
            result = apply_motion(proj, clip["id"], preset="none")
            self.assertEqual(result["keyframes"], [])
            with self.assertRaises(ValueError):
                apply_motion(proj, clip["id"], preset="nope")
            with self.assertRaises(ValueError) as ctx:
                apply_motion(proj, clip["id"], preset="zoom-in",
                             focus={"x": 0.5, "y": 0.5})
            self.assertIn("clip_reframe", str(ctx.exception))

    def test_custom_keyframes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("clip.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            result = apply_motion(
                proj, clip["id"],
                keyframes={"zoom": [{"t": 0, "value": 1},
                                    {"t": 1, "value": 2}]})
            self.assertEqual(result["preset"], "custom")
            self.assertEqual(result["keyframes"][-1]["scale"], 2)

    def test_all_presets_known(self):
        self.assertEqual(len(MOTION_PRESETS), 10)
        self.assertIn("zoom-punch", MOTION_PRESETS)


class ChangeFramingTest(unittest.TestCase):
    def test_cycles_presets_and_stores_transform(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("clip.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            seen = [change_framing(proj, clip["id"])["preset"]
                    for _ in range(6)]
            self.assertEqual(seen, ["wide", "medium", "close",
                                    "left", "right", "wide"])
            _, item = proj.item(clip["id"])
            self.assertEqual(item["transform"]["zoom"], 1)
            change_framing(proj, clip["id"])
            change_framing(proj, clip["id"])
            change_framing(proj, clip["id"])
            _, item = proj.item(clip["id"])
            self.assertEqual(item["reframePreset"], "left")
            self.assertEqual(item["transform"]["pan"], -120)

    def test_render_differs_between_wide_and_left(self):
        if shutil.which("ffmpeg") is None:
            self.skipTest("FFmpeg not available on this machine")
        from vibeedit_core.render import render
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "split.mp4")
            subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", "color=c=red:s=320x180:d=2",
                 "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=2",
                 "-f", "lavfi",
                 "-i", "anullsrc=r=48000:cl=stereo",
                 "-filter_complex", "[0:v][1:v]hstack[v]",
                 "-map", "[v]", "-map", "2:a", "-t", "2",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", src], check=True)
            proj = _make_project(tmp)
            medium = proj.add_media("split.mp4", kind="video",
                                    width=640, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            out_wide = os.path.join(tmp, "wide.mp4")
            render(proj.data, tmp, out_wide, preset="draft")
            # First render had no preset; four cycles reach left:
            # wide -> medium -> close -> left.
            for _ in range(4):
                change_framing(proj, clip["id"])
            _, item = proj.item(clip["id"])
            self.assertEqual(item["reframePreset"], "left")
            out_left = os.path.join(tmp, "left.mp4")
            render(proj.data, tmp, out_left, preset="draft")
            with open(out_wide, "rb") as fh:
                wide_bytes = fh.read()
            with open(out_left, "rb") as fh:
                left_bytes = fh.read()
            self.assertTrue(len(wide_bytes) > 1000)
            self.assertTrue(len(left_bytes) > 1000)
            self.assertNotEqual(wide_bytes, left_bytes)


class MusicReplaceTest(unittest.TestCase):
    def test_replaces_span_keeping_level_and_loops(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            old = proj.add_media("old.wav", kind="audio",
                                 duration=4.0, frames=120, hasAudio=True)
            new = proj.add_media("new.wav", kind="audio",
                                 duration=1.0, frames=30, hasAudio=True)
            first = proj.add_clip(old["id"], "a2", 0, dur=60)
            proj.add_clip(old["id"], "a2", 60, dur=60)
            first["volume"] = -3.0
            first["muted"] = False
            result = music_replace(proj, media_id=new["id"], loop=True)
            self.assertEqual(result["at"], 0)
            self.assertEqual(result["duration"], 120)
            self.assertTrue(result["looped"])
            self.assertEqual(len(result["items"]), 4)
            _, item = proj.item(result["items"][0])
            self.assertEqual(item["volume"], -3.0)

    def test_no_loop_shortens_and_no_music_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            old = proj.add_media("old.wav", kind="audio",
                                 duration=4.0, frames=120, hasAudio=True)
            new = proj.add_media("new.wav", kind="audio",
                                 duration=1.0, frames=30, hasAudio=True)
            proj.add_clip(old["id"], "a2", 0, dur=120)
            result = music_replace(proj, media_id=new["id"], loop=False)
            self.assertTrue(result["shortened"])
            self.assertEqual(len(result["items"]), 1)
            # A project with no Music clips at all errors cleanly.
            proj2 = _make_project(tempfile.mkdtemp(dir=tmp))
            new2 = proj2.add_media("new.wav", kind="audio",
                                   duration=1.0, frames=30,
                                   hasAudio=True)
            with self.assertRaises(ValueError):
                music_replace(proj2, media_id=new2["id"])


class NarrationWindowsTest(unittest.TestCase):
    def test_gap_between_captions_and_voiceover(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            proj.add_text("t1", "hello world", 0, 60)
            voice = proj.add_media("vo.wav", kind="audio",
                                   duration=2.0, frames=60, hasAudio=True)
            track = proj.add_track("audio", "voiceover", "Voiceover")
            proj.add_clip(voice["id"], track["id"], 120, dur=60)
            video = proj.add_media("v.mp4", kind="video",
                                   width=320, height=180, fps=30,
                                   frames=180, duration=6.0)
            proj.add_clip(video["id"], "v1", 0, dur=90)
            proj.add_clip(video["id"], "v1", 90, dur=90)
            proj.add_marker("Intro", 0)
            result = narration_windows(proj, min_seconds=1.0, rate=2.0)
            self.assertEqual(len(result["windows"]), 1)
            window = result["windows"][0]
            # Project fps is 30000/1001, so frame times are 2.002,
            # 4.004 and 3.003, not exact 30 fps seconds.
            self.assertAlmostEqual(window["atSeconds"], 2.0, places=2)
            self.assertAlmostEqual(window["endSeconds"], 4.0, places=2)
            self.assertEqual(window["anchors"]["afterWord"], "world")
            self.assertAlmostEqual(window["anchors"]["firstCut"], 3.0,
                                   places=2)
            self.assertEqual(window["anchors"]["section"], "Intro")
            self.assertEqual(window["budget"], 4.0)


class OutcomesTest(unittest.TestCase):
    def test_import_json_csv_and_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            video = proj.add_media("v.mp4", kind="video",
                                   width=320, height=180, fps=30,
                                   frames=180, duration=6.0)
            proj.add_clip(video["id"], "v1", 0, dur=180)
            proj.add_marker("Part two", 90)
            proj.add_text("t1", "hello world", 0, 60)
            payload = {"curve": [{"t": 0, "retention": 100},
                                 {"t": 3, "retention": 80},
                                 {"t": 6, "retention": 50}],
                       "totals": {"views": 1000}}
            imported = import_outcomes(proj, "exp1", payload)
            self.assertEqual(imported["points"], 3)
            mapped = map_outcomes(proj, "exp1")
            self.assertEqual(len(mapped["sections"]), 2)
            self.assertEqual(mapped["sections"][0]["startRetention"], 100)
            # Marker at frame 90 lands at 3.003 s (30000/1001 fps),
            # so interpolation gives 79.97, not exactly 80.
            self.assertAlmostEqual(
                mapped["sections"][0]["endRetention"], 80, places=1)
            self.assertAlmostEqual(
                mapped["sections"][0]["viewsAtStart"], 1000.0)
            self.assertEqual(mapped["largestDrops"][0]["change"], -30)
            csv_payload = ("t,retention\n0,100\n3,80\n6,50\n")
            imported2 = import_outcomes(proj, "exp2", csv_payload)
            self.assertEqual(imported2["points"], 3)
            with self.assertRaises(KeyError):
                map_outcomes(proj, "nope")


class RunLogTest(unittest.TestCase):
    def test_gates_and_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            proj.data["plan"] = {
                "stages": {"rough-cut": {"skill": "bc:rough-cut",
                                         "required": True},
                           "review": {"required": True}}}
            done = append_run_entry(proj, "stage", {
                "stage": "rough-cut", "status": "done",
                "evidence": "cut list exported"})
            self.assertNotIn("unverified", done["entry"])
            unverified = append_run_entry(proj, "stage", {
                "stage": "sound", "status": "done"})
            self.assertTrue(unverified["entry"]["unverified"])
            with self.assertRaises(ValueError):
                append_run_entry(proj, "stage", {
                    "stage": "colour", "status": "skipped"})
            skipped = append_run_entry(proj, "stage", {
                "stage": "colour", "status": "skipped",
                "reason": "no colour pass in this cut"})
            self.assertEqual(skipped["entry"]["status"], "skipped")
            review = append_run_entry(proj, "stage", {
                "stage": "review", "status": "done",
                "evidence": "review run passed"})
            self.assertEqual(review["entry"]["status"], "done")
            checklist = run_checklist(proj)
            by_id = {s["id"]: s for s in checklist["stages"]}
            self.assertEqual(by_id["rough-cut"]["status"], "done")
            self.assertTrue(by_id["sound"]["unverified"])
            self.assertEqual(by_id["colour"]["status"], "skipped")
            self.assertEqual(checklist["open"], [])

    def test_review_pending_when_required_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            proj.data["plan"] = {
                "stages": {"rough-cut": {"required": True}}}
            review = append_run_entry(proj, "stage", {
                "stage": "review", "status": "done",
                "evidence": "x"})
            self.assertEqual(review["status"], "stage_pending")
            self.assertIn("rough-cut", review["openRequired"])


class MediaDescribeTest(unittest.TestCase):
    def test_describe_description_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("v.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=180, duration=6.0)
            with self.assertRaises(ValueError):
                describe_media(proj, medium["id"], [
                    {"start": 0, "end": 5}])
            with self.assertRaises(ValueError):
                describe_media(proj, medium["id"], [
                    {"start": 0, "end": 3, "size": "CU"},
                    {"start": 2, "end": 4, "size": "WS"}])
            result = describe_media(proj, medium["id"], [
                {"start": 0, "end": 3, "size": "CU", "angle": "eye",
                 "move": "static", "subjects": ["Ana"],
                 "note": "opens", "bestMoment": 1.5}])
            self.assertEqual(result["shots"], 1)
            desc = media_description(proj, medium["id"])
            self.assertEqual(desc["coverage"]["shots"], 1)
            self.assertAlmostEqual(
                desc["coverage"]["describedShare"], 0.5)
            digest = media_digest(proj, medium["id"])
            self.assertEqual(digest["header"]["seconds"], 6.0)
            self.assertIn("Ana", digest["lines"][0])
            self.assertTrue(digest["described"])


class SpeechRateTest(unittest.TestCase):
    def test_vietnamese_syllables_from_transcript_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("v.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=300, duration=10.0)
            medium["analysis_record"] = {"transcript": {"words": [
                {"word": "xin", "start": 0.0, "end": 0.5},
                {"word": "chào", "start": 0.5, "end": 1.0},
                {"word": "các", "start": 1.0, "end": 1.5},
                {"word": "bạn", "start": 1.5, "end": 2.0},
            ]}}
            result = speech_rate(proj, medium["id"])
            entry = result["perMedia"][0]
            self.assertEqual(entry["unit"], "syllables")
            self.assertEqual(entry["words"], 4)
            self.assertAlmostEqual(entry["overall"], 2.0)
            self.assertFalse(result["voices"]["available"])

    def test_missing_transcript_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("v.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            with self.assertRaises(ValueError):
                speech_rate(proj, medium["id"])


class ImageStyleTest(unittest.TestCase):
    def test_style_lock_and_disclose(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            self.assertIsNone(image_style(proj)["styleLock"])
            locked = image_style(proj, style="flat comic",
                                 seed=7, disclosure="AI-made")
            self.assertEqual(locked["styleLock"]["seed"], 7)
            self.assertEqual(locked["styleLock"]["style"], "flat comic")
            cleared = image_style(proj, clear=True)
            self.assertIsNone(cleared["styleLock"])
            empty = image_disclose(proj)
            self.assertEqual(empty["added"], [])
            self.assertIn("No disclosure", empty["note"])
            image_style(proj, disclosure="AI-made")
            gen = proj.add_media("gen.png", kind="image",
                                 width=320, height=180)
            gen["generated"] = True
            proj.add_clip(gen["id"], "v1", 0, dur=60)
            result = image_disclose(proj)
            self.assertEqual(len(result["added"]), 1)
            _, item = proj.item(result["added"][0])
            self.assertTrue(item.get("disclosure"))
            self.assertEqual(item["text"], "AI-made")


class LibraryPackTest(unittest.TestCase):
    def test_export_import_roundtrip_and_refusals(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("v.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            entry = proj.library_add(clip["id"], "hero clip")
            blocked = proj.library_add(clip["id"], "blocked clip")
            blocked["license"] = {"redistribute": False}
            out = os.path.join(tmp, "pack")
            result = export_pack(proj, out)
            self.assertIn(entry["id"], result["exported"])
            self.assertIn(blocked["id"], result["refused"])
            self.assertIn(entry["id"], result["unknownLicenses"])
            self.assertTrue(os.path.isfile(
                os.path.join(out, "pack.json")))
            proj2 = None
            tmp2 = tempfile.mkdtemp(dir=tmp)
            proj2 = _make_project(tmp2)
            from vibeedit_core.round8 import import_pack
            imported = import_pack(proj2, out)
            self.assertIn(entry["id"], imported["added"])
            again = import_pack(proj2, out)
            self.assertIn(entry["id"], again["refused"])
            replaced = import_pack(proj2, out, replace=True)
            self.assertTrue(any(a.startswith(entry["id"] + "-v")
                                for a in replaced["added"]))

    def test_export_refuses_nonempty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            out = os.path.join(tmp, "busy")
            os.makedirs(out)
            with open(os.path.join(out, "x.txt"), "w") as fh:
                fh.write("x")
            with self.assertRaises(ValueError):
                export_pack(proj, out)


class LibraryAnalyzeTest(unittest.TestCase):
    def test_measure_tone_wav(self):
        if shutil.which("ffmpeg") is None \
                or shutil.which("ffprobe") is None:
            self.skipTest("FFmpeg/FFprobe not available")
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            wav_path = _make_wav(os.path.join(tmp, "tone.wav"))
            medium = proj.add_media("tone.wav", kind="audio",
                                    duration=2.0, frames=60,
                                    hasAudio=True)
            clip = proj.add_clip(medium["id"], "a2", 0, dur=60)
            entry = proj.library_add(clip["id"], "tone")
            from vibeedit_core.round8 import analyze_library_item
            result = analyze_library_item(proj, entry["id"],
                                          media_path=wav_path)
            analysis = result["analysis"]
            self.assertIsNotNone(analysis["duration"])
            self.assertIsNotNone(analysis["landmarks"])
            self.assertTrue(result["newVersion"].startswith(
                entry["id"] + "-v"))

    def test_brand_pose_without_backend_errors_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            png = os.path.join(tmp, "photo.png")
            try:
                from PIL import Image
                Image.new("RGB", (32, 32), "red").save(png)
            except Exception:
                self.skipTest("Pillow not available to make a photo")
            try:
                result = brand_pose_image(proj, "kit", "wave",
                                          image=png)
            except Exception as exc:
                self.assertIn("opencv", str(exc).lower())
                return
            self.assertTrue(os.path.isfile(
                result["poses"][0]["sticker"]))


class PluginRound8Test(unittest.TestCase):
    def _install_test_plugin(self, plugins_dir):
        src = os.path.join(plugins_dir, "src_testplug")
        os.makedirs(src)
        manifest = {
            "id": "testplug", "name": "Test Plug",
            "hooks": ["shout", "propose_louder"],
            "entry": "entry.py",
            "actions": [{"id": "shout-action", "title": "Shout",
                         "hook": "shout",
                         "parameters": {"type": "object"}}],
            "views": [{"id": "main", "title": "Main",
                       "placement": "panel",
                       "components": [
                           {"id": "label", "kind": "text",
                            "value": "hello"},
                           {"id": "name", "kind": "input",
                            "value": ""},
                           {"id": "go", "kind": "button",
                            "action": "shout", "item": "ITEM"}]}],
        }
        with open(os.path.join(src, "plugin.json"), "w") as fh:
            json.dump(manifest, fh)
        with open(os.path.join(src, "entry.py"), "w") as fh:
            fh.write(
                "def register():\n"
                "    return {'name': 'testplug',\n"
                "            'shout': shout,\n"
                "            'propose_louder': propose_louder}\n"
                "\n"
                "def shout(project, item_id):\n"
                "    _, item = project.item(item_id)\n"
                "    item['text'] = item['text'].upper()\n"
                "    return item\n"
                "\n"
                "def propose_louder(project, item_id):\n"
                "    return {'propose': [{'op': 'set_text',\n"
                "                         'item': item_id,\n"
                "                         'text': 'PROPOSED'}]}\n")
        result = install_plugin(src, plugins_dir=plugins_dir)
        return result

    def test_overlays_actions_views_proposal_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            pdir = os.path.join(tmp, "plugins")
            os.makedirs(pdir)
            self._install_test_plugin(pdir)
            text = proj.add_text("t1", "hello", 0, 60)
            # Overlays: set, list, validate, clear.
            set_plugin_overlays("testplug", [
                {"id": "o1", "kind": "range", "start": 0, "end": 60,
                 "label": "scene"}], pdir)
            listed = list_plugin_overlays("testplug", pdir)
            self.assertEqual(len(listed["overlays"]), 1)
            with self.assertRaises(ValueError):
                set_plugin_overlays("testplug", [
                    {"id": "bad", "kind": "nope"}], pdir)
            set_plugin_overlays("testplug", [], pdir)
            self.assertEqual(
                list_plugin_overlays("testplug", pdir)["overlays"], [])
            # Actions: unavailable while disabled, available enabled.
            actions = list_plugin_actions(plugin="testplug",
                                          plugins_dir=pdir)
            self.assertEqual(len(actions["actions"]), 1)
            self.assertFalse(actions["actions"][0]["available"])
            set_plugin_enabled("testplug", True, pdir)
            actions = list_plugin_actions(plugin="testplug",
                                          plugins_dir=pdir)
            self.assertTrue(actions["actions"][0]["available"])
            # Views: render, input change, button click runs hook.
            view = get_plugin_view("testplug", "main", pdir)
            self.assertEqual(len(view["components"]), 3)
            # Button click needs the item id carried by the view
            # component in the manifest; rewrite the manifest so
            # the button component carries this text item's id.
            manifest_path = os.path.join(pdir, "testplug",
                                         "plugin.json")
            with open(manifest_path) as fh:
                manifest = json.load(fh)
            manifest["views"][0]["components"][2]["item"] = text["id"]
            with open(manifest_path, "w") as fh:
                json.dump(manifest, fh)
            changed = plugin_view_event(
                "testplug", "main", "name", "change", "Ana",
                project=proj, plugins_dir=pdir)
            name_comp = next(c for c in changed["components"]
                             if c["id"] == "name")
            self.assertEqual(name_comp["value"], "Ana")
            plugin_view_event("testplug", "main", "go", "click",
                              project=proj, plugins_dir=pdir)
            _, item = proj.item(text["id"])
            self.assertEqual(item["text"], "HELLO")
            # Proposal: hook returns propose ops; apply them.
            proposed = apply_plugin(proj, "testplug", "propose_louder",
                                    text["id"], plugins_dir=pdir)
            self.assertFalse(proposed["applied"])
            pid = proposed["proposal"]
            applied = apply_plugin_proposal(proj, pid, "apply")
            self.assertEqual(applied["status"], "applied")
            _, item = proj.item(text["id"])
            self.assertEqual(item["text"], "PROPOSED")
            with self.assertRaises(ValueError):
                apply_plugin_proposal(proj, pid, "apply")
            # Replace: new version, same id; wrong id refused.
            src2 = os.path.join(tmp, "src_v2")
            os.makedirs(src2)
            with open(os.path.join(src2, "plugin.json"), "w") as fh:
                json.dump({"id": "testplug", "name": "Test Plug v2",
                           "hooks": ["shout"], "entry": "entry.py"},
                          fh)
            with open(os.path.join(src2, "entry.py"), "w") as fh:
                fh.write("def register():\n"
                         "    return {'name': 'testplug'}\n")
            set_plugin_enabled("testplug", False, pdir)
            replaced = replace_plugin("testplug", src2, pdir)
            self.assertTrue(replaced["replaced"])
            with open(os.path.join(pdir, "testplug",
                                   "plugin.json")) as fh:
                self.assertEqual(json.load(fh)["name"],
                                 "Test Plug v2")
            src3 = os.path.join(tmp, "src_v3")
            os.makedirs(src3)
            with open(os.path.join(src3, "plugin.json"), "w") as fh:
                json.dump({"id": "other", "name": "Other",
                           "hooks": []}, fh)
            with self.assertRaises(ValueError):
                replace_plugin("testplug", src3, pdir)


class KitTest(unittest.TestCase):
    def test_kit_check_and_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = os.path.join(tmp, "kit")
            os.makedirs(kit)
            for name in ("alpha.md", "beta.md"):
                with open(os.path.join(kit, name), "w") as fh:
                    fh.write(f"# {name}\nbody\n")
            checked = kit_check(kit)
            self.assertEqual(checked["count"], 2)
            self.assertIsNone(checked["newer"])
            self.assertIsNone(checked["channel"])
            src = os.path.join(tmp, "src")
            os.makedirs(src)
            with open(os.path.join(src, "gamma.md"), "w") as fh:
                fh.write("# gamma\n")
            with open(os.path.join(src, "bad name.md"), "w") as fh:
                fh.write("# bad\n")
            installed = kit_install_skills(src, kit)
            self.assertIn("gamma", installed["installed"])
            self.assertIn("bad name", installed["refused"])
            again = kit_install_skills(src, kit)
            self.assertIn("gamma", again["refused"])


class MCPHandlerTest(unittest.TestCase):
    def test_handlers_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("v.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=60, duration=2.0)
            clip = proj.add_clip(medium["id"], "v1", 0, dur=60)
            # The MCP server loads its own project copy from disk,
            # so save before opening the server on the folder.
            save_project(proj.data,
                         os.path.join(tmp, "project.vibeedit.json"))
            server = MCPServer(tmp)
            result = server.call("vibeedit_clip_motion",
                                 {"item": clip["id"],
                                  "preset": "zoom-out"})
            self.assertEqual(result["preset"], "zoom-out")
            appended = server.call("vibeedit_run_append",
                                   {"kind": "note", "text": "hello"})
            self.assertEqual(appended["entries"], 1)
            checklist = server.call("vibeedit_run_checklist", {})
            self.assertEqual(checklist["stages"], [])
            described = server.call(
                "vibeedit_media_describe",
                {"media": medium["id"],
                 "shots": [{"start": 0, "end": 1, "size": "CU"}]})
            self.assertEqual(described["shots"], 1)
            digest = server.call("vibeedit_media_digest",
                                 {"media": medium["id"]})
            self.assertTrue(digest["described"])
            overlays = server.call("vibeedit_plugins_set_overlays",
                                   {"plugin": "p",
                                    "overlays": "[]"})
            self.assertEqual(overlays["overlays"], [])
            with self.assertRaises(Exception) as ctx:
                server.call("vibeedit_clip_backdrop",
                            {"item": clip["id"]})
            self.assertIn("NOT_AVAILABLE", str(ctx.exception))

    def test_registry_counts(self):
        real = [t for t in TOOLS
                if not t["description"].startswith("Not available")]
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), len(real) + len(honest))
        self.assertGreater(len(real), 366)
        self.assertLess(len(honest), 113)


if __name__ == "__main__":
    unittest.main()
