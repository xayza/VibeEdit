---
name: rough-cut
description: Build the rough cut in BashCut by quote: lines resolved to word-exact ranges, kept as selects with reasons, placed in story order; also long → short clips from a podcast or stream. Triggers: "cắt thô", "rough cut", "chọn đoạn", "lọc câu hay", "cắt podcast thành short", "highlight", "selects", "cắt giữa chữ".
---

# Rough cut by quote

You choose by **text**; BashCut resolves it to frames and flags edges inside a word or sentence; it never ranks or
picks. Never type timestamps from memory or from SRT lines: tools that let the model write times are off by
0.6–1.5 s (T06 §4). The ranges below are starting points; choose within them for this footage.

A rough cut is selection and order only: no music, titles, grade or effects unless the user asks (T06 §4). Be
generous on the first pass and tighten later: a discarded moment is slow to find again (T06 §2).

## Before selecting

1. Transcripts and speech gaps of each talking file (`media transcribe`, `media transcript`, `media speech-map`;
   `bc:footage-survey`). When the speech-map says there is no separation (music or noise under the voice), it gives
   no gaps: do not invent them.
2. Classify the source (T06 §4): **words** (the content is what is said: talks, interviews, tutorials), **reactions**
   (laughter, surprise: watch the picture; laughter and "clip that" lag the moment they react to) or **visual**
   (demonstrations, sport: the transcript is weak evidence, use the survey's descriptions).
3. The brief and plan (`project data brief`, `project data plan`): length, outputs and sections decide what is
   worth keeping.
4. Take the survey's recording cues (`bc:footage-survey`, hygiene checklist): no range starts, ends or runs across a
   cue; after "cut that", "take two" or "làm lại" the dead take is not a candidate. Between two takes of a line
   (`[again T]` in `media digest`, `alternatives` from `resolve-range`) the later one wins unless you looked and the
   earlier is better; say which in the select's reason.
5. Cut restarts and repeated phrases, including the ones the transcript hides (the survey's suspect words: a word
   over ~1 s or under ~0.4 confidence, re-transcribed). A select never holds a phrase said twice; keep the later,
   complete take, and check the range again with the re-transcribed words before placing it.

## The select-by-quote loop

For each moment: `bashcut media resolve-range M3 --quote "the first time I opened the app it crashed"`. Pick
among `alternatives` by context.

- `matched` under 1: read `text`. A misheard word is fine, but a range that holds only one or two of your words
  means the quote is not there; never place it.
- An edge `midSentence` is allowed only when you mean it (a deliberate interruption). Otherwise move it to the
  nearest sentence edge the result gives and resolve again.
- **Cut on the `resolve-range` result as it is; never add padding by hand.** In connected speech the next word starts
  within ~0.1 s: a 0.1 s pad pulled the neighbouring words in (lesson, one ad edit). To hold a breath or a reaction,
  resolve a wider quote or move the edge to a sentence edge the result gives, then check the trim with
  `--dry-run` (`cutsInsideWord` must be empty) before applying.
- **Gaps as cut points** (T06 §3, video-use): ≥400 ms of quiet is a clean cut; 150–400 ms needs a look at the picture;
  <150 ms is unsafe. Whisper-style word ends hide pauses, so trust `media speech-map` gaps over word ends (T06 §4).
- **Takes**: default to the last complete take ("people warm up", T06 §3), then confirm by reading or asking; a
  fluent take is not always better.
- **Long lifts**: removing more than 10–20 s at once needs a look (T06 §3): quiet is not empty picture in a screen demo.

Store your choices as selects with reasons, in one edit (`bashcut selects set selects.json --base-rev N`):

```json
[{"media": "M3", "from": 61.42, "to": 74.9, "quote": "the first time I opened the app it crashed",
  "reason": "hook: the problem in one sentence", "evidence": "edges on sentence ends; last complete take of three",
  "mustKeep": true}]
```

Give `order` when the story order differs from the recording order. The user can keep, reject or reorder selects
in the Media panel: before placing, read `selects list` again and follow their choices. Never undo a user's
rejection; ask instead. Keep and reject with a reason (`{"id":"S1","status":"kept","reason":"hook and payoff"}`);
mark the lines the edit cannot lose with `mustKeep`.

## Blind second pass (long → short, or many candidates)

Propose about 2× the clips you need (T06 §3): 30–45 % of AI picks are duds (hotclip, T06 §3). Then judge them
blind: a fresh sub-agent (or you, ignoring your reasons) gets each candidate's text with one sentence of context on
each side (`media transcript --from S --to E`) and returns a verdict with one sentence why:

- **publish**: stands alone and pays off; mark `kept`.
- **review**: promising but needs a trim, a different start or the user's eye; keep `candidate` with the note.
- **drop**: fails the standalone test or quote-mines; mark `rejected` with the reason.

Prefer these tiers to a weighted score (T06 §3). Ranking by score breaks story order; a highlight batch kept in
recording order hides the best clips: order by narrative for one video, by strength for a batch (T06 §2).

### The standalone test

A clip shown without the rest must make sense (T06 §2, openmontage):
- no unresolved "he", "this", "that one" pointing to something outside the clip;
- no reference to earlier context ("as I said");
- no long lead-in before the point; the setup, turn and payoff are inside;
- it does not stop before the payoff or on a comma;
- a stitch of two ranges never makes a meaning that was not said: do not stitch across a "but" or "however" (T06 §2).

## Length

Length follows the moment: setup + turn + payoff, then capped by the platform (T06 §3).

| Kind | Range | What moves it |
|---|---|---|
| vertical short | 15–90 s | one-liners shorter, story arcs longer; cap from `platforms get <id>` (hard vs recommended) |
| topic or chapter clip | 1–6 min | source length and platform |
| sum of selects vs the plan's length | ±10–15 % | report the drift; strict for fixed slots (T06 §3) |
| yield from a long source | no quota; often about 1 per 2–10 min | report the candidate count and why you kept N (T06 §3) |

Never cut natural speech short to hit a quota or a "sweet spot" (T06 §4).

## Placing and checking

The quick path writes the kept lines straight into `plan.cut` (`{media, quote, section}`, `cover` for pictures
over a line), then `plan check` and `plan apply --why "rough cut: 7 lines, hook first"`; the selects stay as the
record of what was picked. Or `selects place` (kept selects on Main, in order); then `timeline sheet --cuts`. One
range without selects: `media place --media M3 --from 61.42 --to 74.9`. Before any later trim, `--dry-run` reports
`cutsInsideWord`; fix those before applying. `captions find "words as said"` finds where a line now plays. A cut
inside a word is a review error; look at doubtful cuts with `review window F`.

Then **G3**: `checkpoint request G3 --summary "<duration> against <plan range>, N selects, what was dropped
and why" --attach <sheet path>`. When G3 is `ask`, wait for the user's answer before rhythm, sound and text;
otherwise go on.

## Several shorts from one source

One project per short, not one timeline: `project derive` (a sibling per kept select; `variants list` shows
them). Open each (`project open <path>`) and finish it through the stages of
`bc:edit-workflow` (its own hook, captions and review). Compare two versions of one short with `variants create`
and `variants diff`.

Log: `run append stage --stage rough-cut --text "20 candidates, 9 kept, 3 shorts derived"`.
