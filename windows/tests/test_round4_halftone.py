"""Round 4 task 4: halftone transition renders for real.

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

Two independent paths are tested:
1. Timeline render: the geq dot mask + maskedmerge chain in
   render.py, between two solid-colour clips.
2. Standalone segment: render_halftone_segment() (Pillow frames +
   FFmpeg encode), the pre-rendered-segment path round 3 planned.

The discriminator is strict on purpose: at the transition
midpoint the frame must contain BOTH near-pure red pixels (the
outgoing picture showing through between dots) and near-pure blue
pixels (the incoming picture inside the dots). A plain dissolve
would blend everything into purple and have almost no pure pixels;
a hard cut would have only one colour; pixelize would average
blocks, not resolve one picture out of dots of the other. So this
test cannot pass for a dissolve/cut/pixelize substitution.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image  # noqa: E402

from vibeedit_core.project import Project, new_project  # noqa: E402
from vibeedit_core.render import (  # noqa: E402
    HALFTONE_TRANSITIONS, TRANSITION_XFADE, list_transition_renderability,
    probe_media, render, render_halftone_segment,
    transition_renderability)


def gen_solid(path, colour, seconds=2):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"color=c={colour}:size=320x180:rate=30:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", path],
        capture_output=True, check=True)


def grab_frame(video, when, out):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(when),
         "-i", video, "-frames:v", "1", out],
        capture_output=True, check=True)
    return Image.open(out).convert("RGB")


def pure_counts(img):
    """(near-pure red pixels, near-pure blue pixels, total)."""
    red = blue = 0
    for r, g, b in img.getdata():
        if r > 200 and g < 80 and b < 80:
            red += 1
        elif b > 200 and r < 80 and g < 80:
            blue += 1
    return red, blue, img.size[0] * img.size[1]


class HalftoneTest(unittest.TestCase):
    def test_renderability_and_registries(self):
        info = transition_renderability("halftone")
        self.assertTrue(info["renders"])
        self.assertIn("geq", info["method"])
        self.assertIn("halftone", HALFTONE_TRANSITIONS)
        self.assertNotIn("halftone", TRANSITION_XFADE)
        kinds = {row["kind"] for row in list_transition_renderability()}
        self.assertIn("halftone", kinds)

    def test_timeline_halftone_renders_dot_dissolve(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_solid(os.path.join(tmp, "a.mp4"), "red")
            gen_solid(os.path.join(tmp, "b.mp4"), "blue")
            proj = Project(new_project("halftone", width=320,
                                        height=180, fps=(30, 1)), tmp)
            info_a = probe_media(os.path.join(tmp, "a.mp4"))
            info_b = probe_media(os.path.join(tmp, "b.mp4"))
            med_a = proj.add_media("a.mp4", kind="video", **info_a)
            med_b = proj.add_media("b.mp4", kind="video", **info_b)
            clip_a = proj.add_clip(med_a["id"], "v1", 0, 0, 60)
            clip_b = proj.add_clip(med_b["id"], "v1", 60, 0, 60)
            # Round 4: add_transition accepts halftone (project.py
            # registry was opened for it); duration in seconds.
            proj.add_transition(clip_a["id"], clip_b["id"],
                                "halftone", 1.0)
            out = os.path.join(tmp, "out-halftone.mp4")
            report = render(proj.data, tmp, out)
            self.assertTrue(os.path.isfile(out))
            # 2 + 2 - 1 = 3 s.
            self.assertAlmostEqual(report["duration"], 3.0, delta=0.05)
            mid = grab_frame(out, 1.5, os.path.join(tmp, "mid.png"))
            red, blue, total = pure_counts(mid)
            # Midpoint: about half the area is dots. Both colours
            # must be well represented as unblended pixels.
            self.assertGreater(red, total * 0.05,
                               f"too few pure red pixels: {red}/{total}")
            self.assertGreater(blue, total * 0.05,
                               f"too few pure blue pixels: {blue}/{total}")
            # And the transition completes: the last frame is blue.
            last = grab_frame(out, 2.9, os.path.join(tmp, "last.png"))
            red, blue, total = pure_counts(last)
            self.assertGreater(blue, total * 0.9)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    def test_standalone_pillow_segment_renders(self):
        tmp = tempfile.mkdtemp()
        try:
            gen_solid(os.path.join(tmp, "a.mp4"), "red")
            gen_solid(os.path.join(tmp, "b.mp4"), "blue")
            out = os.path.join(tmp, "segment.mp4")
            result = render_halftone_segment(
                os.path.join(tmp, "a.mp4"), os.path.join(tmp, "b.mp4"),
                out, duration_s=0.5, fps=30, width=320, height=180)
            self.assertEqual(result["frames"], 15)
            self.assertTrue(os.path.isfile(out))
            info = probe_media(out)
            self.assertAlmostEqual(info["duration"], 0.5, delta=0.2)
            self.assertEqual((info["width"], info["height"]),
                             (320, 180))
            mid = grab_frame(out, 0.25, os.path.join(tmp, "seg.png"))
            red, blue, total = pure_counts(mid)
            self.assertGreater(red, total * 0.05)
            self.assertGreater(blue, total * 0.05)
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
