"""Round 5 tests: desktop completion (Task 3) and installer files
(Task 4, read-only checks of the .bat/.spec text).

Desktop-window rendering, WebView2, and a real Windows exe build
CANNOT be verified on this Linux VM and stay "needs real Windows
check". What IS testable here without a real window is tested for
real, and no test requires pywebview (absent on this VM):
- single-instance probe: a real VibeEdit server answers
  "vibeedit", a free port answers None, and a foreign HTTP server
  answering without the VibeEdit marker answers "other";
- main() hands off to an existing instance (exit 0, browser URL
  opened, no second server started, no lock file created) and
  refuses a foreign-occupied port (exit 2, port-in-use message);
- the pywebview-missing fallback still works and no longer
  crashes with a traceback when the port is taken (exit 2);
- a desktop window that fails to open falls back to the browser
  route instead of propagating a traceback;
- invalid ports are rejected before anything binds;
- all desktop startup messages are plain ASCII (unaccented
  Vietnamese), so a plain cmd window without chcp 65001 cannot
  mojibake them;
- build_windows.bat has no echo line with parentheses inside a
  parenthesised block (the update_and_run.bat v1 bug class), and
  vibeedit.spec bundles static/, plugins/ and skills/ and lists
  every vibeedit_core module as a hidden import. The spec is
  syntax-checked with ast.parse only: PyInstaller cannot
  cross-build a Windows exe from Linux, so no exe is built here.

Run from windows/:  py -m unittest tests.test_round5_desktop -v
  (Windows) / python3 -m unittest tests.test_round5_desktop -v (Linux)
"""

import ast
import errno
import io
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import desktop_app  # noqa: E402
from desktop_app import (  # noqa: E402
    _browser_fallback, already_running_message, ffmpeg_error_message,
    main, port_in_use_message, probe_existing_instance,
    start_desktop_server, shutdown_server)


def _free_port() -> int:
    import socket
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _dummy_server(body: str, status: int = 200):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler name
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):  # noqa: D102 - silence logs
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


class TestSingleInstanceProbe(unittest.TestCase):
    def test_probe_real_vibeedit_server(self):
        tmp = tempfile.mkdtemp()
        port = _free_port()
        server, thread = start_desktop_server(tmp, port)
        try:
            self.assertEqual(probe_existing_instance(port), "vibeedit")
        finally:
            shutdown_server(server, thread)

    def test_probe_free_port_is_none(self):
        self.assertIsNone(probe_existing_instance(_free_port()))

    def test_probe_foreign_server_is_other(self):
        server, thread = _dummy_server("<html><body>Hello</body></html>")
        try:
            port = server.server_address[1]
            self.assertEqual(probe_existing_instance(port), "other")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_probe_foreign_error_status_is_other(self):
        server, thread = _dummy_server("Not found", status=404)
        try:
            port = server.server_address[1]
            self.assertEqual(probe_existing_instance(port), "other")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_probe_creates_no_lock_files(self):
        tmp = tempfile.mkdtemp()
        before = {f for f in os.listdir(tmp)
                  if os.path.isfile(os.path.join(tmp, f))}
        port = _free_port()
        server, thread = start_desktop_server(tmp, port)
        try:
            probe_existing_instance(port)
            probe_existing_instance(_free_port())
        finally:
            shutdown_server(server, thread)
        # The probe itself must not leave junk behind: the only
        # new file is the one the server created for its project
        # (media/ and render/ are directories, not files). A
        # lock-file design would add a file here; the probe
        # design adds none beyond the project file itself.
        after = {f for f in os.listdir(tmp)
                 if os.path.isfile(os.path.join(tmp, f))}
        self.assertEqual(after - before, {"project.vibeedit.json"})


