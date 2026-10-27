"""Phase B4+B5 tests: knowledge/skills store reader + vision backends.

Run from windows/:  python3 -m unittest discover -s tests -v (Linux)
                    py -m unittest discover -s tests -v (Windows)

Skills tests use temp dirs only (except the shipped-dir test, which
only reads windows/skills/). Vision tests adapt to what is actually
installed on the machine: on this Linux VM neither Tesseract nor
OpenCV is present, so the tests assert VisionUnavailable with a clear
message; where a backend IS present, the test uses a real synthetic
image and asserts real output. No network, no Swift, no binaries.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core import skills as skills_mod
from vibeedit_core import vision as vision_mod
from vibeedit_core.vision import VisionUnavailable

SHIPPED_DIR = os.path.join(os.path.dirname(__file__), "..", "skills")

ORIGINAL_MD = (
    "Provenance: Original skill text — test fixture.\n"
    "\n"
    "---\n"
    "name: fixture-original\n"
    "---\n"
    "\n"
    "# Fixture Original\n"
    "\n"
    "Body mentions loudness and LUFS.\n"
)

DERIVED_MD = (
    "Provenance: Derived from the original BashCut docs — test fixture.\n"
    "\n"
    "---\n"
    "name: fixture-derived\n"
    "---\n"
    "\n"
    "# Fixture Derived\n"
    "\n"
    "Body mentions timeline editing.\n"
)


def _write_tmp_skill(directory, name, text):
    path = os.path.join(directory, name + ".md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class SkillsTempDirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vibeedit-skills-")
        _write_tmp_skill(self.tmp, "fixture-original", ORIGINAL_MD)
        _write_tmp_skill(self.tmp, "fixture-derived", DERIVED_MD)
        # Non-markdown files must be ignored by list_skills.
        with open(os.path.join(self.tmp, "notes.txt"), "w") as fh:
            fh.write("not a skill")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_returns_id_title_source(self):
        entries = skills_mod.list_skills(self.tmp)
        by_id = {e["id"]: e for e in entries}
        self.assertEqual(sorted(by_id), ["fixture-derived", "fixture-original"])
        self.assertEqual(by_id["fixture-original"]["title"], "Fixture Original")
        self.assertEqual(by_id["fixture-original"]["source"], "original")
        self.assertEqual(by_id["fixture-derived"]["title"], "Fixture Derived")
        self.assertEqual(by_id["fixture-derived"]["source"], "derived")

    def test_get_returns_full_markdown(self):
        text = skills_mod.get_skill(self.tmp, "fixture-original")
        self.assertIn("Body mentions loudness and LUFS.", text)
        self.assertIn("Provenance: Original skill text", text)

    def test_get_missing_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            skills_mod.get_skill(self.tmp, "no-such-skill")

    def test_get_rejects_traversal_and_non_markdown_ids(self):
        for bad_id in ("..", "../secret", "a/b", "a\\b", "skill.md",
                       "skill.txt", "", ".hidden", "-x.md"):
            with self.subTest(bad_id=bad_id):
                with self.assertRaises(ValueError):
                    skills_mod.get_skill(self.tmp, bad_id)

    def test_search_matches_title_and_body_case_insensitive(self):
        found = skills_mod.search_skills(self.tmp, "LUFS")
        self.assertEqual([e["id"] for e in found], ["fixture-original"])
        found = skills_mod.search_skills(self.tmp, "timeline")
        self.assertEqual([e["id"] for e in found], ["fixture-derived"])
        found = skills_mod.search_skills(self.tmp, "FIXTURE")
        self.assertEqual(len(found), 2)

    def test_search_no_match_is_empty_and_empty_query_lists_all(self):
        self.assertEqual(skills_mod.search_skills(self.tmp, "zzz-no-match"), [])
        self.assertEqual(len(skills_mod.search_skills(self.tmp, "")), 2)

    def test_list_missing_dir_is_empty(self):
        self.assertEqual(
            skills_mod.list_skills(os.path.join(self.tmp, "does-not-exist")),
            [])


class SkillsShippedDirTests(unittest.TestCase):
    def test_shipped_files_are_valid_markdown_with_provenance(self):
        self.assertTrue(os.path.isdir(SHIPPED_DIR),
                        "windows/skills/ must exist")
        names = sorted(f for f in os.listdir(SHIPPED_DIR)
                       if f.endswith(".md"))
        self.assertGreaterEqual(len(names), 1)
        for name in names:
            with open(os.path.join(SHIPPED_DIR, name),
                      encoding="utf-8") as fh:
                first = fh.readline().strip()
            self.assertTrue(
                first.startswith("Provenance:"),
                "%s must start with a provenance header" % name)
            self.assertTrue(
                "Original skill text" in first
                or "Derived from" in first,
                "%s provenance must say original or derived: %r"
                % (name, first))

    def test_shipped_loudness_check_is_original_and_intact(self):
        entries = {e["id"]: e for e in skills_mod.list_skills(SHIPPED_DIR)}
        self.assertIn("loudness-check", entries)
        self.assertEqual(entries["loudness-check"]["source"], "original")
        text = skills_mod.get_skill(SHIPPED_DIR, "loudness-check")
        # Verbatim original body markers (from the original tree).
        self.assertIn("-14 LUFS for YouTube and social video", text)
        self.assertIn("vibeedit audio measure --media <id>", text)

    def test_shipped_derived_skills_labelled_derived(self):
        entries = {e["id"]: e for e in skills_mod.list_skills(SHIPPED_DIR)}
        for skill_id in ("timeline-editing", "review-workflow",
                         "export-presets"):
            with self.subTest(skill_id=skill_id):
                self.assertIn(skill_id, entries)
                self.assertEqual(entries[skill_id]["source"], "derived")


class VisionBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vibeedit-vision-")
        # A tiny real PNG (white 32x24) via Pillow, which the repo
        # already depends on; used only when a backend is present.
        from PIL import Image
        self.img = os.path.join(self.tmp, "white.png")
        Image.new("RGB", (32, 24), color="white").save(self.img)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_raises_before_backend_check(self):
        missing = os.path.join(self.tmp, "nope.png")
        for fn in (vision_mod.ocr_image, vision_mod.detect_faces,
                   vision_mod.cutout):
            with self.subTest(fn=fn.__name__):
                with self.assertRaises(FileNotFoundError):
                    fn(missing)

    def test_ocr_backend(self):
        if shutil.which("tesseract") is None:
            with self.assertRaises(VisionUnavailable) as ctx:
                vision_mod.ocr_image(self.img)
            self.assertIn("tesseract", str(ctx.exception).lower())
        else:
            out = vision_mod.ocr_image(self.img)
            self.assertEqual(out["backend"], "tesseract")
            self.assertIsInstance(out["text"], str)
            self.assertIsInstance(out["lines"], list)

    def test_detect_faces_backend(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            with self.assertRaises(VisionUnavailable) as ctx:
                vision_mod.detect_faces(self.img)
            self.assertIn("opencv", str(ctx.exception).lower())
        else:
            out = vision_mod.detect_faces(self.img)
            self.assertEqual(out["backend"], "opencv-haar")
            # A blank white image really has no faces; this empty
            # list is a real scan result, not a fallback.
            self.assertEqual(out["faces"], [])
            self.assertEqual(out["count"], 0)

    def test_cutout_backend(self):
        try:
            import cv2  # noqa: F401
        except ImportError:
            with self.assertRaises(VisionUnavailable) as ctx:
                vision_mod.cutout(self.img)
            self.assertIn("opencv", str(ctx.exception).lower())
        else:
            out = vision_mod.cutout(
                self.img, os.path.join(self.tmp, "out.png"))
            self.assertEqual(out["backend"], "opencv-grabcut")
            self.assertTrue(os.path.isfile(out["output_path"]))

    def test_vision_module_imports_without_backends(self):
        # Import already happened at module top; re-import must work
        # even with cv2/tesseract absent (they are never top-level).
        import importlib
        mod = importlib.reload(vision_mod)
        self.assertTrue(hasattr(mod, "VisionUnavailable"))


if __name__ == "__main__":
    unittest.main()
