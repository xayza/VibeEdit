"""Round 25 tests: cross-process project file lock + export diagnostics.

(A) File locking. Round 22 fixed the SEQUENTIAL interleave (MCP edit
then web edit, or the reverse, both survive via refresh_from_disk).
What remained was TRUE SIMULTANEOUS writes: both writers read rev N,
mutate, and write rev N+1, losing one update. save_project() was
already atomic (temp + replace), but that only prevents torn files,
not lost updates. The lock (vibeedit_core/filelock.py, O_CREAT|O_EXCL
so it works on Windows and Linux with stdlib only) wraps
[refresh, mutate, save] on both paths: State.apply/undo/redo/save and
the upload/voiceover/plugin endpoints on the web side, and
MCPServer.call on the MCP side. Tests below prove, with real threads
AND real separate processes, that interleaved markers_add-style and
web-apply-style mutations lose nothing and rev stays monotonic, that
a timeout fails loudly, and that a stale lock never wedges the app.

(B) Export-report diagnostics. The round-22 duration_check compares
the container duration with the timeline, which cannot show a
video/audio split — the user's 330s file had video 330.16s against
audio 226.86s. The report now also carries the exact FFmpeg command,
the full filter graph, the -shortest flag, the audio map, a per-clip
source-vs-project fps list, and ffprobe-measured output video/audio
durations side by side. Report-only: render output is unchanged.

No registry change is expected in this round (no new tools, no
conversions): the registry count is pinned here at 481 = 432/49.
"""

import multiprocessing
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.filelock import (  # noqa: E402
    ProjectFileLock, ProjectLockTimeout)
from vibeedit_core.mcp import MCPServer, TOOLS  # noqa: E402
from vibeedit_core.project import (  # noqa: E402
    PROJECT_FILENAME, Project, load_project, new_project, save_project)
from vibeedit_core.render import _attach_duration_check, render  # noqa: E402
from vibeedit_core.server import State  # noqa: E402


def _setup(tmp, name="t1"):
    proj = Project(new_project(name), tmp)
    proj.add_media(os.path.join(tmp, "x.mp4"), "video")
    save_project(proj.data, os.path.join(tmp, PROJECT_FILENAME))
    return proj


def _disk(tmp):
    return load_project(os.path.join(tmp, PROJECT_FILENAME))


def _mp_markers(tmp, tag, count):
    """Multiprocessing worker (top level so spawn can import it)."""
    server = MCPServer(tmp)
    for i in range(count):
        server.call("vibeedit_markers_add",
                    {"text": f"{tag}-{i}", "at": i})


