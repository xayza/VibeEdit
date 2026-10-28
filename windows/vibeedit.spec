# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the VibeEdit Windows port. One-folder build,
# same entry point as `python vibeedit.py` (no separate packaged code
# path). The frozen exe is the server + browser route: double-click
# runs `serve --open-browser` (see vibeedit.py _effective_argv).
# desktop_app.py (the pywebview window) is NOT an entry point here
# and pywebview is NOT bundled; the desktop window stays a
# source-checkout path (run_vibeedit_desktop.bat) until a second
# entry point plus pywebview in build_windows.bat are added.
# Static web UI files, bundled plugins, and the shipped skill
# documents are bundled as data. FFmpeg is NOT bundled by this
# spec: it must be in PATH or placed next to VibeEdit.exe. The
# GitHub Actions workflow (.github/workflows/build-windows.yml)
# copies ffmpeg.exe and ffprobe.exe into dist/VibeEdit/ after the
# PyInstaller build, so the artifact from Actions needs no
# separate FFmpeg install. That workflow step copies ONLY the two
# exes: no FFmpeg licence text or source offer travels with the
# artifact from this spec (see the round 5 licence conclusion in
# the parent report; the licence files are a packaging step that
# still has to be added, not something this spec provides).
# NOTE: this spec was syntax-validated on the Linux VM only
# (ast.parse); the exe itself must be built on Windows with
# build_windows.bat, because PyInstaller cannot cross-build a
# Windows exe from Linux.
# FROZEN-PATH CAVEAT (round 5, must be verified on the first real
# Windows build): server.py and plugins.py resolve static/ and
# plugins/ with an explicit sys._MEIPASS branch, but skills.py
# resolves skills/ only relative to its own file. The skills data
# below is therefore necessary but may not be sufficient: if the
# frozen skills folder does not land where that file-relative
# path points, the frozen app will list zero skills (list_skills
# returns [] for a missing folder, silently). Fixing that would
# be a vibeedit_core/skills.py change, which is out of scope for
# this spec-only round; verify skills_list in the first Windows
# smoke test before claiming the frozen skills panel works.
import os

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(SPEC_DIR, "vibeedit.py")],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SPEC_DIR, "static"), "static"),
        (os.path.join(SPEC_DIR, "plugins"), "plugins"),
        # Round 5 fix: skills/ was missing. vibeedit_core/skills.py
        # reads windows/skills/*.md at runtime (list/get/search/
        # enable); without this entry the frozen app silently
        # listed no skills. There is no templates/ folder and no
        # fonts/ folder shipped with the app (imported fonts are
        # user data in windows/fonts/), so nothing else is a
        # shipped runtime data file. projects/ is user data too:
        # the frozen server deliberately stores it next to the
        # exe, never under the bundle, so it must NOT be a data.
        (os.path.join(SPEC_DIR, "skills"), "skills"),
    ],
    # Round 5: every vibeedit_core module is listed explicitly.
    # Most are reached only through literal function-level imports
    # (server.py / mcp.py import them inside handlers), which
    # PyInstaller's analysis normally traces, but an explicit list
    # costs nothing and protects the frozen build if any one of
    # those imports is ever missed. Deliberately NOT listed:
    # edge_tts, faster_whisper, onnxruntime, cv2 (optional
    # backends, absent from the build env; the app reports them
    # unavailable with a clear error instead of crashing) and
    # webview/pywebview (desktop_app.py is not an entry point).
    # Plugin code is data (spec_from_file_location in
    # plugins.py), never a hidden import, and is covered by the
    # plugins data entry above.
    hiddenimports=[
        "vibeedit_core.analysis",
        "vibeedit_core.beats",
        "vibeedit_core.cuts",
        "vibeedit_core.export_ops",
        "vibeedit_core.filelock",
        "vibeedit_core.karaoke",
        "vibeedit_core.knowledge",
        "vibeedit_core.mcp",
        "vibeedit_core.plugins",
        "vibeedit_core.project",
        "vibeedit_core.render",
        "vibeedit_core.round8",
        "vibeedit_core.round9",
        "vibeedit_core.round15",
        "vibeedit_core.server",
        "vibeedit_core.skill_import",
        "vibeedit_core.skills",
        "vibeedit_core.thumbnail",
        "vibeedit_core.transcribe",
        "vibeedit_core.updater",
        "vibeedit_core.vision",
        "vibeedit_core.voice",
        "vibeedit_core.waveform",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VibeEdit",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="VibeEdit",
)
