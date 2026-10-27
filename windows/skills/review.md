---
name: review
description: Review a BashCut edit before export as a capped loop: review profile from sourced ranges, measure, look, judge by what a viewer perceives, fix and prove with review verify, an independent critic. Triggers: "review", "kiểm tra video", "soát lỗi", "xem lại bản dựng", "chấm bản dựng", "QC", "trước khi xuất".
---

# Reviewing an edit in BashCut

Core measures, renders evidence and states what it did not check; you decide which findings matter and how many
rounds to run. Passing checks is not proof of a good video. One tool's edit had all 29 actions on the beat and every cut on a bar
line, and still had cramped frames, small text and titles over the icons: "the model will satisfy whatever can be
quantified" (T16 §2, guizang). Look at the pixels.

## If you were given a packet

You are a fresh critic with a `review packet --point strategy|draft|process` folder and this skill only: none of
the maker's reasons, on purpose (T16 §4). Judge against the brief and the plan, never what the maker meant.

| Point | You get | You check |
|---|---|---|
| `strategy` (before the rough cut) | brief (`inferred` fields), plan, a story sheet | one message; the payoff answers the hook; fits the brief; each `inferred` field a fair guess; the recipe's plan checks |
| `draft` (before G5) | the files below + `plan.checks` | generic checks and `plan.checks` as a viewer; the measured issues |
| `process` (at the end) | `run checklist`, `run log`, `timeline changes` | below, "Process audit" |

**Generic checks** (every video): one message; `promise.payoff` answers `promise.hook`; opening text and speech
(`hookSeconds`) agree; understandable on mute; captions never repeat on-screen text; nothing the brief did not ask
for: no credits, no "AI voice", "minh hoạ", "stock" or effect labels.

The draft packet:

| File | Use it to |
|---|---|
| `README` | know the project, revision and round |
| `plan.json` | know what the edit promised, for which outputs |
| `digest.json` | in round 2+, check what changed first |
| `issues.json` | start from facts; a measured issue is a number, not yet a finding |
| `shots.json` | find jump cuts, same-framing cuts, unintended gaps, monotony |
| `word-landing.json` | find clipped words, titles early or late on their word |
| `coverage.json` | find missing promised shots or lines (join clips with `plan.json` shots) |
| `measured.json` | never pass what nobody measured |
| `sheet-*.png` | see framing, text size and placement, repeated shots |

Read `README`, `plan.json`, `measured.json`, then the other JSON files, then every sheet; judge the opening from
the first shots, words and cells. Never edit; with the CLI, read-only commands for a doubt (`ui frame F --phone`,
`review window F`) only.

Return, as text, briefed "to roast, not to praise" (T16 §2):

1. Verdict: `pass` (no blocker), `changes` (fixable blockers) or `fail` (the strategy or the cut is wrong). A check
   you could not judge is not a pass: name it under 5.
2. Findings, blockers first: time or frame, severity, what the viewer perceives, evidence (file and field, or
   sheet cell), the stage that owns the fix.
3. The 3–5 fixes first (T16 §7).
4. `needs_user`: taste and missing material, apart from defects.
5. What you could not judge: sound by ear, motion between cells, whatever `measured.json` lists as not measured.

Record it (a log entry, not an edit): `run append audit --point draft --verdict changes --findings 4 --by critic`.
Without the CLI, the maker records exactly your verdict and count.

### Process audit

Read the checklist, log, changes. Flag: a required stage `skipped`, missing or still `pending` when review ran; `done` without
evidence, or evidence not in the log; a skill unread for a stage that ran; a missing or `self` audit; a gate request
without the user's answer; summary claims no entry or change backs ("fixed" without `review verify`, "exported"
without an export). Return the verdict and lessons (symptom → cause → what to do) for `bc:self-learn`.

## Severity: what the viewer perceives

By the viewer at normal speed and size on a phone, not by the metric (T16 §4, reelmimic, talkcraft):

- **blocker**: noticed and hurts understanding or trust: a black or frozen frame, a clipped word, unreadable or
  covered text, speech drowned by music, a missing promised moment, a hook that does not show the topic. Core
  `error` issues (gaps, black on Main, a cut inside a word, missing glyphs, wrong length or shape) are blockers
  unless you show they are not real.
- **polish**: visible only paused, zoomed or side by side. Fix when cheap; never a reason for another round.
- **taste**: a viewer could like it either way (pace, look, transition): `needs_user`.
- **needs user**: only the user can supply or decide it (a missing shot, music choice, a name to spell).

