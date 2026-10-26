# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the VibeEdit Windows port. One-folder build,
# same entry point as `python vibeedit.py` (no separate packaged code
# path). Static web UI files are bundled as data. FFmpeg is NOT
# bundled: it must be in PATH or placed next to VibeEdit.exe.
# NOTE: this spec was syntax-validated on the Linux VM only
# (ast.parse); the exe itself must be built on Windows with
# build_windows.bat, because PyInstaller cannot cross-build a
# Windows exe from Linux.
import os

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(SPEC_DIR, "vibeedit.py")],
    pathex=[SPEC_DIR],
    binaries=[],
    datas=[
        (os.path.join(SPEC_DIR, "static"), "static"),
        (os.path.join(SPEC_DIR, "plugins"), "plugins"),
    ],
    hiddenimports=[],
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
