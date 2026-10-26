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
| `transitions[]` | `{id, kind, from, to, duration}` (frames; rendered since Phase 2: crossfade/wipe/slide) |
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
operations as the CLI and web UI — 23 tools after Phase 2 (see
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
| AVFoundation + Core Image/Metal render | FFmpeg (`windows/vibeedit_core/render.py`): concat/xfade segments, scale/crop fill, drawtext, setpts/atempo, fade/afade, amix, lut3d, eq presets, keyframe expressions | No full transitions library, no main-track keyframes, overlay audio not rendered, no Metal effects |
| AVFoundation preview proxies | Draft export (half resolution, veryfast) | No per-clip proxy generation |
| Core Text captions | FFmpeg drawtext (DejaVu on Linux, Arial/Segoe UI on Windows) | One style per caption item; no word-by-word karaoke |
| SwiftTerm agent dock (Claude/Codex terminals) | Not ported | Agents use the MCP server / CLI from their own terminal |
| Plugins (out-of-process, versioned API) | Not ported | Plugin results are preserved as project data only |
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

## 7. Phase 3 list (explicitly NOT in Phase 2)

- Full original transitions library beyond crossfade/wipe/slide
  (whip, iris, zoom, glitch, etc.) and transition preview stills.
- Keyframes on main-track clips; tilt keyframes; karaoke captions.
- Adjustment layers; LUT strength blending (strength is stored).
- Transcription and voice providers; beat grid, audio
  measurement/loudness, ducking automation.
- Plugins, agent dock terminal, knowledge/skills, review panel.
- Resolve/OTIO export; batch processing.
- Overlay-item audio in renders.
- macOS build verification of the renamed Swift tree (Xcode 16+,
  Swift 6, macOS 14) and a VibeEdit logo/splash replacement.
- A real Windows installer (the port runs from source with Python +
  FFmpeg, or via the launcher scripts; see `windows/INSTALL.md`).
