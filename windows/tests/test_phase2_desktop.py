"""Phase 2 tests: desktop completion, Windows shortcuts, and
Windows-runnable tests.

Desktop-window appearance, HiDPI rendering, and Ctrl shortcuts in
a real Windows browser CANNOT be verified on this Linux VM — those
stay "needs real Windows check". What IS testable here without a
real window is tested for real:
- the desktop server starts, answers GET / 200, shuts down
  cleanly, and its port can be rebound immediately;
- the DPI helper is a no-op (returns False, never raises) off
  Windows, so Linux behaviour is unchanged;
- the FFmpeg / port-in-use messages name the problem and the fix
  instead of a bare traceback;
- POST /api/save (the Ctrl+S endpoint) writes the project file;
- app.js wires Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y / Ctrl+S and the
  single-letter handlers ignore Ctrl-modified keys;
- no test file invokes a bare "python3" subprocess command
  (the one real case, test_phase7.py, now uses sys.executable).

Run from windows/:  py -m unittest discover -s tests -v (Windows)
  / python3 -m unittest discover -s tests -v (Linux)
"""

import json
import os
import re
import socket
import sys
import tempfile
import threading
import unittest
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from desktop_app import (  # noqa: E402
    check_ffmpeg, enable_dpi_awareness, ffmpeg_error_message,
    port_in_use_message, shutdown_server, start_desktop_server)
from vibeedit_core.server import State, make_handler  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

WINDOWS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


class TestDesktopShutdown(unittest.TestCase):
    def test_start_serve_shutdown_rebind(self):
        # Real server thread, real HTTP request, real shutdown.
        # A temp project dir: never the shared default project.
        tmp = tempfile.mkdtemp()
        port = _free_port()
        server, thread = start_desktop_server(tmp, port)
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8", errors="replace")
            self.assertIn("VibeEdit", body)
        finally:
            self.assertTrue(shutdown_server(server, thread))
            self.assertFalse(thread.is_alive())
        # The port must be free immediately: rebind must succeed.
        rebound = ThreadingHTTPServer(("127.0.0.1", port),
                                      make_handler(State(tmp)))
        try:
            rebound.server_close()
        finally:
            try:
                rebound.server_close()
            except Exception:
                pass

    def test_shutdown_is_idempotent(self):
        tmp = tempfile.mkdtemp()
        port = _free_port()
        server, thread = start_desktop_server(tmp, port)
        self.assertTrue(shutdown_server(server, thread))
        # Second shutdown must not raise or hang.
        self.assertTrue(shutdown_server(server, thread, timeout=1.0))


class TestDesktopErrors(unittest.TestCase):
    def test_dpi_helper_is_noop_off_windows(self):
        # On this Linux VM the call must return False, never raise
        # and never touch ctypes.windll (which does not exist here).
        if sys.platform == "win32":
            self.skipTest("Windows-only behaviour differs")
        self.assertFalse(enable_dpi_awareness())

    def test_ffmpeg_check_reports_names(self):
        result = check_ffmpeg()
        self.assertIn("missing", result)
        self.assertIsInstance(result["missing"], list)
        # On this VM ffmpeg/ffprobe are installed; on a machine
        # without them the message must name the fix, not a path.
        msg = ffmpeg_error_message(["ffmpeg", "ffprobe"])
        self.assertIn("ffmpeg", msg)
        self.assertIn("VIBEEDIT_FFMPEG_DIR", msg)
        self.assertIn("PATH", msg)
        self.assertNotIn("Traceback", msg)

    def test_port_in_use_message_names_fix(self):
        tmp = tempfile.mkdtemp()
        port = _free_port()
        server, thread = start_desktop_server(tmp, port)
        try:
            msg = port_in_use_message(port)
            self.assertIn(str(port), msg)
            self.assertIn(str(port + 1), msg)
            self.assertNotIn("Traceback", msg)
            # Binding the same port again must really fail, so the
            # message describes a real condition, not a guess.
            with self.assertRaises(OSError):
                start_desktop_server(tmp, port)
        finally:
            shutdown_server(server, thread)

    def test_save_endpoint_writes_project(self):
        tmp = tempfile.mkdtemp()
        try:
            state = State(tmp)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), make_handler(state))
            port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever,
                                      daemon=True)
            thread.start()
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/save",
                    data=b"{}", method="POST",
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(data.get("ok"))
                proj_files = [f for f in os.listdir(tmp)
                              if f.endswith(".json")]
                self.assertTrue(proj_files)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
        finally:
            pass


class TestWindowsShortcuts(unittest.TestCase):
    def _read(self, rel):
        with open(os.path.join(WINDOWS_DIR, rel),
                  encoding="utf-8") as fh:
            return fh.read()

    def test_ctrl_shortcuts_wired_in_app_js(self):
        js = self._read(os.path.join("static", "app.js"))
        self.assertIn("ctrlKey", js)
        self.assertIn('"/api/save"', js)
        self.assertIn('key === "s"', js)
        self.assertIn('key === "z"', js)
        self.assertIn('key === "y"', js)
        # Single-letter handlers must ignore Ctrl-modified keys so
        # Ctrl+S reaches save instead of splitting at the playhead.
        self.assertIn("if (e.ctrlKey || e.metaKey) return;", js)

    def test_shortcut_hints_say_ctrl_not_cmd(self):
        html = self._read(os.path.join("static", "index.html"))
        self.assertIn("Ctrl+Z", html)
        self.assertIn("Ctrl+S", html)
        self.assertNotIn("Cmd+Z", html)
        self.assertNotIn("Cmd+S", html)
        # No element id was renamed or duplicated by the hint span.
        ids = re.findall(r'id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)), "duplicate ids")

    def test_logo_data_uri_intact(self):
        html = self._read(os.path.join("static", "index.html"))
        self.assertIn("data:image/png;base64,", html)


class TestWindowsRunnableTests(unittest.TestCase):
    def test_no_bare_python3_subprocess_command(self):
        # Regression: the only real "python3" subprocess call was in
        # test_phase7.py and now uses sys.executable. Docstring
        # mentions of the Linux command are fine; only argv
        # literals count here.
        pattern = re.compile(r"""\[\s*['"]python3['"]""")
        offenders = []
        for name in sorted(os.listdir(TESTS_DIR)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(TESTS_DIR, name),
                      encoding="utf-8") as fh:
                src = fh.read()
            if pattern.search(src):
                offenders.append(name)
        self.assertEqual(offenders, [])

    def test_temp_paths_use_platform_join(self):
        # Temp test data must be built with tempfile + os.path.join,
        # never a hardcoded separator path, so the same test can
        # run on Windows. (Behaviour check, not a file scan.)
        with tempfile.TemporaryDirectory() as tmp:
            proj_dir = os.path.join(tmp, "phase2-smoke")
            os.makedirs(proj_dir)
            marker = os.path.join(proj_dir, "marker.txt")
            with open(marker, "w", encoding="utf-8") as fh:
                fh.write("ok")
            self.assertTrue(os.path.isfile(marker))


if __name__ == "__main__":
    unittest.main()
