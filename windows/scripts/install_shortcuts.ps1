# VibeEdit Windows shortcut installer (run on Windows).
# Creates a Start Menu shortcut and a Desktop shortcut that launch
# run_vibeedit.bat (the double-click launcher). Run from the repo's
# windows/ folder, or pass -VibeEditDir <folder>.
param([string]$VibeEditDir = (Split-Path -Parent $PSScriptRoot))

$launcher = Join-Path $VibeEditDir "run_vibeedit.bat"
if (-not (Test-Path $launcher)) {
    Write-Error "run_vibeedit.bat not found in $VibeEditDir"
    exit 1
}
$shell = New-Object -ComObject WScript.Shell
$startMenu = Join-Path $shell.SpecialFolders("Programs") "VibeEdit.lnk"
$desktop = Join-Path $shell.SpecialFolders("Desktop") "VibeEdit.lnk"
foreach ($target in @($startMenu, $desktop)) {
    $shortcut = $shell.CreateShortcut($target)
    $shortcut.TargetPath = $launcher
    $shortcut.WorkingDirectory = $VibeEditDir
    $shortcut.Description = "VibeEdit — CapCut-style video editor (Windows port)"
    $shortcut.Save()
    Write-Host "Created shortcut: $target"
}
Write-Host "Done. Launch VibeEdit from Start Menu or Desktop."
