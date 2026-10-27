"""Round 4 task 5: updater run flow (framework only).

Run from windows/: python3 -m unittest discover -s tests -v
(or: py -m unittest discover -s tests -v on Windows).

The handoff .bat is only ever WRITTEN and its content inspected
here — it is a Windows batch file and is never executed on this
Linux VM. Downloads use a local file:// URL so no network and no
invented releases channel are involved. With no channel
configured, update_status() stays status-only.
"""

import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vibeedit_core import updater  # noqa: E402
from vibeedit_core.mcp import TOOLS  # noqa: E402


class HandoffTest(unittest.TestCase):
    def test_handoff_with_pid_waits_then_starts_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            installer = os.path.join(tmp, "VibeEdit-Setup.exe")
            result = updater.write_update_handoff(installer,
                                                  app_pid=1234)
            self.assertEqual(result["installer"],
                             os.path.abspath(installer))
            self.assertTrue(os.path.isfile(result["handoff"]))
            with open(result["handoff"], encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn('tasklist /FI "PID eq 1234"', content)
            self.assertIn("goto waitloop", content)
            self.assertIn(f'start "" "{os.path.abspath(installer)}"',
                          content)
            # The wait loop uses goto labels, not a parenthesised
            # block: the cmd bug that broke update_and_run.bat v1
            # (nested blocks with parentheses in echo text) cannot
            # recur here.
            self.assertNotIn("if not errorlevel 1 (", content)

    def test_handoff_without_pid_says_quit_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = updater.write_update_handoff(
                os.path.join(tmp, "VibeEdit-Setup.exe"))
            with open(result["handoff"], encoding="utf-8") as fh:
                content = fh.read()
            self.assertNotIn("tasklist", content)
            self.assertIn("already been quit", content)

    def test_prepare_downloads_verifies_and_writes_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = os.path.join(tmp, "asset.bin")
            with open(asset, "wb") as fh:
                fh.write(b"fake-installer-bytes")
            digest = hashlib.sha256(b"fake-installer-bytes").hexdigest()
            dest = os.path.join(tmp, "dl", "VibeEdit-Setup.exe")
            result = updater.prepare_update(
                "file://" + asset, dest, sha256=digest, app_pid=4321)
            self.assertEqual(result["sha256"], digest)
            self.assertTrue(os.path.isfile(dest))
            self.assertTrue(os.path.isfile(result["handoff"]))
            with open(result["handoff"], encoding="utf-8") as fh:
                self.assertIn("4321", fh.read())

    def test_prepare_rejects_bad_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            asset = os.path.join(tmp, "asset.bin")
            with open(asset, "wb") as fh:
                fh.write(b"fake-installer-bytes")
            with self.assertRaises(updater.UpdaterUnavailable):
                updater.prepare_update(
                    "file://" + asset, os.path.join(tmp, "x.exe"),
                    sha256="0" * 64)

    def test_status_stays_status_only_without_channel(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VIBEEDIT_RELEASES_URL", None)
            with mock.patch.object(updater, "_channel_from_file",
                                   return_value=None):
                status = updater.update_status()
        self.assertIsNone(status["update_channel"])
        self.assertIn("no updater configured", status["status"])

    def test_prepare_tool_is_registered_as_real(self):
        names = {t["name"] for t in TOOLS}
        self.assertIn("vibeedit_app_update_prepare", names)
        desc = next(t["description"] for t in TOOLS
                    if t["name"] == "vibeedit_app_update_prepare")
        self.assertFalse(desc.startswith("Not available"))


if __name__ == "__main__":
    unittest.main()
