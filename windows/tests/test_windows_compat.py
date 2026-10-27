"""Phase 5 Windows-compatibility tests.

These tests check CODE PROPERTIES, not Windows execution: the
Linux VM cannot run Windows, so they assert that the production
code contains no POSIX-only or hardcoded-Windows assumptions, that
the path/tool/font helpers behave as specified, and that the
launcher/build/shortcut files exist and reference real files.
Run from windows/:  py -m unittest discover -s tests -v (Windows) / python3 -m unittest discover -s tests -v (Linux)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core.render import (  # noqa: E402
    _filter_path, find_font, find_tool, font_candidates)

WINDOWS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(WINDOWS_DIR, "vibeedit_core")


def _production_sources():
    paths = [os.path.join(WINDOWS_DIR, "vibeedit.py")]
    for name in sorted(os.listdir(CORE_DIR)):
        if name.endswith(".py"):
            paths.append(os.path.join(CORE_DIR, name))
    return paths


class TestNoHardcodedPaths(unittest.TestCase):
    def test_no_tmp_shell_symlink_or_hardcoded_windows_font(self):
        """Production code must not hardcode /tmp, shell=True,
        os.symlink, or a Windows fonts path. Windows fonts come
        from the SystemRoot environment variable (see
        render.font_candidates); temp dirs come from tempfile."""
        for path in _production_sources():
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn("/tmp/", src, path)
            self.assertNotIn("C:\\Windows", src, path)
            self.assertNotIn("C:/Windows", src, path)
            self.assertNotIn("shell=True", src, path)
            self.assertNotIn("os.symlink", src, path)

    def test_filter_paths_used_for_filter_embedded_paths(self):
        """lut3d, drawtext fontfile and subtitles filename must go
        through _filter_path, not through a raw path."""
        with open(os.path.join(CORE_DIR, "render.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("lut3d=file='{_filter_path", src)
        self.assertIn("fontfile='{_filter_path", src)
        self.assertIn("subtitles=filename='{_filter_path", src)

    def test_filter_path_converts_windows_paths(self):
        # Phase 7 correction: the drive colon MUST be escaped as
        # \: — the old expectation (bare C:/...) is exactly the
        # filter string that failed on Windows with
        # "No option name near '/Users/test/...'".
        self.assertEqual(
            _filter_path("C:\\Users\\test\\my cube.cube"),
            "C\\:/Users/test/my cube.cube")
        self.assertEqual(
            _filter_path("D:\\luts\\a'b.cube"), "D\\:/luts/a\\'b.cube")
        # Linux no-op for ordinary paths.
        self.assertEqual(_filter_path("/usr/share/fonts/a.ttf"),
                         "/usr/share/fonts/a.ttf")

    def test_find_font_honours_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            font = os.path.join(tmp, "MyFont.ttf")
            with open(font, "wb") as fh:
                fh.write(b"fake")
            old = os.environ.get("VIBEEDIT_FONT")
            os.environ["VIBEEDIT_FONT"] = font
            try:
                self.assertEqual(find_font(), font)
            finally:
                if old is None:
                    os.environ.pop("VIBEEDIT_FONT", None)
                else:
                    os.environ["VIBEEDIT_FONT"] = old

    def test_find_font_rejects_missing_env_override(self):
        old = os.environ.get("VIBEEDIT_FONT")
        os.environ["VIBEEDIT_FONT"] = os.path.join(
            tempfile.gettempdir(), "definitely-missing-vibeedit.ttf")
        try:
            with self.assertRaises(FileNotFoundError):
                find_font()
        finally:
            if old is None:
                os.environ.pop("VIBEEDIT_FONT", None)
            else:
                os.environ["VIBEEDIT_FONT"] = old

    def test_find_font_prefers_system_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            fonts = os.path.join(tmp, "Fonts")
            os.makedirs(fonts)
            font = os.path.join(fonts, "arial.ttf")
            with open(font, "wb") as fh:
                fh.write(b"fake")
            old_root = os.environ.get("SystemRoot")
            old_font = os.environ.get("VIBEEDIT_FONT")
            os.environ["SystemRoot"] = tmp
            os.environ.pop("VIBEEDIT_FONT", None)
            try:
                self.assertEqual(font_candidates()[0], font)
                self.assertEqual(find_font(), font)
            finally:
                if old_root is None:
                    os.environ.pop("SystemRoot", None)
                else:
                    os.environ["SystemRoot"] = old_root
                if old_font is not None:
                    os.environ["VIBEEDIT_FONT"] = old_font

    def test_find_tool_honours_ffmpeg_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "ffmpeg")
            with open(fake, "wb") as fh:
                fh.write(b"fake")
            old = os.environ.get("VIBEEDIT_FFMPEG_DIR")
            os.environ["VIBEEDIT_FFMPEG_DIR"] = tmp
            try:
                self.assertEqual(find_tool("ffmpeg"), fake)
            finally:
                if old is None:
                    os.environ.pop("VIBEEDIT_FFMPEG_DIR", None)
                else:
                    os.environ["VIBEEDIT_FFMPEG_DIR"] = old

    def test_find_tool_missing_tool_has_clear_error(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            find_tool("vibeedit-no-such-tool-xyz")
        self.assertIn("not found", str(ctx.exception))
        self.assertIn("VIBEEDIT_FFMPEG_DIR", str(ctx.exception))


class TestLauncherFiles(unittest.TestCase):
    def test_launcher_build_spec_shortcut_files_exist(self):
        for rel in ("run_vibeedit.bat", "run_vibeedit.ps1",
                    "build_windows.bat", "vibeedit.spec", "vibeedit.py",
                    os.path.join("scripts", "install_shortcuts.ps1"),
                    os.path.join("static", "index.html"),
                    os.path.join("static", "app.js")):
            self.assertTrue(os.path.isfile(os.path.join(WINDOWS_DIR, rel)),
                            f"missing: {rel}")

    def test_launchers_reference_their_own_folder(self):
        """Launchers must run vibeedit.py from their own folder
        (%~dp0 / $PSScriptRoot), not by cd-ing to a repo root that
        may not exist when only windows/ was copied."""
        with open(os.path.join(WINDOWS_DIR, "run_vibeedit.bat"),
                  encoding="utf-8") as fh:
            bat = fh.read()
        self.assertIn("%~dp0", bat)
        self.assertIn("vibeedit.py", bat)
        self.assertNotIn('cd /d "%~dp0\\.."', bat)
        with open(os.path.join(WINDOWS_DIR, "run_vibeedit.ps1"),
                  encoding="utf-8") as fh:
            ps1 = fh.read()
        self.assertIn("PSScriptRoot", ps1)
        self.assertIn("vibeedit.py", ps1)
        self.assertNotIn("Set-Location ..", ps1)

    def test_spec_and_shortcuts_reference_real_files(self):
        with open(os.path.join(WINDOWS_DIR, "vibeedit.spec"),
                  encoding="utf-8") as fh:
            spec = fh.read()
        self.assertIn("vibeedit.py", spec)
        self.assertIn("static", spec)
        with open(os.path.join(WINDOWS_DIR, "scripts",
                               "install_shortcuts.ps1"),
                  encoding="utf-8") as fh:
            shortcuts = fh.read()
        self.assertIn("run_vibeedit.bat", shortcuts)
        self.assertIn("PSScriptRoot", shortcuts)


if __name__ == "__main__":
    unittest.main()
