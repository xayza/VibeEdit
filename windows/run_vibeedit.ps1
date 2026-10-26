# VibeEdit Windows launcher (right-click -> Run with PowerShell).
# Checks Python + FFmpeg, starts the web server, opens the browser.
Set-Location (Split-Path $MyInvocation.MyCommand.Path -Parent) | Out-Null
Set-Location ..
Write-Host "============================================"
Write-Host " VibeEdit - Dang khoi dong..."
Write-Host "============================================"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "[LOI] Khong tim thay Python. Vui long cai Python 3.10+ va tick 'Add python.exe to PATH' khi cai dat."
  Read-Host "Nhan Enter de thoat"
  exit 1
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "[LOI] Khong tim thay FFmpeg. Vui long cai FFmpeg va them vao PATH."
  Read-Host "Nhan Enter de thoat"
  exit 1
}

Write-Host "[OK] Da thay Python va FFmpeg."
Start-Process -FilePath "python" -ArgumentList "windows\vibeedit.py", "serve", "--port", "8000" -WindowStyle Minimized -PassThru | Out-Null
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