A measured warning is not automatically a blocker (a locked-off interview trips "static shot", a deliberate long
title "long still"): fix, adjust the profile, or accept with a reason.

## Before round 1: the profile

Core has no editorial defaults: the project's `review` object holds the limits. An unset limit reports only the
measured value, as info, listed in `checks.unsetLimits` and by `plan check`. A vlog recipe sets them; otherwise
choose from the ranges below for this genre and footage, write them with `project set-data review review.json
--merge` (or `plan.cut.review`; `setProjectProperties` replaces the whole review object), record each in the plan's
`ranges` with source and reason, and tell the user.

Ranges seen in other review tools (T16 §3), starting points, not defaults:

| Limit | Range | What moves it |
|---|---|---|
| `blackMinSeconds` | 0.1–0.5 s | intended dips to black (a fade-through, an end card) |
| `maxStillSeconds` (exact freeze) | 0.8–1 s | a freeze on video media is usually a decode or render fault |
| `maxShotSeconds` with `stillMotion` | 3–6 s | genre: a calm vlog keeps long stills, a montage does not |
| `maxSilenceSeconds` (whole mix) | 2–5 s | ASMR or a calm vlog tolerates more; a gap inside speech is ~0.8 s |
| word landing (caption or title vs its word) | 0.1–0.3 s | correctness, not taste |
| `minTextContrast` | 3–4.5 : 1 | WCAG 2.x: 3:1 large text (titles), 4.5:1 body text (captions) |
| `loudnessToleranceLU` | 1–2 LU | the platform and the delivery file |
| true peak | −1 to −0.5 dBTP | lossy codecs need −1 |
| length vs plan | 2–15 % | strict for ads and fixed slots, loose for vlogs |
| rounds | 1–3 | 1 when the user is waiting and nothing blocks; up to 3 unattended (T00 §3, T16 §3) |

Platform numbers (length, loudness, safe zones) come from `platforms get <id>`, never from here.

## The loop

```sh
bashcut review measure                      # a job
bashcut jobs wait <job> --done --timeout 100       # repeat on timedOut
bashcut review run --summary --min-severity warning
```

Before round 1, `run checklist`: a stage the plan requires (effects, sound, visuals) still `pending` or `started`
is a blocker, whatever `review run` says. Do it, or log it skipped with the reason; BashCut answers `stage_pending`
to marking review done, G5 and a final export until then. One tutorial passed review with its required effects
stage pending: one zoom reused on every screen shot.

Each round:

1. **Measure, then read.** `stale` checks need measuring again; `unreliable` is not a pass; `status` `incomplete`
   (`unsetLimits` or `notChecked` not empty; loudness before the normalized draft does not count) is never
   reported as passing: set the profile or say what was not checked. Errors first. Info issues
   `voice-text-changed-*`, `captions-source-changed-*`, `beats-source-changed-*`: the result is from an older text
   or file; run their fix (speak, transcribe, detect again) before judging it.
2. **Look in batches.** `timeline sheet --cuts --text` (`--outputs all` for safe zones), then `review window F`
   only at cuts in doubt: ±0.4–1.5 s at 10–12 fps, wider for dialogue cuts,
   narrower for beat cuts (T16 §3; at 30 fps about `--span 12`–`45` with `--step 3`). `ui frame F --phone` for text
   at the width a viewer sees (360–420 px, T16 §3). `review coverage` and `script check` against the plan.
3. **Critic, always.** Give the `review packet --point draft` folder to the `bc:critic` agent (or a sub-agent
   briefed with `<skill_dir>/CRITIC.md`): without your reasons it sees what a viewer sees. No sub-agent: audit
   yourself by that brief from the packet only, `--by self`. Record the verdict with `run append audit` (a skipped
   G5 needs it). Apply its one `plan.cut` patch (`plan apply --patch`) without re-reading the packet. A second
   look only for a blocker no measurement proves; `review verify` proves the rest.
