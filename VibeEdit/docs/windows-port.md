# VibeEdit Windows port — Phase 1 inventory and mapping

> Status: Phase 1. The original macOS Swift code is preserved in this
> tree (renamed VibeEdit) and is NOT deleted. The Windows MVP in
> `windows/` is a separate Python implementation. SwiftUI/AppKit/
> AVFoundation code cannot run on Windows, so "keep everything" in
> Phase 1 means: keep the features, the project format, the edit
> operations and the CLI/MCP behaviour — the macOS UI and media
> layers are re-implemented for Windows (web UI + FFmpeg).
> Swift compilation was NOT verified on the Linux VM used for this
> port; the macOS build needs a macOS/Xcode check before release.

## 1. What was renamed

- Product: BashCut → VibeEdit; CLI `bashcut` → `vibeedit`;
  MCP server `bashcut-mcp` → `vibeedit-mcp`; package `BashCut` →
  `VibeEdit`; modules `BashCut*` → `VibeEdit*` (e.g. `BashCutProject`
  → `VibeEditProject`); project file `project.bashcut.json` →
  `project.vibeedit.json`; cache folder `.bashcut/` → `.vibeedit/`;
  schema `bashcut.project/1` → `vibeedit.project/1`.
- Top folder `BashCut-main/` → `VibeEdit/` (no file referenced the
  old folder name, so this rename is safe).
- Kept as attribution: MIT License, "Copyright (c) 2026 Nolan".
  No new author was invented.
- Deliberately NOT renamed (they point at the original author's
  external resources and renaming them would break links):
  `github.com/dongnguyenvie/BashCut`, `bashcut.birchapps.com`,
  `bashcut-agent-kit` (a separate repository), the Homebrew tap
  `dongnguyenvie/tap/bashcut`, and the CHANGELOG history entries
  below the header (history is a record, not branding). Logo
  artwork (`.github/assets/logo.png`, `app.gif`) still shows the old
  mark until the user supplies a VibeEdit logo.

## 2. Project format (original, and what the Windows MVP reads)

Source of truth: `docs/specs/02-project-format.md` and
`docs/reference/project.schema.json`. A project folder contains
`project.vibeedit.json` (originally `project.bashcut.json`) plus
`footage/` (symlink, read-only), `media/`, `voiceover/`,
`subtitles/`, `render/` and `.vibeedit/` (history, autosave, cache).

Top-level fields (Windows MVP reads/writes all of these; unknown
fields round-trip unchanged):

| Field | Meaning |
|---|---|
| `schema` | `vibeedit.project/1` (MVP also opens `bashcut.project/1`) |
| `id`, `name`, `rev` | Stable ID, project name, revision (+1 per edit) |
| `format` | `{width, height, fps: [num, den], sampleRate}` |
| `contentLanguage` | BCP 47 language of speech/captions (default `vi`) |
| `media[]` | `{id, path (relative), kind, fps, frames, width, height, hasAudio}` |
| `tracks[]` | Ordered back-to-front: visual tracks first, then audio |
| `transitions[]` | `{id, kind, from, to, duration}` (frames; rendered since Phase 2: crossfade/wipe/slide; full library since Phase 3: whip, iris, zoom, glitch, etc.) |
| `markers[]` | `{id, at, kind, label}` (sections) |
| `luts[]`, `providers`, `audio`, `beatGrid` | Preserved; Phase 1 does not apply LUTs/beat grids |

Track roles in the original: video `main` (exactly one, undeletable)
and `overlay`, `adjustment`, `text` (`captions`), audio `dialogue`,
`voiceover`, `music` (with ducking fields), `sfx`.

Item fields: `id`, `media`, `in` (source frame at the media fps),
`dur` and `at` (timeline frames at the project fps), `tag`
(`role`: `speech`/`broll`/`underVO`, `section`), `transform`
(`zoom`, `pan`, `tilt`), `speed`, `color` (LUT + strength),
`linkedAudio`/`linkedVideo`, `text` + `textStyle`
(`size` as a share of frame height, `positionX`/`positionY`),
`keyframes`, `volume` (dB), `fadeIn`/`fadeOut`, `crop`,
`interop` (reserved, preserved).

