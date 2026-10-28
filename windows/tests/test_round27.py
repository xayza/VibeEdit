"""Round 27 — review-and-supplement audit ("rà soát bổ sung").

Findings of the audit (all verified by live behaviour on Linux VM):
- The round-26 language sweep missed English strings that are written
  as SPLIT string literals (implicit concatenation across lines): the
  round-26 scanner evidently only caught single-line literals. This
  round translates the gate-passing split-literal misses (three-gate
  rule from round 26: no test locks it, no code matches on it, not
  intentionally English) plus a few other missed user-visible strings.
- Two FFmpeg decode helpers never close their stderr pipe, which the
  full suite itself reports as ResourceWarnings.
- Docs drift: PARITY.md headline + section-8 row still show round-15
  counts (479 = 420 + 59); README.md has no round 23-26 sections and
  its title still says "Phase 8, final planned phase" although the
  product goal is the full port; WINDOWS_TEST_CHECKLIST.md section 10
  still claims no plugin registry exists (round 15 proved it does)
  and has no round 23-26 verification items; UI_MAP.md stops at
  round 23.

Deliberately NOT translated here (gate failures, documented in the
round report): test-locked strings, code-matched strings ("exceeds"
plugin messages, "No such file" FFmpeg-stderr matcher, "derived
from" provenance matcher), original-app labels / preset names /
technical method specs, console startup banner lines, generated
.bat REM comments, ASS file-format constants, agent-facing
follow-up template text, mcp.py tool descriptions (API contract),
and vision.py "unknown error" (not triggerable live on this VM:
no Tesseract installed, so the binary-missing error fires first).
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.analysis import (
    align_sound,
    decode_sound_levels,
    derive_analysis,
    measure_media,
    speech_map,
    transcribe_words,
)
from vibeedit_core.export_ops import media_metadata
from vibeedit_core.mcp import MCPServer
from vibeedit_core.plugins import _warnings_for_manifest
from vibeedit_core.project import (
    PROJECT_FILENAME,
    Project,
    new_project,
    save_project,
)
from vibeedit_core.render import _attach_duration_check, render
from vibeedit_core.round8 import (
    analyze_library_item,
    image_disclose,
    media_digest,
    import_outcomes,
    kit_check,
    map_outcomes,
    narration_windows,
)
from vibeedit_core.round9 import show_plugin_view
from vibeedit_core.round15 import (
    kit_install_from_zip,
    kit_update,
    write_kit_manifest,
)
from vibeedit_core.server import State, make_handler
from vibeedit_core.skills import remove_skill
from vibeedit_core.updater import update_status

WIN = os.path.join(os.path.dirname(__file__), "..")
STATIC = os.path.join(WIN, "static")


def _ffmpeg(*args):
    return subprocess.run(["ffmpeg", "-y", "-v", "error", *args],
                          capture_output=True, check=True)


def _tone_wav(path, seconds=5.0):
    _ffmpeg("-f", "lavfi", "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ac", "1", "-ar", "8000", path)


def _silent_wav(path, seconds=5.0):
    _ffmpeg("-f", "lavfi", "-i",
            f"anullsrc=r=8000:cl=mono:duration={seconds}", path)


def _clip_mp4(path, seconds=3.0, color="red"):
    _ffmpeg("-f", "lavfi", "-i",
            f"color=c={color}:s=320x180:r=30:d={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:d={seconds}",
            "-shortest", path)


def _video_only_mp4(path, seconds=2.0):
    _ffmpeg("-f", "lavfi", "-i",
            f"color=c=blue:s=320x180:r=30:d={seconds}", path)


def _make_project(tmp, name="round27"):
    data = new_project(name, width=320, height=180, fps=(30, 1))
    proj = Project(data, tmp)
    save_project(data, os.path.join(tmp, PROJECT_FILENAME))
    return proj


def _demo_plugin_dir(tmp):
    pdir = os.path.join(tmp, "plugins")
    folder = os.path.join(pdir, "demo")
    os.makedirs(folder)
    manifest = {"id": "demo", "name": "Demo",
                "views": [
                    {"id": "main", "title": "Main",
                     "placement": "panel", "components": []},
                    {"id": "side", "title": "Side",
                     "placement": "inspector", "components": []}]}
    with open(os.path.join(folder, "plugin.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh)
    return pdir


class TestTranscribeAndSpeechMap(unittest.TestCase):
    def test_transcribe_words_reason_vietnamese(self):
        # No faster-whisper on this VM: the reason must be Vietnamese.
        words, reason = transcribe_words("/tmp/does-not-matter.mp4")
        self.assertEqual(words, [])
        self.assertIn("Chưa cài faster-whisper", reason)
        self.assertNotIn("is not installed", reason)

    def test_measure_media_no_audio_reason_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "video-only.mp4")
            _video_only_mp4(path)
            record = measure_media(path)
            reason = record["transcript"]["reason"]
            self.assertIn("không có track audio nên không có gì để",
                          reason)
            self.assertIn("phiên âm", reason)

    def test_speech_map_flat_reason_vietnamese(self):
        out = speech_map({"levels": [-60.0] * 5, "window": 0.1})
        self.assertIn("Quá ít âm thanh", out["reason"])

    def test_speech_map_close_classes_reason_vietnamese(self):
        levels = [-50.0] * 20 + [-40.0] * 20
        out = speech_map({"levels": levels, "window": 0.1},
                         min_separation_db=100.0)
        self.assertIn("gần nhau hơn minSeparationDb", out["reason"])

    def test_analysis_units_and_measured_on_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "av.mp4")
            _clip_mp4(path)
            record = measure_media(path)
            derived = derive_analysis(record)
            self.assertIn("Khung hình nguồn",
                          derived["picture"]["units"])
            self.assertIn("phân vị", derived["sound"]["units"])
            wav = os.path.join(tmp, "tone.wav")
            _tone_wav(wav)
            sound = decode_sound_levels(wav)
            mapped = speech_map(sound)
            self.assertIn("RMS băng rộng", mapped["measuredOn"])


class TestTransitionAndRenderMessages(unittest.TestCase):
    def _two_clip_project(self, tmp):
        proj = _make_project(tmp)
        _clip_mp4(os.path.join(tmp, "a.mp4"), seconds=1.0)
        _clip_mp4(os.path.join(tmp, "b.mp4"), seconds=1.0)
        ma = proj.add_media("a.mp4", kind="video", width=320,
                            height=180, fps=[30, 1], frames=30,
                            duration=1.0, hasAudio=True)
        mb = proj.add_media("b.mp4", kind="video", width=320,
                            height=180, fps=[30, 1], frames=30,
                            duration=1.0, hasAudio=True)
        first = proj.add_clip(ma["id"], "v1", 0, 0, 30)
        second = proj.add_clip(mb["id"], "v1", 30, 0, 30)
        return proj, first, second

    def test_project_transition_duration_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj, first, second = self._two_clip_project(tmp)
            with self.assertRaises(ValueError) as caught:
                proj.add_transition(first["id"], second["id"],
                                    "dissolve", 1.5)
            self.assertIn("vượt quá clip kề ngắn hơn",
                          str(caught.exception))

    def test_render_transition_duration_vietnamese(self):
        # Same message, raised by the render pipeline's own check.
        with tempfile.TemporaryDirectory() as tmp:
            proj, first, second = self._two_clip_project(tmp)
            proj.add_transition(first["id"], second["id"],
                                "dissolve", 0.5)
            # Lengthen the transition past the shorter clip by hand:
            # add_transition itself refuses, so the render path is
            # reached by editing the stored duration directly.
            proj.data["transitions"][0]["duration"] = 45
            out = os.path.join(tmp, "render", "out.mp4")
            with self.assertRaises(ValueError) as caught:
                render(proj.data, tmp, out, preset="full")
            self.assertIn("vượt quá clip kề ngắn hơn",
                          str(caught.exception))

    def test_duration_warning_reverted_kept_english(self):
        # REVERTED in round 27: test_round22:467 asserts "differs"
        # in this warning. The probe-failure error next door stays
        # Vietnamese (no test locks it).
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "five.mp4")
            _clip_mp4(path, seconds=5.0)
            report = {"duration": 2.0}
            _attach_duration_check(report, path)
            warning = report["duration_check"]["warning"]
            self.assertIn("differs", warning)
            self.assertIn("may be out of sync", warning)

    def test_duration_probe_failed_vietnamese(self):
        report = {"duration": 2.0}
        _attach_duration_check(report, "/nonexistent/out.mp4")
        self.assertIn("probe thất bại",
                      report["duration_check"]["error"])

    def test_skipped_notes_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            os.makedirs(os.path.join(tmp, "media"), exist_ok=True)
            _clip_mp4(os.path.join(tmp, "media", "main.mp4"))
            main = proj.add_media("media/main.mp4", kind="video",
                                  width=320, height=180, fps=[30, 1],
                                  frames=90, duration=3.0, hasAudio=True)
            proj.add_clip(main["id"], "v1", 0, 0, 90)
            # Adjustment layer with no colour set at all (appended
            # directly: add_adjustment itself refuses a colourless
            # layer, and the render loop is what must report it).
            proj.data["tracks"].append(
                {"id": "adj1", "kind": "video", "role": "adjustment",
                 "name": "Adjustment",
                 "items": [{"id": "adj-item", "at": 0, "dur": 30}]})
            # Overlay item whose media record does not exist.
            overlay_track = next(
                t for t in proj.data["tracks"]
                if t["id"] == "v2")
            overlay_track["items"].append(
                {"id": "ov-missing", "media": "no-such-media",
                 "at": 0, "dur": 30})
            out = os.path.join(tmp, "render", "out.mp4")
            report = render(proj.data, tmp, out, preset="full")
            skipped = " ".join(report["skipped"])
            self.assertIn("(chưa đặt màu)", skipped)
            self.assertIn("(không có media)", skipped)


class TestRound8Notes(unittest.TestCase):
    def test_narration_note_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            out = narration_windows(proj)
            self.assertIn("khoảng trống timeline", out["note"])

    def test_outcomes_note_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            video = proj.add_media("v.mp4", kind="video",
                                   width=320, height=180, fps=30,
                                   frames=180, duration=6.0)
            proj.add_clip(video["id"], "v1", 0, dur=180)
            payload = {"curve": [{"t": 0, "retention": 100},
                                 {"t": 3, "retention": 80},
                                 {"t": 6, "retention": 50}],
                       "totals": {"views": 1000}}
            import_outcomes(proj, "exp1", payload)
            mapped = map_outcomes(proj, "exp1")
            self.assertIn("đơn vị của file", mapped["note"])

    def test_describe_note_vietnamese(self):
        # The note lives on media_digest (the measured + caller-fact
        # summary), not on describe_media (which only stores shots).
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            medium = proj.add_media("v.mp4", kind="video",
                                    width=320, height=180, fps=30,
                                    frames=180, duration=6.0)
            out = media_digest(proj, medium["id"])
            self.assertIn("không bao giờ bịa", out["note"])

    def test_disclose_notes_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            out = image_disclose(proj)
            # REVERTED in round 27: test_round8:409 asserts "No
            # disclosure" here. The no-images note below stays
            # Vietnamese (no test locks it).
            self.assertIn("No disclosure", out["note"])
            proj.data["brand"] = {"disclosure": "Demo"}
            out = image_disclose(proj)
            self.assertIn("Không có ảnh đã tạo nào", out["note"])

    def test_library_analyze_notes_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            wav = os.path.join(tmp, "silent.wav")
            _silent_wav(wav)
            proj.data.setdefault("library", []).append({"id": "e1"})
            out = analyze_library_item(proj, "e1", media_path=wav)
            notes = " ".join(out["analysis"]["notes"])
            self.assertIn("Không có window âm thanh nào qua cổng -70 dB",
                          notes)
            self.assertIn("Tempo là null", notes)
            self.assertIn("Cổng landmark dùng envelope dBFS đã đo",
                          out["analysis"]["gateNote"])

    def test_kit_check_note_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = kit_check(tmp)
            self.assertIn("không cấu hình kênh releases", out["note"])
            self.assertIn("chỉ báo cáo kit local", out["note"])


class TestMiscMessages(unittest.TestCase):
    def test_inspector_note_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(tmp)
            pdir = _demo_plugin_dir(tmp)
            out = show_plugin_view(proj, "demo", "side", pdir)
            self.assertFalse(out["shown"])
            self.assertIn("không có gì để mở", out["note"])

    def test_kit_update_note_vietnamese(self):
        import hashlib
        import base64
        import io
        import zipfile
        from unittest import mock

        from vibeedit_core.round15 import KIT_RELEASES_URL

        # Same shape as test_round15's FAKE_SIG: parse_kit_releases
        # requires an "ed25519:"-prefixed signature on every entry.
        fake_sig = ("ed25519:" +
                    base64.b64encode(b"\x00" * 64).decode())

        def skill_md(skill_id):
            return (f"---\nname: {skill_id}\ndescription: test\n---\n"
                    f"# {skill_id}\n\nBody.\n").encode("utf-8")

        def kit_zip_bytes(skill_ids, top="bashcut-agent-kit"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                for sid in skill_ids:
                    zf.writestr(f"{top}/skills/{sid}/SKILL.md",
                                skill_md(sid))
                zf.writestr(f"{top}/LICENSE", "MIT License\n")
            return buf.getvalue()

        def catalog(versions):
            return json.dumps({
                "schemaVersion": 1, "kit": "bashcut",
                "versions": [{"version": v, "url": u, "sha256": s,
                              "signature": fake_sig, "size": n,
                              "releasedAt": "2026-10-18T00:00:00Z",
                              "minAppVersion": "0.0.25"}
                             for v, u, s, n in versions]}).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            kit_dir = os.path.join(tmp, "skills")
            os.makedirs(kit_dir)
            old_zip = kit_zip_bytes(["old-skill"])
            zpath = os.path.join(tmp, "old.zip")
            with open(zpath, "wb") as fh:
                fh.write(old_zip)
            kit_install_from_zip(zpath, kit_dir)
            write_kit_manifest(kit_dir, {
                "source": "x", "version": "0.1.0", "license": "MIT",
                "installed": [{"id": "old-skill",
                               "sha256": hashlib.sha256(
                                   skill_md("old-skill")).hexdigest()}]})
            new_zip = kit_zip_bytes(["new-skill"])
            new_sha = hashlib.sha256(new_zip).hexdigest()
            cat = catalog([("0.1.0", "https://example.invalid/o.zip",
                            "ab" * 32, 10),
                           ("0.2.0", "https://example.invalid/n.zip",
                            new_sha, len(new_zip))])

            def fake_fetch(url):
                if url == KIT_RELEASES_URL:
                    return cat
                return new_zip

            with mock.patch(
                    "vibeedit_core.round15.ed25519_verify",
                    return_value=True):
                res = kit_update(kit_dir, fetcher=fake_fetch)
            self.assertTrue(res["updated"])
            self.assertIn("chỉ báo cáo chứ không áp đặt",
                          res["minAppVersionNote"])

    def test_export_cancel_unknown_job_vietnamese(self):
        from http.server import ThreadingHTTPServer

        with tempfile.TemporaryDirectory() as tmp:
            state = State(tmp)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(state))
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/export/cancel",
                    data=json.dumps({"job": "no-such-job"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST")
                try:
                    urllib.request.urlopen(req, timeout=10)
                    self.fail("expected HTTP 404")
                except urllib.error.HTTPError as err:
                    self.assertEqual(err.code, 404)
                    body = json.loads(err.read().decode("utf-8"))
                    self.assertIn("Không rõ job xuất", body["error"])
            finally:
                server.shutdown()
                server.server_close()

    def test_remove_skill_note_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "x.md"), "w",
                      encoding="utf-8") as fh:
                fh.write("---\nname: x\ndescription: x\n---\n# x\n")
            out = remove_skill(tmp, "x", confirm=True)
            self.assertEqual(out["removed"], "x")
            self.assertIn("khôi phục skill kèm sẵn", out["note"])

    def test_updater_configured_status_vietnamese(self):
        old = os.environ.get("VIBEEDIT_RELEASES_URL")
        os.environ["VIBEEDIT_RELEASES_URL"] = \
            "https://example.invalid/releases"
        try:
            status = update_status()
        finally:
            if old is None:
                os.environ.pop("VIBEEDIT_RELEASES_URL", None)
            else:
                os.environ["VIBEEDIT_RELEASES_URL"] = old
        self.assertIn("đã cấu hình kênh updater", status["status"])
        self.assertIn("app_update_check", status["status"])

    def test_media_not_found_warnings_vietnamese(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = new_project("round27", width=320, height=180,
                               fps=(30, 1))
            save_project(data, os.path.join(tmp, PROJECT_FILENAME))
            # Use a media entry whose file is absent.
            proj = Project(data, tmp)
            medium = proj.add_media("gone.mp4", kind="video")
            out = media_metadata(proj.data, tmp, medium["id"])
            self.assertIn("Không tìm thấy file media trên đĩa",
                          out["warning"])
            server = MCPServer(tmp)
            added = server.call("vibeedit_media_add",
                                {"path": "missing.mp4"})
            self.assertIn("Không tìm thấy file media trên đĩa",
                          added["warning"])

    def test_plugins_hooks_warning_reverted_kept_english(self):
        # Round-27 gate-1 miss, reverted like round 26's reverts:
        # test_round26 pins "Plugin declares code hooks (" in
        # plugins.py source, and test_plugin_install:117 asserts
        # "code hooks" in the runtime warnings. The translation was
        # reverted, not the tests.
        warnings_out = _warnings_for_manifest(
            {"id": "demo", "hooks": ["on_clip"]},
            has_code_files=False)
        joined = " ".join(warnings_out)
        self.assertIn("Plugin declares code hooks (on_clip)", joined)
        self.assertIn("was NOT executed", joined)


class TestStderrPipesClosed(unittest.TestCase):
    def test_no_resource_warning_from_decode_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "tone.wav")
            _tone_wav(wav)
            with warnings.catch_warnings():
                warnings.simplefilter("error", ResourceWarning)
                decode_sound_levels(wav)
                align_sound(wav, wav)


class TestShowShortcutsStable(unittest.TestCase):
    def test_show_shortcuts_still_30_after_app_js_edits(self):
        server = MCPServer()
        result = server.call("vibeedit_show_shortcuts", {})
        self.assertEqual(len(result["shortcuts"]), 30)


class TestJsTranslations(unittest.TestCase):
    def test_js_translations_present(self):
        js = open(os.path.join(STATIC, "app.js"),
                  encoding="utf-8").read()
        for new in ("Chưa có transition nào.",
                    "Chưa có clip nào trên timeline.",
                    "Không gian làm việc: project"):
            self.assertIn(new, js)
        for old in ("No transitions yet.",
                    "No clips on the timeline yet.",
                    "Open project folder via"):
            self.assertNotIn(old, js)
        # The two list buttons (transitions, keyframes) now say Xóa;
        # the toolbar tooltip "Delete" (pinned by round 26) is a
        # different element (aria-label/data-tip) and stays.
        self.assertNotIn(">Remove</button>", js)
        self.assertNotIn(">Delete</button>", js)
        self.assertGreaterEqual(js.count(">Xóa</button>"), 2)


class TestOldEnglishGone(unittest.TestCase):
    def test_changed_sites_no_longer_carry_old_english(self):
        core = os.path.join(WIN, "vibeedit_core")
        gone = {
            "analysis.py": [
                "interval decode gave no frame pair",
                "no audio track, so there is nothing to",
                "Too little sound",
                "Quiet and loud windows are closer",
                "faster-whisper is not installed",
                "Transcription failed and was left empty",
                "Source frames at fps",
                "dBFS. Levels are RMS",
                "broadband RMS per",
            ],
            "export_ops.py": ["Media file not found on disk"],
            "mcp.py": ["Media file not found on disk"],
            # plugins.py has no round-27 translation left: the hooks
            # warning was reverted (see the test above).
            "project.py": ["Transition duration exceeds the shorter"],
            "render.py": ["Transition duration exceeds",
                          "probe failed",
                          "(no colour set)",
                          "(no media)"],
            "round8.py": [
                "Windows are timeline gaps",
                "Retention is in the",
                "Shot facts are caller-supplied",
                "No generated pictures are on the timeline",
                "loudnorm measurement failed",
                "No sound window passes",
                "Tempo detection unavailable",
                "Tempo is null",
                "No agent-kit releases channel",
                "Landmark gate uses",
            ],
            # The docstring still explains the inspector rule in
            # English prose; only the returned note literal changed.
            "round9.py": ["Inspector views follow the selection; "],
            "round15.py": ["minAppVersion gates"],
            "server.py": ["Unknown export job"],
            "skills.py": ["restore shipped skills"],
            "updater.py": ["updater channel configured"],
        }
        for fname, needles in gone.items():
            text = open(os.path.join(core, fname),
                        encoding="utf-8").read()
            for needle in needles:
                self.assertNotIn(needle, text,
                                 f"{fname} still has {needle!r}")


class TestDocsDriftFixed(unittest.TestCase):
    def test_parity_headline_and_table_current(self):
        text = open(os.path.join(WIN, "PARITY.md"),
                    encoding="utf-8").read()
        # Round-18 test pins this substring; the headline keeps it
        # while the counts move to the live values.
        self.assertIn("giao diện vòng 16–17", text)
        self.assertIn("MCP 481 công cụ", text)
        self.assertIn("432", text)
        self.assertIn("49 công cụ kiểm tra-và-báo-lỗi", text)
        self.assertIn(
            "MCP 481 công cụ (432 thao tác thật, "
            "49 kiểm tra-và-báo-lỗi)", text)

    def test_readme_has_rounds_23_to_27_and_full_port_title(self):
        text = open(os.path.join(WIN, "README.md"),
                    encoding="utf-8").read()
        for section in ("Vòng 23", "Vòng 24", "Vòng 25", "Vòng 26",
                        "Vòng 27"):
            self.assertIn(section, text)
        # Only the title line must drop the phrase: the historical
        # "What Phase 8 adds" section body keeps it legitimately.
        title = text.splitlines()[0]
        self.assertNotIn("final planned phase", title)
        self.assertIn("chuyển toàn bộ", title)

    def test_checklist_registry_line_and_new_items(self):
        text = open(os.path.join(WIN, "WINDOWS_TEST_CHECKLIST.md"),
                    encoding="utf-8").read()
        self.assertNotIn("không có registry nào tồn tại", text)
        for needle in ("thanh-hai-learn-ai-2d-studio",
                       "không còn file .lock",
                       "Chẩn đoán xuất",
                       "tiếng Việt"):
            self.assertIn(needle, text)

    def test_ui_map_has_round_27_note(self):
        text = open(os.path.join(WIN, "UI_MAP.md"),
                    encoding="utf-8").read()
        self.assertIn("Vòng 27", text)


if __name__ == "__main__":
    unittest.main()
