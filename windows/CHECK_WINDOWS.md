# VibeEdit Windows checklist (Phase 6)

Step-by-step checks for running the Windows port on Windows. Every
step below was verified by reading the launcher/build scripts in
`windows/` (`run_vibeedit.bat`, `run_vibeedit.ps1`,
`build_windows.bat`, `vibeedit.spec`,
`scripts/install_shortcuts.ps1`); nothing here assumes a step the
scripts do not perform.

> Honest limits, stated up front: no Windows `.exe` was built on
> the Linux VM used for this port (PyInstaller cannot cross-build
> a Windows exe from Linux), and the web UI was not visually
> checked on Windows. Phase 6 adds the honest route to a
> ready-made exe: a GitHub Actions workflow that builds it on a
> real windows-latest runner (section 0). That workflow has NOT
> been run yet — it can only run on GitHub after it is pushed —
> so until its first green run appears, there is no exe to
> download; building locally (step 6) is the fallback.

## 0. Ready-made exe — download from GitHub Actions (recommended)

No Python install, no separate FFmpeg install, no build step:

1. Open https://github.com/xayza/VibeEdit in a browser.
2. Click the **Actions** tab, then the **Build Windows exe**
   workflow, then the latest **successful** run (green check).
   (If no successful run exists yet, the workflow has not run
   since it was added — wait for it, or build locally per step 6.)
3. Scroll to **Artifacts**, download **VibeEdit-Windows**,
   extract the zip to a writable folder.
4. Double-click **VibeEdit.exe**. With no arguments it starts
   the editor server and opens http://127.0.0.1:8000/ in your
   browser automatically (Phase 6 frozen-exe default). Close
   the VibeEdit console window to stop the app.
