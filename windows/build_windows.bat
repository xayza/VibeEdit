@echo off
REM VibeEdit Windows build script (run on Windows, not on the Linux VM).
REM Builds a runnable one-folder app with PyInstaller from vibeedit.py.
REM Requires: Python 3.10+ in PATH, FFmpeg in PATH (not bundled by
REM this script alone; the GitHub Actions workflow copies
REM ffmpeg.exe/ffprobe.exe into dist\VibeEdit\ after this script).
REM Output: dist\VibeEdit\VibeEdit.exe (plus a _internal folder).
REM The exe still needs FFmpeg in PATH at runtime, or ffmpeg.exe next
REM to VibeEdit.exe in dist\VibeEdit\.
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
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install pyinstaller
if errorlevel 1 (
  echo [VibeEdit] Failed to install PyInstaller.
  if not defined GITHUB_ACTIONS   pause
  exit /b 1
)
pyinstaller --clean --noconfirm vibeedit.spec
if errorlevel 1 (
  echo [VibeEdit] PyInstaller build failed.
  if not defined GITHUB_ACTIONS   pause
  exit /b 1
)
echo.
echo [VibeEdit] Built: dist\VibeEdit\VibeEdit.exe
echo [VibeEdit] Copy ffmpeg.exe into dist\VibeEdit\ if FFmpeg is not in PATH.
REM Path check (Phase 5): this script runs from windows\ (cd /d
REM "%~dp0" above), so the shortcut installer is
REM windows\scripts\install_shortcuts.ps1, addressed here as
REM scripts\install_shortcuts.ps1. It creates shortcuts to
REM run_vibeedit.bat (not to the exe); see INSTALL.md.
if not exist scripts\install_shortcuts.ps1 (
  echo [VibeEdit] WARNING: scripts\install_shortcuts.ps1 not found; skipping shortcut step.
) else (
  echo [VibeEdit] Then run: scripts\install_shortcuts.ps1  (creates Start Menu + Desktop shortcuts to run_vibeedit.bat)
)
if not defined GITHUB_ACTIONS pause
