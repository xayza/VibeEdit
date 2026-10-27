---
name: audio-mix
description: Balance sound in a BashCut edit: the mix measured by role, gain, fades, a fixed music bed under the voice, SFX at cuts, licensed music and SFX found, loudness per output. Triggers: "trộn âm thanh", "cân âm lượng", "nhạc to quá", "thêm sfx", "tìm nhạc", "nhạc không bản quyền", "meme sound", "audio mix".
---

# Audio mix in BashCut

You cannot listen: measure, change, measure again, and report the numbers.

## Tools

| Need | How |
|---|---|
| Clip level, fades, mute | Level: `clip volume <item> --db -4 --base-rev last` (`--items a,b` for several; linked sound follows), never `timeline apply` for it. Fades and mute: `setProperties` `fadeIn`/`fadeOut` (frames), `muted`; layer: `layers set --muted on` |
| Volume over time (swell at a drop, dip for one line) | `clip keyframe --property volume` (dB) on audio items or clips with linked sound; replaces `volumeDb`, stacks with fades and ducking |
| Music under speech | **Fixed bed first**: one level from the measured voice, `clip volume <bed> --db D --base-rev last`, ducking off (`setTrackProperties` `{"duckingEnabled": false}`). A `plan.cut` `music` without `duck` does this on apply (`underVoiceDb`, default 16; the result reports `voiceLUFS`, `musicLUFS`, `volumeDb`) |
| Music up in long silences | Only when the edit has silences of 2.5 s or more and the music should come up in them: `plan.cut` `music.duck: true` (or `duckDb`), else `setTrackProperties` `{"duckingEnabled": true, "duckUnderSpeechDb": -D, "duckMinGapFrames": H, "duckAttackFrames": A, "duckReleaseFrames": R}`; gaps shorter than the hold (`duckMinGapFrames`, default 2.5 s) keep the music down |
| New layers | `layers add --kind audio --role music` or `sfx` (voiceover: `bc:voiceover`) |

Ducking follows speech on the dialogue and voiceover layers; a muted layer stops ducking music. Ducking that rises
between closely spaced lines pumps: the bed comes and goes with every line and sounds worse than a steady level.
`mix-measure` `musicBeds[].pumping` and review's `music-pumping` flag it.

## 1. Look before fixing

```sh
bashcut audio mix-measure                  # job, no change: the mix by role
bashcut audio measure --timeline --curve   # job: whole mix, loudness over time and silent stretches
bashcut audio measure --media ID --curve   # job: one file (a music candidate, a take, an SFX)
```

Read `mix-measure` before touching any level, decide by the ranges below, change the **ratio** (music `volumeDb`,
duck depth, keyframes), never the master, then measure again (T11 §4). For the bed: voice LUFS − N − the music
file's LUFS at 0 dB is the `--db` to set (N from the range below). Judge `musicUnderSpeech`, not
`duckUnderSpeechDb`: a quiet take can get almost no ducking from the same setting (open-edit, T11 §2).

## 2. Levels: ranges and what moves them

