@echo off
REM VibeEdit - Mo cua so desktop, khong dung trinh duyet.
REM Chay desktop_app.py, no se dung pywebview mo cua so Edge WebView2.
REM Neu chua cai pywebview, desktop_app.py se huong dan cai dat
REM roi tu mo bang trinh duyet thay the, khong dung im.
REM File nay khong dung khoi lenh trong ngoac don.
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"
if not exist "%SCRIPT_DIR%desktop_app.py" goto :noapp
where python >nul 2>nul
if errorlevel 1 goto :nopython
echo Dang mo VibeEdit dang cua so desktop...
python "%SCRIPT_DIR%desktop_app.py"
goto :end
:noapp
echo Khong tim thay desktop_app.py cung thu muc voi file bat nay.
pause
exit /b 1
:nopython
echo Khong tim thay Python. Vui long cai Python 3.10+ va tick Add python.exe to PATH khi cai dat.
pause
exit /b 1
:end
