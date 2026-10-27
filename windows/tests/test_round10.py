"""Round 10: freeze trim-rounding fix (bug found in round 9).

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

Round 9 found: the freeze path trimmed one source frame with
``trim=start={:.3f}``. At 30 fps the last frame's timestamp
(29/30 = 0.9667 s) rounds UP to "0.967", past the frame itself,
so trim drops it: the freeze segment renders 0 frames and the
output file is shorter than the report claims (report 2.0 s,
file 1.0 s in round 9's case). The same rounding hits the main
video path for any clip starting on a frame that does not land
on a millisecond boundary (frame 29 at 30 fps). Both paths now
use an exact frame-index trim (see _frame_trim in render.py),
which reproduces trim's [start, end) timestamp semantics for
CFR media without the millisecond rounding.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import probe_media, render  # noqa: E402


def _red_blue_clip(tmp):
    """30 fps, 2 s: red 1 s (frames 0-29) then blue 1 s (30-59)."""
    src = os.path.join(tmp, "clip.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i",
         "color=c=red:size=320x180:rate=30:duration=1",
         "-f", "lavfi", "-i",
         "color=c=blue:size=320x180:rate=30:duration=1",
         "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
         "-pix_fmt", "yuv420p", src],
        capture_output=True, check=True)
    return src


def _project_with_clip(tmp, at=0, start=0, dur=60):
    src = _red_blue_clip(tmp)
    proj = Project(new_project("round10", width=320, height=180,
                               fps=(30, 1)), tmp)
    info = probe_media(src)
    medium = proj.add_media("clip.mp4", kind="video", **info)
    clip = proj.add_clip(medium["id"], "v1", at, start, dur)
    return proj, clip


def _frame_count_and_duration(path):
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames",
         "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1", path],
        capture_output=True, text=True, check=True)
    frames = duration = None
    for line in probe.stdout.splitlines():
        key, _, value = line.partition("=")
        if key == "nb_read_frames":
            frames = int(value)
        elif key == "duration":
            duration = float(value)
    return frames, duration


def _grab_frame(video, when, out):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(when),
         "-i", video, "-frames:v", "1", out],
        capture_output=True, check=True)
    return Image.open(out).convert("RGB")


class TestFreezeTrimRounding(unittest.TestCase):
    def test_freeze_last_frame_30fps(self):
        # Round 9's case, generalised: 60-frame clip + 30-frame
        # freeze of its last frame (59/30 = 1.9667 s, which the
        # old 3-decimal trim rounded up to "1.967", dropping it).
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _project_with_clip(tmp)
            frozen = proj.freeze_clip(clip["id"], 30)
            self.assertEqual(frozen["in"], 59)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["duration"], 3.0)
            frames, duration = _frame_count_and_duration(out)
            self.assertEqual(frames, 90)
            self.assertAlmostEqual(duration, 3.0, delta=0.1)
            # The held frame is the last (blue) frame, not red and
            # not missing: a frame exists at 2.5 s and is blue.
            frame = _grab_frame(out, 2.5, os.path.join(tmp, "f.png"))
            px = frame.getpixel((80, 45))
            self.assertGreater(px[2], 180)
            self.assertLess(px[0], 60)

    def test_freeze_with_backdrop_30fps(self):
        # Same freeze at 30 fps, with a backdrop: the backdrop
        # branch reuses the freeze trim, so it must hold too.
        with tempfile.TemporaryDirectory() as tmp:
            proj, clip = _project_with_clip(tmp)
            proj.set_backdrop(clip["id"],
                              {"kind": "color", "color": "#00FF00"})
            proj.freeze_clip(clip["id"], 30)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            frames, duration = _frame_count_and_duration(out)
            self.assertEqual(frames, 90)
            self.assertAlmostEqual(duration, 3.0, delta=0.1)

    def test_main_clip_starting_on_non_ms_frame(self):
        # Main video path, same rounding class: a clip starting
        # at frame 29 (0.9667 s) for 30 frames must render all
        # 30 frames, starting with the red frame 29 — the old
        # trim dropped frame 29 and started on blue frame 30.
        with tempfile.TemporaryDirectory() as tmp:
            proj, _ = _project_with_clip(tmp, start=29, dur=30)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            frames, duration = _frame_count_and_duration(out)
            self.assertEqual(frames, 30)
            self.assertAlmostEqual(duration, 1.0, delta=0.1)
            frame = _grab_frame(out, 0.0, os.path.join(tmp, "f.png"))
            px = frame.getpixel((80, 45))
            self.assertGreater(px[0], 180)
            self.assertLess(px[2], 60)