Rules kept in the MVP: integer-frame timing; stable IDs (split keeps
the ID on the left half); no overlap on one track; visual tracks
before audio tracks; atomic saves; `rev` increments per edit.
Fields the port does not yet interpret (kept, not dropped):
main-track `keyframes`, `adjustment` items, `beatGrid`,
`providers`, `interop`, `targets`. (Overlay/text keyframes and
per-clip LUT/colour presets are interpreted since Phase 2.)

## 3. Core edit operations (original → Windows MVP)

Original operations are atomic `EditOperation` batches applied by
`timeline apply --base-rev N` (see `docs/specs/05-agent-integration.md`
and `docs/reference/commands.md`: 249 commands in total).

| Original | Windows MVP (Phase 1) |
|---|---|
| `project create/open/save` | `vibeedit new/open`, web UI, MCP `vibeedit_project_*` |
| `timeline get --format text\|json` | `vibeedit timeline`, MCP `vibeedit_timeline_get` |
| `timeline apply` (trim, split, move, delete, set properties) | `vibeedit trim/split/move/delete/speed`, MCP `vibeedit_timeline_apply` |
| `media place`, `layers add` | `vibeedit add` (clip), web UI add-clip form |
| `media import` | Web UI media upload → `media/`; CLI `add` with ffprobe metadata |
| `captions import/export` (SRT) | Phase 2: `vibeedit srt-import/srt-export`, UI SRT panel, MCP `vibeedit_srt_import/export` |
| `timeline undo/redo` | CLI undo via `.bak` file; web UI undo/redo (50-step session history) |
| `export start` | `vibeedit export --preset draft\|full`, web UI Export buttons, MCP `vibeedit_export_start` |
| `media proxy`, `media analyze`, `media transcribe` | Not in Phase 1 (no ML providers bundled, same as the original's stance) |

## 4. CLI and MCP mapping

Original CLI: `bashcut <group> <command>`; original MCP tools:
`bashcut_<group>_<command>` (249 tools) plus plugin-action tools
`bashcut_action_<id>`, served by `bashcut-mcp` over stdio, forwarding
to the app's automation socket.

Windows CLI: `python windows/vibeedit.py <command>` (see
`windows/README.md` for the full list). Windows MCP:
`windows/vibeedit_core/mcp.py`, stdio JSON-RPC 2.0, server name
`vibeedit-mcp`, with real tools that call the same Project
operations as the CLI and web UI — 38 tools after Phase 3 (see
`windows/README.md` for the list).

Not yet ported (Phase 3): the remaining ~226 tools (review, beats,
audio measurement, knowledge/skills, plugins, UI actions/dialogs,
agent dock terminals, Resolve/OTIO export, batch), plugin-action
tools, and the socket-based live app connection (the MCP server
is single-project and edits the project file directly).

## 5. macOS-only modules → Windows mapping

| macOS layer | Windows Phase 1 replacement | Limit |
|---|---|---|
| SwiftUI + AppKit UI, timeline, viewer | Web UI (`windows/static/`): preview top, editor panel, multi-track timeline strip bottom, CapCut-style | Preview plays the latest export only; no live timeline scrub |
| AVFoundation + Core Image/Metal render | FFmpeg (`windows/vibeedit_core/render.py`): concat/xfade segments, scale/crop fill, drawtext, setpts/atempo, fade/afade, amix, lut3d, eq presets, keyframe expressions, zoompan main-track keyframes, blended-LUT strength, overlay audio, loudnorm | No Metal effects; main-track motion+opacity combined and still-image keyframes not rendered (see §7) |
| AVFoundation preview proxies | Draft export (half resolution, veryfast) | No per-clip proxy generation |
| Core Text captions | FFmpeg drawtext (DejaVu on Linux, Arial/Segoe UI on Windows) | One style per caption item; no word-by-word karaoke |
| SwiftTerm agent dock (Claude/Codex terminals) | Not ported | Agents use the MCP server / CLI from their own terminal |
| Plugins (out-of-process, versioned API) | Minimal in-process hook in Phase 3 (`windows/plugins/`, `transform_text`/`apply_color`) — NOT the original plugin system | Plugin results are preserved as project data only |
| macOS Keychain secrets, Application Support paths | Plain project folder on Windows; no secrets are stored by the MVP | Do not put API keys in project JSON |

## 6. Phase 2 — DONE (what Phase 1 did not do, now implemented)

- Transitions: `transitions[]` keeps the original shape
  `{id, kind, from, to, duration}` with duration in frames; kinds
  accepted are `dissolve` (also `crossfade`/`fade`), `wipe`,
  `wipe-left/right/up/down`, `slide`, `slide-left/right/up/down`,
  mapping to FFmpeg xfade names (fade, wipeleft, wiperight, wipeup,
  wipedown, slideleft, slideright, slideup, slidedown). Duration
  0.1–2.0 s, must not exceed the shorter adjacent clip, clips must
  be directly consecutive on the main track. Rendered with xfade
  (video) + acrossfade (audio); edge fades on the incoming side
  are skipped at a transition. Output timeline = project timeline
  minus transition durations (overlays/text/music after a boundary
  shift earlier accordingly). Transition preview stills from the
  original are NOT ported.
- Keyframes: stored on items as `keyframes[]` with `at` in frames
  relative to the item start and properties `x`, `y` (0..1),
  `scale` (>0), `opacity` (0..1), `volume` (dB, -60..24). Rendered
  linearly: overlay/text position (overlay x/y and drawtext x/y
  expressions use main-timeline time), overlay/text scale (scale
  and drawtext fontsize expressions), text opacity (drawtext alpha
  expression), audio volume (volume expression, eval=frame).
  Overlay opacity is rendered stepwise (clip split at opacity
  keyframes, constant alpha per segment) because FFmpeg's
  colorchannelmixer alpha expression has no time variable.
  Keyframes on main-track clips are stored but not rendered.
- LUT/colour: item `color` = `{lut, preset, strength}`; LUT via
  FFmpeg lut3d (validated .cube with LUT_3D_SIZE; missing/invalid
  is a hard error). Presets via eq: vivid, warm, cool, faded, mono.
  Adjustment layers are NOT ported.
- SRT: import into a text track (overlap-rejected, validated
  before any cue is added) and export from a text track; CLI
  `srt-import`/`srt-export`, UI import/export, MCP
  `vibeedit_srt_import/export`.
- MCP: 23 real tools (was 9). New: media_place, clip_trim/split/
  move/delete/speed/keyframes/color, text_add, transition_set/
  remove, srt_import/export, export_status.
- Windows launcher: `windows/run_vibeedit.bat` + `run_vibeedit.ps1`
  (check Python + FFmpeg, start server, poll port, open browser)
  and `windows/INSTALL.md` (Vietnamese).

## 7. Phase 3 — DONE (what Phase 2 did not do, now implemented)

- Full transitions library (all verified against FFmpeg 8.1.2's
  xfade list, never silently replaced by dissolve): whip
  (wind left/right/up/down), iris open/close (circleopen/
  circleclose), zoom-in (zoomin), glitch (pixelize), fadeblack,
  fadewhite, fadefast, fadeslow, smooth left/right/up/down,
  cover/reveal left/right/up/down, diagonal TL/TR/BL/BR,
  horizontal/vertical slices, hblur, fadegrays, squeeze
  horizontal/vertical, vertical/horizontal open (barn-door
  equivalent), circlecrop, rectcrop, distance, wipe-tl/tr/bl/br.
  NOT implemented (no such xfade effect in this FFmpeg build):
  a true lens iris with mask animation, a glitch with RGB
  channel shift, and zoom-out (`zoom` maps to zoomin only).
  Transition preview stills from the original are NOT ported.
- Main-track keyframes now render: position/scale via zoompan
  (linear interpolation; a trailing fps filter after zoompan is
  deliberately omitted because it duplicated frames ~512x on
  this FFmpeg build — verified 90 input frames became 46080),
  opacity stepwise (as Phase 2 overlays), volume via a volume
  expression. Exceptions, reported in the render `skipped` list:
  a main clip with BOTH motion and opacity keyframes renders
  opacity only (zoompan's frame counter restarts per segment),
  and main-track image (still) clips with keyframes are stored
  but not rendered.
- LUT strength blending (0–1) renders for real: a blended .cube
  is written per render by linearly mixing an identity LUT with
  the user's LUT at the given strength (grid order R fastest,
  then G, then B; DOMAIN_MIN/MAX honoured). Verified: strength 0
  renders identically to no LUT (mean VAVG 127.3 = source) and
  strength 1 is the full LUT (mean VAVG 240.0 for a red LUT).
  Strength 0 skips the lut3d filter entirely. eq presets are not
  strength-blended. Adjustment layers are NOT ported.
- Batch export: `vibeedit.py batch <folder...>` (CLI) and the
  web UI Batch & OTIO panel (the open project is exported
  first); projects export sequentially, one failure never stops
  the others, and each result reports ok/output/duration or an
  error.
- OTIO export: `vibeedit.py otio-export` writes a real
  OpenTimelineIO JSON file (Timeline.1 → Stack.1 → one Track.1
  per project track; Clip.1 with source_range RationalTime at
  the project rate and ExternalReference to the media file;
  Transition.1 with SMPTE_Dissolve for dissolve/crossfade/fade
  and Custom otherwise, VibeEdit kind/id/from/to in metadata;
  Marker.1 on the Stack; per-clip id/at/speed/keyframes/colour/
  volume/fades in metadata). OTIO import is NOT included.
- Overlay-item audio renders at its timeline position, mixed
  with main-track audio and music. Loudness normalisation:
  `export --normalize` (or the UI checkbox) applies single-pass
  loudnorm (I=-16, TP=-1.5, LRA=11) when audio exists.
- MCP: 38 real tools (was 23). New: markers_add/list/remove,
  transitions_list, keyframes_get, clip_color_get, clip_fade,
  project_info, media_metadata, project_duplicate, otio_export,
  batch_queue/run/status, export_normalized.
- Windows installer: `windows/build_windows.bat` +
  `vibeedit.spec` (PyInstaller one-folder, same `vibeedit.py`
  entry point; FFmpeg still required separately) and
  `windows/scripts/install_shortcuts.ps1` (Start Menu + Desktop
  shortcuts to `run_vibeedit.bat`). The exe was NOT built on the
  Linux VM (PyInstaller cannot cross-build Windows) — the
  scripts are the deliverable and must run on Windows.
- Plugins (minimal, real, Windows-port-only hook — NOT a port
  of the original macOS plugin system): `windows/plugins/`
  modules with `register()` returning named hooks
  (`transform_text`, `apply_color`); two working examples ship
  (`uppercase_text`, `vivid_color`); CLI `plugin-list` /
  `plugin-run`.
- Transcription entry point (real local provider only):
  `vibeedit.py transcribe <project> <media> [--model small]`
  calls faster-whisper when installed and adds segments as
  captions; when faster-whisper is absent it errors clearly
  with the install command and writes nothing. No other
  provider is bundled or stubbed. A new provider implements
  `transcribe(path, model) -> [(start_s, end_s, text)]` in
  `vibeedit_core/transcribe.py`.

## 7b. Phase 4 — DONE (what Phase 3 did not do, now implemented)

- OTIO import: `vibeedit.py otio-import <file.otio> <dest>` (new
  project, or `--merge` into an existing project) reads the Phase 3
  OTIO export back into a VibeEdit project: tracks, clips (with
  source in/duration, speed, keyframes, colour, volume, fades),
  transitions (kind/id/from/to/duration from metadata, or
  SMPTE_Dissolve -> dissolve), markers, and per-clip media. Media
  paths resolve relative to the .otio file first, then as stored;
  missing files are imported anyway and listed in the report's
  `missing` list — never dropped, never invented. Round-trip test:
  export -> import keeps clip counts, timings and transitions, and
  the imported project renders (6 s minus a 0.5 s transition =
  5.5 s). CLI, web UI panel, MCP tool.
- Karaoke captions: text items carry `karaoke: {words: [{text,
  start, end}]}` (seconds relative to the cue; words must join to
  the cue text, in order, inside the cue). Rendered as one burned
  .ass track (libass `\k` tags, sung = yellow, unsung = white) via
  FFmpeg's subtitles filter; standalone export writes
  `render/karaoke.ass`. Verified with a real render (karaoke_items
  = 1, duration correct).
- Adjustment layers: items on an `adjustment` track (created on
  demand) with a colour preset and/or .cube LUT, applied to the
  main-track picture only for their time range via eq/lut3d with
  an `enable` window. Overlap on the adjustment track is rejected;
  a missing/invalid LUT is a hard error. Verified: a mono layer
  measurably lowers the frame's mean channel spread vs the
  unadjusted render.
- Beat grid: `vibeedit_core/beats.py` decodes audio with FFmpeg
  to mono 11025 Hz floats and runs an energy-onset detector
  (512-sample windows, 256 hop, beat time at window centre,
  threshold = median + 0.5 * (max - median), min gap 0.3 s). Stored
  in `beatGrid` (source media id, beats in seconds, method). Web UI
  draws beats as ticks on the ruler; `beat-snap` snaps a frame to
  the nearest beat; `beats-to-markers` copies the grid to markers.
  Measured on synthetic burst audio: 5/5 bursts within 0.05 s;
  silence yields []. On real music this is a rough grid.
- Music ducking: `audio.ducking` config (enabled, amountDb,
  threshold, ratio, attack, release); renders sidechain-compress
  music items with the main-track audio as sidechain (asplit, so
  the main audio feeds both the compressor and the mix). Amount
  sets ratio as 10 ** (amount / 20). Verified in an isolated
  sidechain test: music during a dialogue burst was >3 dB quieter
  than during silence; a full project render reports
  `ducking_applied: true`.
- Tilt keyframes: `tilt` (-180–180 degrees) renders with FFmpeg's
  rotate filter (per-frame angle expression, output size pinned
  to input size) on main-track and overlay clips. Still-image
  clips with keyframes remain stored-not-rendered, as before.
- MCP: 54 real tools (was 38). New: otio_import, karaoke_add/get/
  export_ass, adjustment_add/remove/list, beat_detect/list/snap,
  beats_to_markers, ducking_set/get, project_stats,
  export_ducked, clip_tilt. CLI, server ops and a web UI Phase 4
  panel cover the same features.
- 55 tests OK (5 Phase 1 + 14 Phase 2 + 17 Phase 3 + 19 Phase 4).

## 8. Phase 5 list (explicitly NOT in Phase 4)

- Additional transcription providers behind the `transcribe.py`
  interface; voice providers; karaoke by syllable (words only now).
- Main-track motion+opacity combined rendering; LUT strength
  blending for eq presets.
- Agent dock terminal, knowledge/skills, review panel,
  transition preview stills.
- The remaining ~195 original MCP tools; a Windows .exe built
  and tested on Windows.
- macOS build verification of the renamed Swift tree (Xcode 16+,
  Swift 6, macOS 14) and a VibeEdit logo/splash replacement.
