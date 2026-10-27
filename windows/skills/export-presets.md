Provenance: Derived from the original BashCut docs — this is NOT original skill text. Written for the Windows port from the original's own documentation (`VibeEdit/docs/reference/commands.md`, format `--outputs` preset list) and the original preset entries the Windows port already implements. No original SKILL.md for export presets exists in the original tree.

---
name: export-presets
description: Pick the export preset that matches the destination platform before exporting. Use when the user asks where a video is going, what size or quality to export, or for a draft vs final render.
---

# Export presets

The project declares the presets it is made for, the first one primary: review checks the first preset's platform (safe area, longest length, smallest text) and the export sheet starts with it.

- Short vertical video: tiktok, reels, shorts — 1080p-class vertical, about 8 Mbps.
- Feed: feed-4x5 (about 5 Mbps), square, portrait-3x4.
- YouTube: youtube-1080 (about 12 Mbps), youtube-4k (about 45 Mbps).
- Quick draft: quick-draft — 720p, about 4 Mbps, for a fast preview, not for delivery.
- Master: prores — ProRes 422 HQ in a .mov container for further editing, not for direct upload.

Rules:

1. Ask which platform the video is for when it is not already set; do not guess a preset from the video's shape alone.
2. A draft export is never delivered as the final: say which preset was used for every file handed over.
3. An unknown preset name is an error, never a silent fall back to another preset. Report it and ask the user to pick a real one.
4. Changing the preset list is a project edit: the first preset stays primary, and review re-checks against the new primary.

Limits: this skill picks presets; it does not render. Rendering, loudness normalisation and platform upload are separate steps.