4. **Decide each finding** by severity: fix it (one labelled edit; the issue's `fix` if any), change the profile
   when the limit is wrong for this video (say why), accept it with a reason, or list it for the user.
5. **Verify each fix.** `review verify <id>` (or `all`) re-measures before and after. Say "fixed" only with that
   result: "looks better" does not count (T16 §2). Then look only at what changed (`timeline sheet --entries
   c2,t1`).
6. **Log the round**: `run append round --round 1 --fixed 3 --left 2`.

Applying a `fix`: run its command with `fix.arguments` (`timeline.apply`: the ops in a file, `--label "<the issue
title>"`); `export.start` → loudness comes from a normalized draft, last; `selects.place` → place it or unmark it
with a reason (`bc:rough-cut`); a `hint` only → that area's skill, or the user when it is taste. Never hide a
failure with a transition or a flash (T16 §4).

| Issue | Look and measure | Fix with |
|---|---|---|
| black, frozen picture, long static shot | `ui frame F`, `review picture --from F --to G`, `review shots --summary` | `bc:beat-cut`, `bc:effects`; black: offline media or a hiding layer |
| jump cut, repeated framing, gap, cut in a word | `review window F`, `review shots`, `timeline apply --dry-run` | `bc:rough-cut`, `bc:beat-cut` |
| cut or text off the beat or the word | `review window F`, `review sync --events cuts,text` | `bc:beat-cut`, `bc:captions-text` |
| the picture pulses on the beat, too many flashes | `review sync --events impacts` | `bc:effects`, `bc:beat-cut` |
| one sound effect repeated like a machine gun | `review sync --events sfx` | `bc:audio-mix` |
| text in a zone, too small, overlap, contrast | `ui frame F --phone`, `review layout --frame F --contrast` | `bc:captions-text` |
| no hook, slow opening | `review shots --to F`, `review layout --to F --ink`, `transcript words --to F`, first sheet cells | story (`bc:edit-workflow`), `bc:captions-text` |
| dead air, music gaps, voice drowned | `review window F`, `audio mix-measure` | `bc:audio-mix` |
| live speech and voiceover at different levels, music close under a quiet voice | `audio mix-measure` `speechWindows` (each within ~2 LU of the voiceover, music 15–20 LU under), true peak after any raise | `bc:audio-mix` "Real speech vs voiceover" |
| a restart or a phrase said twice; a voiceover line repeating the live line beside it | `transcript words --heard`: words over ~1 s or under ~0.4 confidence, re-transcribed; the live words around each voiceover line | `bc:rough-cut`, `bc:voiceover` |
| a screen zoom that misses what the line names, one framing reused across lines | `ui frame F --phone` at each line's key word, `timeline get` transforms per screen clip | `bc:effects` "Zooms on a screen recording" |
| loudness, true peak | the normalized draft, `platforms get <id>` | `bc:audio-mix` |
| colour jumps between clips | `color measure --by clip`, `ui frame F` | `bc:color-grade` |
| a promised shot or line missing | `review coverage`, `script check` | `bc:rough-cut`, `bc:stock-images`, ask |
| a `plan.visuals` row missing, > 0.3 s off its word, or over the face | `timeline get`, `review window F`, `media subjects` | the row's building skill (`bc:visual-plan` §2) |
| a reference style drifts | `review compare --reference ID --ours ID` | `bc:style-study` |
| a plugin's issue (`source`) | that plugin's skill | its `fix` |

## Rounds and stopping

- Cap: the `rounds` range above, never more than `workflow gates` › `maxReviewRounds` (the user's setting).
- From round 2, `review run --summary --since-rev R` (R = the previous round's revision) gives the diff. First
  confirm the previous fixes; then **only a new blocker fails the round**. New polish and taste findings are listed,
  not chased (T16 §2, reelmimic): rubric creep is how loops never end.
- Stop early when a round fixes nothing. What is left goes to the user with reasons, never silently shipped.

## Accept with a reason

Keep a warning or info that is right for this video: `review accept <id> --reason "locked-off interview, chosen"
--base-rev N` (the export report lists it). Accept an error only when no fix exists, and tell the user; to change a
whole check set `review.severities.<check>` to `{"severity": "warning", "reason":
"…"}`.

## The draft

Loudness and the delivered file are measured from a normalized export: make it last, review once more, then
request G5 (`bc:edit-workflow`):

```sh
bashcut export start --preset quick-draft --name draft-v1 --include-srt --normalize-audio
bashcut export status                      # also the delivered-file checks
bashcut review run --summary --min-severity warning
```

## Report

A few lines from `run log` and the last summary: `status`; audit verdicts (self-audited?); rounds; fixes (issue →
edit → `review verify` numbers); profile changes and accepted issues with reasons; `needs_user`; coverage: copy
`checks.notChecked`, `failed`, `unreliable`, and "not listened to" for sound you could not hear. Example: "Review: 2 rounds. Closed a 1.2 s
black gap at 0:41 (verified: 0 black frames), raised the caption out of the Reels bar. Kept: the 9 s shot at 0:12
(locked-off interview). Not checked: the music under your voice by ear." Log it: `run append measured --measured … --not-measured …`.
