---
name: captions-text
description: Captions and on-screen text in BashCut: captions from speech or a script, word timing, SRT import, word-by-word styles, titles, templates, place and chapter cards, Vietnamese fonts, size, contrast, safe area. Triggers: "phụ đề", "sub", "chữ trên hình", "tiêu đề", "thẻ chương", "nhãn địa điểm", "font", "lỗi font tiếng Việt".
---

# Captions and on-screen text

BashCut draws all text itself; never render text into a video with Pillow or ffmpeg. The numbers below are ranges
with their sources (T09 = the captions study): read the measurement first, choose a value inside the range for this
speaker, genre and frame, and say why.

## 1. Words first

```sh
bashcut captions generate --media MEDIA_ID --replace          # job; --fresh transcribes again (new vocabulary)
bashcut captions generate --media MEDIA_ID --from 128 --to 148 --replace   # one stretch again (source seconds)
bashcut captions export --format text > /tmp/captions.srt   # edit text by hand, then:
bashcut captions import /abs/captions.srt --base-rev N --replace
```

The whole file is transcribed once and kept (`media transcribe` makes it without placing captions). Captions do
not move when their clips move; `transcript words --heard` does, so time graphics and SFX to it after re-cutting.
Before grouping, read (`media transcript --as words`, `speech rate`): the language, the lowest-`confidence` words
(names, words over noise), the speaker's median `gapBefore` and the speech rate. Fix text without moving times; let core own the timings (T09 §4).

- Speech recognition invents text over music, crowds, rooms and screen recordings ("hãy subscribe kênh…",
  "cảm ơn các bạn đã theo dõi", repeated phrases). Delete those cues; a clip with only that text has no speech.
- A cue longer than ~10 s, or one word repeated many times ("à à à …"), is a recognition loop: its word timings
  are smeared (one 5 min talk lost 128–237 s to three such cues). Find them in `captions export` (`review run`
  does not judge text). Don't cut on them; transcribe that stretch again in ~20 s pieces (`--from/--to` with
  `--replace`), which gave clean sentences in that project. Whole clip first, then the pieces with `--replace`; a
  whole-clip run without `--replace` after a ranged one added every line of the range a second time.
- Fix product and place names by hand; show acronyms read as words ("xê en xê") as letters (CNC).

## 2. Group cues

Choose the groups from the measurement, inside these ranges (T09 §3, §7):

| Delivery | Words per cue | Pause that breaks a cue | Characters per line |
|---|---|---|---|
| Energetic vertical (hooks, reactions) | 2–4 | 0.15–0.3 s | vertical: 15–32 Latin |
| Conversational (vlog, review, talking head) | 3–6 | 0.25–0.5 s | vertical: 15–32 Latin |
| Landscape subtitles (tutorial, interview) | 6–8, or full lines | 0.5–0.6 s | 32–42, two lines |

- Fast talkers (high `speech rate`, short median gap) need the low end of the pause range; set the break near the
  speaker's own median gap, not a house number. Cue length 0.5–5 s for social, up to ~7 s for subtitles; one cue
  on screen at a time; bridge tiny gaps so captions do not flicker (T09 §3).
- Character limits depend on font width and size: CJK counts double, and rendered width matters more than the count
  (T09 §3). Lines: 1–2; one for punchy vertical styles.
- No single number is "right": the sources contradict each other on words per cue (always 3 vs never fixed), the
  pause (250 vs 500 ms) and vertical line length (~28–30 vs 32) (ShortGPT, ghost-editor, hyperframes; T09 §3, §5).
- Reading speed is a fact, not an error: about 15–20 Latin characters per second is comfortable and above ~25 is
  hard (T09 §3). Captions of real speech follow the speech; look again at cues above ~20 cps and split or merge
  them, but do not paraphrase.

Then let core re-time the groups in one undoable edit:

```sh
bashcut captions group /abs/groups.json --base-rev N          # [[0,1,2],[3,4,5,6],…] word indices from transcript words
bashcut captions group /abs/groups.json --source heard --base-rev N   # indices from transcript words --heard
bashcut captions group --max-chars C --max-seconds S --break-gap G --from F --to G2 --base-rev N   # rule mode
```

Groups are runs of word `index` values, in order, each word once, covering the whole stretch. Break at meaning
(phrase ends, commas), not only at the limit. Rule mode needs all three limits from the table (no default). Read
each cue's cps, gaps and overlaps in the result; fix outliers by regrouping, or `timeline undo`.

