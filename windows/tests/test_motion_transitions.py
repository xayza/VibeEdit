"""Phase B6 motion-transition tests: real FFmpeg renders for every
newly implemented motion kind, a clear-error test for every kind
that still cannot render, a no-duplicates test for the transition
list, and reframe tests.

Renderability honesty (see vibeedit_core/render.py):
- MOTION_TRANSITIONS kinds render with real filter chains (rotate,
  zoom-overlay, geq diamond mask, hue, strobe, mirrored tile), not
  plain xfade substitutions. The dissolve in several chains is only
  the blend between two motion-transformed pictures.
- kaleidoscope is a 2x2 mirrored-tile + rotation approximation, NOT
  a true six-way hexagonal kaleidoscope (no FFmpeg filter does that);
  it is named as such in render.py and here.
- swing rotates about the centre (FFmpeg rotate has no left-edge
  perspective pivot), not a true left-edge swing.
- Round 4: halftone now renders (geq dot mask + maskedmerge in the
  timeline render, plus the Pillow pre-rendered segment in
  test_round4_halftone.py) and is no longer in the unrenderable
  set; the unrenderable tests below now iterate whatever (if
  anything) remains unrenderable, and must never fall back to
  dissolve/fade.

Wiring note: Project.add_transition() in project.py does NOT yet
accept the motion kinds (that file belongs to another agent in this
batch), so these tests build the transitions entry directly on the
project dict — exactly what render() consumes — rather than going
through add_transition(). Once project.py's registry is updated,
the same renders should also work through the API.

Run from windows/:  python3 -m unittest discover -s tests -v (Linux)
  / py -m unittest discover -s tests -v (Windows)
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import (  # noqa: E402
    MOTION_TRANSITIONS, UNRENDERABLE_TRANSITIONS,
    list_transition_renderability, probe_media, render,
    transition_renderability)

# The original's 39 built-in kinds (TransitionMotion.groups, read
# from the Swift tree; the Windows xfade registry already covers
# most of them, this batch covers the motion remainder).
ORIGINAL_39 = [
    "dissolve", "blink", "flash", "dip-black", "double-exposure",
    "whip", "whip-right", "whip-up", "whip-down",
    "wipe", "wipe-right", "wipe-up", "wipe-down", "barn-door",
    "shutter", "slide", "slide-up",
    "iris", "diamond",
    "zoom", "crash-zoom", "crash-out",
    "spin", "roll", "roll-right",
    "swing", "arc", "arc-right",
    "infinite-zoom", "infinite-out",
    "screen-in", "screen-out",
    "blur", "seamless-zoom",
    "glitch", "halftone", "flicker", "color-shift", "kaleidoscope",
]

EXPECTED_MOTION = {
    "spin", "swing", "arc", "arc-right", "diamond", "crash-out",
    "infinite-out", "screen-in", "screen-out", "dip-black",
    "color-shift", "flicker", "kaleidoscope",
}


def gen_clip(path, source, freq, seconds=2):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"{source}=size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def grab_frame(video, when, out):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(when),
         "-i", video, "-frames:v", "1", out],
        capture_output=True, check=True)
    return Image.open(out).convert("RGB").resize((64, 36))


def frame_mae(img_a, img_b):
    a, b = list(img_a.getdata()), list(img_b.getdata())
    total = 0
    for i in range(len(a)):
        for c in range(3):
            total += abs(a[i][c] - b[i][c])
    return total / (len(a) * 3)


class TestMotionTransitions(unittest.TestCase):
    def _two_clip_project(self, tmp, kind, clip_seconds=2,
                          trans_frames=30):
        """Two 2s clips back to back with ``kind`` between them.

        Output duration is 2 + 2 - 1 = 3s; the transition window in
        the output is 1..2s, its midpoint 1.5s. The outgoing tail
        midpoint corresponds to clip A at 1.5s, the incoming head
        midpoint to clip B at 0.5s.
        """
        gen_clip(os.path.join(tmp, "a.mp4"), "testsrc2", 440,
                 seconds=clip_seconds)
        gen_clip(os.path.join(tmp, "b.mp4"), "testsrc", 660,
                 seconds=clip_seconds)
        proj = Project(new_project("motion", width=320, height=180,
                                    fps=(30, 1)), tmp)
        info_a = probe_media(os.path.join(tmp, "a.mp4"))
        info_b = probe_media(os.path.join(tmp, "b.mp4"))
        med_a = proj.add_media("a.mp4", kind="video", **info_a)
        med_b = proj.add_media("b.mp4", kind="video", **info_b)
        frames = int(round(clip_seconds * 30))
        clip_a = proj.add_clip(med_a["id"], "v1", 0, 0, frames)
        clip_b = proj.add_clip(med_b["id"], "v1", frames, 0, frames)
        # Direct dict entry: Project.add_transition() does not yet
        # accept motion kinds (see module docstring).
        proj.data["transitions"].append({
            "id": "tr-motion", "kind": kind,
            "from": clip_a["id"], "to": clip_b["id"],
            "duration": trans_frames})
        return proj

    def _render_kind(self, tmp, kind, clip_seconds=2, trans_frames=30):
        proj = self._two_clip_project(tmp, kind, clip_seconds,
                                      trans_frames)
        out = os.path.join(tmp, f"out-{kind}.mp4")
        report = render(proj.data, tmp, out)
        self.assertTrue(os.path.isfile(out), f"no output for {kind}")
        expected = clip_seconds * 2 - trans_frames / 30.0
        self.assertAlmostEqual(report["duration"], expected, delta=0.05)
        info = probe_media(out)
        self.assertAlmostEqual(info["duration"], expected, delta=0.2)
        return out, expected

    def _assert_really_transitions(self, tmp, kind):
        out, _ = self._render_kind(tmp, kind)
        trans_mid_out = 1.5  # output time of transition midpoint
        pure_a = grab_frame(os.path.join(tmp, "a.mp4"), 1.5,
                            os.path.join(tmp, "pure-a.png"))
        pure_b = grab_frame(os.path.join(tmp, "b.mp4"), 0.5,
                            os.path.join(tmp, "pure-b.png"))
        mid = grab_frame(out, trans_mid_out,
                         os.path.join(tmp, "mid.png"))
        mae_a = frame_mae(mid, pure_a)
        mae_b = frame_mae(mid, pure_b)
        # A hard cut or a static picture would sit on (or very near)
        # one of the pure frames; a real transition frame is a
        # transformed/blended picture, clearly different from both.
        # Threshold 5 (of 255) is far below the observed margins
        # (tens to >100) but far above encode noise (~1).
        self.assertGreater(mae_a, 5,
                           f"{kind}: mid-transition frame too close "
                           f"to pure first clip (MAE {mae_a:.1f})")
        self.assertGreater(mae_b, 5,
                           f"{kind}: mid-transition frame too close "
                           f"to pure second clip (MAE {mae_b:.1f})")

    def test_motion_registry_matches_expected_set(self):
        self.assertEqual(set(MOTION_TRANSITIONS), EXPECTED_MOTION)

    def test_full_length_transition_renders(self):
        # Transition as long as both clips: empty pre/post parts
        # must be skipped, never concatenated as empty segments.
        tmp = tempfile.mkdtemp()
        try:
            out, _ = self._render_kind(tmp, "spin", clip_seconds=1,
                                       trans_frames=30)
            self.assertTrue(os.path.isfile(out))
            info = probe_media(out)
            self.assertAlmostEqual(info["duration"], 1.0, delta=0.2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_existing_xfade_kind_still_renders(self):
        tmp = tempfile.mkdtemp()
        try:
            out, _ = self._render_kind(tmp, "dissolve")
            self.assertTrue(os.path.isfile(out))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unrenderable_kinds_raise_clear_error_no_output(self):
        for kind, reason in UNRENDERABLE_TRANSITIONS.items():
            with self.subTest(kind=kind):
                tmp = tempfile.mkdtemp()
                try:
                    proj = self._two_clip_project(tmp, kind)
                    out = os.path.join(tmp, f"out-{kind}.mp4")
                    with self.assertRaises(ValueError) as ctx:
                        render(proj.data, tmp, out)
                    message = str(ctx.exception)
                    self.assertIn(kind, message)
                    # The reason must name the technical limitation,
                    # not just repeat the kind name.
                    self.assertTrue(len(message) > len(kind) + 20,
                                    f"error too vague for {kind}: "
                                    f"{message!r}")
                    self.assertIn("pre-rendered", message)
                    self.assertFalse(os.path.isfile(out),
                                     f"{kind} must not produce output")
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)

    def test_unknown_kind_still_raises(self):
        tmp = tempfile.mkdtemp()
        try:
            proj = self._two_clip_project(tmp, "no-such-kind")
            with self.assertRaises(ValueError) as ctx:
                render(proj.data, tmp, os.path.join(tmp, "out.mp4"))
            self.assertIn("Unknown transition kind", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_transition_list_no_duplicates_and_covers_original(self):
        records = list_transition_renderability()
        kinds = [r["kind"] for r in records]
        self.assertEqual(len(kinds), len(set(kinds)),
                         "duplicate kind names in transition list")
        for kind in ORIGINAL_39:
            self.assertIn(kind, kinds, f"original kind missing: {kind}")
        by_kind = {r["kind"]: r for r in records}
        for kind in EXPECTED_MOTION:
            self.assertTrue(by_kind[kind]["renders"],
                            f"{kind} should render in this batch")
            self.assertIsNotNone(by_kind[kind]["method"])
            self.assertIsNone(by_kind[kind]["reason"])
        for kind in UNRENDERABLE_TRANSITIONS:
            self.assertFalse(by_kind[kind]["renders"])
            self.assertIsNone(by_kind[kind]["method"])
            self.assertIn(kind, by_kind[kind]["reason"])
        self.assertTrue(by_kind["dissolve"]["renders"])
        self.assertTrue(by_kind["dissolve"]["method"].startswith("xfade:"))
        self.assertFalse(transition_renderability("nope")["renders"])

    def test_reframe_left_window_vs_right_window(self):
        tmp = tempfile.mkdtemp()
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi",
                 "-i", "color=c=red:s=160x180:r=30:d=2",
                 "-f", "lavfi",
                 "-i", "color=c=blue:s=160x180:r=30:d=2",
                 "-filter_complex", "[0:v][1:v]hstack",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 os.path.join(tmp, "split.mp4")],
                capture_output=True, check=True)
            for name, window, expect_red in [
                    ("left", {"x": 0, "y": 0, "w": 0.5, "h": 1}, True),
                    ("right", {"x": 0.5, "y": 0, "w": 0.5, "h": 1},
                     False)]:
                proj = Project(new_project("reframe", width=320,
                                            height=180, fps=(30, 1)),
                               tmp)
                info = probe_media(os.path.join(tmp, "split.mp4"))
                medium = proj.add_media("split.mp4", kind="video",
                                        **info)
                clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
                clip["reframe"] = window
                out = os.path.join(tmp, f"reframe-{name}.mp4")
                render(proj.data, tmp, out)
                frame = grab_frame(out, 1.0,
                                   os.path.join(tmp, f"{name}.png"))
                pixels = list(frame.getdata())
                mean_r = sum(p[0] for p in pixels) / len(pixels)
                mean_b = sum(p[2] for p in pixels) / len(pixels)
                if expect_red:
                    self.assertGreater(mean_r, mean_b + 50,
                                       "left reframe should be red")
                else:
                    self.assertGreater(mean_b, mean_r + 50,
                                       "right reframe should be blue")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_reframe_invalid_window_raises(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_clip(os.path.join(tmp, "a.mp4"), "testsrc2", 440)
            proj = Project(new_project("reframe-bad", width=320,
                                        height=180, fps=(30, 1)), tmp)
            info = probe_media(os.path.join(tmp, "a.mp4"))
            medium = proj.add_media("a.mp4", kind="video", **info)
            clip = proj.add_clip(medium["id"], "v1", 0, 0, 60)
            clip["reframe"] = {"x": 0.8, "y": 0, "w": 0.5, "h": 1}
            with self.assertRaises(ValueError) as ctx:
                render(proj.data, tmp, os.path.join(tmp, "out.mp4"))
            self.assertIn("reframe", str(ctx.exception))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _make_render_test(kind):
    def test(self):
        tmp = tempfile.mkdtemp()
        try:
            self._assert_really_transitions(tmp, kind)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    test.__name__ = f"test_render_{kind.replace('-', '_')}"
    test.__doc__ = (f"Real FFmpeg render for motion kind {kind!r}: "
                    "output exists, duration correct, and the "
                    "mid-transition frame differs from both pure "
                    "clip frames.")
    return test


# One real-render test method per newly implemented kind, so a
# failure names the kind that broke.
for _kind in sorted(MOTION_TRANSITIONS):
    setattr(TestMotionTransitions,
            f"test_render_{_kind.replace('-', '_')}",
            _make_render_test(_kind))


if __name__ == "__main__":
    unittest.main()
