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

Phase 2 rules (desktop completion):
- Clean shutdown: when the pywebview window closes (or Ctrl+C),
  the HTTP server is explicitly shut down and its thread joined,
  so no process lingers and the port can be rebound immediately.
- Understandable errors, never a bare traceback as the only
  output: missing pywebview, missing FFmpeg/FFprobe, and a port
  already in use each print a short Vietnamese message saying
  exactly what is missing and what to do. Console messages use
  unaccented Vietnamese on purpose: a plain Windows cmd window
  without `chcp 65001` would otherwise show mojibake.
- HiDPI: on Windows only, per-monitor DPI awareness is enabled
  via ctypes before the window opens (guarded by a sys.platform
  check, so Linux/macOS behaviour is completely unchanged).
  Default window is 1600x900, resizable; the web UI itself uses
  flexible panels + internal scrolling (see static/style.css
  media queries), so it stays usable at 1280x720 and 1920x1080
  without a fixed-pixel layout breaking at 720p.

If pywebview is not installed, this prints exactly what to install
in Vietnamese and falls back to the browser route (server in the
foreground, browser opened), instead of crashing silently.
"""

from __future__ import annotations

import argparse
import errno
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

DEFAULT_WIDTH = 1600
DEFAULT_HEIGHT = 900


def enable_dpi_awareness() -> bool:
    """Enable per-monitor DPI awareness on Windows only.

    Returns True only when a Windows DPI-awareness call succeeded.
    On any other platform (or if the call fails) returns False and
    never raises, so the app still starts at normal DPI.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        # Per-monitor v2 (value 2); fall back to system-aware (1),
        # then to the legacy SetProcessDPIAware call.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return True
        except Exception:  # noqa: BLE001 - try the older APIs
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            return True
        except Exception:  # noqa: BLE001 - try the legacy call
            pass
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:  # noqa: BLE001 - DPI is cosmetic, never fatal
        return False


def check_ffmpeg() -> dict:
    """Check ffmpeg/ffprobe in the 3 supported locations.

    Returns {"ffmpeg": path-or-None, "ffprobe": path-or-None,
    "missing": [...names...]}. Uses render.find_tool, which checks
    VIBEEDIT_FFMPEG_DIR, then PATH, then next to the app.
    """
    from vibeedit_core.render import find_tool
    found: dict = {}
    missing: list[str] = []
    for name in ("ffmpeg", "ffprobe"):
        try:
            found[name] = find_tool(name)
        except FileNotFoundError:
            found[name] = None
            missing.append(name)
    found["missing"] = missing
    return found


def ffmpeg_error_message(missing: list[str]) -> str:
    """Short Vietnamese message for missing FFmpeg tools."""
    names = " va ".join(missing)
    return (
        f"Khong tim thay {names}. VibeEdit van mo duoc de soan thao, "
        "nhung xuat video, thumbnail va song am se bao loi.\n"
        "Cach khac phuc (chon 1 trong 3):\n"
        "  1. Cai FFmpeg roi them vao PATH, hoac\n"
        "  2. Dat bien moi truong VIBEEDIT_FFMPEG_DIR tro toi thu muc "
        "chua ffmpeg.exe, hoac\n"
        "  3. Copy ffmpeg.exe va ffprobe.exe vao cung thu muc voi app."
    )


def port_in_use_message(port: int) -> str:
    """Short Vietnamese message for a port already in use."""
    return (
        f"Cong {port} dang bi chiem (co the mot cua so VibeEdit khac "
        "dang chay).\n"
        "Cach khac phuc: dong cua so VibeEdit kia roi chay lai, hoac "
        f"chay: python desktop_app.py --port {port + 1}"
    )


def start_desktop_server(project: str | None, port: int):
    """Start the web server in a background thread.

    Returns (server, thread). Raises OSError (errno EADDRINUSE)
    when the port is already taken, so the caller can print the
    port-in-use message instead of a traceback.
    """
    state = State(project)
    server = ThreadingHTTPServer(("127.0.0.1", port),
                                 make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def shutdown_server(server, thread, timeout: float = 5.0) -> bool:
    """Shut a desktop server down cleanly and join its thread.

    Returns True when the thread actually finished within the
    timeout (the port is then free to rebind immediately).
    Never raises: a shutdown failure must not mask the real exit.
    """
    try:
        server.shutdown()
    except Exception:  # noqa: BLE001 - best effort, still close
        pass
    try:
        server.server_close()
    except Exception:  # noqa: BLE001 - best effort
        pass
    try:
        thread.join(timeout=timeout)
    except Exception:  # noqa: BLE001 - best effort
        pass
    return not thread.is_alive()


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
    enable_dpi_awareness()
    ffmpeg = check_ffmpeg()
    if ffmpeg["missing"]:
        print("CANH BAO:")
        print(ffmpeg_error_message(ffmpeg["missing"]))
    if webview is None:
        print("Chua cai pywebview. Cai 1 lan trong .venv cua ban:")
        print("    pip install pywebview")
        print("Sau do chay lai: python desktop_app.py")
        print("Tam thoi mo bang trinh duyet thay the...")
        run_server(args.project, port=args.port, open_browser_flag=True)
        return 0
    try:
        server, thread = start_desktop_server(args.project, args.port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(port_in_use_message(args.port))
            return 2
        print(f"Khong khoi dong duoc server: {exc}")
        print("Kiem tra thu muc project va quyen ghi, roi chay lai.")
        return 1
    print(f"VibeEdit server dang chay tai http://127.0.0.1:{args.port}/")
    if not _wait_for_server(args.port):
        print("Khong ket noi duoc toi server. Kiem tra cong dang bi chiem?")
        shutdown_server(server, thread)
        return 1
    print("Mo cua so desktop VibeEdit...")
    print("Dong cua so de thoat sach (server se tu tat, cong duoc giai phong).")
    try:
        webview.create_window("VibeEdit", f"http://127.0.0.1:{args.port}/",
                              width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
                              resizable=True)
        webview.start()
    except KeyboardInterrupt:
        print("\nNhan Ctrl+C, dang tat server...")
    finally:
        # Clean shutdown on every exit path: window closed, Ctrl+C,
        # or a webview error. Without this the old code returned
        # while the daemon thread kept the port bound.
        if shutdown_server(server, thread):
            print("Da tat server, cong da duoc giai phong.")
        else:
            print("Server dang tat (cho thread ket thuc)...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
