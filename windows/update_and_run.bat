@echo off
REM VibeEdit - Cap nhat roi chay, khong can tai ZIP moi lan.
REM Neu co .git thi git pull truoc; neu khong co git hoac pull loi
REM thi chi canh bao va VAN CHAY code hien co, khong dung lai.
REM Sau do chay server tu chinh thu muc cua script.
REM Chu y: file nay khong dung khoi lenh trong ngoac don, vi cac
REM dau ngoac don trong thong bao se lam cmd bao loi.
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR="
if exist "%SCRIPT_DIR%.git" set "REPO_DIR=%SCRIPT_DIR%"
if not defined REPO_DIR if exist "%SCRIPT_DIR%..\.git" set "REPO_DIR=%SCRIPT_DIR%.."
if not defined REPO_DIR goto :nogit
echo [CAP NHAT] Dang lay code moi nhat tu GitHub...
pushd "%REPO_DIR%"
where git >nul 2>nul
if errorlevel 1 goto :nogitcmd
git pull --ff-only
if errorlevel 1 goto :pullfail
popd
goto :run
:nogitcmd
popd
echo [CANH BAO] Khong tim thay git. Bo qua buoc cap nhat, chay code hien co.
goto :run
:pullfail
popd
echo [CANH BAO] git pull that bai. Bo qua, chay code hien co.
goto :run
:nogit
echo [CANH BAO] Khong tim thay thu muc .git. Day co the la ban tai ZIP nen khong pull duoc.
echo Hay clone 1 lan: git clone https://github.com/xayza/VibeEdit.git roi chay script trong thu muc windows cua ban clone.
echo Van chay code hien co o duoi day.
goto :run
:run
cd /d "%SCRIPT_DIR%"
if not exist "%SCRIPT_DIR%vibeedit.py" goto :novibeedit
where python >nul 2>nul
if errorlevel 1 goto :nopython
where ffmpeg >nul 2>nul
if errorlevel 1 echo [CANH BAO] Khong tim thay FFmpeg trong PATH. Server van chay, nhung xuat video va xem truoc can FFmpeg.
echo.
echo [OK] Dang chay VibeEdit tai http://127.0.0.1:8000/
echo De dung app: bam Ctrl+C trong cua so nay.
python "%SCRIPT_DIR%vibeedit.py" serve --port 8000 --open-browser
goto :end
:novibeedit
echo [LOI] Khong tim thay vibeedit.py cung thu muc voi update_and_run.bat.
echo Hay copy ca thu muc windows roi chay lai.
pause
exit /b 1
:nopython
echo [LOI] Khong tim thay Python. Vui long cai Python 3.10+ va tick Add python.exe to PATH khi cai dat.
pause
exit /b 1
:end
