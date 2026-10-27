"""Round 6: GPLv3 packaging for the FFmpeg bundle.

Covers the round-5 licence finding, closed for real in round 6:
the CI artifact bundles a gyan.dev GPLv3 static build, so the
licence text plus a source offer generated from the bundled
binaries' real versions must travel with it.

No exe is built here (PyInstaller cannot cross-build Windows exes
on this Linux VM); the packaging script itself is exercised for
real against a temp dist folder with fake ffmpeg/ffprobe binaries.
"""

import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOWS = os.path.dirname(HERE)
REPO = os.path.dirname(WINDOWS)
SCRIPT = os.path.join(WINDOWS, "scripts", "package_licenses.py")
GPL_SRC = os.path.join(WINDOWS, "THIRD_PARTY_LICENSES", "GPLv3.txt")

# Affirmative descriptions of the bundled FFmpeg as LGPL. Deliberately
# NOT a bare "LGPL" scan: PARITY.md / README.md / CHECK_WINDOWS.md
# legitimately mention LGPL only to prohibit calling the artifact
# that ("must never be described as ... LGPL", "NOT LGPL").
FORBIDDEN_LGPL_PATTERNS = [
    r"GPL/LGPL",
    r"LGPL-licensed",
    r"LGPL build",
    r"\bis LGPL\b",
    r"\bare LGPL\b",
    r"\(LGPL\)",
]


def _fake_tool(path, version_line):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/bin/sh\n")
        fh.write(f"echo '{version_line}'\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP
              | stat.S_IXOTH)


class TestGPLv3Text(unittest.TestCase):
    def test_full_text_present_and_structured(self):
        self.assertTrue(os.path.isfile(GPL_SRC), "GPLv3.txt missing")
        with open(GPL_SRC, encoding="utf-8") as fh:
            text = fh.read()
        # Pure licence text: no provenance header was prepended.
        self.assertTrue(text.startswith("GNU GENERAL PUBLIC LICENSE"))
        self.assertIn("Version 3, 29 June 2007", text)
        self.assertIn("Copyright", text)
        self.assertIn("Free Software Foundation", text)
        self.assertIn("END OF TERMS AND CONDITIONS", text)
        for section in ("0. Definitions", "6. Conveying Non-Source Forms",
                        "11. Patents", "15. Disclaimer of Warranty",
                        "16. Limitation of Liability",
                        "17. Interpretation"):
            self.assertIn(section, text, f"missing section {section}")
        self.assertGreater(len(text.splitlines()), 600,
                           "GPLv3 text looks truncated")

    def test_provenance_note_is_separate(self):
        readme = os.path.join(WINDOWS, "THIRD_PARTY_LICENSES",
                              "README.md")
        self.assertTrue(os.path.isfile(readme))
        with open(readme, encoding="utf-8") as fh:
            note = fh.read()
        self.assertIn("gnu.org/licenses/gpl-3.0.html", note)
        self.assertIn("29 June 2007", note)
        self.assertIn("GPLv3", note)


class TestPackageLicensesScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dist = os.path.join(self.tmp, "VibeEdit")
        os.makedirs(self.dist)
        _fake_tool(os.path.join(self.dist, "ffmpeg"),
                   "ffmpeg version 99.9-test-round6")
        _fake_tool(os.path.join(self.dist, "ffprobe"),
                   "ffprobe version 99.9-test-round6")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, extra):
        return subprocess.run(
            [sys.executable, SCRIPT, "--dist", self.dist,
             "--windows-dir", WINDOWS] + extra,
            capture_output=True, text=True, timeout=60)

    def test_packages_licence_offer_and_notice_with_real_versions(self):
        proc = self._run(["--bundle-url",
                          "https://example.invalid/ffmpeg-test.zip"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = os.path.join(self.dist, "THIRD_PARTY_LICENSES")
        with open(GPL_SRC, "rb") as fh:
            src_bytes = fh.read()
        with open(os.path.join(out, "GPLv3.txt"), "rb") as fh:
            self.assertEqual(fh.read(), src_bytes,
                             "bundled GPLv3 text must be verbatim")
        with open(os.path.join(out, "SOURCE_OFFER.txt"),
                  encoding="utf-8") as fh:
            offer = fh.read()
        # Both version lines come from the binaries actually present,
        # not from a hand-written constant.
        self.assertIn("ffmpeg version 99.9-test-round6", offer)
        self.assertIn("ffprobe version 99.9-test-round6", offer)
        self.assertIn("[bundled]", offer)
        self.assertIn("https://example.invalid/ffmpeg-test.zip", offer)
        self.assertIn("at least three years", offer)
        self.assertIn("ffmpeg.org/download.html", offer)
        with open(os.path.join(out, "THIRD_PARTY_NOTICE.txt"),
                  encoding="utf-8") as fh:
            notice = fh.read()
        self.assertIn("GPLv3", notice)
        self.assertIn("NOT MIT and NOT LGPL", notice)

    def test_offer_without_bundle_url_records_local_install(self):
        proc = self._run([])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        with open(os.path.join(self.dist, "THIRD_PARTY_LICENSES",
                               "SOURCE_OFFER.txt"),
                  encoding="utf-8") as fh:
            offer = fh.read()
        self.assertIn("No bundle URL was recorded", offer)
        self.assertIn("ffmpeg version 99.9-test-round6", offer)

    def test_missing_licence_source_is_a_hard_error(self):
        empty_windows = os.path.join(self.tmp, "windows")
        os.makedirs(empty_windows)
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--dist", self.dist,
             "--windows-dir", empty_windows],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("GPLv3", proc.stderr)

    def test_missing_dist_is_a_hard_error(self):
        proc = subprocess.run(
            [sys.executable, SCRIPT, "--dist",
             os.path.join(self.tmp, "no-such-dist"),
             "--windows-dir", WINDOWS],
            capture_output=True, text=True, timeout=60)
        self.assertNotEqual(proc.returncode, 0)


class TestNoLgplDescription(unittest.TestCase):
    PACKAGING_FILES = [
        os.path.join(WINDOWS, "build_windows.bat"),
        os.path.join(WINDOWS, "scripts", "package_licenses.bat"),
        os.path.join(WINDOWS, "scripts", "package_licenses.py"),
        os.path.join(REPO, ".github", "workflows", "build-windows.yml"),
        os.path.join(WINDOWS, "CHECK_WINDOWS.md"),
        os.path.join(WINDOWS, "INSTALL.md"),
        os.path.join(WINDOWS, "README.md"),
        os.path.join(WINDOWS, "THIRD_PARTY_LICENSES", "README.md"),
    ]

    def test_no_file_calls_the_bundle_lgpl(self):
        for path in self.PACKAGING_FILES:
            self.assertTrue(os.path.isfile(path), f"missing: {path}")
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for pattern in FORBIDDEN_LGPL_PATTERNS:
                self.assertIsNone(
                    re.search(pattern, text),
                    f"{path} still describes the bundle as LGPL: {pattern}")

    def test_workflow_and_checklist_name_gplv3_and_package_step(self):
        with open(os.path.join(
                REPO, ".github", "workflows", "build-windows.yml"),
                encoding="utf-8") as fh:
            workflow = fh.read()
        self.assertIn("GPLv3", workflow)
        self.assertIn("package_licenses.bat", workflow)
        self.assertIn("Verify licence files in artifact", workflow)
        self.assertIn("FFMPEG_BUNDLE_URL", workflow)
        with open(os.path.join(WINDOWS, "CHECK_WINDOWS.md"),
                  encoding="utf-8") as fh:
            checklist = fh.read()
        self.assertIn("GPLv3", checklist)
        self.assertIn("package_licenses.bat", checklist)
        with open(os.path.join(WINDOWS, "build_windows.bat"),
                  encoding="utf-8") as fh:
            build = fh.read()
        self.assertIn("package_licenses.bat", build)


if __name__ == "__main__":
    unittest.main()
