---
name: color-grade
description: Colour-grade a BashCut edit by measurement: probe, try looks or a generated .cube LUT on real frames, check for damage and back off, apply with adjustment layers and library looks. Triggers: "tone màu", "chỉnh màu", "color grade", "LUT", "màu phim", "màu cinematic", "hình nhạt", "hình gắt".
---

# Colour grade

Grade after picture lock, before captions (T12 §7). The loop: **probe → measure → candidates → check → back off**.
Numbers are readings with their source, not targets: what to change and how much follows the footage and intent.

## BashCut's colour tools

Whole video: `library place LOOK --at-frame 0 --duration TOTAL_FRAMES`. A range: `adjustment add --look
matte-cinematic --at-frame F --duration D` (grades every layer below). One clip: its `color`. A LUT: `luts import
/abs/look.cube --name "Matte" --base-rev N` (ID in `timeline get` `luts`). Built-in looks: `original`, `vivid`,
`muted-film`, `black-white`, `bright-airy`, `moody`. Grade picture layers only; adjustments never touch text
layers above them. White balance and black/white points need a generated LUT (`grade.py`).

## 1. Probe

`media analyze` (job), then `media analysis --media ID`: a `tech.transferKind` other than `sdr` (iPhone shoots
HLG by default) needs handling first; the looks were fitted on Rec709. No tone-mapping control yet: tell the user
which clips are HLG/PQ/log instead of grading over them (T12 §4, §5).

## 2. Measure

`color measure`, `--by clip` (outliers), `--samples N` for long or changing clips. Find the **brightest, darkest
and skin-heavy** clips: check them later. Never judge from one frame (T12 §4).

| Reading | Range seen | What moves it | Source |
|---|---|---|---|
| Mid luma, daylight vlog | ~30–50 | lower on purpose for night, low-key, silhouettes: not "too dark" | T12 §3, §7 |
| Clipped highlights | share near 0 | deliberate sun or sky may clip | T12 §7 |
| Matte blacks / rolled whites | black > 3 reads as matte; white < 90 as rolled | examples, not targets | style-study (T15 §3) |
| Saturation | < 30 reads muted, > 45 punchy | genre: food punchy, cinematic muted | style-study (T15 §3), T12 §3 |
| Split tone | shadow R−B < 0 with highlight R−B > 0 = teal-orange | — | style-study (T15 §3) |
| Shot match | each clip's difference from the median clip | you choose how far to pull an outlier | drama-skills (T12 §3) |

A recipe's *intent* (`recipe.skill` in `project get`), e.g. "bright, warm, skies kept": turn it into which
readings matter, never into fixed numbers.

## 3. Candidates

**Default: one sheet, one pick.** Turn the intent into a target, then let the scripts rank, check and draw:

```sh
uv run "<skill_dir>/fetch_luts.py"      # once per Mac (setup, or a new --folder of your LUTs): prints one line
uv run "<skill_dir>/grade.py" candidates --target warm,film [/abs/clip.mp4 | MEDIA_ID ...]   # sheet path + 1 line each
uv run "<skill_dir>/grade.py" candidates --pick 3 --strength 0.7   # luts import + adjustment add over the edit
```

`--target`: tags (warm, cool, teal-orange, matte, film, bw, vivid, muted, punchy, soft, bright, dark, moody,
clean, green), a look name below, or a `bc:style-study` profile JSON. It ranks the LUT library (log LUTs only with
`--log`), tries the best on 3 frames (brightest, darkest, most skin), drops damage past `--max-clip` (default 1 %
of detailed pixels; 0.5–2 seen), `--max-crush` (2 %; 1–3) and `--max-skin` (8°; 5–12), and adds `--gen` 3 looks
below fitted to the footage. Look at the sheet once, pick a number (`N@frame:duration` for a range). Picks and
skips, remembered per recipe (`--for`), move the ranking. Never read a LUT list or `.cube`.