**After every cut, regroup from what is heard:** `captions group --source heard` with indices from `transcript
words --heard`. Captions made before the cut keep words of lines cut away (one edit showed half a dropped sentence).

## 3. Script text, speech timing

When a script or voiceover text exists, show the script's exact words, never the recogniser's paraphrase (T09 §2,
§4). One line of the script is one cue:

```sh
bashcut captions align --media MEDIA_ID --text "$(cat /abs/script-lines.txt)" --replace   # job
```

Read `score` and the `unmatched` words: a low score means the take does not follow the script (ad-libs, a cut
line). Hand-written cues get estimated word timings; aligned cues get the speech's.

## Word by word

`captions generate --word-style …` or, on existing captions, `captions words`. `highlight` suits talking
heads and reviews; `reveal` suits hooks and short punchlines; keep `none` for cinematic serif captions. Emphasis:
0–25 % of words depending on style, fewer is the safer default; one highlight span per line (T09 §3).

- One animated title per moment; captions stay still. Entrances and exits of titles and stickers: `bc:effects`
  "In and Out".

## Looks: templates and presets

A hook, a CTA, a label and a caption differ in role, not in kind: pick the **look** for the video (tone, platform,
footage), use it whatever role the line plays, and keep one title look per video.

| Template (library) | Look | Suits |
|---|---|---|
| `stacked-keyword` | heavy condensed lines, the keyword line large and yellow | vlog, travel, food, Shorts hooks |
| `headline-subline` | wide caps headline over a small sentence | tutorials, lists, explainers |
| `boxed-keyword` | one huge word or number on a light plate | list counts, prices, scores |
| `two-tone-pop` | short lines alternating white/yellow, hard offset shadow | playful, kids, comedy, energetic edits |

Write template text in 2–3 short lines (`\n`), the keyword alone on its line (the last of two, the middle of three,
or `emphasis.line`). Busy or bright footage: keep the shadow, or give the emphasis a `plate`. Check the frame and
tune `fill`, `font` or `emphasis` for the video rather than keep the default.

| Renderer preset | Look |
|---|---|
| `bold-outline` | white bold with a thick outline: plain captions (review, food, talking) |
| `cinematic-serif` | small mustard serif: cinematic captions |
| `hook-title` | the stacked-keyword look (no plate); older projects keep working |
| `place-card` | dark plate with a yellow bar, left-aligned |
| `keyword-sticker` | dark text on a yellow sticker |
| `chapter-card` | cream serif between thin gold rules |

Place a style with `library place ID --text "…"` or restyle with `library apply ID --item ITEM`. Save a styled
title the user approves (`library save-selection --kind text-preset`); when they correct it, `library update ID`
(`bc:library`).

A whole-video style is a look (`bc:color-grade`) plus one `patchItems` restyle of every caption.
`textStyle.positionY` is the baseline from the bottom (0–1); `size` is a share of the short side, and a line wider
than 90% of the frame shrinks to fit. Add a text layer with `layers add --kind text --role
overlay` when the captions layer is busy.

Size (T09 §3): captions 3–6 % of frame **height** (measured glyphs), secondary text at least 3 %, hook text 6–9 %.
The sources disagree on the minimum (3 % to 5.2 %), and BashCut's `size` and `fontShare` measure the short side,
not the height: on 9:16 a height share is 16/9 times larger as a short-side share. Judge the result on a phone-size
frame, not the number. Text is **read** (big, with contrast) or **texture** (dimmed or blurred so nobody tries):
a line meant to be read that cannot be is enlarged or deleted; the closing URL or CTA is never the smallest line.
`review` counts keyed `zoom` and `textStyle.size` held for half a second: `keyedScale` under 1 → raise the key.

## Fonts and colour

The presets and templates use `System-CondensedBlack` (San Francisco; `System-` + optional Condensed, Compressed
or Expanded + Regular…Black), Verdana Bold, Marker Felt Wide, Arial Bold and Times: all ship with macOS and draw
Vietnamese tone marks right. Helvetica Neue's condensed faces have the letters but misplace stacked marks (Ắ, Ở): avoid them for
Vietnamese. Arial and Times also cover Greek and Cyrillic, but not CJK or Thai (Times not Arabic either). With `plan apply`,
titles and captions belong in `plan.cut` (`preset`, `style`); `plan check` flags a font that lacks the content
language.

- `fonts list --covers`: fonts that draw here with every letter of the content language. A font BashCut cannot
  find draws as Helvetica; `review run` reports it and text whose characters the font lacks.
