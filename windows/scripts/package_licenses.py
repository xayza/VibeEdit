"""Package third-party licence files into a built Windows dist folder.

Build-time only (stdlib only). Run by ``scripts/package_licenses.bat``
at the end of ``build_windows.bat`` and again by the CI workflow
after the FFmpeg binaries have been copied into the dist folder.

What it does, in ``<dist>/THIRD_PARTY_LICENSES/``:

- copies ``windows/THIRD_PARTY_LICENSES/GPLv3.txt`` verbatim
  (missing source licence file is a hard error: a distribution
  without it must not ship);
- writes ``SOURCE_OFFER.txt`` — the written offer required by GPLv3
  section 6b — generated from the ffmpeg/ffprobe binaries actually
  present in this build: their real ``-version`` first lines and the
  bundle URL, when one was supplied. Version lines are never
  hand-written in advance, so the offer always matches the binaries
  it travels with;
- writes ``THIRD_PARTY_NOTICE.txt`` — a short summary naming what
  is GPLv3 (the bundled FFmpeg/FFprobe binaries) and what is not
  (VibeEdit's own code, which follows the original BashCut MIT
  licence).

Nothing here is legal advice; a real legal review is still required
before a public release that bundles codecs.
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import subprocess
import sys

FFMPEG_SOURCE_URL = "https://ffmpeg.org/download.html"
GYAN_BUILDS_URL = "https://www.gyan.dev/ffmpeg/builds/"


def _first_version_line(tool_path: str | None) -> str:
    """First ``-version`` line of a tool, or a plain record when the
    tool is missing or its version cannot be read. The where-record
    (bundled/PATH) comes from _find_tool, not from here."""
    if tool_path is None:
        return "not present in this distribution"
    try:
        proc = subprocess.run(
            [tool_path, "-version"], capture_output=True, text=True,
            timeout=30)
    except Exception as exc:  # noqa: BLE001 - version probe must not crash
        return f"present but version unreadable: {exc}"
    line = (proc.stdout or "").splitlines()
    if proc.returncode != 0 or not line:
        return "present but version unreadable"
    return line[0].strip()


def _find_tool(name: str, dist_dir: str) -> tuple[str | None, str]:
    """Find ``name`` (ffmpeg/ffprobe) preferring the dist folder,
    then PATH. Returns (path, where) with where in bundled/PATH/none."""
    for candidate in (os.path.join(dist_dir, name + ".exe"),
                      os.path.join(dist_dir, name)):
        if os.path.isfile(candidate):
            return candidate, "bundled"
    found = shutil.which(name)
    if found:
        return found, "PATH"
    return None, "none"


def package_licenses(dist_dir: str, bundle_url: str | None,
                     windows_dir: str) -> dict:
    """Write the licence folder into ``dist_dir``. Returns a summary
    dict. Raises FileNotFoundError if the source GPLv3 text or the
    dist folder itself is missing."""
    if not os.path.isdir(dist_dir):
        raise FileNotFoundError(
            f"dist folder not found (build it first): {dist_dir}")
    licence_src = os.path.join(windows_dir, "THIRD_PARTY_LICENSES",
                                "GPLv3.txt")
    if not os.path.isfile(licence_src):
        raise FileNotFoundError(
            f"GPLv3 source text missing: {licence_src} — refusing to "
            "package a distribution without its licence")
    out_dir = os.path.join(dist_dir, "THIRD_PARTY_LICENSES")
    os.makedirs(out_dir, exist_ok=True)
    shutil.copyfile(licence_src, os.path.join(out_dir, "GPLv3.txt"))

    ffmpeg_path, ffmpeg_where = _find_tool("ffmpeg", dist_dir)
    ffprobe_path, ffprobe_where = _find_tool("ffprobe", dist_dir)
    ffmpeg_ver = _first_version_line(ffmpeg_path)
    ffprobe_ver = _first_version_line(ffprobe_path)
    ffmpeg_src = ffmpeg_where if ffmpeg_path else "not present"
    ffprobe_src = ffprobe_where if ffprobe_path else "not present"
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    if bundle_url:
        bundle_line = (f"Binary bundle downloaded from: {bundle_url}\n"
                       "The binaries above are the ones from that bundle, "
                       "copied into this distribution at packaging time.")
    else:
        bundle_line = ("No bundle URL was recorded for this build: the "
                       "binaries above came from the local FFmpeg install "
                       "or were copied by hand. The Corresponding Source "
                       "for the exact versions above is the FFmpeg source "
                       "for those versions.")

    offer = (
        "SOURCE OFFER FOR THE BUNDLED FFMPEG / FFPROBE BINARIES\n"
        "=====================================================\n"
        "\n"
        "This distribution of VibeEdit bundles FFmpeg and FFprobe\n"
        "binaries, which are licensed under the GNU General Public\n"
        "License, version 3 (GPLv3). The full licence text travels\n"
        "with this distribution as GPLv3.txt in this same folder.\n"
        "\n"
        f"Packaging date (UTC): {today}\n"
        "\n"
        "Binaries in THIS distribution (recorded at packaging time\n"
        "from the binaries actually present — do not hand-edit the\n"
        "version lines below):\n"
        f"  ffmpeg : [{ffmpeg_src}] {ffmpeg_ver}\n"
        f"  ffprobe: [{ffprobe_src}] {ffprobe_ver}\n"
        "\n"
        f"{bundle_line}\n"
        "\n"
        "WRITTEN OFFER (GPLv3 section 6b):\n"
        "This offer is valid for at least three years from the date\n"
        "this distribution was made, and for as long as spare parts or\n"
        "customer support are offered for it. Anyone who possesses\n"
        "the object code in this distribution may obtain a copy of\n"
        "the Corresponding Source for the bundled FFmpeg/FFprobe\n"
        "binaries, at no charge, from a network server:\n"
        f"  - FFmpeg source downloads: {FFMPEG_SOURCE_URL}\n"
        "    (pick the source matching the version lines above)\n"
        f"  - gyan.dev build pages and their linked build sources: {GYAN_BUILDS_URL}\n"
        "    (for builds taken from the gyan.dev essentials bundle)\n"
        "\n"
        "This file is generated at packaging time by\n"
        "scripts/package_licenses.py; re-running that script after\n"
        "replacing the bundled binaries regenerates it with the new\n"
        "versions. This offer is not legal advice.\n"
    )
    with open(os.path.join(out_dir, "SOURCE_OFFER.txt"),
              "w", encoding="utf-8") as fh:
        fh.write(offer)

    notice = (
        "THIRD-PARTY NOTICE — VibeEdit Windows distribution\n"
        "================================================\n"
        "\n"
        "VibeEdit's own code follows the original BashCut MIT licence.\n"
        "\n"
        "The FFmpeg and FFprobe binaries bundled next to VibeEdit.exe\n"
        "are NOT MIT and NOT LGPL: they are licensed under the GNU\n"
        "General Public License, version 3 (GPLv3). The full GPLv3\n"
        "text is GPLv3.txt in this folder, and the written offer for\n"
        "their Corresponding Source is SOURCE_OFFER.txt in this folder.\n"
        "\n"
        "Do not remove this folder when redistributing the artifact.\n"
        "Patent and codec notes are jurisdiction-dependent; nothing\n"
        "here is legal advice.\n"
    )
    with open(os.path.join(out_dir, "THIRD_PARTY_NOTICE.txt"),
              "w", encoding="utf-8") as fh:
        fh.write(notice)

    return {"dist": os.path.abspath(dist_dir),
            "licence_dir": os.path.abspath(out_dir),
            "ffmpeg": {"where": ffmpeg_src, "version": ffmpeg_ver},
            "ffprobe": {"where": ffprobe_src, "version": ffprobe_ver},
            "bundle_url": bundle_url or ""}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Package FFmpeg GPLv3 licence + source offer "
                    "into a built dist folder.")
    parser.add_argument("--dist", required=True,
                        help="Built dist folder (e.g. dist/VibeEdit)")
    parser.add_argument("--bundle-url", default=None,
                        help="URL the bundled FFmpeg binaries were "
                             "downloaded from, if any")
    parser.add_argument("--windows-dir", default=None,
                        help="windows/ folder holding "
                             "THIRD_PARTY_LICENSES (default: parent of "
                             "this script's folder)")
    args = parser.parse_args(argv)
    windows_dir = args.windows_dir or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    try:
        summary = package_licenses(args.dist, args.bundle_url, windows_dir)
    except FileNotFoundError as exc:
        print(f"[package_licenses] ERROR: {exc}", file=sys.stderr)
        return 2
    print("[package_licenses] Wrote THIRD_PARTY_LICENSES into "
          f"{summary['licence_dir']}")
    print(f"[package_licenses] ffmpeg [{summary['ffmpeg']['where']}]: "
          f"{summary['ffmpeg']['version']}")
    print(f"[package_licenses] ffprobe [{summary['ffprobe']['where']}]: "
          f"{summary['ffprobe']['version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
