# VibeEdit

VibeEdit is a video editor that coding agents can drive: everything
the UI does, an agent can do through a CLI or MCP server.

## Product goal: the FULL BashCut macOS editor, as a Windows app

The goal is to convert the **entire** original macOS BashCut editor
into a complete Windows application named VibeEdit — not limited to an
MVP or a Phase 1, and without proactively dropping any original
feature. Features of the original that are not ported yet are listed
as `missing — planned to port` in `windows/PARITY.md`, never as
out of scope.

## Repository layout — and the target structure

The final product has only two applications:

- **`BashCut-main/`** (on the user's machine) — the original macOS
  app, kept as-is for macOS. It is never modified or lost in any step.
- **`VibeEdit/`** — today this is still the original native macOS
  editor code (Swift 6, macOS 14, SwiftUI + AppKit + AVFoundation),
  renamed from BashCut to VibeEdit. It cannot run on Windows. See
  `VibeEdit/README.md` for the macOS app. Original author attribution
  is kept: MIT License, Copyright (c) 2026 Nolan.

Current development layout (do not mistake it for the target):

- **`windows/`** — the Windows port in active development: a Python
  (stdlib + FFmpeg only) re-implementation of the timeline model,
  with a web UI in the original app's layout, a `vibeedit` CLI, a
  stdio MCP server, FFmpeg rendering, and a pywebview/WebView2
  desktop window. See `windows/README.md` to run it on Windows.
  **This is the only place Windows work happens for now.**
- **`VibeEdit/`** — still Swift/macOS code. It will become the home of
  the finished Windows app only after the gated merge step below.
  It is NOT Windows code today, and this README does not claim
  otherwise.

### The final merge is a separate, gated step (NOT done yet)

Merging the Windows code into `VibeEdit/` happens ONLY after the port
is complete and tested, and the old structure is cleaned up ONLY after
code and data are preserved. When that step comes, it must, in order:

1. Verify `BashCut-main` is intact (unmodified, nothing lost).
2. Diff the `VibeEdit/` Swift tree against `BashCut-main` for any
   Swift-tree-only changes (rename, port docs) and preserve them.
3. Create a tag/snapshot of the repo before merging.
4. Only then merge the Windows code into `VibeEdit/` and clean up
   the old structure.
5. Re-test the whole Windows app after the merge (open project,
   import, edit, export) before calling the merge done.

Until then: no move, rename, or delete inside `VibeEdit/` or
`BashCut-main` for the Windows port.

## Current status (honest, full-parity round 22; UI round 19)

- **MCP: 481 tools** (live count from the app's `/api/mcp-tools`
  endpoint; the number in docs goes stale as tools are added): **432
  real-operation tools and 49 check-and-error tools** that raise a
  structured `NOT_AVAILABLE` error with the blocker and the port path,
  never a fake success. Round 3 verified by test that all 249 original CommandCatalog
  spec names have a registry name (dots/hyphens normalised, 6 via
  real aliases sharing handlers, as in the original's own
  shared-handler design), and round 15 re-ran that check with the
  same result; round 19 converted 17 more honest tools to real
  (13 show_* dialog aliases, agent_quick_edit, and 3 session-state
  tools ui_select/ui_seek/context_get); round 20 converted 3 more
  (show_shortcuts parsed from app.js at runtime, ui_frame/ui_frames
  rendered with FFmpeg); round 21 converted 2 more (agent_status as
  agent_kit_check data per the original spec, app_vibeedit_debug_log
  reading a real file-backed MCP invocation log); round 22 kept the
  audit part's 2 conversions (agent_terminals and
  app_vibeedit_automation_clients, empty lists that are real because
  the server by design has no such elements) and fixed the
  Windows-tested bugs: rev-sync data loss (RAM copy overwriting an
  external agent's edits), the zoompan-fps export doubling, blocking
  synchronous export (now background jobs), MCP notification responses,
  inputSchema for all 479 tools (270 non-empty, 209 genuinely empty),
  and the Agent dock copy button (now the real absolute command);
  round 23 added folder-form skills, skill import from file/folder/
  plugin-folder/.zip (copy-only, preview + manifest), a Knowledge
  panel rework (clickable skill table, rendered markdown detail,
  search, import preview/install, Claude Code sync) and MCP
  resources for skills, taking the registry to 481 tools (429 real,
  52 honest); round 24 audited every honest tool (3 empty-by-design
  conversions: voice_clone_list, ui_dialog, chat_status — 432 real,
  49 honest), made export probe real audio streams before emitting
  [i:a], made export cancel SIGKILL the running FFmpeg process, and
  clarified missing-argument errors to ValueError naming the keys;
  round 25 added a cross-process project file lock (O_CREAT|O_EXCL,
  stdlib-only, so simultaneous web + MCP writes serialize instead of
  losing one update; long-running tools run outside the lock by
  design) and export-report diagnostics (exact FFmpeg command, filter
  graph, -shortest flag, audio map, per-clip source-vs-project fps,
  and ffprobe-measured output video/audio durations, plus a Review
  panel diagnostics line); round 26 swept remaining user-visible English strings to Vietnamese under a three-gate rule (no test locks it, no code matches on it, not intentionally English), reverting 10 messages whose English forms old tests assert (see `windows/PARITY.md` round 26); what remains genuinely unported is listed
  honestly in `windows/PARITY.md`.
- **UI rounds 16–17:** round 16 harmonized colors (neutral chrome,
  cyan only for active/selected/focus + CTA + clip-type colors +
  playhead, Export CTA gradient softened to #0e7490→#be185d, clip
  colors muted to translucent fills, AI Agent column widened
  300px→340px); round 17 moved the tool rail to a horizontal top row
  (CapCut-style, same 12 tools, same handlers); the timeline ruler
  and lane playheads now share one origin (ruler margin equals the
  track-label width plus gap), so ruler ticks, the ruler playhead,
  the lane playheads and clips align at the same time; round 18
  finished the overall layout (48px topbar, status toast, right-side
  agent drawer, split library, aspect-correct preview canvas, CSS
  tokens/dedup) and added two keyboard-shortcut batches (mapped keys
  listed in windows/README.md, unmapped keys honestly reported, no
  fakes); round 19 added draggable panel resizing (tool/details/
  timeline/agent, persisted in localStorage, double-click reset),
  a clipping-proof body-level icon tooltip, a single "+ Nhập"
  import control, and fixed a blocking fps bug (source-frame
  durations used as project frames doubled 60fps clips in 30fps
  projects — now converted both sides plus a one-time migration
  for old projects), upload dedupe by SHA-256, and a batch of
  real-click fixes from Windows testing (the `post is not defined`
  bug killing 14 buttons, magnetic toggle, go-to-start, voice
  backend checks, undo/redo status, tab-close server tracebacks);
  target + full suite results are in windows/README.md.
- **Working:** project/media/timeline editing (cut, trim, move,
  copy/paste, split, undo/redo, markers, close gaps), full magnetic
  Main block-move + linked audio, source and export preview, audio
  (volume, fades, ducking, loudnorm, waveform, beat grid), captions
  (SRT, karaoke, text presets), colour (LUT, adjustment layers,
  per-parameter sliders, keyframes), speed curves, reverse/freeze,
  reframe (render-side, API/MCP), export presets, OTIO export/import,
  review workflow (run/accept/verify + data sub-tools), CLI + MCP,
  plugins with enable/disable/install **and manifest entry
  execution**, desktop window with clean shutdown, Ctrl shortcuts,
  magnetic reorder, knowledge store, skills read + write, caption
  transcription/generation/alignment (where faster-whisper is
  installed), font import, in-app voiceover recording (browser
  MediaRecorder + real upload endpoint; mic itself still needs a
  real Windows check), Compare masked wipe with time-sync, voice
  generation via Edge TTS / Piper (where the backend is installed),
  motion transitions including halftone (geq dot mask +
  alphamerge/overlay, plus the Pillow pre-rendered segment), update
  defer/skip state, library/plugin search, declared-hook plugin
  execution, full media.analyze pipeline (tech/picture/sound
  records keyed by file content, speech map, filmstrip,
  audio sync), media proxies, single-instance
  desktop handoff with browser fallback, scene-cut detection and
  cut-list correction (`media_cuts`), plugin option read/set
  (`plugins_options`/`plugins_option`) and the plugin on/off switch
  (`plugins_set`), clip motion from the original MotionPresets and
  ReframePreset cycling (render-side crop expressions), music
  replacement keeping volume/fades, narration windows, outcomes
  store + mapping, run log + checklist with stage gates, media
  description/digest from shot facts + analysis records, speaking
  rate measured from transcript words, image style lock + disclose
  labels, library pack export/import with licence checks, library
  item analysis, image-path brand pose, plugin overlays/actions/
  views/proposals/replacement, agent-kit local check + skill-pack
  install, signed-releases kit update + deferral (kit 0.1.56, 17
  skills, MIT licence), plugin registry fetch/browse/updates/
  install-record (review-only: registry providers are macOS-only),
  clip backdrop (blur/colour, real render on main-track
  stills, video and freeze frames), run-panel state (dismiss/toggle/
  follow, reported by run_checklist), run follow-up request drafts
  (fix-issues/another-recipe in the original's exact wording),
  plugin show-view (recorded as the project's shown view), frame-exact
  trims on overlay video and motion-transition windows (round 11:
  exact source/project frame indices instead of millisecond-rounded
  trims, plus a final-mix audio pad so the export `-shortest` flag
  can no longer eat the last video frame), half-open [start, end)
  overlay enable windows matching the original's CMTimeRange
  semantics (round 12: no more repeated overlay frame at the exact
  end time, on millisecond-exact and non-millisecond ends alike),
  end-to-end integration export verified against its own report
  (135 frames / 4.5 s composite, server smoke with clean shutdown)
  and a Windows test checklist document (round 13), a round-14 UI rebuild matching the original app plus the Neon Nights spec (agent sidebar left, neon clip colours, two-way playhead/preview sync within one frame), a round-15 agent-kit + plugin-registry completion (signed-releases kit update, registry fetch/browse/updates/install-record),
  605 tests OK on the Linux VM.
- **Partial:** Compare view is a masked wipe with time-sync, not
  sample-accurate frame lock; ProRes/4K export presets render on
  the Linux VM from synthetic clips but not yet from native 4K
  footage; plugin install works (folder/zip, gated download,
  remove, registry fetch/browse/updates/install-record with SHA-256
  + signature checks; registry installs are review-only records
  because registry providers are macOS-only) ; vision/OCR/cutout
  works only where Tesseract/OpenCV are installed, otherwise it
  errors clearly; the updater can check/download/verify, write an
  installer handoff script and record defer/skip choices, but
  replacing a running app still needs the user to quit and run that
  script by hand, and no real releases location has been picked yet;
  desktop/HiDPI/Ctrl shortcuts are verified on Linux only, not yet
  in a real Windows window/browser.
- **Still missing — planned to port (see `windows/PARITY.md` for the
  full table with a port path per item):** voice cloning (needs a
  cloning provider model — none exists in either tree), real
  learned-segmentation execution (needs a user-supplied ONNX model
  + runtime), running registry provider plugins on Windows (their
  providers are macOS-only; fetch/browse/updates/install-record are
  done), a clean-Windows installer/.exe
  (the FFmpeg bundle licence is now packaged, not just checked:
  the full GPLv3 text from gnu.org plus a source offer generated
  from the bundled binaries' real versions are copied into the
  artifact by `windows/scripts/package_licenses.py` and the CI
  workflow verifies all three licence files — but the workflow
  still has to reach GitHub by real git/web UI and run green once
  to prove it — see `windows/PARITY.md`), and Windows CI.
  `chat.stop`, `view.compare` and `view.safe-area`
  stay honest-error MCP tools by design (no chat session exists;
  Compare and Safe-area already exist as web-UI controls).
- **Verification split, stated plainly:** the user has verified the
  server starting, the UI opening, and media/timeline on real Windows
  (Python 3.12.10, FFmpeg 9.0.2); unit tests and renders have been
  verified on a Linux VM only (FFmpeg 8.1.2); the original Swift code
  has never been compiled here (no Xcode); the Windows installer and
  Windows CI have never run. A Windows CI workflow file exists from
  Phase 6 but is NOT in the repo yet (pushing workflow files through
  the GitHub App is blocked with 403) — it must be added with real
  git or the GitHub web UI, and no Windows .exe exists to download
  until it has run green once.

The macOS UI and media layers are re-implemented for Windows rather
than compiled (which is impossible: SwiftUI/AppKit/AVFoundation do
not exist on Windows). The port keeps the features, project format,
edit operations, and CLI/MCP behaviour of the original wherever they
are already ported; what is not yet ported is tracked in
`windows/PARITY.md`, not silently dropped.
