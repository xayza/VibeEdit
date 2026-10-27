"""VibeEdit as a real desktop window (Windows).

This does NOT rewrite the UI: it starts the exact same web server
(vibeedit_core.server, same project folder, same port logic) in a
background thread and shows the exact same UI in a desktop window
via pywebview, which on Windows uses the built-in Edge WebView2 —
no Electron, no Qt, no Node, no new UI code. That is why the window
looks like a desktop app (title bar, no browser tabs or address
bar) while every panel, track and button stays the one already
built and tested.

Usage (Windows, inside the windows/ folder):
    pip install pywebview
    python desktop_app.py [--port 8000] [--project <folder>]

If pywebview is not installed, this prints exactly what to install
in Vietnamese and falls back to the browser route (server in the
foreground, browser opened), instead of crashing silently.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
import urllib.request

try:
    import webview  # type: ignore  # pywebview, Windows WebView2
except ImportError:  # expected on machines without pywebview
    webview = None

from vibeedit_core.server import State, make_handler, run_server
from http.server import ThreadingHTTPServer


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001 - server not up yet, keep waiting
            time.sleep(0.25)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VibeEdit desktop window")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project", default=None,
                        help="Project folder (default: windows/projects/default)")
    args = parser.parse_args(argv)
    if webview is None:
        print("Chua cai pywebview. Cai 1 lan trong .venv cua ban:")
        print("    pip install pywebview")
        print("Sau do chay lai: python desktop_app.py")
        print("Tam thoi mo bang trinh duyet thay the...")
        run_server(args.project, port=args.port, open_browser_flag=True)
        return 0
    state = State(args.project)
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"VibeEdit server dang chay tai http://127.0.0.1:{args.port}/")
    if not _wait_for_server(args.port):
        print("Khong ket noi duoc toi server. Kiem tra cong dang bi chiem?")
        return 1
    print("Mo cua so desktop VibeEdit...")
    webview.create_window("VibeEdit", f"http://127.0.0.1:{args.port}/",
                          width=1600, height=900)
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
