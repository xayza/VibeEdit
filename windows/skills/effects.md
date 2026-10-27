---
name: effects
description: Pick the effect that fits the moment and genre, then make it natively in BashCut: 39 transition kinds, In/Out of text and stickers, punch-in, Ken Burns, speed ramps, freeze, reverse, reframe. Triggers: "hiệu ứng", "chuyển cảnh", "transition", "speed ramp", "chữ nhảy", "tua nhanh", "zoom vào màn hình", "cắt khung dọc".
---

# Effects: look, then when, then how

Decide **when** first; most cuts stay hard. Ranges carry their source (T08 effects, T07 pacing, T19 reframing:
the kit's research notes, naming the editors' kits); a measured reference (`bc:style-study`) or the user's taste
wins. Measure → choose → act → measure again.

## 1. Read what the cut already does

`bashcut review measure` (job: picture motion per shot), then `bashcut review shots --summary`. Count kinds and runs from
each shot's `cut.kind`. Look for runs of one transition kind, neighbouring cuts with `sameFraming`,
every shot with the same `cameraMove` (one failure: all 12 shots a push-in, vox-director; T08 §2), one ease on most
moves, long stretches with no motion. Decide **motif or mistake** for each; a motif is fine when it is a choice.
Other kits warn on: the same transition on two consecutive cuts, one kind more than 2× in a film under 60 s (3 when
longer), fewer than 3 families when there are 5+ cuts, one ease on more than half the moves (saas-motion-kit
`variety_audit`; T08 §2). Prompts to look, not rules.

## 2. When

- **Effects serve a moment, not the whole video.** Special transitions: 1–3 per minute of short form, 0–1 in
  documentary or cinematic work (saas-motion-kit, openmontage, hyperframes; T08 §3); the rest are hard cuts on a
  sentence, beat or action. Sources disagree: speech-led, documentary and cinematic edits keep most cuts hard;
  motion-graphic and short-form ads rotate flavours (T08 §3).
- **Choose by what the cut means**, never by rotating kinds by shot number (student-kit; T08 §4): new place → whip,
  shutter or cover-the-lens; same place, time skip → blink, dissolve or a jump cut; product or dish reveal → speed
  ramp, freeze or a zoom-hit (`crash-zoom`) into it; end of a chapter or story beat → `dip-black`; a memory or
  dream → `double-exposure` or `blur`. A dissolve says time passed; between takes of one sentence use a snap
  punch-in instead (ghost-editor; T08 §3).
- **Never use a flash or transition to hide a missing action** or a moment that should be seen (ReelMimic; T08 §2).
- **Whole-frame hits are rare by default** (flash, blink, crash-zoom, flicker, whole-frame zoom punch, exposure
  pop): each is a slam. `bashcut review sync --events impacts` lists them with beat and spacing. One promo study
  kept about 2–4 per 30–60 s on the strongest beats and moved only an element on the other beats; event and MV
  edits use far more. Check `perMinute` and `minSpacingBeats` before adding another.
- **Every visible move gets a matching sound**, sized to it (`bc:audio-mix`); cutting all music and SFX for 1–2 s
  on a punchline worked once.
- Cinematic: hard cuts, no whoosh; the look and serif captions carry the feel.

| Genre | Fits |
|---|---|
| Food / travel | whip, cut on action, place cards, pop stickers, speed ramp on food action, build-up → reveal |
| Review / ads | freeze + label, price as a keyword sticker, reverse-into-hand hook, crash-zoom on the product |
| Talking head | jump cuts with punch-in, keyword stickers, In/Out on captions and stickers, few transitions |
| Explainer / cards | swing, arc or slide between full-frame cards; iris or diamond to open a title card |
| Real estate | slow speed, keyword stickers for price and area |
| Event / MV, hype | beat cuts, flash, blink, crash-zoom, glitch, halftone, flicker, speed ramps |

## 3. Motion in three families

**Camera-like moves** (zoom, pan, tilt, rotation over a shot). Sources mix three different moves (T08 §3):

