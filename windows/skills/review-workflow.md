Provenance: Derived from the original BashCut docs — this is NOT original skill text. Written for the Windows port from the original's own documentation (`VibeEdit/docs/reference/commands.md`, section `review`, and `VibeEdit/VibeEdit/Core/Automation/CommandCatalog+Knowledge.swift` review specs). No original SKILL.md for the review workflow exists in the original tree.

---
name: review-workflow
description: Review the timeline before export and report issues by severity. Use when the user asks whether an edit is ready, before an export, or after a round of fixes.
---

# Review workflow

1. Run the review before export (`review run`). Issues come back with an id, kind, severity (error, warning, info), title, detail, frame, raw-number facts, and sometimes a suggested fix. Errors are listed first.
2. Read the summary status honestly: fail means there are errors; incomplete means no errors but a limit is unset or a check has not run; pass means the checks that could run passed. A check that has not run is reported as not run, never as passed.
3. Invariants are always checked: gaps, black picture, cuts inside a word, missing fonts or glyphs, output length and shape, and true peak. Editorial checks only run against limits set in the project's review settings; without a limit there is no verdict.
4. After fixes, re-run with the revision range (`--since-rev`) to see what is fixed, new, and persisting. Issues the user has accepted stay hidden unless explicitly listed, and are counted as accepted, not as passed.
5. A pass by an agent is recorded as the review stage only when no earlier stage the plan requires is still open. Never claim a review stage the run did not record.

Limits: review reports facts and suggested fixes; it changes nothing. Fixing is a separate, approved edit step.
