Provenance: Derived from the original BashCut docs — this is NOT original skill text. Written for the Windows port from the original's own documentation (`VibeEdit/docs/reference/commands.md`, section `timeline`, and `VibeEdit/VibeEdit/Core/Automation/CommandCatalog+Timeline.swift`). No original SKILL.md for timeline editing exists in the original tree.

---
name: timeline-editing
description: Edit the timeline with validated operations: read the timeline, apply ops atomically, cut a range, and undo. Use when the user asks to change clips, trim, split, move, or remove a span.
---

# Timeline editing

1. Read before you edit. Get the timeline (`timeline get`) and the current revision first. Never edit from memory: an edit applied on a stale revision is refused, and that refusal is the safety net, not an error to work around.
2. Apply edits as one atomic, undoable step (`timeline apply` with the ops list and the base revision). A dry run first returns the fingerprint of the ops; an apply with an expected fingerprint refuses ops that differ from the reviewed dry run.
3. Cutting a span out of the whole timeline (`timeline cut-range --from <from> --to <to>`) trims items over an edge, splits a clip spanning the whole range and joins its parts, and moves everything later left, with markers, sections and the beat grid. Linked sound follows its picture's cut; a music bed keeps playing and loses its tail.
4. Record why: every apply carries a reason and evidence (review issue IDs, transcript ranges, measurements). The undo history keeps them, so a later reader can see what an edit rested on.
5. Check the result: re-read the timeline after the apply and confirm the revision moved and the change is the one asked for. If the apply reports nothing changed, say so — do not re-apply the same ops.

Limits: this skill only describes the edit flow. It does not invent operations: only validated timeline operations may be applied, and an operation the validator rejects is not retried in a different spelling.