| Move | Range | Source |
|---|---|---|
| Slow drift, Ken Burns | 0.3–1.5 %/s, about 1.03–1.07 over a shot; alternate direction between shots | talkcraft, jianshuo, digitalsamba |
| Snap punch on a word | 1.1–1.15 | kinocut, ghost-editor |
| Size change at a cut | 1.15–1.3, capped by headroom | `bc:beat-cut` |
| Beat pulse | ≤2% as texture; full-frame impacts at most 3 per film, ≥16 beats apart | bestagentkits, guizang |

- The ceiling is resolution, not taste: `scale.maxZoomNative` and `pixelRatio` per clip (`timeline get`, `review
  shots`); past 1 output pixel per source pixel it upscales, so look at `ui frame F` before keeping it.
- State drift as a rate so short and long shots feel alike: end zoom = 1 + rate × seconds (0.5 %/s over 8 s ≈ 1.04).
- Two moves in a row read as a glitch: merge into one gesture, front-load the travel (student-kit). Ease out on
  entrances, in on exits, linear only for a constant drift (T08 §3).
- After applying, check `cameraMove` `perSecond` (`review shots`) against the chosen range.

**Speed and time.** Speed changes break lip sync: b-roll and action only, never talking shots.

- Real slow motion needs 50/60/120 fps sources (`media analysis` tech facts); slowing 30 fps below ~0.5× stutters
  (our edits; T08 §3).
- A few frames short: slow the clip slightly, never freeze its last frame (vox-director ~1.02–1.1; T08 §3).
- Fast-forward: 1.5–2× when narrated over, 4–20× for silent waiting (digitalsamba, vlog tutorial; T19 §3);
  `setSpeed` goes to 16×. One example: a 65 s typing stretch read clearly at 16× (about 4 s) with no presenter or
  captions and one label saying what happens (the action, never the speed or effect name).

**Graphic moves and transitions.** Durations in seconds; frames = seconds × the project fps (T08 §3).

| Kind | Length | Source |
|---|---|---|
| Whip | 0.2–0.4 s; 1–2 per short; same direction on both sides, never back and forth in a row | assafkip, saas-motion-kit |
| Dissolve, dip-black | 0.3–1.0 s; bookend fades and chapter dips 0.5–1.0 s | openmontage |
| Blink, shutter, zoom, spin, wipe (and their group: slide, barn-door, roll, crash) | quick ~0.2–0.5 s, standard ~0.7–1.5 s | digitalsamba (two tables in one repo disagree) |
| Swing, arc (next card turns in about an edge) | ~0.3 s between full-frame cards of an explainer; never between footage shots | Reelcrew study (30 videos, 2026-10-07) |
| Glitch (RGB split), halftone (print dots), other stylized | glitch 0.2–0.4 s, halftone 0.4–0.8 s; hype, showreel and comic edits only, about every 2.7 s at most | Reelcrew study |
| Text or sticker In / Out | entrance 0.2–0.6 s, exit shorter | talkcraft |
| Impact (slam, flash, crash-zoom) | 0.10–0.25 s after its target is fully visible | assafkip |

### Transition kinds

39 built-in kinds in 11 groups (the Transitions panel):

| Group | Kinds | Reads as |
|---|---|---|
| Fade | `dissolve`, `blink`, `flash` (to white), `dip-black`, `double-exposure` | time passed, chapter end, memory |
| Whip | `whip` (left), `whip-right`, `whip-up`, `whip-down` | a new place, energy |
| Wipe | `wipe` (from left), `wipe-right`, `wipe-up`, `wipe-down`, `barn-door`, `shutter`, `slide`, `slide-up` | next item, before/after |
| Shape | `iris`, `diamond` | opening or closing a title |
| Crash | `zoom`, `crash-zoom`, `crash-out` | a hit, a reveal |
| Roll | `spin`, `roll`, `roll-right` | playful, hype |
| Arc | `swing`, `arc`, `arc-right` | cards of an explainer |
| Infinite | `infinite-zoom`, `infinite-out` | into or out of a picture |
| Screen | `screen-in`, `screen-out` | into or out of a device |
| Seamless | `blur`, `seamless-zoom` | match between similar shots |
| Stylized | `glitch`, `halftone`, `flicker`, `color-shift`, `kaleidoscope` | hype, showreel, comic |

