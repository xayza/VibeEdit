@echo off
REM Thin wrapper around package_licenses.py: copies the GPLv3 text
REM and generates SOURCE_OFFER.txt plus THIRD_PARTY_NOTICE.txt
REM into dist\VibeEdit\THIRD_PARTY_LICENSES.
REM Build-time only. When FFMPEG_BUNDLE_URL is set, that URL is
REM recorded in SOURCE_OFFER.txt as the bundle the binaries came
REM from; when it is not set, the offer records that the binaries
REM came from the local install or were copied by hand.
REM This file deliberately uses no setlocal and no cd, so the
REM caller's directory is untouched and the exit code is the
REM Python script's exit code. Echo lines inside the blocks below
REM contain no parentheses, by the same rule that fixed the
REM update_and_run.bat v1 cmd bug.
if defined FFMPEG_BUNDLE_URL (
  python "%~dp0package_licenses.py" --dist "%~dp0..\dist\VibeEdit" --windows-dir "%~dp0.." --bundle-url "%FFMPEG_BUNDLE_URL%"
) else (
  python "%~dp0package_licenses.py" --dist "%~dp0..\dist\VibeEdit" --windows-dir "%~dp0.."
)