| Stem | Range (T11 §3) | Moves it |
|---|---|---|
| Voice (real speech or voiceover), per stem before the mix | −16 to −20 LUFS | Level each speaking clip first: cameras can differ by 15–20 dB (kit edits). |
| Real speech beside a voiceover | each live-speech clip within ~2 LU of the voiceover | One tutorial left the presenter's camera at −31 LUFS against a −17.5 LUFS voiceover: it sounded like another room. |
| Music under speech | 5–18 dB under the voice | Less when the music carries the piece (montage-like vlog, sparse speech, low `presenceShare`); more for dense information, a soft voice, music with vocals or strong 1–4 kHz energy, accessibility. Sources: ~5 dB, with ~10 dB reported by viewers as "there is no music" (bestagentkits, outcome); 10–14 (reelmimic); 18–20 (openmontage). |
| Music under continuous voiceover | one fixed level 14–18 dB under the voice (default 16) | No level change between lines (Nolan, #630). |
| Music in speech gaps | short gaps (under 2.5 s) never rise; only a silence of 2.5 s or more (intro before the first line, a montage break, the outro) may rise toward voice level | Read `musicInGaps` and `musicBeds`, not the setting (bestagentkits, video-recap, #630). |
| Duck timing (ducking on) | attack 5–200 ms, release 350–600 ms (frames = ms × fps / 1000), hold 2.5 s | The hold keeps the bed down through gaps between lines. |
| Duck depth (ducking on) | 6–14 dB | Then check the measured ratio. |
| SFX, relative to the voice's p95 | subtle UI −16…−12, transitions −14…−8, impacts and memes −8…−3 dB | By role (ghost-editor). Files differ by 20 dB, so measure the file. |
| SFX density | 6–12 subtle per minute plus 1–3 memes (ghost-editor); none for a calm tutorial | Genre (T11 §7). Never the same sample twice in a row. |
| SFX sync | audible peak within 2 frames of its anchor | A correctness rule (guizang, shotcraft); `mix-measure` gives the offsets. |
| Joins, music tail | joins 10–40 ms fades; music tail 1–5 s | Tail by ending style. |

Seen in our edits (not targets): SFX peaking near −21 dB were audible without covering words; a soft piano
(presence share 0.006) sat under a calm male voice ducked 8 dB with nothing to fix.

## Two mixing styles

**Review / food / talking**: one structured song under everything at one fixed level near the deep end of the range; a
whoosh or pop on the hook's special transition; SFX matched to on-screen motion.

**Narrative / cinematic**: music is not a constant bed. Loud in montage (ducking on, rising only in the montage's
silences of 2.5 s or more), down while information is spoken. No
whoosh on ordinary cuts. SFX only with a reason (shutter on a photo cut, real foley pushed up on a montage cut).
Silence is a tool: drop the music 1.5–3 s before the punchline (split the music clip and fade out), leave the most
honest line with no music. Keep the music continuous across section changes.

## Library first

- `library place` puts a sound on the Music or SFX layer; a `loopable` one fills the duration back to back.
  `library preview` plays for the user, not you; saving, tags, analysis: `bc:library`.
- Nothing fits: `library search "soft whoosh" --kind audio` (plugin), else download (below). Never generate music.

## Choosing music

- Prefer **one structured track** at least as long as the video (intro → build → drop → break) and align the
  drop with the hook's special moment. A flat loop measured as perfectly even was still judged boring.
- Songs with a quiet intro dip ~11 dB every time they loop: trim the intro (`trim` or `slip`) before repeating it.
- Put song changes and loop points **on a hard picture cut**: the eye takes the scene change and the ear ignores
  the join.
- Under a talking voice, compare `presenceShare` (1–4 kHz, where consonants carry words) and `loudnessRangeLU` of
  the imported candidates and the voice (`audio measure --media`). Example: the §2 piano 0.006 (LRA 2 LU), lofi
  0.046 (LRA 5.3), voice 0.063. Compare shares between tracks only, not as exact fractions (band edges fall
  24 dB/octave: tones at 2 and 3 kHz alone read 0.684).
- Under speech use instrumental music; lyrics mask the words. Never use songs from a platform's library (TikTok
  and CapCut trending sounds): they are muted when posted on another platform or run as an ad.

## Finding music and SFX online

Policy (decided): download what fits and record nothing: the user handles rights. Dead ends: Bensound, BBC SFX,
ProductionCrate (T21 §3).

| Source | How | Licence |
|---|---|---|
| **Freesound API** (SFX) | `FREESOUND_API_KEY` (free, freesound.org/apiv2/apply), through `fetch_audio.py` | CC0 taken first, then CC BY (credit line); NonCommercial never |
| **Openverse API** (Jamendo, ccMixter, Freesound, Wikimedia) | `curl`, no key, searchable, gives licence and duration | per file: CC0 free; CC BY needs the credit line (T21 §3) |
| **Pixabay Music / Sound Effects** | no API, blocks `curl`: a browser tool on `pixabay.com/music/search/<q>/` or `/sound-effects/search/<q>/` (Vietnamese under `/vi/`), else Mixkit or Openverse | Pixabay Content License: commercial use, no credit; some tracks are registered in Content ID, so keep the page URL as proof (T21) |
| **Mixkit** (music and SFX) | no API: the file URL on `mixkit.co/free-stock-music/tag/<lo-fi\|chill\|upbeat\|cinematic>/` or `/free-sound-effects/<whoosh\|pop\|ding\|click>/` | Mixkit free licences: commercial use, no credit; not resold or shared as stand-alone sound (T21) |
| **tiengdong.com** (Vietnamese meme sounds: "ting ting", "bụp bụp", "oh nooo") | download the one that fits | "All rights reserved", many clipped from shows: organic posts only, never ads or monetised YouTube (T21) |

- **One command** (flags: `--help`): `uv run <skill_dir>/fetch_audio.py --dest <project>/media/audio --music
  "<mood words>" --sfx whoosh,pop --import` (Openverse music; SFX from Freesound with a key, else Mixkit, else
  Openverse).
- **Fetch more than you need, choose by numbers.** Library first (it holds the user's Online resources
  downloads, measured), then one `--slots slots.json` call (`[{"slot": "cut-whoosh", "sfx": "whoosh", "count":
  10}, {"slot": "bed", "music": "lofi chill", "count": 6}]`) downloads, measures and prints one table. Choose by
  onset near 0 for a hit on the cut, peak where the sound lands, BPM near the cut's pace, a bed lifting where the
  video does; `library preview` only for a tie, then `--pick "cut-whoosh=2@120;bed=1@0:900"` places them. Ranges (tune;
  SFX slots from the plan's cuts, transitions, graphic entrances, keyword pops): ≤ 30 s 4–8 kinds × 6–10, 1 bed ×
  4–6; 30–90 s 8–15 × 8–12, 1–2 × 5–8; 1.5–5 min 15–30 × 8–12, 2–4 × 5–8; cap ~150 MB a minute (`--max-mb`).
- **Openverse** by hand: `curl "https://api.openverse.org/v1/audio/?q=lofi&license=cc0,by&category=music"` (SFX:
  drop `category`; `duration` in ms). Freesound's CDN is slow (~12 s a MB); the script fetches in parallel.
- Good keywords: "lofi chill", "upbeat corporate", "cinematic ambient", "meme". Download into the project's
  `media/audio/`, then `media import` (`--source URL` only when you have it; nothing goes on the video or in its
  description unless the user asks).

## Real speech vs voiceover

- Never two voices at once; the gap from real speech is in `bc:voiceover` §5.
- B-roll under voiceover often has people talking: at −15/−28 dB the words stayed intelligible. Split at the
  voiceover's edges and mute only that piece, or use an installed vocal-removal plugin. Keep the original sound
  everywhere the voiceover is silent: stripping it everywhere made a cameraman's real voice disappear.
- **Match real speech to the voiceover** (the sound stage is required whenever both are in the edit):
  1. `bashcut audio mix-measure`: read `speechWindows` and note which window is a camera clip and which the
     voiceover.
  2. Per live-speech clip, read the source's true peak first (`bashcut audio measure --media ID`): the gain you
     can add is the true-peak ceiling (−1 dBTP) minus that peak. One +12 dB raise put a clip at +5 dBTP.
  3. Set each clip's gain to bring it within ~2 LU of the voiceover (`clip volume`); where its peaks cap the gain,
     raise to the cap and pull its loudest words down with a volume keyframe, or lower the voiceover to meet it.
  4. Set the bed 15–20 LU under the quieter of the two voices: a bed fitted to the voiceover sat only 0–4 LU under
     a quiet presenter.
  5. `mix-measure` again: every speech window within ~2 LU, `musicUnderSpeech` p10 ≥ 15 LU in camera windows too,
     and no true peak over the ceiling (`audio measure --timeline`). Log the numbers as the stage's evidence.
- After the mix, report seconds of real speech vs voiceover.

## Screen recordings ("ẩn giọng desktop")

- Speech comes from the presenter's camera; mute the screen recording (it held the same voice 2.5 s late via the
  room mic, plus desktop sound).
- The camera mic hears the laptop speaker: drop sentences where the demo plays the tool's output (its script, not
  the presenter). To keep the output's sound (a hook showing the result), place the output file itself at the
  `media sync` offset (`bc:footage-survey`), never the speaker leak, and start the music bed after it.