- **One-look font choice** (open fonts, so every video does not wear the Mac's): `uv run
  <skill_dir>/fetch_fonts.py --candidates --role title|caption|lower-third --target <tags> --n 12 --text "<the
  project's real words>"` draws one numbered sheet (fonts lacking a letter are left out; earlier picks of this
  recipe first): look once, then `--pick 3[,7]` imports it and saves a text preset; never read `fonts list`.
  Tags: category, condensed, wide, rounded, geometric, high-contrast, mono-line, tall-x, heavy, bold-display. Starting
  ranges: titles heavy or bold-display, condensed for 3+ words a line; captions sans, tall-x, mono-line, 600–800;
  at most 2 families a video. Stacked marks (Ắ Ở) look wrong on the sheet → next one. Never `~/Library/Fonts`.
- Two fonts in one title: `text line-style ITEM --line 0 --font NAME --scale 1.4 --base-rev last` per line (`-1`
  last), or `textStyle.lines`.
- **Brand kit** (`project get` › `brand`) comes first: tie titles to it with `brandRoles` (plan.cut title `style`:
  `{"brandRoles": {"fill": "text", "background.color": "accent", "font": "heading"}}`).
- Contrast is measured, not assumed: `review layout --contrast` (fill and outline against the picture behind).
  Below about 4.5 (the AA level one source checks, T09 §3), change fill or stroke, thicken the outline or move the
  text, then measure again.
- A plate (caption pill, title box): `background {color, opacity, padding, radius}` and an emphasis `plate` take
  padding and radius **× font size, never pixels**: a pill is about `{"opacity": 0.6, "padding": 0.3, "radius":
  0.5}`, a rounded box radius 0.15–0.25. `"radius": 24` (CSS habit) draws a giant oval; `plan check` warns
  `plate-units`.

## Placement

- Safe zones are facts per output: `platforms get` (the strictest zones of the project's outputs of that shape).
  Do not carry one platform's numbers to another.
- Vertical caption height is the biggest contradiction in T09 (from 55–60 % down to near the bottom bar across a
  dozen sources): decide from the zones, faces, a picture-in-picture camera and product cards on this frame, and
  keep one zone per sequence (T09 §3, §4). `review layout` `faceOverlap` stays null: read face boxes with
  `bashcut media subjects --media ID --from S --to S2` and keep captions off them; check on the frame.
- Keep labels clear of each other (a top-left step label and a top-right tag collided in one project).
- Sync (T09 §3): captions start 0–0.15 s before the word; cards and graphics lead by 0.15–0.6 s. Read
  `speech.onsetOffsetFrames` instead of assuming.
- Hold authored text at least its reading time, plus 1–1.5 s after its animation ends; a hook can be shorter when
  the same words are spoken (T09 §3). For the hook, the sources disagree (1–2 s vs a 3 s window): judge from
  `review layout --to F` and `transcript words --to F`; the project sets `hookSeconds`.
- Copy budget (T09 §3): hook text 3–8 words, overlays ≤ 6; on-screen text repeats only the key word or number of
  the spoken line.
- **No captions while a title or card is on screen.** Remove or shorten the cues under a hook title, a price card
  or a CTA card: the same words twice read as a mistake (captions repeated the title and the price card in one ad;
  the critic flagged it). `review layout` `captionOverlap` finds them.
- **Content only, no production notes.** On-screen text says what the viewer needs (a word, a price, a place),
  never how the video was made: no "AI voice", effect or speed names ("x8", "slow motion"), sources or credits
  (labels: `bc:stock-images`).
- Place card at each location change, with the real place and time. Chapter cards only in tutorials and list
  videos: in one narrative vlog, cards with a flash and boom at every section felt disjointed; a hard cut, a
  bridging voiceover sentence and a small quiet date label worked better.
- Emoji stickers: `library place fire` (text items) or, animated, all pops at once: `bc:stock-images` fetch_emoji.py; off faces.

## Review limits are the project's

Core has no caption limits of its own: without them the caption checks report facts only. When the genre needs a
check, set `captionLineChars`, `captionMaxLines` and `minTextSize` (a share of the short side, see Size) from the
range you chose, the way `bc:review` "Before round 1" writes limits (merge; a recipe may already have set others).

## Verify

`review layout --contrast` (or `--frame F`, `--to F --ink` for the opening): read `edges` against the zones,
`density`, `captionOverlap`, `templateRepeats` (one preset overused on a layer). Render the longest-line cue and
every title with `ui frame F --phone` (390 px): readable, off faces, no collision? Then `captions export --as text
--format text` for cps and gaps, and `review run`. Stop after about three rounds of fixes and show the user what
is left (T09 §7).
