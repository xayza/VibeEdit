---
name: beat-cut
description: Give a BashCut edit rhythm by measurement: beat grid or word edges, shot lengths per section from sourced ranges, rhythm and sync checked; punch-ins sized from zoom headroom. Use when cutting to music or the cut feels flat or rushed. Triggers: "cắt theo nhịp", "cắt theo beat", "khớp nhạc", "lệch nhịp", "bản dựng phẳng", "nhàm", "punch-in".
---

# Beat cutting and punch-in reframes

The loop: **measure → choose → cut → measure again → adjust**. Numbers are ranges with their source (T07 pacing,
T03 shot grammar, T08 effects: the kit's research notes, naming the editors' kits they came from). Starting
points, not targets: a user's reference, measured with `bc:style-study`, wins.

## 1. Measure what drives the cuts

| Video | Cuts follow | Measure |
|---|---|---|
| Montage, travel teaser, MV, music-led | beat grid, music energy | `beats detect`, `beats grid`, `audio energy` |
| Talking, review, food with speech, tutorial | phrase edges; picture follows words | `transcript words --heard`, `speech rate` |

Speech-led: do **not** lay cuts on the grid first (one example: a grid-first draft had 10 silent gaps, 21 s).
Chain the spoken lines, cut picture at phrase ends (the gap before a word in `transcript words --heard`), then put
music under it. Denser speech (`speech rate`) carries more per shot, so shots hold longer (T07 §3). Before a music
hit after a line, leave 0.1–0.6 s of air (bestagentkits ≥0.12 s, video-use 400–600 ms; T07 §3).

Long pauses in one talking clip: Silence Markers cuts them (`bashcut plugins run bashcut.silence-markers.remove
--params '{"detect":"auto","minSilenceMs":400,"paddingMs":100}'` with the clip selected; `mark` only adds section
markers). An older version refuses `detect`: leave it out there (`plugins actions silence`). Look at the long spans
in `data.removed` (`media strip --media ID --from S --to S`) before keeping it: a long "pause" can be a reaction, a
laugh or b-roll sound. Shorter `minSilenceMs` for a fast talker, more `paddingMs` for a slow one. Then section 6.

## 2. Read the music

Place the music first, then `beats detect` (job; needs an audio.beats provider), `beats grid`, `audio energy`
(job). Judge the grid before cutting on it. You cannot listen: a weak grid means ask the user, or cut on phrases.

| Fact | Strong | Weak → do |
|---|---|---|
| `fit.rmsErrorMs` | small next to a frame (33 ms at 30 fps); kits gate at mean <10 ms (shotcraft), median <15 ms (jianshuo) (T07 §3) | tempo drifts: detect per song or section, cut on phrases |
| `confidence` | stands out from the alternates (no published threshold) | rubato, ambient, speech-heavy: energy lifts/drops and phrases |
| `alternates` | one tempo clearly stronger | similar: pick by how fast the music moves, ask the user. One example: 58.7 BPM detected, truth 117 (the bar) |
| `downbeats`, `phaseScores` | one phase clearly highest | close: a full-band grid can lock onto hi-hats, every cut half a beat late (hyperframes; T07 §4). Ask the user to check a downbeat hits (`ui seek F`) |
| `strengths` | — | "the hit table is a candidate pool, not a trigger" (shotcraft; T07 §2) |

Several songs: detect each media.

Find moments in the energy curve yourself: a **lift** is levelDb or fullness rising several dB over ~2 s against
the 2 s before, a **drop** the reverse, a **breath** a 0.5–2 s dip before a lift. Snap each to the nearest beat or
downbeat. Pointers, not cut points: they shape a section, build → breath → hit on a downbeat → hold (reelmimic;
T07 §2). One breath of 0.5–2 s before the main hit, a payoff hold of ≥1 s (T07 §7).

## 3. Choose shot lengths and cut points

Pick a band per section, then move inside it by content:

| Genre / section | Median shot | Source |
|---|---|---|
| Fast short-form, montage, ads, food inserts | 0.6–2 s | assafkip, iart, znyupup (T07 §3) |
| Speech-led vertical | 2–4 s | T03 §3 |
| Narrative, vlog, b-roll travel | 2.5–6 s (travel 3–4.5 s) | higgsfield, vox-director, vlog plugin (T07 §3, T03 §3) |
| Calm vs urgent tone | 2–4 s vs 0.4–1 s | saas-motion-kit (T07 §3) |
| Hero hold | one per film, 1.5–2.5× the average | higgsfield (T07 §3) |

- **Shorter**: high-motion, low-information shots, energy lifts and drops; **longer**: dense speech, text to read,
  landscapes, calm tone, after a breath (T07 §3).
- Cuts per minute seen: dialogue 14–16 (davinci, "descriptive, NOT a target"), daily vlog 8–12, review 10–14,
  travel 13–16 (vlog plugin), food TikTok 30–40, cinematic vlog 12–20 (style-study) (T07 §3). Compare, don't aim.