| Look | Use for | Fitted reference (`looks.json`) |
|---|---|---|
| `matte-cinematic` | default cinematic: street, daytime, travel | black ~7, white ~84, sat ~28; teal shadows, peach highlights, greens to olive, skin protected |
| `warm-film` | warm indoor light, late afternoon, personal stories | deep blacks (~2.6), highlights ~66–76, sat ~29, warm mids |
| `faded-memory` | hook, flashback or emotional low point, then back to colour | near black-and-white, lifted blacks |
| `teal-orange`, `clean-bright`, `moody-green`, `bw`, `film-print` | blockbuster/travel; food, product, tutorial; forest, rain, night; drama; narrative | set by hand, not fitted (`grade.py looks`) |

Also `library list --kind look`.

- **Strength** 0.5–1.0; 0.6–0.8 is typical (openmontage). Lower for log-like or already saturated footage,
  skin-heavy shots and mixed light (T12 §3).
- **One look for the video**; fix outliers with per-clip `color` or a second adjustment over them (T12 §4).
- A LUT is half the look, light when shooting the other half. Harsh noon sun stays harsh: say so instead of
  pushing the grade until skin breaks.
- A matte look lifts pure black backgrounds to dark grey; use another look over those ranges if true black matters.

### Generated looks by hand (`grade.py`, when the sheet has nothing close)

```sh
G="<skill_dir>/grade.py"           # the folder this SKILL.md is in; run with uv (installs numpy + Pillow)
uv run "$G" looks
uv run "$G" match /abs/clip.mp4 matte-cinematic --exposure S --wb R,G,B   # JSON report, writes nothing
uv run "$G" lut matte-cinematic --exposure S --wb R,G,B -o /abs/project/luts-src/matte.cube
uv run "$G" preview /abs/clip.mp4 /abs/project/luts-src/matte.cube -o /tmp/prev.jpg --n 6
```

`match` reports the footage through the look against the look's `ref` and `range` in `looks.json` (`outside`: 0
inside, − below, + above, null with no range; each range has its `why`); it corrects nothing. You decide the
exposure (stops added to the look's) and white balance (R,G,B multipliers on the look's), try them with
`match` again, then write the LUT with `lut`. Leave the white balance alone on scenes meant to be coloured
(sunset, neon, screen recordings, graphics): the reference tint is the look's, not the scene's (T12 §4).
`match` runs on the source file only; the real check is BashCut's composite in step 4. Never read a `.cube` body;
judge a LUT by its frames (T12 §4). Your own look: a params JSON (keys in `grade.py -h`) in place of a look name.
Then `luts import` the `.cube` and `adjustment add --lut LUT_ID --lut-strength 0.8` over the edit.

## 4. Check

`color measure --compare source`, `ui frames --compare graded --frames F1,F2,F3` (brightest, darkest, skin-heavy),
`ui frame F --phone`.

Read the damage facts in `change` **relative to the source**, then look at the frames. One worked example
(DaVinci Resolve's grade checker, thresholds are parameters): `clippedGrowth` 0.5 % of pixels, washed-out
`chromaRatio` 0.60, milky `blackLift` L* 8, and a grade that moved `meanDeltaE` 6 without any flag "is worth a
second opinion": undamaged is not the same as good (T12 §2, §3). A matte look lifts blacks on purpose; a warm look
moves the mid tint on purpose: compare with the intent. Check every sampled clip, not the average; name the clip
and frame that fails.

## 5. Back off

On damage, lower before adding: `lutStrength` first, then the exposure or white balance you passed. Resolve
backs off ×0.8 per try down to 0.5 (T12 §2). Change the adjustment's `color` (send every key) or `timeline undo`
and add it again. **At most 3 attempts.** Then stop: show the user `ui frames --compare graded` of the gentlest
attempt with its numbers and ask (`ui view --compare on` toggles before/after in the viewer for them).

## Keep what worked

- `library place ID` (an adjustment) or `library apply ID --item ITEM` (one clip's grade) copies its LUT in.
- Once the user approves: `library save-selection --kind look --item ADJUSTMENT`, or from a LUT: `library add
  --kind look --file /abs/matte.cube`. A correction: `library update ID`, or `--as NEW_ID` for a built-in or plugin
  look.
- Matching a reference channel: measure several of its frames with `grade.py measure --json` (videos the user
  has the right to use), compare with your footage, and move a look's params toward them; see `bc:style-study`.
