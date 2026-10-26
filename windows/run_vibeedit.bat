@echo off
REM VibeEdit Windows launcher (double-click to run).
REM Checks Python + FFmpeg, starts the web server, opens the browser.
chcp 65001 >nul
cd /d "%~dp0\.."
echo ============================================
echo  VibeEdit - Dang khoi dong...
echo ============================================

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
start "VibeEdit Server" /min python windows\vibeedit.py serve --port 8000
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
