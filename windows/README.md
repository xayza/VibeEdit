# VibeEdit — Windows (Phase 2)

A Windows re-implementation of the VibeEdit (formerly BashCut) video
editor's core: timeline editing, project JSON, CLI/MCP control and
FFmpeg rendering. The original macOS Swift app is preserved in
`VibeEdit/` in this repo; it cannot run on Windows (SwiftUI, AppKit
and AVFoundation are macOS-only), so this port re-implements the
timeline model in Python and renders with FFmpeg. See
`VibeEdit/docs/windows-port.md` for the full inventory and mapping.

## What Phase 2 adds (on top of Phase 1)

- Transitions between consecutive main-track clips: crossfade
  (dissolve), wipe left/right/up/down, slide left/right/up/down,
  duration 0.1–2.0 s, rendered with FFmpeg xfade/acrossfade. The
  output timeline is shorter than the project timeline by the sum
  of transition durations; overlays, text and music after a
  transition boundary shift earlier by the same amount.
- Keyframes (times in seconds relative to the clip start, edited in
  the inspector): position (x/y) and scale for overlay/text clips,
  opacity for overlay/text clips, volume for audio clips. Position,
  scale and volume are rendered with linear interpolation; text
  opacity is rendered linearly; overlay opacity is rendered
  stepwise (held at each keyframe value) because FFmpeg's
  colorchannelmixer alpha has no time variable. Keyframes on
  main-track clips are stored but not rendered yet.
- SRT import (into the Captions track, overlap-rejected) and export.
- Colour: per-clip .cube LUT via lut3d (a missing/invalid LUT is a
  hard error, never a silent skip) and eq presets (vivid, warm,
  cool, faded, mono).
- MCP expanded from 9 to 23 real tools (see below).
- Windows launcher: double-click `windows\run_vibeedit.bat` (or
  right-click `windows\run_vibeedit.ps1` → Run with PowerShell);
  it checks Python + FFmpeg, starts the server, polls the port and
  opens the browser. See `windows/INSTALL.md` (Vietnamese).

## What Phase 1 does

- CapCut-style web UI: preview on top, editor/inspector panel in
  the middle, multi-track timeline strip at the bottom (Main,
  Overlay, Captions, Dialogue, Music). Click a clip to select it,
  drag it to move it (including across tracks), click the ruler to
  move the playhead, press `S` to split the selected clip at the
  playhead. Undo/redo (50 steps), media upload, clip/text editing.
- CLI (`vibeedit.py`): new, open, list, timeline, add, text, trim,
  split, move, delete, speed, undo, export, serve, mcp.
- MCP server (`vibeedit_core/mcp.py`): stdio JSON-RPC, tools
  `vibeedit_project_*`, `vibeedit_timeline_*`, `vibeedit_media_list`,
  `vibeedit_export_start` — real operations, not stubs.
- FFmpeg export: project resolution (default 1080x1920) or draft
  (half resolution), H.264/AAC, clips in timeline order, gaps as
  black + silence, text overlays, speed (setpts/atempo), fades,
  overlay video compositing, mixed audio. Preview plays the latest
  export only — it is not a live GPU timeline render.
- Project format: `vibeedit.project/1`, and it also opens original
  `bashcut.project/1` / `project.bashcut.json` files. Unknown
  fields round-trip unchanged.

## What Phase 2 does NOT do yet

Adjustment layers, transcription/voice providers, beat grid,
plugins, agent dock terminals, Resolve/OTIO export, batch
processing, overlay-item audio, a real Windows installer, or the
remaining ~226 original MCP tools. See the Phase 3 list in
`VibeEdit/docs/windows-port.md`.

## Requirements

- Python 3.10+ (stdlib only, no pip packages).
- FFmpeg + FFprobe in `PATH` (rendering and media probing).
  On Windows, download a build from gyan.dev or use
  `winget install Gyan.FFmpeg`, then make sure `ffmpeg` is on PATH.

## Run the web UI (Windows)

Double-click `windows\run_vibeedit.bat`, or from a terminal:

```bat
cd VibeEdit
python windows\vibeedit.py serve --port 8000
```

Then open http://127.0.0.1:8000/ in a browser. The default project
lives in `windows\projects\default\`. To use another project folder,
pass `--project <folder>`. Put your media files in the project's
`media\` folder (or use the Upload button), add clips from the
editor panel, then Export.

## Run the CLI

```bat
python windows\vibeedit.py new myvideo --dir windows\projects --width 1080 --height 1920
python windows\vibeedit.py add windows\projects\myvideo media\clip1.mp4 v1 0 --dur 90
python windows\vibeedit.py text windows\projects\myvideo t1 0 60 "Hello VibeEdit"
python windows\vibeedit.py transition windows\projects\myvideo <clip1> <clip2> dissolve 0.5
python windows\vibeedit.py keyframe windows\projects\myvideo <clip> 1.0 opacity 0.5
python windows\vibeedit.py color windows\projects\myvideo <clip> --lut C:\luts\my.cube --preset vivid
python windows\vibeedit.py srt-import windows\projects\myvideo captions.srt
python windows\vibeedit.py srt-export windows\projects\myvideo captions_out.srt
python windows\vibeedit.py timeline windows\projects\myvideo
python windows\vibeedit.py export windows\projects\myvideo --preset full
```

Times in CLI arguments are frames (the original's unit). Export
presets: `full` (project resolution) and `draft` (half resolution).

## Open an original BashCut project

Copy the project folder (or at least its `project.bashcut.json` and
its media) into `windows\projects\<name>\`, then:

```bat
python windows\vibeedit.py open windows\projects\<name>
python windows\vibeedit.py serve --project windows\projects\<name>
```

The MVP reads the original schema and preserves fields it does not
understand; saving writes `project.vibeedit.json` next to it (the
original file is left untouched). Media paths are resolved relative
to the project folder; `@assets/...` workspace paths and symlinked
`footage/` folders from macOS are NOT resolved in Phase 1 — copy
the media files into the project folder first.

## MCP server

```bat
python windows\vibeedit.py mcp windows\projects\myvideo
```

The server speaks newline-delimited JSON-RPC 2.0 on stdin/stdout
(`initialize`, `ping`, `tools/list`, `tools/call`). Point any
MCP-compatible agent at it with the `vibeedit-mcp` server name.

23 tools (Phase 2 total): `vibeedit_project_get/create/open/save`,
`vibeedit_timeline_get/apply/undo`, `vibeedit_media_list/place`,
`vibeedit_clip_trim/split/move/delete/speed/keyframes/color`,
`vibeedit_text_add`, `vibeedit_transition_set/remove`,
`vibeedit_srt_import/export`, `vibeedit_export_start/status`.
Every tool calls a real Project operation; none is a stub.

## Tests

```bat
cd windows
python -m unittest discover -s tests -v
```

Tests generate their own media with FFmpeg into a temp folder; no
real footage, no network, no Swift toolchain needed.

## Honest limits

- The renamed Swift tree in `VibeEdit/` has NOT been compiled on
  Windows (impossible) or on macOS in this environment — the macOS
  build needs Xcode 16+ on macOS 14 before any macOS release.
- The web UI has NOT been visually checked in a real browser on
  Windows in this environment (API + unit checks only).
- Logo artwork still shows the old BashCut mark until a VibeEdit
  logo is supplied.
