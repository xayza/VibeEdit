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

Round 5 adds defer/skip state: ``app_update_later`` and
``app_update_skip`` are real even with no channel configured —
they record the user's choice in the same ``updater.json`` file
that holds the channel (never clobbering ``releases_url``):
``skipped_versions`` is a list of versions never to offer again,
and ``deferred`` records one version plus the UTC time after
which it may be offered again (``remind_after``). ``update_status``
reports both, so ``app_update_check`` shows them.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import urllib.request

CURRENT_VERSION = "0.1.0"


class UpdaterUnavailable(Exception):
    """No updater channel is configured, or the channel failed."""


def _state_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "updater.json")


def _read_state() -> dict:
    """Whole updater.json as a dict; missing/corrupt files read as
    {} so a broken state file never blocks a defer/skip choice
    (the write below then replaces it with valid state)."""
    path = _state_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(data: dict) -> dict:
    """Write updater.json atomically (temp file + replace) so a
    crash mid-write cannot leave a half-written state file."""
    path = _state_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp, path)
    return data


def _channel_from_file() -> str | None:
    return _read_state().get("releases_url") or None


def get_channel() -> str | None:
    """The configured releases API URL, or None when unconfigured."""
    return os.environ.get("VIBEEDIT_RELEASES_URL") or _channel_from_file()


def defer_update(version: str, remind_in_days: int = 7) -> dict:
    """Record "remind me later" for ``version`` (round 5, real
    even with no channel configured).

    Stores ``deferred`` = {"version", "deferred_at",
    "remind_after"} (UTC ISO timestamps, remind_after = now +
    remind_in_days) in updater.json, preserving any existing
    keys (notably ``releases_url`` and ``skipped_versions``).
    ``remind_in_days`` must be >= 0. Returns the stored record.
    """
    version = str(version or "").strip()
    if not version:
        raise ValueError("defer_update cần version")
    try:
        days = int(remind_in_days)
    except (TypeError, ValueError) as exc:
        raise ValueError("remind_in_days phải là số nguyên") from exc
    if days < 0:
        raise ValueError("remind_in_days phải >= 0")
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    record = {"version": version,
              "deferred_at": now.isoformat().replace("+00:00", "Z"),
              "remind_after": (now + datetime.timedelta(days=days)
                               ).isoformat().replace("+00:00", "Z")}
    state = _read_state()
    state["deferred"] = record
    _write_state(state)
    return {"deferred": record, "status": "deferred"}


def skip_update(version: str) -> dict:
    """Record "never offer this version again" (round 5, real
    even with no channel configured).

    Appends ``version`` to ``skipped_versions`` in updater.json
    (deduplicated), preserving every other key. Returns the
    skipped version plus the full skipped list.
    """
    version = str(version or "").strip()
    if not version:
        raise ValueError("skip_update cần version")
    state = _read_state()
    skipped = [v for v in state.get("skipped_versions", [])
               if isinstance(v, str)]
    if version not in skipped:
        skipped.append(version)
    state["skipped_versions"] = skipped
    _write_state(state)
    return {"skipped": version, "skipped_versions": skipped,
            "status": "skipped"}


def update_status() -> dict:
    """Current version + channel status. Never touches the network
    when no channel is configured. Round 5: also reports the
    defer/skip state so app_update_check shows it."""
    channel = get_channel()
    state = _read_state()
    base = {"current_version": CURRENT_VERSION,
            "update_channel": channel,
            "deferred": state.get("deferred"),
            "skipped_versions": [v for v in
                                 state.get("skipped_versions", [])
                                 if isinstance(v, str)]}
    if not channel:
        base["status"] = ("no updater configured in this build; "
                          "set VIBEEDIT_RELEASES_URL to a real "
                          "VibeEdit releases API URL, or write "
                          "updater.json next to vibeedit_core, to "
                          "enable update checks")
        return base
    base["status"] = ("updater channel configured; call "
                      "app_update_check with check=true to query it")
    return base


def check_latest(channel: str | None = None) -> dict:
    """Query the configured channel for the latest release.
    Returns {"current_version", "latest_version", "page", "notes",
    "update_available"}. Raises UpdaterUnavailable when no channel
    is configured or the channel cannot be read. Never installs
    anything."""
    url = channel or get_channel()
    if not url:
        raise UpdaterUnavailable(
            "Chưa cấu hình kênh updater: hãy đặt VIBEEDIT_RELEASES_URL thành URL API releases VibeEdit thật trước.")
    request = urllib.request.Request(
        url, headers={"User-Agent": "VibeEdit-updater",
                      "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise UpdaterUnavailable(
            f"Không đọc được kênh releases {url}: {exc}"
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
        f"Kênh releases {url} không trả về danh sách release nhận dạng được (mong đợi mảng releases GitHub hoặc object {{'version': ...}}).")


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
            f"Không tải được {url}: {exc}") from exc
    actual = digest.hexdigest()
    if sha256 and actual != sha256.lower():
        raise UpdaterUnavailable(
            f"SHA-256 tải về không khớp cho {url}: mong đợi {sha256}, nhận được {actual}; file không đáng tin")
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
