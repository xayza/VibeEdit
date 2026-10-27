---
name: visual-plan
description: Decide what the viewer sees on every line of a talking video: one treatment per line (speaker, punch-in, B-roll, stock, icon, text, graphic, screen, nothing) anchored to a word, balanced, written to plan.visuals. Triggers: "minh hoạ", "kế hoạch hình ảnh", "câu này hiện gì", "b-roll cho script", "visual plan", "thêm hình cho lời nói".
---

# Visual plan

Building skills decide one moment; this plan decides the whole video first, so treatments vary, land on words and
reach the density and look needed. Plan and research here; the building skills build.

## 0. When and where

Stage `visuals`, added at the story stage when words carry the video (none for a music montage or a vlog told by
pictures). It runs after the cut is locked (words and frames fixed) and before sound and captions (SFX and caption
mode depend on it):

```sh
# --merge replaces top-level fields whole: read plan.stages, add the key, write all of stages back.
# stages.json: {"stages": {…the recipe's stages…, "visuals": {"after": "voiceover", "required": true, "why": "talking video"}}}
bashcut project set-data plan stages.json --merge --base-rev N
```

If BashCut lists the stage before review (ignoring `after`), still do it after the cut.

## 1. Read what is said and what exists

- **A written script** (`plan.beats` from `bashcut.vlog:hook-script`): start from it, do not re-derive. Join
  `script check` (`at`, `end`, `heardShare` per beat) with `plan.beats` by `id`. A beat with an `onScreen` note is a
  draft row: `line` = text, `from`/`to` = `at`/`end`, `beat` = id, `show` = the note, `treatment` = its `treatment`
  or the table's name for what the note asks. Only check them (§2–§3) and fill gaps: a beat without a note, a long
  beat needing two rows, `heardShare` below ~0.6 (re-worded or cut: take its words from what is heard).
- **No script**: split `transcript words` into lines at sentence or idea boundaries, with first and last word frames.
- What exists: described shots (`review coverage`, `media describe`), on screen now (`timeline sheet --cuts --text`).
- Targets, each with its source: a reference's measured profile (`bc:style-study`), else the recipe's ranges, else
  the kit's (`bc:motion-graphics` §3, `bc:effects`).

## 2. One treatment per line

Ask of every line: what does the viewer imagine, and does the picture already show it?

| Treatment | Shows | Built with |
|---|---|---|
| `speaker` | the face carries it: opinion, feeling, punchline | nothing added |
| `punch-in` | same shot, closer, on the strongest word | `bc:beat-cut`, `bc:effects` |
| `own-broll` | the user's shot of what is said | `bc:rough-cut`, `media place` |
| `stock` | photo or video of a thing, place or action the footage lacks | `bc:stock-images` |
| `icon` | small symbol: money, time, place, yes/no, arrow | `bc:stock-images` (Iconify) |
| `text` | keyword, number or label as native text | `bc:captions-text` |
| `graphic` | designed motion: kinetic type, counter, chart, pointer, mock screen, card, diagram | `bc:motion-graphics` |
| `generated` | a shot that cannot be filmed or found | `bashcut.vlog:scene-prompt`, `library generate` |
| `screen` | screen recording or screenshot of what is explained | `media place`, `bc:effects` (focus) |
| `none` | bare on purpose so the next line lands | — |

Not a closed list: a new treatment needs a name, what it shows and who builds it. A combination is one treatment (a
`stock` photo with a `text` keyword is `stock`; `show` says both).

Guides, not rules:
- Concrete words (thing, number, place, step, comparison) can be shown; abstract or emotional lines are usually the
  speaker's.
- A number reads best counted or written, a process as steps or a diagram, a comparison side by side, a named object
  as the user's own shot, then stock, then an icon.
- Anchor each row to one word (`at`): entrances end on its first frame. Hold until the idea's narration ends,
  unless it is an accent.
- **Screen lines**: one `screen` row per narration line, `show` naming the panel the line names; a new row where
  the screen changes inside a line (contact sheet and scene cuts, `bc:effects` §5). Never one framing for every
  screen row. Each row is checked with `ui frame F --phone` at its `at` word.
- Text and captions never say the same thing twice: decide the caption mode here (full, keywords only, none) and
  write it into `stages.captions.rules` (with all of `stages`, as in §0).

## 3. Balance the whole video

Check the rows end to end against the targets before researching:
- **Density and interval**: picture changes and graphics per minute within target; nothing in the hook's first
  1–3 s that does not serve the hook.
- **Variety**: one treatment on three lines in a row reads as a template unless the reference does exactly that;
  vary the device within it too.
- **Presence**: speaker screen share within target; keep the face on emotion, the hook's promise and the payoff.
- **Faces**: nothing covers the face while it speaks the point (`media subjects`).

Change rows until it fits; mark targets left on purpose `"deliberate": true` with the reason.

## 4. Research and look

Rows that need what the project lacks:
- `stock`, `icon`: 3–6 candidates per row (`bc:stock-images` §1 and Icons), a batch on one contact sheet; look,
  pick, import.
- `own-broll`: matching described shots; check the frame (`media frames --sheet`).
- `graphic`: note each row's starting example from the plugin's catalog (`bashcut.hyperframes:hyperframes` §1),
  or new; design happens at build.
- `generated`: the prompt idea; generation and any price wait for the build.

No good candidate: change treatment (often to `text` or `speaker`); never keep a weak picture.

## 5. Write the plan

`project set-data plan visuals.json --merge --base-rev N`; `visuals` rows in time order:

```json
{"visuals": [
  {"line": "one of the best ways", "from": 0, "to": 36, "at": 12, "treatment": "graphic",
   "show": "serif lead-in, 'Best ways' slams in lime", "why": "the hook's claim, made to read in 1 s"},
  {"line": "which can boost", "from": 186, "to": 216, "at": 201, "treatment": "punch-in",
   "show": "1.12× on 'boost'", "why": "a strong verb the face sells"}
]}
```

Frames are timeline frames; `show` is one phrase of what is seen; `why` is the line's need, not the treatment's
name; `beat` is the script beat's id. A row departing from its note says so in `why` ("note asked for a
price card; the board in shot already shows it"). The picture's source lives on the imported media, not here.

Gate: when the brief asks to approve visuals or rows need paid generation, `checkpoint request visuals --summary
"<rows by treatment, targets>" --attach <contact sheet>`; otherwise go on.

## 6. Hand off and close

Build in this order, each row by its skill: picture that replaces a moment (`own-broll`, `stock` video, `screen`)
→ `graphic` → `stock` photos and `icon` → `text` → `punch-in`. Each visual's sound is `bc:audio-mix`'s, at the
row's `at`. Record the stage (`run append stage --stage visuals`, evidence: row count,
candidates sheet). The draft review checks every row against the timeline (`bc:review`).

## Report

Targets and sources, rows by treatment with shares (speaker on screen, graphics a minute, mean picture change),
what you rejected, the caption mode, targets left on purpose.
