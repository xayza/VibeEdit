---
name: self-learn
description: Turn problems hit while editing in BashCut into lasting fixes: lessons (symptom, cause, fix), preferences, project facts, project skills, or a proposed kit change. Use after a failed or redone step, a user correction, or at session end. Triggers: "rút kinh nghiệm", "học từ lỗi này", "nhớ lần sau", "lần sau đừng", "cập nhật skill", "self-learn".
---

# Self-learn

A problem solved in chat but not written down **will happen again**.

Run it once the problem is solved (you need the real cause), not mid-step. At the end of a session, sweep for
anything missed, starting from `bashcut run log --kind correction`: in Claude Code the kit's hook keeps there,
quoted, every user message that reads like a correction (also across a compaction). They are candidates: most
become one lesson, some are one-off instructions. Then `bashcut knowledge verdicts`: a command whose changes were
undone or edited two or more times is a candidate too; one verdict is not a preference.

After a process audit (`bc:review`, "Process audit"), start from its lessons (from the checklist and run log, not
your memory), then add what the user corrected.

Worth recording: the user corrects you ("không, dùng X", "thật ra…", "X chứ không phải Y") or rejects a proposed
action; says to remember ("nhớ là…", "lần sau đừng…"); a `bashcut` command fails or a result had to be redone. A
question, a one-off instruction for this clip or vague feedback ("chưa ổn") is not a lesson.

## 1. Write the lesson

Symptom → cause → what to do, with the number or error text that proves it.

| Good | Bad |
|---|---|
| "Whip transition refused: clips were not adjacent on one layer. Close the gap first (`timeline close-gap`)." | "Transitions are tricky." |
| "Music dipped 11 dB at every loop: the song has a quiet intro. Trim 2.6 s off its start before repeating." | "Watch the music." |

Only what was **observed** this session (an error, a measurement, the user's words); a guess is not a lesson.
First search by tag and keyword (`knowledge lessons --tag transitions`, `--query "close-gap"`): the same problem is
often worded differently. If it exists, `knowledge update-lesson ID --seen` (no approval needed) and add the quote
to its evidence when it says something new, instead of a second lesson.

**How often and how lately**: from `occurrences`, `lastSeen` and `sources` on `knowledge lessons` rows (older
lessons: count "seen again" lines in the evidence), not your memory:
- sources from two or more projects: move it to every project (`--scope user`);
- seen three or more times although active: its fix or `--check` does not work; rewrite the fix, or propose it to
  the kit (step 3) when it is about how a skill tells you to work;
- a workaround last seen before an app update where the plain way now works: disable it, say so in its evidence.
  Old alone is never a reason.

## 2. Put it in the right place

Each session starts with a summary of active lessons, preferences and facts (`context get` → `knowledge`).

| About | Goes to |
|---|---|
| This project: what went wrong, how to avoid it | a project lesson (below) |
| This project: people, places, footage notes, what the user approved | a fact: `bashcut knowledge set-fact host "Lan, speaks fast"` |
| The user's taste (length, pace, voice, style) | a preference: `bashcut knowledge set-pref pace calm` (every project; waits in the Knowledge inbox, below); `--scope project` for this one |
| A mistake that will happen in any project | a lesson with `--scope user`; waits in the user's proposals |
| A workflow repeated two or three times here | a project skill: `bashcut skills save NAME FILE` (shared with Claude and Codex) |
| A workflow the user repeats in every project | `bashcut skills save NAME FILE --scope user` (needs the user's approval) |
| A kit rule wrong, missing or too vague | a proposed kit change (step 3) |
| A skill that should have loaded but didn't | its `description` (add the user's real words), via step 3 |
| A plugin's skill (`<plugin-id>:<name>`) wrong or missing a step | a lesson tagged with the plugin ID, or a project copy (`skills get ID`, `skills save NAME FILE`); plugin skills are read-only and come back unchanged with the plugin |
| A library item that failed, was undone right after `library apply`/`place`, or was corrected | fix, copy or prune it with `bc:library` ("Look after it"); never remove without a yes |
| BashCut itself (a bug, a missing command or effect) | a note for the BashCut maintainers with the command, input and error |

```bash
bashcut knowledge add-lesson "Whip refused on non-adjacent clips" \
  --symptom "transition add failed: clips not adjacent" --cause "a 3-frame gap on v1" \
  --fix "timeline close-gap before adding a transition" --evidence "rev 41, error text" \
  --check "Are the two clips touching on one layer?" \
  --tags transitions --status proposed
```

- **A case:** the rule, the user's words **quoted, not paraphrased** in `--evidence` (a paraphrase lost which title
  the user meant to hold, and the fix landed on the wrong one), and a `--check` question for before the next draft
  ("Does every moment the viewer should remember get a full still hold?"). Feedback unclear about *which* element:
  confirm the target before changing anything.
