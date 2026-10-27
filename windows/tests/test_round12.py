"""Round 12: overlay enable windows must be half-open [start, end).

Round 11 left this open on purpose: every enable window in render.py
used FFmpeg between(t, start, end), which is inclusive on BOTH ends,
and the overlay filter repeats its last frame on EOF, so an overlay
still showed one repeated frame at exactly its end time — even for
millisecond-exact durations. Round 12 first read the original spec
and only then fixed it:

- Original: every video item (main AND overlay tracks) is placed
  with CMTimeRange(start: destination, duration: fps.time(duration))
  (CompositionBuilder.swift ~155, ~215), CMTimeRange is half-open
  [start, start+duration) by definition, item.end is defined as
  at + duration (Project.swift:99), and a lane is reused when
  prev.end <= start (VideoCompositionLanes.swift: take) — i.e. the
  frame at `end` belongs to the NEXT item, never to this one.
- Windows port before this round: between() inclusive, so the
  frame at t=end showed the overlay's last frame once more.

Repro (fail BEFORE the fix, pass AFTER it), all at 30 fps, main
track 90 frames so the frame AFTER the window exists to inspect:
- Plain overlay video, 30 frames: output frame 30 must be main
  only (gray), not the overlay's repeated red frame.
- Plain overlay video, 29 frames (end 29/30 = 0.9667 s, NOT a
  millisecond mark): output frame 29 must be main only. This also
  catches .3f rounding of the end UP to "0.967", which would
  re-include the boundary frame even with a half-open operator.
- Opacity-split overlay video, 30 frames: same frame-30 check
  through the per-segment path.
- Still-image overlay, 30 frames: same frame-30 check.
- Adjustment layer (mono over red), 30 frames: frame 30 must be
  pure red again, frames 0..29 grayscale.
- Text overlay, 30 frames: no text pixel at frame 30.
- Helper unit test: _enable_window truncates (never rounds up)
  the end, so 29/30 formats as 0.966666, not 0.966667.

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).
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


def _is_red(px):
    return px[0] > 180 and px[1] < 80 and px[2] < 80


def _is_gray(px):
    return max(px) - min(px) < 30 and 80 < px[0] < 180


def _base_project(tmp, main_color="gray"):
    main_src = _color_clip(tmp, "main.mp4", [(main_color, 90)])
    proj = Project(new_project("round12", width=320,
                               height=180, fps=(30, 1)), tmp)
    main = _add_clip_media(proj, main_src, "main.mp4")
    proj.add_clip(main["id"], "v1", 0, 0, 90)
    return proj


def _video_overlay_project(tmp, dur, opacity_keyframes=False):
    proj = _base_project(tmp)
    ov_src = _color_clip(tmp, "ov.mp4", [("red", 60)])
    ov = _add_clip_media(proj, ov_src, "ov.mp4")
    item = proj.add_clip(ov["id"], "v2", 0, 0, dur)
    if opacity_keyframes:
        proj.add_keyframe(item["id"], 0.0, "opacity", 1.0)
        proj.add_keyframe(item["id"], 0.5, "opacity", 1.0)
    return proj


class TestOverlayEnableHalfOpen(unittest.TestCase):
    def test_plain_overlay_30_frames_ends_at_frame_30(self):
        # Millisecond-exact end (30/30 = 1.000 s): the old
        # between() showed the red overlay once more at frame 30.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _video_overlay_project(tmp, 30)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["overlay_clips"], 1)
            self.assertTrue(_is_red(_grab_frame(
                out, 0.0, os.path.join(tmp, "f0.png")).getpixel((80, 45))))
            self.assertTrue(_is_red(_grab_frame(
                out, 29 / 30.0, os.path.join(tmp, "f29.png")).getpixel((80, 45))))
            # Frame 30 is the first frame AFTER the window: main only.
            self.assertTrue(_is_gray(_grab_frame(
                out, 30 / 30.0, os.path.join(tmp, "f30.png")).getpixel((80, 45))))

    def test_plain_overlay_29_frames_non_ms_end(self):
        # End 29/30 = 0.9667 s: .3f rounding UP to "0.967" would
        # re-include frame 29 even with a half-open operator, so
        # the end must be truncated, never rounded up.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _video_overlay_project(tmp, 29)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertTrue(_is_red(_grab_frame(
                out, 28 / 30.0, os.path.join(tmp, "f28.png")).getpixel((80, 45))))
            self.assertTrue(_is_gray(_grab_frame(
                out, 29 / 30.0, os.path.join(tmp, "f29.png")).getpixel((80, 45))))

    def test_opacity_split_overlay_ends_at_frame_30(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _video_overlay_project(tmp, 30, opacity_keyframes=True)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["overlay_clips"], 2)
            self.assertTrue(_is_gray(_grab_frame(
                out, 30 / 30.0, os.path.join(tmp, "f30.png")).getpixel((80, 45))))

    def test_still_overlay_ends_at_frame_30(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _base_project(tmp)
            still_path = os.path.join(tmp, "still.png")
            Image.new("RGB", (320, 180), (255, 0, 0)).save(still_path)
            still = proj.add_media("still.png", kind="image",
                                   width=320, height=180)
            proj.add_clip(still["id"], "v2", 0, 0, 30)
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertTrue(_is_red(_grab_frame(
                out, 0.0, os.path.join(tmp, "f0.png")).getpixel((80, 45))))
            self.assertTrue(_is_gray(_grab_frame(
                out, 30 / 30.0, os.path.join(tmp, "f30.png")).getpixel((80, 45))))

    def test_adjustment_layer_ends_at_frame_30(self):
        # Mono over red: frames 0..29 grayscale, frame 30 pure red.
        with tempfile.TemporaryDirectory() as tmp:
            proj = _base_project(tmp, main_color="red")
            proj.add_adjustment(0, 30, preset="mono")
            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertEqual(report["adjustment_layers"], 1)
            px0 = _grab_frame(out, 0.0, os.path.join(tmp, "f0.png")).getpixel((80, 45))
            self.assertLess(max(px0) - min(px0), 30)
            px30 = _grab_frame(out, 30 / 30.0, os.path.join(tmp, "f30.png")).getpixel((80, 45))
            self.assertTrue(_is_red(px30))

    def test_text_overlay_ends_at_frame_30(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = _base_project(tmp, main_color="black")
            proj.add_text("t1", "X", 0, 30, size=0.5,
                          position_x=0.5, position_y=0.5)

            def _bright_in_box(video, when, name):
                # Draft preset renders at half resolution (160x90
                # for a 320x180 project); scan around the centre.
                frame = _grab_frame(video, when, os.path.join(tmp, name))
                best = 0
                for x in range(55, 106, 5):
                    for y in range(20, 71, 5):
                        best = max(best, max(frame.getpixel((x, y))))
                return best

            out = os.path.join(tmp, "out.mp4")
            report = render(proj.data, tmp, out, preset="draft")
            self.assertEqual(report["skipped"], [])
            self.assertGreater(_bright_in_box(out, 0.0, "f0.png"), 200)
            self.assertLess(_bright_in_box(out, 30 / 30.0, "f30.png"), 40)


class TestEnableWindowHelper(unittest.TestCase):
    def test_half_open_and_truncated_end(self):
        from vibeedit_core.render import _enable_window
        # Half-open: start inclusive, end exclusive.
        self.assertEqual(_enable_window(0.0, 1.0),
                         "gte(t,0.000000)*lt(t,1.000000)")
        # 29/30 s truncated to 0.966666, never rounded up to
        # 0.966667 (which is past the boundary frame's timestamp).
        self.assertEqual(_enable_window(0.0, 29 / 30.0),
                         "gte(t,0.000000)*lt(t,0.966666)")
        # A start on a non-millisecond frame is truncated down, so
        # the first frame is not dropped by a rounded-up start.
        self.assertEqual(_enable_window(2 / 30.0, 1.0),
                         "gte(t,0.066666)*lt(t,1.000000)")


if __name__ == "__main__":
    unittest.main()
