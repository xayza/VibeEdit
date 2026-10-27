"""Round 11: frame-exact trim for overlay video + transition windows.

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

Round 10 fixed the same .3f rounding class for freeze and the main
video path (trim=start={:.3f} rounds 29/30 = 0.9667 s UP to
"0.967", past the frame itself, dropping it). Round 10 left two
families open: overlay video trims (render.py ~2022, ~2060) and
transition-window trims (~1133-1266). This file reproduces them
BEFORE the fix and proves them gone AFTER it:

- Overlay (plain path, ~2060): an overlay clip starting at
  source frame 29 for 30 frames must show source frame 29 (red)
  as its first frame. The old trim dropped frame 29, so the
  overlay started on blue frame 30.
- Overlay (opacity-split path, ~2022): the same first-frame
  check with two opacity keyframes, which routes through the
  per-segment sub_src trim.
- Transition chain splits (~1246-1266, dip-black): outgoing
  58 frames + incoming 60 frames with a 29-frame dip-black
  transition must render exactly 89 frames (58 + 60 - 29).
  The old .3f splits gave pre 30 (one extra), tail 28 (one
  short), head 30 (one extra), post 30 (one short) and a
  30-frame segment, for 90 frames total.
- Transition content shift (spin): the same 58/60/29 geometry
  with a spin transition, where the incoming clip's frame 29
  is the only white frame. After the fix it lands at output
  frame 58 (pre 29 + segment 29); before the fix output frame
  58 is a blended segment frame or the wrong post frame.

The dip-black INNER split (half = trans_s / 2, ~1133-1138)
is deliberately NOT changed: a half-frame split point is
16.7 ms from its neighbouring frame boundaries at 30 fps,
far more than the 0.5 ms rounding error, so the .3f trim and
the frame trim select identical frames there (proven by the
dip-black count test passing with only the chain splits
fixed). Audio atrim is untouched on purpose (continuous
timestamps; sub-millisecond error cannot drop a frame).
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


def _color_clip(tmp, name, segments):
    """30 fps clip from (color, frames) segments, concatenated."""
    inputs = []
    for color, frames in segments:
        inputs += ["-f", "lavfi", "-i",
                   f"color=c={color}:size=320x180:rate=30:"
                   f"duration={frames / 30.0}"]
    n = len(segments)
    filt = "".join(f"[{i}:v]" for i in range(n)) + \
        f"concat=n={n}:v=1:a=0"
    src = os.path.join(tmp, name)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs,
                    "-filter_complex", filt,
                    "-pix_fmt", "yuv420p", src],
                   capture_output=True, check=True)
    return src


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


def _add_clip_media(proj, src, name):
    info = probe_media(src)
    info["hasAudio"] = False
    return proj.add_media(name, kind="video", **info)


class TestOverlayVideoTrimRounding(unittest.TestCase):
    def _overlay_project(self, tmp, opacity_keyframes=False):
        # Main: solid gray, 90 frames. Overlay source: red frames
        # 0-29, blue from frame 30, so source frame 29 (timestamp
        # 29/30 = 0.9667 s, the non-millisecond boundary frame) is
        # the last red frame and frame 30 is blue.
        main_src = _color_clip(tmp, "main.mp4", [("gray", 90)])
        ov_src = _color_clip(tmp, "ov.mp4", [("red", 30), ("blue", 30)])
        proj = Project(new_project("round11-ov", width=320,
                                   height=180, fps=(30, 1)), tmp)
        main = _add_clip_media(proj, main_src, "main.mp4")
        ov = _add_clip_media(proj, ov_src, "ov.mp4")
        proj.add_clip(main["id"], "v1", 0, 0, 90)
        item = proj.add_clip(ov["id"], "v2", 0, 29, 30)
        if opacity_keyframes:
            proj.add_keyframe(item["id"], 0.0, "opacity", 1.0)
            proj.add_keyframe(item["id"], 0.5, "opacity", 1.0)
        return proj

    def test_overlay_starts_on_non_ms_source_frame(self):
        # Plain path (~2060): first overlay frame must be source
        # frame 29 (red), not frame 30 (blue).
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._overlay_project(tmp)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["overlay_clips"], 1)
            frame = _grab_frame(out, 0.0, os.path.join(tmp, "f.png"))
            px = frame.getpixel((80, 45))
            self.assertGreater(px[0], 180)
            self.assertLess(px[2], 60)

    def test_overlay_opacity_split_starts_on_non_ms_source_frame(self):
        # Opacity-split path (~2022): same first-frame check with
        # two opacity keyframes (segments at 0-0.5 s, 0.5-1 s).
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._overlay_project(tmp, opacity_keyframes=True)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            # Two opacity segments -> two overlay composites.
            self.assertEqual(report["overlay_clips"], 2)
            frame = _grab_frame(out, 0.0, os.path.join(tmp, "f.png"))
            px = frame.getpixel((80, 45))
            self.assertGreater(px[0], 180)
            self.assertLess(px[2], 60)


class TestTransitionWindowTrimRounding(unittest.TestCase):
    def _two_clip_project(self, tmp, kind, b_segments):
        # A: 58 frames, colour change exactly at frame 29 (the
        # boundary frame the chain split must hand to the tail).
        # B: 60 frames; frame 29 is the marker for the spin test.
        a_src = _color_clip(tmp, "a.mp4", [("red", 29), ("blue", 29)])
        b_src = _color_clip(tmp, "b.mp4", b_segments)
        proj = Project(new_project("round11-tr", width=320,
                                   height=180, fps=(30, 1)), tmp)
        med_a = _add_clip_media(proj, a_src, "a.mp4")
        med_b = _add_clip_media(proj, b_src, "b.mp4")
        clip_a = proj.add_clip(med_a["id"], "v1", 0, 0, 58)
        clip_b = proj.add_clip(med_b["id"], "v1", 58, 0, 60)
        proj.data["transitions"].append({
            "id": "tr-11", "kind": kind,
            "from": clip_a["id"], "to": clip_b["id"],
            "duration": 29})
        return proj

    def test_dip_black_chain_split_frame_count(self):
        # 58 + 60 - 29 = 89 frames. The old splits rendered 90.
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._two_clip_project(
                tmp, "dip-black", [("yellow", 30), ("magenta", 30)])
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            frames, duration = _frame_count_and_duration(out)
            self.assertEqual(frames, 89)
            self.assertAlmostEqual(duration, 89 / 30.0, delta=0.1)
            self.assertAlmostEqual(report["duration"], 89 / 30.0,
                                   delta=0.05)

    def test_spin_post_segment_starts_on_correct_frame(self):
        # B's only white frame is its frame 29. After the fix it
        # is the first post frame: output frame 58 (pre 29 +
        # segment 29). Before the fix output frame 58 is a
        # blended segment frame or the wrong post frame.
        with tempfile.TemporaryDirectory() as tmp:
            proj = self._two_clip_project(
                tmp, "spin", [("black", 29), ("white", 1),
                              ("black", 30)])
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            frames, _ = _frame_count_and_duration(out)
            self.assertEqual(frames, 89)
            frame = _grab_frame(out, 58 / 30.0,
                                os.path.join(tmp, "f.png"))
            px = frame.getpixel((80, 45))
            self.assertGreater(px[0], 200)
            self.assertGreater(px[1], 200)
            self.assertGreater(px[2], 200)