- **A graphic or effect block:** tag `block:<name>` (e.g. `block:stat-counter`) with the value that failed and the
  range that worked; `graphic examples <name>` shows it next time (any project for a `--scope user` lesson).
- **Status:** `active` (default) when the cause is proven; `--status proposed` when unsure, so the user reviews it.
  A lesson for every project is always proposed.
- **Tags:** one or two areas (captions, audio, pacing, color, transitions, export…), so `--tag` finds them.
- **Keys:** short, lowercase, stable (`pace`, `caption.style`, `music.genre`, `host`), so a later `set-pref`
  replaces the value instead of adding a near-duplicate.
- **Preference for every project:** `set-pref` usually returns `"approval": "proposed"`: it waits in the Knowledge
  inbox, **not applied yet**. Tell the user; do not repeat the command or treat the value as set. A newer proposal
  for the same key replaces the older one (`knowledge proposals`).

An unsaved project refuses project writes: save it first. Memos (`knowledge memo`) hold longer notes such as a
style study's measurements; never append lessons to them. `legacy` in `knowledge get` (an older memo from the agent
workspace or home folder): tell the user; the Knowledge sheet can move it.

Wrong or outdated: `knowledge update-lesson ID --status disabled` (kept for the record) or `remove-lesson ID`;
`set-pref KEY --remove`.

**Undo a change** (yours or one the user wants back) to lessons, preferences, facts, memos or skills: find it in
`knowledge history --kind lesson --target LESSON_ID --limit 5`, then `knowledge revert CHANGE_ID`, rather than
re-typing the old value. Reverting an every-project change waits for the user's approval.

**Splitting an old memo** (`memoSplit: pending` in `knowledge get`): only when the user asks (the Knowledge sheet's
**Ask the agent to split it** button), read the memo and queue a JSON file once: `knowledge split-memo entries.json`
or `knowledge split-memo notes.json --scope user` (no facts). One short entry per idea, only what the memo says, in
its language (a Vietnamese memo gives Vietnamese titles, fixes and values; keys and tags stay English). Long notes
such as style measurements stay in the memo; do not edit it.

## 3. Changing the kit

Installed skills are managed by the plugin system; edits there are lost on update. Instead:

1. `bashcut skills get NAME --scope kit`, then change a copy: a few lines, never a rewrite, not a rule already
   there, each line backed by what happened.
2. Show it to the user. If they agree and the kit repository is local, apply it there on a branch and open a PR.
3. Otherwise propose it (it waits in the Knowledge inbox; the installed kit is unchanged):

   ```bash
   bashcut skills propose beat-cut SKILL.md --summary "close gaps before a transition" \
     --reason "whip refused twice on a 3-frame gap"
   ```

Kit 0.1.0 renamed the skills (`bashcut-beat-cut` is now `beat-cut`, shown as `bc:beat-cut`): update old names in
project memos and project skills. Keep skills short: a SKILL.md over ~250 lines moves detail into a `REFERENCE.md`.

## Report

Short: what went wrong → where the lesson went → the lines added. Nothing worth recording: say so in one line.