- **Beats per shot 2–8**, fewer at peaks (opuscar); cutting every beat for over ~8 beats reads as noise (T07 §7).
  Seconds = beats × 60 / BPM (4 beats: 2 s at 120, 2.7 s at 90): choose the count from the band, not a pattern.
- Vary the rate: one acceleration, one breath, a hero hold (T07 §4). Open with the hook for short form, establish
  first for narrative, real estate or a travel arrival (T03 §3); the plan says which.

One example (travel/food vlog, not a rule): cold open 6 beats (~2.6 s), busy sections 4 (2 on peaks, ~1.6–2.0 s),
quiet ending 4 on slow music (~3.5–4 s); a uniform 3.6 s cut felt flat whatever the content; pieces under ~0.6 s
were merged. The cold open was ~8 s of three shots (the ending, the loudest, the quietest), then chronological
with a section marker and a place label (`bc:captions-text`) at each location change.

## 4. Cut in one apply

Plan in beats and seconds, convert to frames last (shotcraft): beat frame = music item `at` + (beat second −
source-in second) × fps at speed 1 (`beats grid` also gives `downbeatFrames`). Per section: cut points → (clip,
in-point) from its moments in turn → one `timeline apply`, labelled per section. Spread in-points across sources;
never reuse one spot. `roll` nudges a cut onto a beat or word gap; `slip` changes what a clip shows.

## 5. Punch-in reframes from measured headroom

The most effective change when the footage has one angle. Read each clip's `scale` (`timeline get`, `review shots`).

- **Headroom is `maxZoomNative`** (largest zoom before upscaling), per clip: ~2 for 4K in a 1080 landscape project,
  1.0 for same-resolution footage (every punch-in upscales), ~1.125 for 4K landscape filling 1080×1920.
- **Step** by purpose (T08 §3): size change at a cut 1.15–1.3, snap punch on a word 1.1–1.15, slow drift 1.03–1.07
  over the shot. Aim for one described size step (wide → medium → close, T03 §7), within headroom where you can.
- Past headroom is a judgement, not a limit: look at `ui frame F` (and `ui frames --compare source --items CLIP`)
  first. One example: same-resolution footage looked acceptable at 1.28, soft beyond.
- Pan and tilt need margin (none at zoom 1.0 with `frameCoverage` 1). Place the crop on what matters, seen in the
  frame, never a blind centre (`bc:effects`, Reframe).
- Never punch in on signs or text (one example: 1.28 cut "Lẩu Bò Nồi Đất" to "Nồi Đấ").
- A patch replaces the whole `transform`: send zoom, pan and tilt together.

Neighbouring cuts keep the same framing only by choice. One edit's rotation (zoom, pan, tilt): (1.00,0,0)
(1.28,60,−25) (1.14,−50,15) (1.22,0,30) (1.00,0,0) (1.18,70,10) (1.26,−65,−20) (1.10,40,25). Talking heads:
punch-ins every 4–6 s seen (vlog talking-head recipe; ghost-editor 4–6 per 60 s reel; T08 §3), timed to sentence
starts, not a clock.

## 6. Measure again, then adjust

`review measure` (job), `review shots --summary`, `review sync --bins`, `review sync --events impacts`, and
`review sync --events cuts,sfx --rendered` after an export of this revision.

- **Rhythm** (overall, per section): median, cv, cuts per minute against your band. 6+ consecutive shots varying
  under ~0.15 cv (davinci) or a `mode` share over ~60% (saas-motion-kit) is monotony: break it unless the calm is
  intended (T07 §3).
- **Runs of the same described size and move**: 2 → look; 3+ → change size, angle or relation, or say why (a
  motif, a locked-off talk) (higgsfield; T03 §3). A talking head is one setup: punch-ins make the change.
- **Cut facts**: `sameSetup` with a small `sourceGapSeconds` is a jump cut (punch-in or cutaway); `sameFraming`
  means a missing punch-in; `motion`, `cameraMove` show stillness and repeated moves.
- **Beat sync**: hard cuts within ±1–2 frames; 3 is perceptible (shotcraft pass ≤3 f, ideal ≤1.5 f; T07 §3). A
  median offset away from 0 with tight p10–p90: the grid's phase or the whole music is off, shift once or recheck
  the downbeat, not cut by cut. A wide spread: cuts are off the grid, `roll` them.
- **Whole-picture hits** (`impacts`): a cut on the beat changes *when*, not *how hard*. Hits on every kick read as
  the camera shaking. One promo study: ~2–4 per 30–60 s, on the strongest beats, ~16 beats apart; other accents
  moved one element (title, card, number), not the frame. MV, event and hype edits use many more on purpose:
  decide by genre, say why when `perMinute` is high.
- **Word sync**: a cut `inside` a word clips it; move it into the gap.
- **Rendered**: `lagMs`, `driftMsPerMinute`: does the export land where the timeline does?

Then look: `ui frame F` on three consecutive cuts in one scene (three shot sizes?), `review window F` across a
doubtful cut, `review run` for problems. Adjust with `roll`/`slip`, measure again; stop after 3 rounds or when a
round changes nothing, and say what is left and why. Lock the cut before `bc:audio-mix`.
