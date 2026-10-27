---
name: motion-graphics
description: Designed, animated graphics over footage in BashCut: stat and checklist cards, counters, lower thirds, diagrams, kinetic type; whether a sentence needs one, anchored and held, made with a graphics.render plugin. Triggers: "đồ hoạ", "motion graphic", "thẻ thông tin", "số liệu chạy", "counter", "lower third", "infographic", "animation chữ".
---

# Motion graphics

Sources: T13 = motion-graphics study, T22 = renderer study. Choose inside each range from this video's speech, genre
and frame; say why. Captions and plain titles: `bc:captions-text`; transitions, punch-ins, item In/Out: `bc:effects`.

## 1. Does this sentence need a graphic?

With `plan.visuals` (`bc:visual-plan`), build its `graphic` rows at their `at` word, showing their `show`; question
a row only when building shows it fails, and update the plan. Without one: a graphic shows what the words don't
(example, number, relationship, consequence). Read `transcript words`: what did the speaker make the viewer imagine?
- Skip it when the card would restate the caption: captions and on-screen text take one role each, never both
  (openmontage). Leave some sentences bare so the next card lands (ghost-editor).
- Change the graphic when the content changes, never on a timer ("every 15 s" is an anti-pattern, digitalsamba).
- Graphics over talk keep the voice under them; never cut to a silent standalone card (vibetube).
- Vary the device; one card on every point reads as a template (T13).

## 2. Pick the cheapest tool that does it

1. **Native text** (`bc:captions-text`), first choice: titles, labels, keyword stickers, place and chapter cards.
   Editable, no render.
2. **A library item**: `library list --panel stickers` / `--kind text-preset` (saved card, alpha movie).
3. **A `graphics.render` plugin** (§4): kinetic type, counter, chart, clicking pointer, mock screen, full-frame
   card, building diagram, speaker shrinking into a card. Rendered once to a `.mov` with alpha; re-render when its
   words change.
Say which and why. A graphics-led reference or genre (a dense explainer short of designed type and cards) needs §4
for most sentences.

## 3. Timing (anchor to words, not seconds)

| What | Range | Sources and why it varies |
|---|---|---|
| Entrance lands on the payoff word | entrance end = the word's start; entrance 0.15–0.6 s | video-use, vibetube (~0.4 s), student-kit (0.15–0.6 s); shorter for energetic cuts, ≤0.15 s for impacts |
| Hold, one idea | 3–8 s, and at least its narration + about 1 s | video-use (floor 3, simple 5–7), vibetube (≥ narration + 1 s), openmontage (3–5 s cap). They conflict: tie the hold to the narration span |
| Hold, diagram that builds | 8–14 s | video-use; complexity and words on it |
| Accent hit | 0.5–2 s, recognisable not readable | video-use, openmontage; only for emphasis or music hits |
| Final-frame hold | 0.5–1.5 s | video-use (≥1 s); longer for a number the viewer must remember |
| Stagger between elements | 0.06–0.10 s opener, 0.3–0.4 s narrative, 0.5–0.6 s dramatic | student-kit; one new element at a time when each is read |
| Entrance / exit | 0.2–0.8 s / 0.15–0.5 s, entrance stronger | talkcraft |
| Words on a card | ≤ about 2–3 per second of hold | student-kit, guizang (6–9 CJK chars/s); measure the real text |
| Density, talking footage | 3–8 graphics a minute, sparser for long videos; a measured reference replaces it | openmontage (3–6/min), hyperframes (card every 6–20 s by length); high for tutorials and explainers, low for vlogs and when the face carries the emotion. Graphics-led explainer shorts run far above: one measured reference changed the picture every ~1.6 s with about 30 graphics a minute (blycreativs before/after, 2026-10-09). With a user reference, take the number from `bc:style-study` |
| First graphic | within the first ~5 s, usually the hook title | vibetube |

Taste stated as law ("never linear", "no bounce") is not a rule: linear suits constant pans and counters; overshoot
1.05–1.12 suits playful, none calm or premium (shotcraft, saas).

Steps: payoff word's timeline frame W → entrance length E → overlay starts at W − E (the composition's entrance
takes E) → hold until the narration it illustrates ends + 0.5–1 s.

## 4. Make it with a graphics plugin

This kit decides what, where and when; a `graphics.render` plugin makes it (`plugins list`):

- **HyperFrames Graphics**: read `bashcut.hyperframes:hyperframes` before the first graphic; its examples and
  catalog are raw material. Many graphics over a voice: rows in `plan.cut.graphics`, built in one `bin/graphic plan`
  call, never one by one, one shared `render.frame` for one look. Short rows: a graphic over more than ~10 s is one row per section (a growing
  diagram: same `render.scene` on each), so an edit re-renders one slice. Look before you render: `bin/graphic plan --only
  ID --snapshot S1,S2,…` shows a row as PNGs in seconds; tweak with snapshots, then one full `plan` (a 40 s graphic
  takes about 3 min to render). Brand mascot: one pose per section. A place video (real estate, a
  venue): all location data from one `bin/osm-map` call into a copy of `amenity-radius`; every count, minute and km
  on screen comes from its output.
- None ready: `plugins search --capability graphics.render`, install, `plugins setup` if its health asks. While
  the install waits or fails, use native text and say what is missing.
- The user's Remotion or After Effects project: they render it (ProRes 4444 or HEVC with alpha); import with
  `library add --kind sticker --file`. Never run Remotion renders for them (licence, T22).

**Numbers on a card: facts table first.** Before searching the web, ask open data for every figure in one call: `uv
run <skill_dir>/fetch_facts.py --questions facts.jsonl --json`, one question per number (a Wikidata property, a World
Bank indicator for a country, or a Wikipedia `summary`; `--help` for the fields). Check each matched the right place
or thing. Rows go straight into widget data: `value` → a counter's `to` or a bar's `value`, `" " + unit` → `unit`;
keep `credit`, date and source URL with the script line (the frame's `credit` only when the user asks). Answers are
cached in `project data facts`. Search the web only for rows that came back `none`, never to replace an answered one;
a figure the table cannot hold (a price, a fee) is a web row from the start.

**Animated accents (Lottie): a check, an arrow, a loader, confetti.** All of a video's in one call: `uv run
<skill_dir>/fetch_lottie.py --words "check,arrow,loader,confetti" --dest <project>/media/lottie` draws one sheet
(useAnimations MIT, Noto Animated CC BY 4.0, LottieFiles Lottie Simple License). One look, then `--pick
"check=2;confetti=1"`; one accent = one `bin/graphic place lottie` (options in the plugin skill). A Noto pick's
credit ("Google (Noto Emoji)") goes in the description only when the user asks. Never `.lottie` zips or animations
with image assets.

Hand the plugin a brief, not a template: words, payoff frame, what the viewer sees, hold, look (style profile,
reference frames, the video's titles).

## 5. Check

- Landing frame and entrance: `ui frame W --phone`, `review window W --span E`. Readable at phone size, on the word,
  face clear (`media subjects` boxes vs the card's rectangle).
- `review layout` for the native text around it; `review shots` sees the overlay as a layer.
- Re-timing the voice moves words, not the overlay: after cuts there, re-read `transcript words`, move or re-render.

## Report

Which sentences got a graphic and why, the tool for each (native, library, rendered), its timing against the word,
the render numbers (seconds, size) and what was left bare on purpose.
