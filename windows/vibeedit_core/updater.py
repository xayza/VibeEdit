"""App updater framework for the Windows port (round 3).

What this is, honestly: a check/download/verify framework against
a CONFIGURABLE releases location. By default no channel is
configured, so the status check is the only thing that runs (the
behaviour of earlier builds). Nothing here invents a releases URL:
the channel comes from the ``VIBEEDIT_RELEASES_URL`` environment
variable (a GitHub Releases API URL such as
``https://api.github.com/repos/<owner>/<repo>/releases``) or from
an ``updater.json`` file next to this module with a
``{"releases_url": ...}`` object. Until the user picks a real
VibeEdit releases location, there is no updater channel, and this
module says so.

What this is NOT: an installer, and it never replaces a running
app. Round 4 adds the handoff step: after a verified download,
``write_update_handoff`` writes a Windows ``.bat`` that waits for
the app process to exit (tasklist loop over the app PID) and then
starts the downloaded installer. The user still runs that script
by hand after quitting VibeEdit — the app never executes the
installer itself, and with no channel configured the behaviour
stays status-only. The ``app.update`` MCP tool therefore stays a
check-and-error tool for replacing the running app, while
``app_update_prepare`` (download + verify + handoff) is real.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request

CURRENT_VERSION = "0.1.0"


class UpdaterUnavailable(Exception):
    """No updater channel is configured, or the channel failed."""


def _channel_from_file() -> str | None:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "updater.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    url = data.get("releases_url") if isinstance(data, dict) else None
    return url or None


def get_channel() -> str | None:
    """The configured releases API URL, or None when unconfigured."""
    return os.environ.get("VIBEEDIT_RELEASES_URL") or _channel_from_file()


def update_status() -> dict:
    """Current version + channel status. Never touches the network
    when no channel is configured."""
    channel = get_channel()
    if not channel:
        return {"current_version": CURRENT_VERSION,
                "update_channel": None,
                "status": "no updater configured in this build; "
                          "set VIBEEDIT_RELEASES_URL to a real "
                          "VibeEdit releases API URL, or write "
                          "updater.json next to vibeedit_core, to "
                          "enable update checks"}
    return {"current_version": CURRENT_VERSION,
            "update_channel": channel,
            "status": "updater channel configured; call "
                      "app_update_check with check=true to query it"}


def check_latest(channel: str | None = None) -> dict:
    """Query the configured channel for the latest release.
    Returns {"current_version", "latest_version", "page", "notes",
    "update_available"}. Raises UpdaterUnavailable when no channel
    is configured or the channel cannot be read. Never installs
    anything."""
    url = channel or get_channel()
    if not url:
        raise UpdaterUnavailable(
            "No updater channel is configured: set "
            "VIBEEDIT_RELEASES_URL to a real VibeEdit releases API "
            "URL first.")
    request = urllib.request.Request(
        url, headers={"User-Agent": "VibeEdit-updater",
                      "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise UpdaterUnavailable(
            f"Could not read the releases channel {url}: {exc}"
        ) from exc
    if isinstance(payload, list) and payload:
        latest = payload[0]
        version = str(latest.get("tag_name", "")).lstrip("v")
        return {"current_version": CURRENT_VERSION,
                "latest_version": version,
                "page": latest.get("html_url"),
                "notes": latest.get("body", "")[:2000],
                "update_available": version != CURRENT_VERSION,
                "assets": [{"name": a.get("name"),
                            "url": a.get("browser_download_url"),
                            "size": a.get("size")}
                           for a in latest.get("assets", [])]}
    if isinstance(payload, dict) and payload.get("version"):
        version = str(payload["version"]).lstrip("v")
        return {"current_version": CURRENT_VERSION,
                "latest_version": version,
                "page": payload.get("page"),
                "notes": payload.get("notes", ""),
                "update_available": version != CURRENT_VERSION,
                "assets": payload.get("assets", [])}
    raise UpdaterUnavailable(
        f"The releases channel {url} did not return a recognisable "
        "release list (expected a GitHub releases array or a "
        "{'version': ...} object).")


def download_release(url: str, dest: str,
                     sha256: str | None = None) -> dict:
    """Download a release asset to ``dest`` and verify its SHA-256
    when one is given. Returns {"path", "bytes", "sha256"}. This
    never executes the download; installing it is a separate,
    manual step (quit VibeEdit, then run the installer)."""
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "VibeEdit-updater"})
    digest = hashlib.sha256()
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=300) as resp, \
                open(dest, "wb") as handle:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                total += len(chunk)
    except Exception as exc:
        raise UpdaterUnavailable(
            f"Could not download {url}: {exc}") from exc
    actual = digest.hexdigest()
    if sha256 and actual != sha256.lower():
        raise UpdaterUnavailable(
            f"Download SHA-256 mismatch for {url}: expected "
            f"{sha256}, got {actual}; the file is not trusted")
    return {"path": dest, "bytes": total, "sha256": actual}


def write_update_handoff(installer_path: str,
                         app_pid: int | None = None,
                         dest_dir: str | None = None) -> dict:
    """Write the Windows handoff script for a verified download.

    Writes ``vibeedit-update-run.bat`` next to the installer (or
    into ``dest_dir``). The script waits for the VibeEdit app
    process (``app_pid``, via a tasklist loop) to exit and then
    starts the installer; with no PID it assumes VibeEdit has
    already been quit and says so. It never runs anything by
    itself, never replaces a running process, and is safe to
    inspect before running: it is plain batch text. Returns
    {"handoff", "installer", "app_pid", "instructions"}. The
    script is only ever *written* here; running it on Windows is
    a manual user step after quitting VibeEdit.
    """
    installer = os.path.abspath(installer_path)
    out_dir = dest_dir or os.path.dirname(installer)
    os.makedirs(out_dir, exist_ok=True)
    handoff = os.path.join(out_dir, "vibeedit-update-run.bat")
    lines = [
        "@echo off",
        "REM VibeEdit update handoff (round 4). This script is",
        "REM written by the updater after a verified download.",
        "REM It never runs by itself: quit VibeEdit, then",
        "REM double-click this file. It waits for the app",
        "REM process to exit and then starts the installer.",
        "REM It never replaces a running process.",
    ]
    if app_pid is not None:
        pid = int(app_pid)
        lines += [
            f"REM Waiting for app process {pid} to exit...",
            ":waitloop",
            f'tasklist /FI "PID eq {pid}" 2>nul | '
            f'find /I "{pid}" >nul',
            "if errorlevel 1 goto runit",
            "timeout /t 2 /nobreak >nul",
            "goto waitloop",
            ":runit",
        ]
    else:
        lines += [
            "REM No app PID was given: this script assumes",
            "REM VibeEdit has already been quit. If VibeEdit is",
            "REM still running, close it first, then run this",
            "REM script again.",
        ]
    lines += [
        f'start "" "{installer}"',
        "echo VibeEdit update installer started.",
    ]
    with open(handoff, "w", encoding="utf-8") as handle:
        handle.write("\r\n".join(lines) + "\r\n")
    return {"handoff": handoff, "installer": installer,
            "app_pid": app_pid,
            "instructions": "Quit VibeEdit, then double-click "
                            "vibeedit-update-run.bat; it waits for "
                            "the app process to exit and then starts "
                            "the installer."}


def prepare_update(url: str, dest: str,
                   sha256: str | None = None,
                   app_pid: int | None = None) -> dict:
    """Download + SHA-256 verify + write the installer handoff.

    Returns the download result plus the handoff dict. With no
    channel configured, callers should not reach this (check
    first); nothing here invents a releases URL — ``url`` is
    caller-supplied, from the configured channel.
    """
    result = download_release(url, dest, sha256)
    result.update(write_update_handoff(dest, app_pid=app_pid))
    return result
