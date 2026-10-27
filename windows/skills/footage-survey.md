---
name: footage-survey
description: Survey footage before a BashCut edit: inventory, contact sheets, shot descriptions, missing coverage, silent audio, broken files, mixed orientation; a camera synced with a screen recording by sound. Use at the start of an edit. Triggers: "khảo sát footage", "xem footage", "contact sheet", "có những cảnh gì", "đồng bộ", "quay màn hình".
---

# Footage survey

Run this **first**, before promising anything about the edit. Import the clips first (`media import
/abs/footage-folder --base-rev N`: the whole folder in one call, without `--place`); importing does not touch the
timeline.

```sh
bashcut media inventory
bashcut media analyze                             # job: measure every file once (kept by content)
bashcut media frames --sheet                      # contact sheets of every clip (8 frames each)
bashcut media frames --sheet --media A,B --count 12   # clips that change inside (walks, timelapses)
bashcut media frames --sheet --every 2 --media ID     # a long take, a rendered draft
```

**Then actually look at every sheet** with the image reader, every cell. That is the whole value of this skill.

## Run reading

In the quick path this is a sub-agent's job: `bc:surveyor`, or your own sub-agent with `<skill_dir>/SURVEYOR.md` as
its brief; the editor plans from its answer and never prints the transcript or the whole digest itself.
`media digest` is the one short read of what is measured, described and said; read it before the longer commands.

Read in this order:

1. `context get` › `analysis`: wait for running jobs, or carry the gaps into the plan as unknowns.
2. `media inventory`: the totals first. Run the checklist below on it before looking at pictures.
3. The sheets, one at a time. Clips that change inside need more cells: 3–6 per shot plus one every 10–15 s inside
   a long shot is the range other tools use (T05), fewer when the token budget is tight.
4. `review shots --media ID --summary` and `media analysis --media ID` where the sheet and the numbers disagree (a
   cut the sheet misses, a "static" clip that moves).
5. Transcripts of the talking clips (`media transcript`, below).
6. `media describe` every clip you may use **before planning**, so the plan cites shots, not file names.

Numbers only point; the frame confirms (`media frame`, below).

## Honesty and hygiene checklist

Say each of these plainly before planning; each one has spoiled a real edit somewhere (T05):

- **Broken files**: `media import` refuses a file it cannot read (camera cards hold ~1 KB stub `.MP4`s); a moved
  file shows `fileMissing`. Leave them out.
- **Variable frame rate** (`tech.variableFrameRate`; phone screen recordings often are): check sync and in-points
  on the frame, not by arithmetic.
- **HDR or log** (`tech.transferKind`: `pq`/`hlg` = HDR, `log` = flat until graded, `unknown` = untagged): tell
  `bc:color-grade` before anyone judges the colour.
- **Truncated audio** (`tech.audioMinusVideoSeconds` well below 0; one tool flags a track 2 s short, T05): the
  sound ends before the picture, so cut before it.
- **Silent clips**: `hasAudio: false`, or a `sound` whose `loudDb` stays near `floorDb` (−91 dB = no sound at
  all). Other tools put speech 10–15 dB over the clip's own floor (more margin in a quiet room, less on a street,
  T05): a clip that never gets that far above its floor has no usable sound. Plan voiceover or music.
- **Portrait and landscape mixed**: `orientation` is the picture as shown (phones often store 1920×1080 with
  rotation −90, which is portrait). Check it before choosing the project canvas.
- **fps**: other rates play fine, but true slow motion needs 50/60/120 fps sources (`media list`: `fps`).
- **Not measured, transcribed or described** (`totals.notMeasured`, `notTranscribed`, `notDescribed`): name them
  in the plan; never fill them with a guess ("no speech found" is not "silent" unless the floor says so).