`motion` properties (any other kind name): zoom, panX/Y, rotation, opacity, exposure, scaleX, reveal,
revealFromRight/Top/Bottom, revealCenter, iris, diamond, swing, rgbSplit, halftone, blur, blurX/Y, zoomBlur, hue,
saturation, kaleidoscope.

### In and Out of text, stickers and overlays

A caption, title, sticker, graphic or overlay clip that is not part of a video cut takes any kind as its own
entrance and exit, played inside its own frame (an iris or wipe reveals the text itself): `setProperties`
`{"enter": {"kind": "iris", "duration": 12}, "exit": {"kind": "whip-up", "duration": 8, "easing": "in"}}`, or
`bashcut clip transition ITEM --side in --kind iris --frames 12 --base-rev last` (`--kind none` removes). Use it
instead of hand keyframes for item entrances and exits. A cut transition at a clip edge wins; a split keeps `enter`
left and `exit` right.

## 4. Reframe: crop only to what matters

A crop decides what the viewer loses. Check the frame first, never crop blind.

1. **Facts**: `scale` (`fit`, `frameCoverage`, `maxZoomNative`) in `timeline get` / `review shots`; `review layout
   --frame F` for the pictures on screen at F.
2. **Look** at the start, middle, end and action peaks of each shot (nateherkai; T19 §2): `media frame` (source
   size, so you read a rectangle in source pixels), `ui frame F`, `ui frames --compare source --items CLIP`. Faces
   and people: `media subjects` (job); `box` is shares of the source picture from the top left, so multiply by the
   media's width and height; check it on `media frame` at that `frame`. `review layout` `faceOverlap` is null when
   no boxes are stored (unknown, not "no face"); `review.maxFaceOverlap` turns it into a `text-face` issue.
   `media describe` subjects are your own tags.
3. **A face subject: one call**, `bashcut clip reframe ITEM --mode locked|cut|follow --base-rev last` (job); look at
   its `preview` grid, that is your check. `--gate` 0.85–0.95, `--drift` 0.1–0.2, `--min-hold` 1–2 s; locked for a
   talking head, cut when the presenter changes place, follow only for real movement. Not a face: step 4.
4. **Crop when what matters fits**: `clip motion ITEM --focus x,y,w,h` around the subject, locked for the shot
   ("don't move unless you must", hotclip; T19 §2). Leave 0.3–0.5 of the face size around a face, more for a
   gesturing presenter (openmontage, hotclip; T19 §3). `--focus-to` only when the subject really moves; no smooth
   drift on a talking head (jianshuo). Check `pixelRatio` afterwards.
5. **Fall back to fit** when it does not fit (two people far apart, a wide landscape, a sign): `fill` false or
   `project format --clips fit`; `clip backdrop ITEM --kind blur` suits screens, slides and photos, not footage
   with a subject (nateherkai; T19 §3). Order: fit → a fixed crop at a position you checked → the original shape.
   A centre crop without a frame check is the anti-pattern (openmontage; T19 §4).

## 5. Zooms on a screen recording

One framing per narration line, aimed at the panel that line names, changing when the screen changes. One tutorial
reused a single framing (pan 0, tilt −480, zoom 1.9) on every screen shot: each sentence named a different panel
and the zoom showed none of them.

1. **Where the screen changes**: `bashcut media frames --media ID --sheet --every 2` and the scene cuts in `bashcut
   media analysis --media ID` (correct them with `media cuts`). A new page, dialog or menu inside a line starts a
   new framing there.
2. **What each line names**: join the line's words (`transcript words`) with the frame under its key word; read the
   panel's rectangle in the recording's pixels on `bashcut media frame --media ID --at SECONDS`.
