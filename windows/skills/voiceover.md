---
name: voiceover
description: Voiceover in BashCut: measured speaking rate and narration windows, lines sized to them, text prepared for TTS, takes from a voice.synthesize provider checked against their text, re-takes in place, dubbing. Triggers: "lồng tiếng", "thuyết minh", "đọc lời", "giọng AI", "clone giọng", "TTS", "dịch lồng tiếng", "voiceover".
---

# Voiceover

The numbers below are ranges with their source: choose with the measurements in hand, then measure again.

## Provider and voice

Check `capabilities get voice.synthesize --voices`. `reason: missing` → `plugins search --capability
voice.synthesize`, install one speaking the content language (`project get` › `contentLanguage`, else the
footage's) (`bc:edit-workflow`); `not_configured` or `unhealthy` → quote its `detail`. Until one serves, finish
without voiceover (captions or on-screen text carry the lines) and say so in the final summary. `voice use` sets
the project's voice; `voice speak --voice` overrides it once.

- Only voices with `speaksContentLanguage: true` read the script naturally; none → say so, offer a provider with
  one or a recorded voiceover. Pick by region, style, measured rate, then audition 2–3 on the **hardest** line,
  not the first; the first voice is rarely the pick (T10 §2).
- Saved clones (`kind: clone`, from My voices) carry the user's consent: no `--clone-consent`. Prefer the
  user's clone when the video is theirs and they speak in it; a preset for a narrator, when the clone sounds off
  on the hardest line, or another language.
- Make a clone only when the user asks, of their own voice or one whose owner agreed: Voice panel › + Clone a
  voice… (picks and checks a clean 3–8 s), or `voice clone-add --consent own|permission` with the consent they
  gave in this conversation (the app asks them to approve). A refusal names the reason: pick another part, never
  retry the same one.
- The older plugin option `referenceAudio` clones without saving; pass `--clone-consent` only when the user said
  yes in this conversation, never by default (T10 §6).
- Never mark AI voiceover on the video (no "AI voice" text or sticker); the voice should simply sound natural.

## 1. Measure before writing

There is no normal speaking rate: it varies by voice, language, genre and energy (T10 §3). Measure it in the
content language's unit (syllables for Vietnamese, characters for Chinese/Japanese/Korean, else words) with
`speech rate` (each speaker in the footage) or `speech rate --voice PROVIDER/VOICE` (that voice's earlier takes);
a voice with no measured rate yet: one test line with `voice speak` (nothing is placed), read its `unitsPerSecond`.

- When the voiceover should sound like the creator, size lines from the creator's own measured rate.
- Never reuse an English words-per-second figure for a syllable language (T10 §3).
- Published Vietnamese rates are a sanity check for a measurement, never a budget. Pauses removed (compare
  `articulation`): read speech 4.7–5.3 syllables a second (Bradlow, Interspeech 2019: 4.74; Pellegrino et al.,
  Language 2011: 5.22). Pauses inside phrases kept (compare `overall`): 200–245 a minute, 3.3–4.1 a second
  (Vu et al., ACL 2025, PhoAudiobook: audiobooks 201; news, YouTube and conversation sets 224–243). A measurement
  far outside these: check the transcript for dropped or merged words before sizing lines from it.

**Never say what the person is about to say.** Read the live speech on each side of every window (`transcript
words --heard --from F --to G`, about 5 s each way) and drop or rewrite a line that repeats it: "Mình chỉ bạn làm
từng bước nhé" right before the presenter said the same thing played the idea twice. A voiceover line bridges,
sets up or adds what the speech does not say.

Then `narration windows --min-seconds S --rate R` gives speech-free windows with a unit budget each. Write each
line to its budget, with slack from the voice's p10–p90 spread. A line that does not fit: **cut text**, never
plan to speed the voice (T02 §4). TTS length drifts (a 50 s script came out 40–45 s, T10 §3): final timing comes
from the take, not the script.

## 2. Prepare the text

Spell out what gets misread:
- Numbers, years, times: `2026` → "hai nghìn không trăm hai mươi sáu", `7h30` → "bảy giờ ba mươi". Captions
  keep the digits (T10 §2).
- Units and symbols: km, %, °C, `k` (nghìn đồng).
- Acronyms as letters ("xê en xê" for CNC); show them as letters again in captions.
- English or unusual words: rephrase in plain words rather than respelling ("chill" was read "chiều").
- Very short exclamations (≤ 5 words) with an expressive voice fail often; use a calm voice or a longer line.

When a phrase is misread in every take, **rewording beats regenerating** ("kín xe" → "chật cứng xe"). Change
approved text minimally and tell the user which words changed.

## 3. Synthesize

**A whole script** (an explainer, a narrated ad, any edit whose picture follows the voice): lines in
`plan.cut.voiceover` [{id, text, section, pause}], all voiced in one job; `plan apply` plays each line's best take
with captions in the script's words:

```sh
bashcut voice lines --takes 2 --min-similarity 0.9   # job: every line voiced, transcribed and checked
bashcut voice lines --only l3,l7                     # after rewording those lines in plan.cut
```

Choose `--min-similarity` from §4. One line, one sentence: the take is checked against it and the captions break
on it.

**One line at a time** (a fix, a dub, a line over a fixed shot):

```sh
bashcut voice speak "Text of one line" --takes 3          # job; measures and keeps every take, places none
bashcut voice place TAKE_PROJECT_PATH --at-frame F         # the take you picked
bashcut voice speak "Text" --takes 1 --choose 1 --at-frame F   # one take, placed at once
```

- Pick the take yourself (core picks none), for example the one whose `unitsPerSecond` is closest to the rate you
  sized the line with. One line or short paragraph per call, placed at its window.
- Give every call a stable `--request-id` (`vo-<section>-<n>`). A paid provider: `--dry-run` first and show the
  user its `estimate`; the job's `usage` reports what it charged.
- Takes: 3–6, more for short or expressive lines (T10 §3).
- A take whose rate is far from the voice's measured rate (video-recap flags beyond about ±30 %, T10 §3) has
  likely dropped, repeated or invented words: check it first.
- Style or emotion directives: compare with a neutral take of the same text: +25 % duration "took effect", < 5 %
  "not applied" (jianshuo, T10 §3).
- Unplaced takes stay in `voiceover/generated`; place them with `voice place`, never `media import` (that loses
  the voice text and the AI provenance).

## 4. Check every kept take

`voice check --item ITEM` (or `--media MEDIA --text "…"`, or `--items all`). The model misreads, drops or repeats
words, mostly **at the start** of a line. Read `words` and `extra`, not only `similarity`: a repeated word barely
moves it. `--min-similarity` only for a pass/fail flag (one kit gates at 0.92 for Chinese, T10 §3); your call. Recognition also mishears some regional accents
(s→x, final n→ng): count only errors a listener would hear. Fix by rewording or a re-take.

## 5. Fit to picture

Fix in order of naturalness (T10 §4, jianshuo ladder):

1. **Shorten or reword the text**, then re-take.
2. **Provider rate**, when the voice `supportsRate` (jianshuo slows −12…−15 % before stretching, T10 §3).
3. **Stretch with pitch kept**: `voice fit --item ITEM --to-frame F --min-ratio MIN --max-ratio MAX`, bounds
   yours. Ranges seen: slowing to 0.82–0.95 (floors 0.82 jianshuo, 0.85 digitalsamba; imperceptible above
   ~0.92); speeding up to about 1.1 and only after rewriting failed. How much goes unheard varies with the
   voice's timbre and the music masking it (T10 §3).
4. **Change the text more**, with the user's consent (it changes the captions).

Silence at a line end is often better than a stretched voice. Ranges seen: tail after the last word 0.1–0.5 s,
longer before a cut or reveal; gaps between sentences 0.2–0.8 s, up to 1–3 s after a key line (T10 §3).

- Never over real speech. Keep a gap from real voices (0.3 s worked in our edits); set the project's
  `review.voiceoverMarginSeconds` so `review run` checks it.
- Give each voiceover section b-roll longer than the line: a too-short clip made the voiceover run into the next
  spoken cut.
- Captions come from your text, timed by the take (`bc:captions-text`). Level: against the music, not one
  number (`bc:audio-mix`).

## 6. Re-take one line

`voice speak --replace ITEM --takes 1` (same text), or `voice speak "Reworded line"`, pick, then `voice place
TAKE --replace ITEM`. The item keeps its place; captions are re-timed. Check it, and fit again if its length
changed.

## 7. Dubbing and localisation

1. **Transcribe** the original (`media transcribe`) and measure both rates: the original speaker (`speech rate
   --media ID`) and the target voice.
2. **Translate** per cue, keeping cue boundaries at sentence ends. Languages differ in length (Mandarin takes
   60–80 % of the time Spanish does, jianshuo, T10 §2), so size each cue from the target voice's measured rate.
3. **Sample one cue first**: the most performance-sensitive one, not the first. Get the user's yes on voice and
   pace before batching (OpenMontage, T10 §2).
4. **Per cue, fit ladder**: shorten the text → re-take → `voice fit` within bounds → move the cue
   (`timeline move`) into nearby silence. Tell the user which cues were shortened (it changes the meaning) and
   which moved.
5. **Keep the original audio as a bed** under the dub, not muted: jianshuo keeps it at 0.15–0.25 linear
   (≈ −16…−12 dB, T10 §3); set it with `volumeDb` and check with `bc:audio-mix`.
6. Check every cue (`voice check`), then re-time captions from the takes.