- **Recording cues** (phone footage often starts and ends with them): words said to the camera or the crew, not to
  the viewer. Read them in `media digest`, and in `media transcript --media ID --as words` for the exact word
  edges. List each cue with media, seconds and kind before planning, so the plan never quotes one:
  - **start / end of a take**: "bắt đầu", "ok quay nhé", "3, 2, 1", "rolling", "action" in the first ~3 s; "xong",
    "ok rồi", "cut", "tắt đi" in the last ~3 s. Cut them off.
  - **throw away what came before**: "cắt đoạn này", "bỏ đoạn đó", "nói lại", "làm lại", "cut that", "scratch that",
    "take two", "again": the phrase before it is a dead take; the next phrase that says nearly the same words
    (`[again T]`) is the one to use, unless the frame or the delivery says otherwise.
  - **clap or slate**: no words; an `event` word (or "(vỗ tay)", "[clapping]") when the provider marks events,
    else look at the first second's frames. It is a sync point (`media sync`), never in the cut.
  A cue is yours to judge from its words and place, not from a word list: "làm lại" inside a sentence to the viewer
  ("tôi làm lại từ đầu") is content.
- **Suspect words hide restarts**: in `media transcript --media ID --as words`, flag every word longer than about
  1 s or with `confidence` under about 0.4. Whisper merges a false start into one long word: "Hello mọi người, hôm
  nay mình sẽ" said twice came back as one word "demo", 1.8 s at 0.24, and the restart reached the video.
  Re-transcribe just that window (±1 s) with another model and read what was said:
  ```sh
  ffmpeg -ss 12.0 -to 15.8 -i camera.mov -ac 1 -ar 16000 window.wav
  mlx_whisper window.wav --model mlx-community/whisper-large-v3-turbo --language vi --word-timestamps True --output-format json
  ```
  List each restart or repeated phrase (media, seconds, both takes) with the recording cues, for `bc:rough-cut`.

## Reading a contact sheet

| You see | Conclusion |
|---|---|
| Frames of one clip clearly differ | the clip has coverage and several usable moments |
| Frames of one clip are identical | locked-off camera: the clip gives **one** shot size |
| Many clips look alike | repeated scenes: the edit will feel monotonous |
| Rows with texture and no people (smoke, rain, objects, hands) | often the best cutaways: prioritise them |

## When coverage is missing, say so

No editing technique creates shots that were never filmed. Real case: two 4-minute clips, 22–24 frames each,
all nearly identical — 9 minutes of footage gave two shot sizes. Then:

1. State the limit, with the contact sheet as evidence.
2. Offer what can be saved: punch-in reframes (`bc:beat-cut`), stock or illustration images (`bc:stock-images`),
   voiceover over b-roll (`bc:voiceover`).
3. Give a shot list for next time. Per location a few shots of about 10 s (long enough to trim both ends): hands
   doing something (close, fill the frame); the shop front or sign before entering; the food or product right when
   it arrives; walking feet or a slow pan of the space.

## Two recordings of one session (camera + screen)

Filename clocks lie (82 s and 101 s apart by name, 2.44 s by sound once the recording had been trimmed). Measure
with `media sync --media CAMERA_ID --to SCREEN_ID [--item CAMERA_CLIP]` (job; screen time = camera time + offset;
with `--item`, `item.otherSourceIn` is the screen in-point). A render played inside a screen recording: `--media
SCREEN_ID --to RENDER_ID`, it starts at −offset (a 46 s render found in a 5 min recording at 275.74 s, 0.97).

- Use BashCut's number, not ffmpeg's: ffmpeg read a DJI camera's sound 44 ms later (it keeps 2112 samples of AAC
  priming that BashCut drops) and gave −2.49 for −2.44.
- Not reliable below 0.4 or when the halves differ by more than 0.02 s (`steady`): wrong match or drifting clocks.
- Matching caption sentences instead was too rough (9 matches, −1.5 to −4.8 s, median −2.94 for −2.44).

## Time and place