class TestRound25Lock(unittest.TestCase):
    def test_acquire_release_removes_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, PROJECT_FILENAME)
            with open(proj, "w") as fh:
                fh.write("{}")
            lock = ProjectFileLock(proj)
            self.assertFalse(lock.locked)
            with lock:
                self.assertTrue(lock.locked)
                self.assertTrue(os.path.isfile(proj + ".lock"))
            self.assertFalse(lock.locked)
            self.assertFalse(os.path.exists(proj + ".lock"))

    def test_timeout_raises_clear_error(self):
        # The contender must be a DIFFERENT thread: same-thread
        # re-acquisition is deliberately re-entrant (see
        # test_same_thread_reentry_deepens).
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, PROJECT_FILENAME)
            with open(proj, "w") as fh:
                fh.write("{}")
            errors = []

            def contender():
                try:
                    with ProjectFileLock(proj, timeout=0.3, poll=0.02):
                        pass
                except Exception as exc:  # noqa: BLE001 - collected
                    errors.append(exc)

            with ProjectFileLock(proj):
                start = time.monotonic()
                worker = threading.Thread(target=contender)
                worker.start()
                worker.join()
                self.assertLess(time.monotonic() - start, 5.0)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ProjectLockTimeout)
            self.assertIn("Could not acquire project lock", str(errors[0]))
            self.assertIn(".lock", str(errors[0]))

    def test_stale_lock_is_reaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, PROJECT_FILENAME)
            with open(proj, "w") as fh:
                fh.write("{}")
            lock_path = proj + ".lock"
            with open(lock_path, "w") as fh:
                fh.write("999999:dead-holder")
            old = time.time() - 3600
            os.utime(lock_path, (old, old))
            with ProjectFileLock(proj, stale_after=60.0):
                pass
            self.assertFalse(os.path.exists(lock_path))

    def test_release_on_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, PROJECT_FILENAME)
            with open(proj, "w") as fh:
                fh.write("{}")
            with self.assertRaises(RuntimeError):
                with ProjectFileLock(proj):
                    raise RuntimeError("boom")
            self.assertFalse(os.path.exists(proj + ".lock"))

    def test_same_thread_reentry_deepens(self):
        # Round 25 fix for a real full-suite failure: plan_apply
        # dispatches to timeline_apply through MCPServer.call while
        # already holding the lock. Same-thread re-entry must deepen
        # the count, not wait out its own timeout, and the file must
        # survive until the outermost release.
        with tempfile.TemporaryDirectory() as tmp:
            proj = os.path.join(tmp, PROJECT_FILENAME)
            with open(proj, "w") as fh:
                fh.write("{}")
            with ProjectFileLock(proj):
                with ProjectFileLock(proj, timeout=1.0):
                    self.assertTrue(os.path.isfile(proj + ".lock"))
                self.assertTrue(os.path.isfile(proj + ".lock"))
            self.assertFalse(os.path.exists(proj + ".lock"))

    def test_validation_fails_before_lock_wait(self):
        # Round-24 fail-fast validation must still run before any
        # lock wait: a bad call under a held lock errors at once,
        # it does not sit out the 10s timeout.
        with tempfile.TemporaryDirectory() as tmp:
            _setup(tmp)
            server = MCPServer(tmp)
            with ProjectFileLock(os.path.join(tmp, PROJECT_FILENAME)):
                start = time.monotonic()
                with self.assertRaises(ValueError):
                    server.call("vibeedit_markers_add", {})
                self.assertLess(time.monotonic() - start, 5.0)


class TestRound25Concurrent(unittest.TestCase):
    def test_threads_mixed_writers_no_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup(tmp)
            start_rev = _disk(tmp)["rev"]
            errors = []

            def mcp_writer(tag):
                try:
                    server = MCPServer(tmp)
                    for i in range(5):
                        server.call("vibeedit_markers_add",
                                    {"text": f"{tag}-{i}", "at": i})
                except Exception as exc:  # noqa: BLE001 - collected
                    errors.append(exc)

            def web_writer(tag, base):
                try:
                    state = State(tmp)
                    for i in range(5):
                        state.apply({"op": "add_text", "track": "t1",
                                     "text": f"{tag}-{i}",
                                     "at": base + i * 100, "dur": 30})
                except Exception as exc:  # noqa: BLE001 - collected
                    errors.append(exc)

            threads = [threading.Thread(target=mcp_writer, args=(f"m{i}",))
                       for i in range(2)]
            threads += [threading.Thread(target=web_writer,
                                         args=(f"w{i}", 1000 + i * 10000))
                        for i in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            final = _disk(tmp)
            markers = {m["text"] for m in final.get("markers", [])}
            texts = {it.get("text") for tr in final["tracks"]
                     for it in tr["items"] if it.get("text")}
            self.assertEqual(len(markers), 10)
            self.assertEqual(len(texts), 10)
            # No lost rev bumps: every op bumped exactly once.
            self.assertEqual(final["rev"], start_rev + 20)
            self.assertFalse([f for f in os.listdir(tmp)
                              if f.endswith(".lock")])

    def test_processes_no_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup(tmp)
            start_rev = _disk(tmp)["rev"]
            ctx = multiprocessing.get_context()
            procs = [ctx.Process(target=_mp_markers,
                                 args=(tmp, f"p{i}", 4))
                     for i in range(3)]
            for p in procs:
                p.start()
            for p in procs:
                p.join(timeout=60)
            for p in procs:
                self.assertEqual(p.exitcode, 0)
            final = _disk(tmp)
            markers = {m["text"] for m in final.get("markers", [])}
            self.assertEqual(len(markers), 12)
            self.assertEqual(final["rev"], start_rev + 12)
            self.assertFalse([f for f in os.listdir(tmp)
                              if f.endswith(".lock")])


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args],
                   capture_output=True, check=True)


