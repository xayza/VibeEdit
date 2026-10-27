@echo off
REM VibeEdit - Cap nhat roi chay (khong can tai ZIP moi lan).
REM Neu co .git (ban clone tu GitHub) thi git pull truoc; neu khong
REM co git hoac pull loi thi chi canh bao va VAN CHAY code hien co,
REM khong dung lai. Sau do chay server tu chinh thu muc cua script.
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR="
if exist "%SCRIPT_DIR%.git" set "REPO_DIR=%SCRIPT_DIR%"
if not defined REPO_DIR if exist "%SCRIPT_DIR%..\.git" set "REPO_DIR=%SCRIPT_DIR%.."
if defined REPO_DIR (
  echo [CAP NHAT] Dang lay code moi nhat tu GitHub (git pull --ff-only)...
  pushd "%REPO_DIR%"
  where git >nul 2>nul
  if errorlevel 1 (
    echo [CANH BAO] Khong tim thay git. Bo qua buoc cap nhat, chay code hien co.
  ) else (
    git pull --ff-only
    if errorlevel 1 echo [CANH BAO] git pull that bai (co the do xung dot hoac mat mang). Bo qua, chay code hien co.
  )
  popd
) else (
  echo [CANH BAO] Khong tim thay thu muc .git. Day co the la ban tai ZIP nen khong pull duoc.
  echo Hay clone 1 lan: git clone https://github.com/xayza/VibeEdit.git roi chay script trong thu muc windows\ cua ban clone.
  echo Van chay code hien co o duoi day.
)
cd /d "%SCRIPT_DIR%"
if not exist "%SCRIPT_DIR%vibeedit.py" (
  echo [LOI] Khong tim thay vibeedit.py cung thu muc voi update_and_run.bat: %SCRIPT_DIR%vibeedit.py
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
if errorlevel 1 echo [CANH BAO] Khong tim thay FFmpeg trong PATH. Server van chay, nhung xuat video / xem truoc can FFmpeg.
echo.
echo [OK] Dang chay VibeEdit tai http://127.0.0.1:8000/
echo De dung app: bam Ctrl+C trong cua so nay.
python "%SCRIPT_DIR%vibeedit.py" serve --port 8000 --open-browser