`media inventory` gives `capturedAt` and `location` as the file records them (phones write both; most action
cameras write neither), with places grouped about 100 m apart: "12 min of speech, 3 places, 5 clips not
described" comes from one call. When a file has no capture time, cameras often put it in the name:
`DJI_20260808201922_0400_D.MP4` → 20:19:22 on 08/08. Use it for the order of the trip and for place or time labels
(`bc:captions-text`). Subfolders may reuse the same clip numbers; `folder` keeps them apart.

## Describe what you saw

Write down each clip's shots so other skills and later sessions need not look again: `media describe
/abs/shots.json --media ID --base-rev N` (`--merge` adds), coverage in `media description`. Facts only, in its
vocabulary:

```json
[{"start": 0, "end": 4.2, "size": "WS", "angle": "eye", "move": "pan", "direction": "left",
  "subjects": ["market", "vendor"], "people": 3, "onScreenText": false, "confidence": 0.8,
  "bestMoment": 2.6, "looked": [0.5, 2.6, 4.0]},
 {"start": 4.2, "end": 9.0, "size": "CU", "move": "handheld", "subjects": ["bánh mì"], "bestMoment": null}]
```

- Source seconds (`cells[].seconds`); shots may not overlap. Follow the measured shots (`picture.shots`) where the
  camera cut; one long take can be split where the picture changes.
- `confidence` is how sure you are from what you saw (one frame of a fast move is a guess); `looked` lists the
  frames you actually looked at. No pairings or verdicts ("good opener", "cuts well with C0042"): those belong to
  the plan, not the footage.
- `review shots` then shows each clip's `described` facts on the timeline, so runs of the same size and move are
  visible (`bc:beat-cut`).

## Measured record in BashCut

`media analysis --media ID`, `media speech-map`, `media transcribe` (job; needs a captions.transcribe plugin) and
`media transcript --media ID --as text --format text` read the record BashCut keeps per file content. The numbers
carry no verdicts; you decide what they mean for this edit (`tech`: see the checklist):
- `picture.shots`: the camera's own cuts inside a file (a phone edit, a reference video). One long shot with low
  motion = locked-off: one shot size, as the contact sheet shows. `minScore` (default 0.1) is the cut limit; cut
  scores differ per detector and per footage (screen recordings, fast action and dissolves each need their own,
  T05): lower it when a soft cut is missing, check the frame, and fix the list with `media cuts`.
- `sound` `active` spans are sound over the floor, not necessarily speech: transcribe to know.
- `media speech-map`: `separation: none` means the floor and the sound over it do not separate (street noise,
  music under the voice): there are no silences to cut by level there, so read the transcript spans it adds (after
  `media transcribe`) or listen. `levelCoveredByWords` low = loud sound without words (music, wind, crowd).

Use the record for the checklist and in-points, the sheet for what the shots *are*. In a large folder, measure
only what you will use (`media analyze --media ID`).

## Picking in-points

- Pick by measured sharpness, not by eye on a small sheet: motion blur hides at sheet size (`media analysis
  --samples`: `sharpness` per sample; compare within one clip, it depends on the picture). Look at the frame full
  size before committing (`bashcut media frame --media ID --at SECONDS`, then read the PNG; once placed, `ui frame
  F` shows it in the edit).
- One clip's sound and words over time: `bashcut media strip --media ID [--from S --to S]` draws frames, the level,
  the speech-map gaps and the words on one image.
- Speech: `captions generate` later reuses the transcript. Word `confidence` (`--as words`): other tools re-transcribe, with a larger model or
  vocabulary hints, when the mean is under 0.7–0.85, depending on the language and the noise (T05). Speech
  recognition invents text over music, crowd noise and silence ("hãy subscribe kênh…", "cảm ơn các bạn đã theo
  dõi"): drop lines like that, and treat a clip whose only text is that as having no speech. If the speech is in
  another language than the project, say so before cutting on it.

## Into BashCut

After the survey, place only the clips you will use (`media place`), and write what you found (coverage gaps, best
moments, silent clips) as project facts so later sessions know, for example
`bashcut knowledge set-fact coverage "no wide shot of the market; C0042 has silent audio"`.
