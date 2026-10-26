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
| `transitions[]` | `{id, kind, from, to, duration}` (frames; Phase 1: preserved, not rendered) |
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
Fields the MVP does not yet interpret (kept, not dropped):
`keyframes`, `color`/LUTs, `adjustment` items, `beatGrid`,
`providers`, `interop`, `targets`.

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
| `captions import/export` (SRT) | Text items in the timeline; SRT import/export is Phase 2 |
| `timeline undo/redo` | CLI undo via `.bak` file; web UI undo/redo (50-step session history) |
| `export start` | `vibeedit export --preset draft\|full`, web UI Export buttons, MCP `vibeedit_export_start` |
| `media proxy`, `media analyze`, `media transcribe` | Not in Phase 1 (no ML providers bundled, same as the original's stance) |

## 4. CLI and MCP mapping

Original CLI: `bashcut <group> <command>`; original MCP tools:
`bashcut_<group>_<command>` (249 tools) plus plugin-action tools
`bashcut_action_<id>`, served by `bashcut-mcp` over stdio, forwarding
to the app's automation socket.

Windows MVP CLI: `python windows/vibeedit.py <command>` (see
`windows/README.md` for the full list). Windows MVP MCP:
`windows/vibeedit_core/mcp.py`, stdio JSON-RPC 2.0, server name
`vibeedit-mcp`, with a real subset of tools that call the same
Project operations as the CLI and web UI:

`vibeedit_project_get`, `vibeedit_project_create`,
`vibeedit_project_open`, `vibeedit_project_save`,
`vibeedit_timeline_get`, `vibeedit_timeline_apply`,
`vibeedit_timeline_undo`, `vibeedit_media_list`,
`vibeedit_export_start`.

Not yet ported (Phase 2): the remaining ~240 tools (review, beats,
audio measurement, knowledge/skills, plugins, UI actions/dialogs,
agent dock terminals, Resolve/OTIO export, batch), plugin-action
tools, and the socket-based live app connection (the MVP MCP server
is single-project and edits the project file directly).

## 5. macOS-only modules → Windows mapping

| macOS layer | Windows Phase 1 replacement | Limit |
|---|---|---|
| SwiftUI + AppKit UI, timeline, viewer | Web UI (`windows/static/`): preview top, editor panel, multi-track timeline strip bottom, CapCut-style | Preview plays the latest export only; no live timeline scrub |
| AVFoundation + Core Image/Metal render | FFmpeg (`windows/vibeedit_core/render.py`): concat segments, scale/crop fill, drawtext, setpts/atempo, fade/afade, amix | No transitions (fades to/from black only), no keyframes, no LUTs, overlay audio not rendered, no Metal effects |
| AVFoundation preview proxies | Draft export (half resolution, veryfast) | No per-clip proxy generation |
| Core Text captions | FFmpeg drawtext (DejaVu on Linux, Arial/Segoe UI on Windows) | One style per caption item; no word-by-word karaoke |
| SwiftTerm agent dock (Claude/Codex terminals) | Not ported | Agents use the MCP server / CLI from their own terminal |
| Plugins (out-of-process, versioned API) | Not ported | Plugin results are preserved as project data only |
| macOS Keychain secrets, Application Support paths | Plain project folder on Windows; no secrets are stored by the MVP | Do not put API keys in project JSON |

## 6. Phase 2 list (explicitly NOT in Phase 1)

- Full transitions library (crossfades, wipes, slides) and the
  original transition preview stills.
- Keyframe animation (zoom/pan/tilt/opacity/volume curves).
- LUT grading and adjustment layers.
- SRT caption import/export; transcription and voice providers.
- Beat grid, audio measurement/loudness, ducking automation.
- Plugins, agent dock terminal, knowledge/skills, review panel.
- Resolve/OTIO export; batch processing.
- Overlay-item audio in renders.
- macOS build verification of the renamed Swift tree (Xcode 16+,
  Swift 6, macOS 14) and a VibeEdit logo/splash replacement.
- A real Windows installer (the MVP runs from source with Python +
  FFmpeg; see `windows/README.md`).