class TestMainSingleInstance(unittest.TestCase):
    def test_handoff_to_existing_instance(self):
        port = _free_port()
        opened = []
        with mock.patch.object(desktop_app, "probe_existing_instance",
                               return_value="vibeedit"), \
                mock.patch.object(desktop_app, "open_existing_instance",
                                  side_effect=lambda p: opened.append(p)
                                  or True):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", str(port)])
        self.assertEqual(code, 0)
        self.assertEqual(opened, [port])
        self.assertIn("dang chay roi", out.getvalue())

    def test_handoff_ignores_project_arg_with_warning(self):
        port = _free_port()
        with mock.patch.object(desktop_app, "probe_existing_instance",
                               return_value="vibeedit"), \
                mock.patch.object(desktop_app, "open_existing_instance",
                                  return_value=True):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", str(port), "--project", "somewhere"])
        self.assertEqual(code, 0)
        self.assertIn("--project bi bo qua", out.getvalue())

    def test_foreign_port_refused(self):
        port = _free_port()
        with mock.patch.object(desktop_app, "probe_existing_instance",
                               return_value="other"):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", str(port)])
        self.assertEqual(code, 2)
        self.assertIn("dang bi chiem", out.getvalue())
        self.assertIn(str(port + 1), out.getvalue())

    def test_invalid_port_rejected_before_binding(self):
        for bad in ("0", "-1", "70000"):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", bad])
            self.assertEqual(code, 2, bad)
            self.assertIn("khong hop le", out.getvalue())


class TestBrowserFallback(unittest.TestCase):
    def test_pywebview_missing_fallback_runs_browser_route(self):
        # On this VM webview is None, so main takes the fallback
        # branch. A fake run_server proves the branch is reached
        # with the browser flag, without starting a real server.
        port = _free_port()
        calls = []
        fake = mock.Mock(side_effect=lambda *a, **k: calls.append((a, k)))
        with mock.patch.object(desktop_app, "probe_existing_instance",
                               return_value=None), \
                mock.patch.object(desktop_app, "run_server", fake):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", str(port)])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1].get("open_browser_flag"))
        self.assertIn("pywebview", out.getvalue())
        # The printed fallback text must be plain ASCII.
        out.getvalue().encode("ascii")

    def test_fallback_port_taken_is_message_not_traceback(self):
        port = _free_port()
        err = OSError(errno.EADDRINUSE, "address in use")
        with mock.patch.object(desktop_app, "probe_existing_instance",
                               side_effect=[None, "other"]), \
                mock.patch.object(desktop_app, "run_server",
                                  side_effect=err):
            out = io.StringIO()
            with redirect_stdout(out):
                code = _browser_fallback(None, port)
        self.assertEqual(code, 2)
        self.assertIn("dang bi chiem", out.getvalue())
        self.assertNotIn("Traceback", out.getvalue())

    def test_fallback_hands_off_to_vibeedit_on_bind_race(self):
        port = _free_port()
        err = OSError(errno.EADDRINUSE, "address in use")
        opened = []
        with mock.patch.object(desktop_app, "probe_existing_instance",
                               side_effect=[None, "vibeedit"]), \
                mock.patch.object(desktop_app, "run_server",
                                  side_effect=err), \
                mock.patch.object(desktop_app, "open_existing_instance",
                                  side_effect=lambda p: opened.append(p)
                                  or True):
            out = io.StringIO()
            with redirect_stdout(out):
                code = _browser_fallback(None, port)
        self.assertEqual(code, 0)
        self.assertEqual(opened, [port])
        self.assertIn("dang chay roi", out.getvalue())


class FakeWebview:
    """Stand-in for pywebview: records the window, never opens one."""
    instances = []

    def __init__(self, fail=False):
        self.fail = fail
        self.windows = []

    def create_window(self, *args, **kwargs):
        self.windows.append((args, kwargs))

    def start(self):
        if self.fail:
            raise RuntimeError("WebView2 runtime missing (simulated)")
        return None


