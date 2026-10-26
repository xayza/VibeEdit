# VibeEdit — Windows (Phase 3)

A Windows re-implementation of the VibeEdit (formerly BashCut) video
editor's core: timeline editing, project JSON, CLI/MCP control and
FFmpeg rendering. The original macOS Swift app is preserved in
`VibeEdit/` in this repo; it cannot run on Windows (SwiftUI, AppKit
and AVFoundation are macOS-only), so this port re-implements the
timeline model in Python and renders with FFmpeg. See
`VibeEdit/docs/windows-port.md` for the full inventory and mapping.

## What Phase 3 adds (on top of Phase 2)

- Full transition library (all rendered with FFmpeg xfade on the
  build in this environment — FFmpeg 8.1.2): whip (wind), iris
  open/close (circleopen/circleclose), zoom-in (zoomin), glitch
  (pixelize), fadeblack/fadewhite, smooth left/right/up/down,
  cover/reveal left/right/up/down, diagonal TL/TR/BL/BR,
  horizontal/vertical slices, hblur, fadegrays, squeeze horizontal/
  vertical, vertical/horizontal open (barn-door equivalent), plus
  circlecrop, rectcrop, distance and wipe-tl/tr/bl/br. Kinds are
  validated the same way as Phase 2 (0.1–2.0 s, clips consecutive,
  no overlap per cut). The transition picker in the web UI lists
  the new kinds. NOT implemented (no xfade effect of that name in
  this FFmpeg build, and never silently replaced by dissolve):
  a true lens iris with mask animation, a glitch effect with RGB
  channel shift, and a zoom-out — `zoom` maps to zoomin only.
- Main-track keyframes now render: position/scale via zoompan
  (linear interpolation, per-frame), opacity via held segments
  (same stepwise approach as Phase 2 overlays), volume via a
  volume expression. The Phase 2 "stored but not rendered"
  limitation for main-track clips is gone, with two honest
  exceptions: a main-track clip that has BOTH motion keyframes
  (x/y/scale) and opacity keyframes renders opacity only and
  reports the motion as skipped (zoompan resets its frame counter
  per segment, so the timing would be wrong); main-track image
  (still) clips with keyframes are stored but not rendered.
- LUT strength (0–1) renders for real: a blended .cube is written
  per render by linearly mixing an identity LUT with the user's
  LUT at the given strength, so strength 0 renders (nearly)
  identical to no LUT and strength 1 is the full LUT. Preset
  colour (eq) is not strength-blended — it is applied at full
  strength, and combining preset + LUT keeps both filters.
- Batch export: `vibeedit.py batch <folder...> [--preset] [--normalize]`
  exports projects sequentially and reports success/failure per
  project without stopping on a failed one; the web UI has a Batch
  & OTIO panel (the open project is always exported first).
- OTIO export: `vibeedit.py otio-export <project>` (or the web UI
  button) writes a real OpenTimelineIO JSON file
  (`render/timeline.otio`): Stack with one Track per project
  track, Clip items with `source_range` (RationalTime at the
  project rate), `ExternalReference` to the media file,
  Transitions (SMPTE_Dissolve for dissolve/crossfade/fade,
  Custom for other kinds, with the VibeEdit kind/id/from/to kept
  in metadata), Markers, and per-clip metadata (id, at, speed,
  keyframes, colour, volume, fades). OTIO import is NOT included.
- Overlay audio: an overlay item whose media has audio renders
  that audio at its timeline position, mixed with main-track
  audio and music. Loudness normalisation: `export --normalize`
  (or the UI checkbox) applies single-pass loudnorm
  (I=-16, TP=-1.5, LRA=11) when audio exists.
- MCP expanded from 23 to 38 real tools (see below).
- Windows installer: `windows\build_windows.bat` (+
  `vibeedit.spec`) builds a one-folder PyInstaller app on Windows,
  and `windows\scripts\install_shortcuts.ps1` creates Start Menu
  + Desktop shortcuts to `run_vibeedit.bat`. The exe was NOT built
  on this Linux VM (PyInstaller cannot cross-build Windows) —
  the scripts are the deliverable, and they must be run on Windows.
- Plugins (minimal, real): `windows/plugins/` modules with a
  `register()` returning named hooks (`transform_text`,
  `apply_color`). Two working examples ship: `uppercase_text`
  and `vivid_color` (`plugin-list` / `plugin-run` CLI commands).
  This is a new Windows-port hook, NOT a port of the original
  macOS plugin system.
- Transcription entry point (real local provider only):
  `vibeedit.py transcribe <project> <media> [--model small]`
  calls faster-whisper when installed and adds segments as
  captions; when faster-whisper is absent it errors clearly with
  the install command and writes nothing. No other provider is
  bundled or stubbed; adding one means implementing the
  `transcribe(path, model) -> [(start_s, end_s, text)]` interface
  in `vibeedit_core/transcribe.py`.

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
  colorchannelmixer alpha has no time variable. Main-track
  keyframes were stored but not rendered in Phase 2 — Phase 3
  renders them (see above).
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

## What Phase 3 does NOT do yet

Adjustment layers, beat grid, agent dock terminals, OTIO import,
a Windows .exe built and tested on Windows, voice providers, or
the remaining ~211 original MCP tools (38 of 249 ported). Phase 4
candidates: additional transcription providers behind the
`transcribe.py` interface, main-track motion+opacity combined
rendering, LUT strength blending for eq presets, and a checked
PyInstaller build. See the Phase 3/4 lists in
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
python windows\vibeedit.py color windows\projects\myvideo <clip> --lut C:\luts\my.cube --preset vivid --strength 0.5
python windows\vibeedit.py marker-add windows\projects\myvideo "Intro" 0
python windows\vibeedit.py otio-export windows\projects\myvideo
python windows\vibeedit.py batch windows\projects\a windows\projects\b --normalize
python windows\vibeedit.py transcribe windows\projects\myvideo media\clip1.mp4 --model small
python windows\vibeedit.py plugin-list
python windows\vibeedit.py plugin-run windows\projects\myvideo uppercase_text transform_text <text-item-id>
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

38 tools (Phase 3 total) — Phase 2's 23 plus:
`vibeedit_markers_add/list/remove`, `vibeedit_transitions_list`,
`vibeedit_keyframes_get`, `vibeedit_clip_color_get`,
`vibeedit_clip_fade`, `vibeedit_project_info`,
`vibeedit_media_metadata`, `vibeedit_project_duplicate`,
`vibeedit_otio_export`, `vibeedit_batch_queue/run/status`,
`vibeedit_export_normalized`. Every tool calls a real Project or
export operation; none is a stub.

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
