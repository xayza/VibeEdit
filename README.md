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

## Current status (honest, Phase 0 — after code-gap batch 2)

- **MCP: 144 of the original 249 tools** (live count from the app's
  `/api/mcp-tools` endpoint; the number in docs goes stale as tools
  are added). Every ported tool calls a real Project/export operation.
- **Working:** project/media/timeline editing (cut, trim, move,
  copy/paste, split, undo/redo, markers, close gaps), source and
  export preview, audio (volume, fades, ducking, loudnorm, waveform,
  beat grid), captions (SRT, karaoke, text presets), colour (LUT,
  adjustment layers, per-parameter sliders, keyframes), speed curves,
  reverse/freeze, export presets, OTIO export/import, CLI + MCP,
  example plugins with enable/disable, desktop window.
- **Partial:** Compare view is not frame-locked; ProRes/4K export
  presets are mapped but not fully rendered; desktop clean shutdown
  and HiDPI are untested on real Windows; Windows (Ctrl) shortcuts
  are not standardised yet; tests are not yet clean on Windows.
- **Still missing — planned to port (see `windows/PARITY.md` for the
  full table with a port path per item):** vision/OCR/cutout,
  knowledge/skills store for agents, full magnetic block-move +
  linked audio, plugin install from URL, ~105 remaining original MCP
  tool names, motion-only transition kinds, a clean-Windows
  installer/.exe, and Windows CI.
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
