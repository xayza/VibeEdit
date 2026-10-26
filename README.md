# VibeEdit

VibeEdit is a video editor that coding agents can drive: everything
the UI does, an agent can do through a CLI or MCP server.

This repository contains two things:

- **`VibeEdit/`** — the original native macOS editor (Swift 6,
  macOS 14, SwiftUI + AppKit + AVFoundation), renamed from BashCut
  to VibeEdit. It cannot run on Windows. See `VibeEdit/README.md`
  for the macOS app and `VibeEdit/docs/windows-port.md` for the
  rename + port inventory. Original author attribution is kept:
  MIT License, Copyright (c) 2026 Nolan.
- **`windows/`** — the Windows MVP (Phase 1): a Python
  (stdlib + FFmpeg only) re-implementation of the timeline model,
  with a CapCut-style web UI (preview on top, editor panel,
  multi-track timeline strip at the bottom), a `vibeedit` CLI, a
  stdio MCP server, and FFmpeg rendering. See `windows/README.md`
  to run it on Windows.

Phase 1 keeps the features, project format, edit operations and
CLI/MCP behaviour of the original; the macOS UI and media layers
are re-implemented for Windows rather than compiled (which is
impossible: SwiftUI/AppKit/AVFoundation do not exist on Windows).
What is not yet ported — transitions library, keyframes, LUTs,
plugins, agent dock, Resolve/OTIO export — is listed as Phase 2 in
`VibeEdit/docs/windows-port.md`.