5. FFmpeg is already inside: `ffmpeg.exe` and `ffprobe.exe`
   sit next to `VibeEdit.exe` in the extracted folder, and the
   app looks for them there before PATH. Do not move
   `VibeEdit.exe` away from its folder on its own — the exe
   needs `_internal\` and the bundled FFmpeg next to it.

FFmpeg licence note: the artifact bundles the gyan.dev FFmpeg
essentials build. FFmpeg is GPL/LGPL-licensed software; the
bundled build's licence terms travel with it (see the FFmpeg
project's licence pages). If you redistribute the artifact,
include the FFmpeg licence information for that build.

## 1. Get the code

```bat
git clone https://github.com/xayza/VibeEdit
cd VibeEdit
```

Or download the repo ZIP and extract it. You need the whole
`windows\` folder together: `vibeedit.py`, `vibeedit_core\`,
`static\`, `plugins\`, plus the launcher scripts. Copying
`run_vibeedit.bat` alone somewhere else does not work — the
launcher now checks that `vibeedit.py` sits next to it and stops
with an error if it does not.

## 2. Install Python 3.10+

Download Python 3.10 or newer from python.org. During install,
tick **Add python.exe to PATH** (the launchers find Python with
`where python`, so without PATH they stop with
`[LOI] Khong tim thay Python`).

Check:

```bat
python --version
```

## 3. Install FFmpeg (+ FFprobe)

Option A — put FFmpeg on PATH (recommended). Download a full build
from https://www.gyan.dev/ffmpeg/builds/ and add its `bin` folder
to PATH, or:

```bat
winget install Gyan.FFmpeg
```

Option B — no PATH change: put `ffmpeg.exe` (and `ffprobe.exe`)
in the same folder as `vibeedit.py` / `VibeEdit.exe`, or point the
`VIBEEDIT_FFMPEG_DIR` environment variable at the folder that
contains them. The app searches in that order: `VIBEEDIT_FFMPEG_DIR`,
then PATH, then next to the script/executable.

Check:

```bat
ffmpeg -version
ffprobe -version
```

No Python packages are needed: the Windows port uses only the
Python standard library plus FFmpeg.

## 4. (Optional) virtual environment

Only needed if you want an isolated Python for the build step or
for running from a terminal. From the `windows\` folder:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

`build_windows.bat` creates `windows\.venv` itself if it does not
exist, so this step is not required before building.

## 5. Run the web UI

Double-click `windows\run_vibeedit.bat`, or right-click
`windows\run_vibeedit.ps1` → Run with PowerShell. The launcher
checks Python and FFmpeg, starts the server in its own window,
waits up to 30 seconds for http://127.0.0.1:8000/ to answer, then
opens your browser there.

From a terminal instead (from the repo root):

```bat
python windows\vibeedit.py serve --port 8000 --open-browser
```

(`--open-browser` is new in Phase 6: it opens the editor URL
once the server starts. Without it, open
http://127.0.0.1:8000/ yourself.)

or from inside `windows\`:

```bat
python vibeedit.py serve --port 8000
```

The default project lives in `windows\projects\default\`; pass
`--project <folder>` to use another project folder. While you use
the app, do NOT close the "VibeEdit Server" window — closing it
stops the app. To stop, close that window or press Ctrl+C in it.

## 6. Build a Windows exe (optional, on Windows only)

Prefer the ready-made artifact in section 0. To build locally
instead, from the `windows\` folder, double-click or run:

```bat
build_windows.bat
```

(Phase 6: the script's `pause` prompts are skipped when
`GITHUB_ACTIONS` is set, so the same script also runs
unattended in the Actions workflow.)

The script checks Python, creates/activates `windows\.venv`,
installs PyInstaller, and runs `pyinstaller vibeedit.spec`.
Output: `windows\dist\VibeEdit\VibeEdit.exe` (one-folder build).
FFmpeg is NOT bundled: keep FFmpeg on PATH, or copy `ffmpeg.exe`
(and `ffprobe.exe`) into `windows\dist\VibeEdit\` next to the exe.

Then, for Start Menu / Desktop shortcuts, run from `windows\`:

```powershell
scripts\install_shortcuts.ps1
```

(right-click → Run with PowerShell). The shortcuts point at
`run_vibeedit.bat` (the double-click launcher), not at the exe.
A frozen exe stores its default project next to the exe
(`dist\VibeEdit\projects\default\`), not inside the bundled data
folder; if you installed the app somewhere read-only, run it from
a writable folder or pass `--project` to a writable folder.

## 7. User checks on Windows (not done on the Linux VM)

- [ ] The Actions "Build Windows exe" run goes green, the
      VibeEdit-Windows artifact downloads, and double-clicking
      `VibeEdit.exe` opens the UI at http://127.0.0.1:8000/
      with no Python/FFmpeg install.
- [ ] `run_vibeedit.bat` opens the UI at http://127.0.0.1:8000/
      and an export renders (needs FFmpeg in PATH).
- [ ] The web UI looks right in a real browser (preview top,
      editor panel, timeline strip bottom, agent dock panel).
- [ ] `build_windows.bat` produces `dist\VibeEdit\VibeEdit.exe`
      and the exe starts and exports.
- [ ] A text overlay renders (needs a font: any `.ttf` in the
      system Fonts folder, or set `VIBEEDIT_FONT` to a `.ttf`).

## Common errors and fixes

| Error | Fix |
|---|---|
| `[LOI] Khong tim thay Python` | Reinstall Python 3.10+ with "Add python.exe to PATH" ticked, then reopen the terminal/launcher. |
| `[LOI] Khong tim thay FFmpeg` | Install FFmpeg on PATH (step 3), or put `ffmpeg.exe` next to the app, or set `VIBEEDIT_FFMPEG_DIR`. |
| `[LOI] Server khong phan hoi sau 30 giay` | Look at the "VibeEdit Server" window for the real error (often a missing font on export, or a port already in use). If port 8000 is taken, run `python vibeedit.py serve --port 8001` from `windows\` instead. |
| `No font found for text overlays` on export | Install a font into the system Fonts folder, or set `VIBEEDIT_FONT` to a `.ttf` file. Text-free projects export without a font. |
| `FFmpeg tool 'ffmpeg' not found` | Same as the FFmpeg row above; the message names the fix. |
| PowerShell refuses to run a `.ps1` | Use the `.bat` launcher instead — it needs no execution-policy change. |
| Launcher says `vibeedit.py` is missing | You copied the launcher alone: copy the whole `windows\` folder (step 1). |
| Export fails with a LUT error | The `.cube` path must exist on your machine and end in `.cube`; a bad LUT is a hard error, never silently skipped. |
| Export fails: `No option name near '/Windows/Fonts/...'` | **Fixed in Phase 7.** FFmpeg splits filter options on unescaped colons even inside quotes, so a Windows drive path broke drawtext. The app now escapes every colon as `\:` in filter paths. If you still see this on an older checkout, pull the latest code. |
| Vietnamese text shows as mojibake (e.g. `xin chÃ o`) in export errors | **Fixed in Phase 7.** FFmpeg error output is now decoded as UTF-8 instead of the Windows locale codepage. The project file itself was always UTF-8; only the displayed error was mangled. Pull the latest code. |