## SFX

- Size the sound to the motion: soft whoosh for a slow move, short whoosh for a hard zoom, pop for stickers and
  labels, ding on a final number, hit on the shocking line. Never the same whoosh on every cut.
- A whoosh peaks on the cut; a riser ends on the reveal. Report the `mix-measure` offsets; move an effect only
  when you decide to.
- Judge an effect against the voice at the same moment: `peakOverVoiceDb` for short hits, pops and whooshes
  (400 ms loudness reads a 0.2 s effect several dB low, so `overVoiceDb` makes it look buried), `overVoiceDb` for
  longer beds and risers. Far under both is lost: raise it or move it off the words. Judge `sharedWith` effects as
  one.
- **Runs of one sound** (list items popping in, cards dealing): `review sync --events sfx` lists `sfxRuns`. The
  same file at the same level and spacing sounds mechanical: alternate two samples, step the gain down along the
  run (one that worked: −8 → −12 dB, about 0.40 → 0.25 linear, over six hits), let the spacing follow the motion
  (closer as the cards speed up; when they blur together, one whoosh instead). Pitch shifting is not needed.
- The user's SFX folder, the Audio panel and the library first. In a `plan.cut` edit, SFX go in its `sfx` list
  (`on` a clip or title, `offset`).

## Loudness and verify

- **Each export is normalized to its own preset's target** (`platforms get` `targets`; export
  `--normalize-audio`, needs `audio.loudness`). Values seen: −14 LUFS short-form, −16 podcast, web or
  voice-only, broadcast −23/−24; true peak −1 to −1.5 dBTP, lower when the platform re-encodes (T11 §3). Override
  only for a reason the user gave (`setProjectProperties` `{"output": {"targets": {"tiktok": {"integratedLUFS": L,
  "truePeakDbTP": TP}}}}`); a recipe never sets it.
- Before export: `audio measure --timeline --curve` for silences and jumps between sections (one source keeps
  chapters within 2 LU, another warns at ±1 LU, T11 §3), and `review run`.
- **Camera-mic speech with short peaks** (laughs, plosives, bangs) caps normalization at the true-peak ceiling:
  one edit stayed at −16 LUFS against −14. BashCut has no limiter: lower the gain (or a volume keyframe) on each
  loud line until its peaks sit with the rest, then normalize again.
- After a normalized export, read the receipt (`export status`); `review run` checks it against that export's
  target. Renderers can move the true peak: trust the delivered file, not the setting.
- Report the numbers and list the joins and voiceover windows for the user to play (`ui seek`).
