# VibeEdit Windows launcher (right-click -> Run with PowerShell).
# Checks Python + FFmpeg, starts the web server, opens the browser.
#
# Layout fix (Phase 5): this script runs vibeedit.py from its OWN
# folder ($PSScriptRoot). It used to change directory to the parent
# and run windows\vibeedit.py, which only worked for a full repo
# checkout and broke when only the windows\ folder was copied
# elsewhere (the parent then has no windows\ subfolder). vibeedit.py
# sits next to this launcher in both layouts, so no directory change
# is needed, and the server resolves its project/static folders
# relative to its own files, not to the working directory.
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path $MyInvocation.MyCommand.Path -Parent }
$app = Join-Path $scriptDir "vibeedit.py"
Write-Host "============================================"
Write-Host " VibeEdit - Dang khoi dong..."
Write-Host "============================================"

if (-not (Test-Path $app)) {
  Write-Host "[LOI] Khong tim thay vibeedit.py cung thu muc voi run_vibeedit.ps1: $app"
  Write-Host "Hay copy ca thu muc windows\ (gom vibeedit.py, vibeedit_core\, static\) roi chay lai."
  Read-Host "Nhan Enter de thoat"
  exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "[LOI] Khong tim thay Python. Vui long cai Python 3.10+ va tick 'Add python.exe to PATH' khi cai dat."
  Read-Host "Nhan Enter de thoat"
  exit 1
}
# Chap nhan FFmpeg o 3 cho, giong nhu bo render: thu muc chi dinh
# trong VIBEEDIT_FFMPEG_DIR, FFmpeg co tren PATH, hoac ffmpeg.exe
# cung thu muc voi launcher nay. Truoc day chi chap nhan PATH nen
# nguoi dung da cai dung theo huong dan van bi chan o day.
$ffmpegOk = $false
if ($env:VIBEEDIT_FFMPEG_DIR -and (Test-Path (Join-Path $env:VIBEEDIT_FFMPEG_DIR "ffmpeg.exe"))) { $ffmpegOk = $true }
elseif (Get-Command ffmpeg -ErrorAction SilentlyContinue) { $ffmpegOk = $true }
elseif (Test-Path (Join-Path $scriptDir "ffmpeg.exe")) { $ffmpegOk = $true }
if (-not $ffmpegOk) {
  Write-Host "[LOI] Khong tim thay FFmpeg. Hay lam 1 trong 3 cach: them FFmpeg vao PATH, dat ffmpeg.exe cung thu muc voi VibeEdit, hoac dat bien moi truong VIBEEDIT_FFMPEG_DIR tro toi thu muc chua ffmpeg.exe."
  Read-Host "Nhan Enter de thoat"
  exit 1
}

Write-Host "[OK] Da thay Python va FFmpeg."
Start-Process -FilePath "python" -ArgumentList $app, "serve", "--port", "8000" -WindowStyle Minimized -PassThru | Out-Null
Write-Host "Dang cho server khoi dong (toi da 30 giay)..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/" -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $ok = $true; break }
  } catch { Start-Sleep -Seconds 1 }
}
if (-not $ok) {
  Write-Host "[LOI] Server khong phan hoi sau 30 giay."
  Read-Host "Nhan Enter de thoat"
  exit 1
}
Start-Process "http://127.0.0.1:8000/"
Write-Host ""
Write-Host "VibeEdit dang chay tai http://127.0.0.1:8000/"
Write-Host "De dung app: tat tien trinh python dang chay server (Task Manager) hoac dong cua so server."
Read-Host "Nhan Enter de thoat cua so nay (server van chay)"