3. **Build**: `clip motion ITEM --focus x,y,w,h` per line (split at line edges, or `--focus-to` / `--keyframes`
   for a move inside one clip), out to the full screen between steps. Plan.cut clip rows take `focus` and
   `focusKeys` once BashCut's focus-band change ships (branch `feat/focus-visible-band`); write them there then,
   so `plan apply` keeps them.
4. **Check every framing** with `bashcut ui frame F --phone` at the line's key word: the named panel fills the
   frame and its text reads; no neighbouring window. Two lines in a row with the same transform on different
   screens is a miss unless they name the same panel.

## Library first

Built-ins: effect presets `ken-burns-in`, `ken-burns-out`, `zoom-punch-in`, `punch-in`, `speed-ramp`,
`slow-motion`; transition presets `soft-dissolve`, `quick-whip`, `zoom-punch`; emoji stickers. Set a preset's
parameters (`library get ID`) from sections 3–4, not the defaults. Saving, making and fixing presets: `bc:library`.

## How, in BashCut

| Effect | Make it with |
|---|---|
| Transition | `transition` on the plan.cut row (`"whip:6"`), else `upsertTransition`; kinds above |
| Speed, ramp, reverse | `setSpeed`, `setSpeedCurve` (preset or points), `clip reverse ITEM` (job) |
| Freeze frame | select the clip, playhead on the frame, `ui action clip.freeze`; or `freezeFrame` (a source frame held for the whole item) on a split piece |
| Punch-in / reframe | `setProperties` `transform` zoom/pan/tilt, zoom from the clip's headroom (`bc:beat-cut`) |
| Picture in picture | the second clip on an overlay layer, `transform` zoom below 1 |
| Black-and-white moment | `adjustment add --look black-white` over the range |
| Pop text, labels, prices, word-by-word captions | text templates, `keyword-sticker`, `place-card`, `captions words` (`bc:captions-text`) |
| Stickers | `library place`; animated emoji and logos: `bc:stock-images` |
| Fade from/to black | `dip-black` between clips; at the start or end, `dissolve` against a black clip; sound: `fadeIn`/`fadeOut` |
| Ken Burns, slow push-in | `clip motion --preset zoom-in` (zoom-out, pan-*), or keyframes at the drift rate above |
| Text or sticker entrance / exit | `enter` / `exit` on the plan.cut row, else In and Out above; `clip motion --preset pop-in` for a pop that stays |
| Custom move | `clip motion ITEM --keyframes` (frames from the item's start) or one key with `clip keyframe` |
| Zoom onto a panel of a screen recording | `clip motion ITEM --focus x,y,w,h [--focus-to …]`, the panel's rectangle in the recording's pixels. One panel per sentence; the rectangle around the panel only. One example: at zoom 1.9 a 1920 px recording showed 1010 px and a neighbouring window crept in; 2.6 isolated the panel. Confirm with `ui frame`; per line, §5 |
| Presenter box over a screen recording | `setProperties` `crop` {left, right, top, bottom, radius (0.5 = circle)} on the camera clip, then `transform` to size and place it: 0.25–0.6 of the width, smaller when the screen text is dense, larger when the face carries the story (T19 §3). The visible part keeps its place in the picture: an uneven crop (left 0.28, right 0) left the face off-centre until pan moved it back by (left − right) / 2 × canvas width × zoom |

## Not possible yet: say so and offer the alternative

Typewriter text, counting numbers, shake, film grain, glitch held over a shot (only as a transition or In/Out),
segmentation (text behind a person, cut-outs), object tracking (faces: `clip reframe`), AI-generated transitions.
Note it as a feature request (BashCut or a plugin action); never fake it with a pre-rendered file.

## Verify

`review shots --summary` again: the runs you meant to break are gone, the rest are motifs you can name. Look
before, inside and after each effect (`ui frame F`; first, middle and last frame of a moving item; `review window
F` across a transition); after a reframe, what matters is still in frame. Ask the user to listen to the sound.