def _video(tmp, name, rate, with_audio):
    src = ["-f", "lavfi", "-i",
           f"testsrc=duration=2:size=320x180:rate={rate}"]
    if with_audio:
        src += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    _ffmpeg(*src, "-c:v", "libx264", "-pix_fmt", "yuv420p",
            *([ "-c:a", "aac", "-shortest"] if with_audio else []),
            os.path.join(tmp, name))


class TestRound25Report(unittest.TestCase):
    def test_report_has_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            _video(tmp, "silent.mp4", "30", False)
            proj = Project(new_project("t1", width=320, height=180,
                                       fps=(30, 1)), tmp)
            medium = proj.add_media("silent.mp4", kind="video")
            proj.add_clip(medium["id"], "v1", 0, 0, 60)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            cmd = report["ffmpeg_command"]
            self.assertIsInstance(cmd, list)
            self.assertIn("ffmpeg", cmd[0])
            self.assertIn("-filter_complex", cmd)
            self.assertIsInstance(report["filter_complex"], str)
            self.assertTrue(report["filter_complex"])
            self.assertEqual(report["shortest"], "-shortest" in cmd)
            self.assertIn("audio_map", report)
            clips = report["clip_fps"]
            self.assertEqual(len(clips), 1)
            # Unprobed record: source fps honestly unknown, render
            # falls back to the project fps (effective_fps).
            self.assertIsNone(clips[0]["source_fps"])
            self.assertFalse(clips[0]["source_fps_known"])
            self.assertEqual(clips[0]["project_fps"], 30.0)
            self.assertEqual(clips[0]["effective_fps"], 30.0)
            durations = report["output_durations"]
            self.assertAlmostEqual(durations["video_s"], 2.0, delta=0.3)
            self.assertIsNotNone(durations["audio_s"])
            self.assertAlmostEqual(durations["audio_s"], 2.0, delta=0.5)
            self.assertIsNone(report["duration_check"]["warning"])

    def test_report_fps_mismatch_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            _video(tmp, "fast.mp4", "60000/1001", True)
            proj = Project(new_project("t1", width=320, height=180,
                                       fps=(30000, 1001)), tmp)
            medium = proj.add_media("fast.mp4", kind="video",
                                    fps=[60000, 1001], frames=120,
                                    duration=2.0, hasAudio=True)
            proj.add_clip(medium["id"], "v1", 0, 0, 60)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            clips = report["clip_fps"]
            self.assertEqual(len(clips), 1)
            self.assertAlmostEqual(clips[0]["source_fps"], 59.94,
                                   delta=0.01)
            self.assertAlmostEqual(clips[0]["project_fps"], 29.97,
                                   delta=0.01)
            self.assertNotAlmostEqual(clips[0]["source_fps"],
                                      clips[0]["project_fps"], delta=0.01)

    def test_duration_warning_still_fires(self):
        with tempfile.TemporaryDirectory() as tmp:
            _video(tmp, "two.mp4", "30", False)
            report = {"duration": 10.0}
            _attach_duration_check(report, os.path.join(tmp, "two.mp4"))
            self.assertIsNotNone(report["duration_check"]["warning"])
            self.assertAlmostEqual(report["duration_check"]["file_s"],
                                   2.0, delta=0.3)


class TestRound25RegistryUnchanged(unittest.TestCase):
    def test_counts_still_481_432_49(self):
        honest = [t for t in TOOLS
                  if t["description"].startswith("Not available")]
        self.assertEqual(len(TOOLS), 481)
        self.assertEqual(len(TOOLS) - len(honest), 432)
        self.assertEqual(len(honest), 49)
