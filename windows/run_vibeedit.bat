@echo off
REM VibeEdit Windows launcher (double-click to run).
REM Checks Python + FFmpeg, starts the web server, opens the browser.
REM
REM Layout fix (Phase 5): this script runs vibeedit.py from its OWN
REM folder (%~dp0). It used to "cd .." to the repo root and run
REM windows\vibeedit.py, which only worked for a full repo checkout
REM and broke when only the windows\ folder was copied elsewhere
REM (the parent then has no windows\ subfolder). vibeedit.py sits
REM next to this launcher in both layouts, so no cd is needed, and
REM the server resolves its project/static folders relative to its
REM own files, not to the working directory.
chcp 65001 >nul
set "VE_DIR=%~dp0"
set "VE_APP=%VE_DIR%vibeedit.py"
echo ============================================
echo  VibeEdit - Dang khoi dong...
echo ============================================

if not exist "%VE_APP%" (
  echo [LOI] Khong tim thay vibeedit.py cung thu muc voi run_vibeedit.bat: %VE_APP%
  echo Hay copy ca thu muc windows\ (gom vibeedit.py, vibeedit_core\, static\) roi chay lai.
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo [LOI] Khong tim thay Python. Vui long cai Python 3.10+ va tick "Add python.exe to PATH" khi cai dat.
  pause
  exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [LOI] Khong tim thay FFmpeg. Vui long cai FFmpeg va them vao PATH, hoac dat ffmpeg.exe cung thu muc voi VibeEdit.
  pause
  exit /b 1
)

echo [OK] Da thay Python va FFmpeg.
start "VibeEdit Server" /min python "%VE_APP%" serve --port 8000
echo Dang cho server khoi dong (toi da 30 giay)...
powershell -NoProfile -Command "$ok=$false; for ($i=0; $i -lt 30; $i++) { try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/' -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ok=$true; break } } catch { Start-Sleep -Seconds 1 } }; if ($ok) { Write-Host '[OK] Server da san sang.' } else { Write-Host '[LOI] Server khong phan hoi sau 30 giay. Hay xem cua so VibeEdit Server.'; exit 1 }"
if errorlevel 1 (
  pause
  exit /b 1
)
start http://127.0.0.1:8000/
echo.
echo VibeEdit dang chay tai http://127.0.0.1:8000/
echo DUNG DONG cua so "VibeEdit Server" trong luc dung.
echo De dung app: dong cua so "VibeEdit Server" hoac bam Ctrl+C trong do.
pause
