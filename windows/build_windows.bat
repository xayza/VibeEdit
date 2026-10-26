@echo off
REM VibeEdit Windows build script (run on Windows, not on the Linux VM).
REM Builds a runnable one-folder app with PyInstaller from vibeedit.py.
REM Requires: Python 3.10+ in PATH, FFmpeg in PATH (not bundled).
REM Output: dist\VibeEdit\VibeEdit.exe (plus a _internal folder).
REM The exe still needs FFmpeg in PATH at runtime, or ffmpeg.exe next
REM to VibeEdit.exe in dist\VibeEdit\.

setlocal
cd /d "%~dp0"
where python >nul 2>&1
if errorlevel 1 (
  echo [VibeEdit] Python not found in PATH. Install Python 3.10+ with "Add python.exe to PATH" and retry.
  pause
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
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
pip install --upgrade pip >nul
pip install pyinstaller
if errorlevel 1 (
  echo [VibeEdit] Failed to install PyInstaller.
  pause
  exit /b 1
)
pyinstaller --clean --noconfirm vibeedit.spec
if errorlevel 1 (
  echo [VibeEdit] PyInstaller build failed.
  pause
  exit /b 1
)
echo.
echo [VibeEdit] Built: dist\VibeEdit\VibeEdit.exe
echo [VibeEdit] Copy ffmpeg.exe into dist\VibeEdit\ if FFmpeg is not in PATH.
echo [VibeEdit] Then run: scripts\install_shortcuts.ps1  (creates Start Menu + Desktop shortcuts)
pause
