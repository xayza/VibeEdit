# VibeEdit Windows shortcut installer (run on Windows).
# Creates a Start Menu shortcut and a Desktop shortcut that launch
# run_vibeedit.bat (the double-click launcher). Run from the repo's
# windows/ folder, or pass -VibeEditDir <folder>.
# Path note (Phase 5, verified): this script lives in windows\scripts\,
# so $PSScriptRoot's parent is windows\, which is where
# run_vibeedit.bat lives — the default below is correct, and the
# shortcuts intentionally target run_vibeedit.bat, not the PyInstaller
# exe (the exe still needs the launcher's Python/FFmpeg checks
# documented in INSTALL.md; point -VibeEditDir at a folder that
# contains run_vibeedit.bat).
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
