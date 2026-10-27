---
name: style-study
description: Learn a creator's or channel's editing style by measurement (pacing, shots, hook, text, colour, sound) and turn it into a memo, a library look, text presets and rules, without copying content. Triggers: "học style", "phân tích kênh", "làm giống kênh X", "dựng theo phong cách này", "phân tích video của tôi", "kênh của tôi".
---

# Study a style

**Measure → look at frames → profile with tolerances → differences.** Profile numbers come from the references,
never from this skill. T15 = style-reference study, T01 = ideation, T07 = pacing.

## Sources

Use the user's videos or download references (e.g. `yt-dlp`); keep them in a private folder outside any project
that will be published, and never re-upload them.

How many (T15 §3, T01 §3): one video to mimic that clip; a channel style needs several (5–15 in one study, 10–30 in
another). Confidence by sample count: under 10 low, 10–15 medium, above 15 higher (T01 §3, §7); say the tier next to
every number.

## 1. Measure

In a separate study project (`project create --name "Study - Channel X"`), never the one you publish: `media
import`, `media analyze`, `media transcribe`. All with `--media REF`:

| Facet | Command | Record |
|---|---|---|
| Rhythm | `review shots --summary`; `media analysis` | mean, median, cv, mode, cuts per minute; cuts per 10 s, shot-length histogram |
| Shot sizes, moves | `media describe` the shots you looked at (`bc:footage-survey`), then `review shots --summary` | shares of each size, move, direction; runs of the same size and move |
| Hook and close | `media frames --sheet --from 0 --to 3 --count 6`; `media transcript --as words --to 5` | first cut, first words, first text on screen, the last seconds |
| Speech | `speech rate`; `media speech-map` | rate p10/p50/p90 (syllables for Vietnamese), pauses, speech share |
| Sound | `audio measure --curve` (job) | LUFS, LRA, true peak; short-term level during words vs in the gaps |
| Colour | `media place` the references, then `color measure --by clip` | black, white, mid, saturation, tint per band, per reference |
| Text | `media ocr --step 0.5` (job), then contact sheets | share of seconds with text, box y, line height as a share of the frame, words per card, how long a card holds; case and look by eye |
| Faces | `media subjects --step 1` (job) | share of seconds with a face, face height (a size proxy), where it sits |

A reference's sound is one mixed track: read music under voice from the gap level against the word level (`audio
mix-measure` splits stems only on our timeline).

## 2. Look before trusting a number

Numbers flag, eyes decide (T15 §4).

- Cut detection misses dissolves, whips and fades through black, fast camera moves score like cuts, and a hard cut
  in a dark scene can score very low (T15 §2). Look: `media frames --sheet --every 1` for structure, `media strip`
  around a suspect cut, `media analysis --min-score X` for weaker candidates; fix the list with `media cuts`.
- Open the 3–5 longest shots and the opening on frames before writing about them.
- Speech recognition invents text over music: check the words against the strip before counting speech.
- OCR and face boxes are raw (a logo, sign or reflection reads as text, a poster as a face): check them against
  `media frame` before counting; which text is a caption is yours to decide.
- Mark anything you estimated (by eye, from a few frames) as `est.` (T15 §4).

## 3. Profile with tolerances

Per facet: median and p25–p75 across the references (not only a mean), with n, files and date (T15 §3, §4).
Tolerance:

- ±20–40 % for shot length, cut rate and duration, as a **preference**, not a gate (T15 §3); sources contradict
  (one: ±30 % a must; another: ×0.7–1.3 "a preference, not a hard rule"). Tighten for "exactly like X"; widen when
  our footage has less coverage than the reference or the length differs a lot.
- Keep the cut **rate** per section type (hook, body, payoff), not the total number of cuts, when our video is
  longer or shorter (T15 §3, T07 §7). Hand the band to the recipe or `bc:beat-cut` as a range.
- Priority: the user's instruction > what our footage allows > the reference (T15 §2, §7).
- Colour and sound are raw values (black/white point, saturation, tint; level under words and in gaps), not labels
  like "matte" or "punchy" (T15 §3).

## Own-channel mode

The creator's own history is the benchmark, not genre averages (T01 §2, §4). With view counts, rank each video by
its **multiple over the channel's own median** (needs at least 4 videos, T01 §2, §3); report it and let the creator
judge (one source flags 1.5–3×, T01 §3). The multiple says a video did well, not why: compare the outliers' profile
with the rest and call it a pattern to test, with its confidence tier. Without view counts, the profile is "how you
edit now".

## 4. Differences, not a copy

- Per reference, one learn / don't-take note: what to learn (rhythm, structure, transition type, camera idea,
  holds) and what not to take (T01 §2, T15 §2).
- Never reproduce their text, music, graphics, logos or characters, their exact sequence of shots, or a look so
  close it passes for theirs (T15 §2, §4).
- Before planning, list 3–5 deliberate differences across structure, opening, signature move, look, music and
  ending; one source asks that at least 4 of these 6 differ (T15 §3).
- After the cut, measure ours the same way (`review shots --summary`, `color measure --graded`, `audio
  mix-measure`), compare pictures with `media frames --reference REF --media OURS --count 6` (OURS: a source clip
  or imported draft export), and check the differences are still there.

## 5. Turn it into BashCut

`library list --pack "Channel X"` first: the style may have been studied before.

1. **Project memo** (`knowledge memo`): the profile table (facet, median, p25–p75, tolerance, n, confidence,
   source and date), the learn / don't-take notes, the differences and 5–10 rules, each with its number.
2. **Look**: move the closest `bc:color-grade` look toward the measured values on an adjustment. The whole style is
   that look plus one `patchItems` caption restyle (`bc:captions-text`).
3. **Library pack**: build each piece once, then `library save-selection --kind look --name "Channel X look" --item
   ADJUSTMENT --pack "Channel X"` (also `text-preset`, `transition-preset`, `effect-preset` for its signature
   moves, `audio` for SFX you have the rights to). `--scope user` (every project) waits for the user's approval.
4. **Review limits**: when the user wants the style checked, set the project's `review` keys (`minShotSeconds`,
   `maxShotSeconds`, caption limits) from the profile's range.
5. **Rules for skills**: a finding true beyond this channel is a kit change proposal (`bc:self-learn`).

Tell the user the rules that matter most (numbers, n, confidence) and the differences you will keep.
