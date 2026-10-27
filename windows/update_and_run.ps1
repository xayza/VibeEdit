# VibeEdit - Cap nhat roi chay (khong can tai ZIP moi lan).
# Neu co .git (ban clone tu GitHub) thi git pull truoc; neu khong
# co git hoac pull loi thi chi canh bao va VAN CHAY code hien co,
# khong dung lai. Sau do chay server tu chinh thu muc cua script.
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path $MyInvocation.MyCommand.Path -Parent }
$repoDir = $null
if (Test-Path (Join-Path $scriptDir ".git")) { $repoDir = $scriptDir }
elseif (Test-Path (Join-Path (Join-Path $scriptDir "..") ".git")) { $repoDir = Join-Path $scriptDir ".." }
if ($repoDir) {
  Write-Host "[CAP NHAT] Dang lay code moi nhat tu GitHub (git pull --ff-only)..."
  Push-Location $repoDir
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[CANH BAO] Khong tim thay git. Bo qua buoc cap nhat, chay code hien co."
  } else {
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
      Write-Host "[CANH BAO] git pull that bai (co the do xung dot hoac mat mang). Bo qua, chay code hien co."
    }
  }
  Pop-Location
} else {
  Write-Host "[CANH BAO] Khong tim thay thu muc .git. Day co the la ban tai ZIP nen khong pull duoc."
  Write-Host "Hay clone 1 lan: git clone https://github.com/xayza/VibeEdit.git roi chay script trong thu muc windows\ cua ban clone."
  Write-Host "Van chay code hien co o duoi day."
}
Set-Location $scriptDir
$app = Join-Path $scriptDir "vibeedit.py"
if (-not (Test-Path $app)) {
  Write-Host "[LOI] Khong tim thay vibeedit.py cung thu muc voi update_and_run.ps1: $app"
  Write-Host "Hay copy ca thu muc windows\ (gom vibeedit.py, vibeedit_core\, static\) roi chay lai."
  Read-Host "Nhan Enter de thoat"
  exit 1
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "[LOI] Khong tim thay Python. Vui long cai Python 3.10+ va tick 'Add python.exe to PATH' khi cai dat."
  Read-Host "Nhan Enter de thoat"
  exit 1
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "[CANH BAO] Khong tim thay FFmpeg trong PATH. Server van chay, nhung xuat video / xem truoc can FFmpeg."
}
Write-Host ""
Write-Host "[OK] Dang chay VibeEdit tai http://127.0.0.1:8000/"
Write-Host "De dung app: bam Ctrl+C trong cua so nay."
python $app serve --port 8000 --open-browser