class TestWebviewPath(unittest.TestCase):
    def test_window_success_shuts_down_cleanly(self):
        tmp = tempfile.mkdtemp()
        port = _free_port()
        fake = FakeWebview()
        with mock.patch.object(desktop_app, "webview", fake), \
                mock.patch.object(desktop_app, "probe_existing_instance",
                                  return_value=None):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", str(port), "--project", tmp])
        self.assertEqual(code, 0)
        self.assertEqual(len(fake.windows), 1)
        url = fake.windows[0][0][1]
        self.assertEqual(url, f"http://127.0.0.1:{port}/")
        # The port must be free again after the window "closed".
        server, thread = start_desktop_server(tmp, port)
        shutdown_server(server, thread)

    def test_window_failure_falls_back_to_browser(self):
        tmp = tempfile.mkdtemp()
        port = _free_port()
        fake = FakeWebview(fail=True)
        calls = []
        fake_server = mock.Mock(
            side_effect=lambda *a, **k: calls.append((a, k)))
        with mock.patch.object(desktop_app, "webview", fake), \
                mock.patch.object(desktop_app, "probe_existing_instance",
                                  return_value=None), \
                mock.patch.object(desktop_app, "run_server", fake_server):
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["--port", str(port), "--project", tmp])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][1].get("open_browser_flag"))
        text = out.getvalue()
        self.assertIn("Khong mo duoc cua so desktop", text)
        self.assertIn("RuntimeError", text)
        self.assertNotIn("Traceback", text)


class TestDesktopMessagesAscii(unittest.TestCase):
    def test_all_startup_messages_are_plain_ascii(self):
        messages = [
            ffmpeg_error_message(["ffmpeg", "ffprobe"]),
            ffmpeg_error_message(["ffmpeg"]),
            port_in_use_message(8000),
            already_running_message(8000),
        ]
        for msg in messages:
            # Raises UnicodeEncodeError if any accent slipped in.
            msg.encode("ascii")
            self.assertNotIn("Traceback", msg)


class TestInstallerFiles(unittest.TestCase):
    """Read-only checks of the files Task 4 was allowed to change.

    These do not build anything: a Windows exe cannot be built
    from this Linux VM, and running PyInstaller here would produce
    a misleading Linux binary.
    """

    def _read(self, name):
        path = os.path.join(os.path.dirname(__file__), "..", name)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def _block_depth_echo_lines(self, text):
        """Yield (line, depth) for echo lines inside (...) blocks.

        Cmd counts parentheses textually inside a block, so an
        echo line containing ( or ) inside a block breaks the
        block. Tracking is deliberately simple: a line ending
        with an opening block paren raises depth, a line that is
        just a closing paren lowers it. This matches the style
        used in build_windows.bat (blocks opened on the if line).
        """
        depth = 0
        for line in text.splitlines():
            stripped = line.strip()
            if depth > 0 and stripped.lower().startswith("echo "):
                yield line, depth
            if stripped.endswith("(") and not stripped.lower().startswith(
                    ("echo ", "rem ")):
                depth += 1
            elif stripped == ") else (":
                pass  # depth unchanged: close then reopen
            elif stripped == ")":
                depth -= 1

    def test_build_bat_no_parens_in_block_echo_lines(self):
        text = self._read("build_windows.bat")
        offenders = [line for line, _ in self._block_depth_echo_lines(text)
                     if "(" in line or ")" in line]
        self.assertEqual(offenders, [])

    def test_build_bat_verifies_exe_and_both_ffmpeg_tools(self):
        text = self._read("build_windows.bat")
        self.assertIn("dist\\VibeEdit\\VibeEdit.exe", text)
        self.assertIn("if not exist dist\\VibeEdit\\VibeEdit.exe", text)
        self.assertIn("ffmpeg.exe and ffprobe.exe", text)
        self.assertIn("activate.bat", text)

    def test_desktop_bat_prefers_venv_python(self):
        text = self._read("run_vibeedit_desktop.bat")
        self.assertIn(".venv\\Scripts\\python.exe", text)
        self.assertIn("desktop_app.py", text)

    def test_spec_syntax_and_data_and_hiddenimports(self):
        text = self._read("vibeedit.spec")
        ast.parse(text)  # syntax check only, never a build
        self.assertIn('"static"', text)
        self.assertIn('"plugins"', text)
        self.assertIn('"skills"', text)
        core = os.path.join(os.path.dirname(__file__), "..",
                            "vibeedit_core")
        for name in sorted(os.listdir(core)):
            if name.endswith(".py") and name != "__init__.py":
                module = "vibeedit_core." + name[:-3]
                self.assertIn('"%s"' % module, text, module)

    def test_spec_does_not_claim_ffmpeg_bundled(self):
        text = self._read("vibeedit.spec")
        self.assertIn("FFmpeg is NOT", text)


if __name__ == "__main__":
    unittest.main()
