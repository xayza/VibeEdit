@echo off
REM VibeEdit Windows build script (run on Windows, not on the Linux VM).
REM Builds a runnable one-folder app with PyInstaller from vibeedit.py.
REM Requires: Python 3.10+ in PATH, FFmpeg in PATH (not bundled by
REM this script alone; the GitHub Actions workflow copies
REM ffmpeg.exe and ffprobe.exe into dist\VibeEdit\ after this script).
REM A local build without that workflow step still needs FFmpeg in
REM PATH at runtime, or ffmpeg.exe and ffprobe.exe copied next to
REM VibeEdit.exe in dist\VibeEdit\ by hand.
REM Output: dist\VibeEdit\VibeEdit.exe (plus a _internal folder).
REM The exe is the server plus browser route, not the pywebview
REM desktop window: desktop_app.py is not a PyInstaller entry point
REM and pywebview is deliberately not installed here.
REM CI note (Phase 6): this script is also run by GitHub Actions.
REM `pause` waits for a keypress and would hang a CI runner, so
REM every pause below is skipped when GITHUB_ACTIONS is set
REM (GitHub sets it automatically on windows-latest runners).

setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo [VibeEdit] Python not found in PATH. Install Python 3.10+ with "Add python.exe to PATH" and retry.
  if not defined GITHUB_ACTIONS   pause
  exit /b 1
)
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [VibeEdit] WARNING: ffmpeg not found in PATH. The build continues, but the app cannot export until FFmpeg is installed.
)
if not exist .venv (
  echo [VibeEdit] Creating .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo [VibeEdit] Failed to create .venv.
    if not defined GITHUB_ACTIONS pause
    exit /b 1
  )
)
if not exist .venv\Scripts\activate.bat (
  echo [VibeEdit] .venv exists but its activate script is missing. Delete .venv and retry.
  if not defined GITHUB_ACTIONS pause
  exit /b 1
)
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
if errorlevel 1 (
  echo [VibeEdit] WARNING: pip upgrade failed, continuing with the existing pip.
)
REM Pillow is an optional runtime dependency: only the vision cutout
REM paths import it (lazily, inside vibeedit_core\vision.py), so the
REM core editor/export run without it — but the frozen build should
REM still include it, or learned cutout fails with a clear error.
REM pywebview is deliberately not installed here: the exe is the
REM server plus browser route, and desktop_app.py stays a
REM source-checkout path. Optional voice/transcription/vision
REM backends are likewise not installed: edge-tts, faster-whisper,
REM onnxruntime and opencv are absent from the frozen build, and
REM the app reports them unavailable with a clear error instead.
pip install pillow pyinstaller
if errorlevel 1 (
  echo [VibeEdit] Failed to install Pillow/PyInstaller.
  if not defined GITHUB_ACTIONS   pause
  exit /b 1
)
pyinstaller --clean --noconfirm vibeedit.spec
if errorlevel 1 (
  echo [VibeEdit] PyInstaller build failed.
  if not defined GITHUB_ACTIONS   pause
  exit /b 1
)
if not exist dist\VibeEdit\VibeEdit.exe (
  echo [VibeEdit] PyInstaller reported success but dist\VibeEdit\VibeEdit.exe was not found.
  if not defined GITHUB_ACTIONS   pause
  exit /b 1
)
REM Round 6: package the FFmpeg GPLv3 licence text and the
REM generated source offer into dist\VibeEdit. This step never
REM fails the local build by itself: a dev build without licences
REM must still not be distributed, and the warning below says so
REM plainly. The CI workflow runs the same script again after
REM bundling FFmpeg, and that step DOES fail the run if the
REM licence source is missing.
call scripts\package_licenses.bat
if errorlevel 1 (
  echo [VibeEdit] WARNING: licence packaging failed; do not distribute dist\VibeEdit until it succeeds.
)
cd /d "%~dp0"
echo.
echo [VibeEdit] Built: dist\VibeEdit\VibeEdit.exe
echo [VibeEdit] Copy ffmpeg.exe and ffprobe.exe into dist\VibeEdit\ if FFmpeg is not in PATH.
REM Path check (Phase 5): this script runs from windows\ (cd /d
REM "%~dp0" above), so the shortcut installer is
REM windows\scripts\install_shortcuts.ps1, addressed here as
REM scripts\install_shortcuts.ps1.
REM Round 5 fix: the old echo line below lived inside this
REM parenthesised else block AND contained parentheses of its own,
REM the exact bug class that broke update_and_run.bat v1 on cmd.
REM Echo lines inside a parenthesised block must never contain
REM parentheses. The line is also reworded because the old text
REM misdirected exe users: install_shortcuts.ps1 creates shortcuts
REM to run_vibeedit.bat for a source checkout, not to this exe.
if not exist scripts\install_shortcuts.ps1 (
  echo [VibeEdit] WARNING: scripts\install_shortcuts.ps1 not found; skipping shortcut step.
) else (
  echo [VibeEdit] NOTE: scripts\install_shortcuts.ps1 creates shortcuts to run_vibeedit.bat for a source checkout, not to this exe.
  echo [VibeEdit] For the built app, create a shortcut to dist\VibeEdit\VibeEdit.exe yourself.
)
if not defined GITHUB_ACTIONS pause
