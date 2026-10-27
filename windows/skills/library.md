---
name: library
description: Grow and look after the BashCut library: make a missing preset, effect, transition, look, sticker or sound, harvest what to keep after an edit, fix, copy or prune items. Triggers: "thiếu hiệu ứng", "không có cái nào hợp", "tạo preset", "lưu lại", "dùng lại lần sau", "để dành", "xong rồi".
---

# Library: make, harvest, look after

Eight kinds: `text-preset`, `sticker`, `effect-preset`, `transition-preset`, `look`, `audio`, `voice`, `clip`
(footage), plus a `brand` kit. Four scopes, searched in this order: the project (`.bashcut/library`), this Mac
(`user`), plugin packs, built-ins (read-only).

- Save to the **project** by default; no approval needed.
- `--scope user` (every project on this Mac) waits for the user's click in the app. Offer it for things the user
  will clearly want again (their channel's grade, their outro sound), and say it needs their click.

## 1. Something is missing: make it

1. **Check first**: `library list --kind K --query "shake"`. A close item with other numbers is not missing: apply
   it with `--set`, or copy it with `library update ID --as NEW_ID` and change the copy.
2. **Ask a plugin**: `library search` or `library generate` (jobs; a paid provider: `--dry-run` first). Show the
   candidates, check the licence, then `library add --from-result JOB:N`. No provider (`capabilities get
   library.generate --kind sticker` says why): say so; installing or turning one on is the user's job.
3. **Build it on the timeline, then save it** (most reliable): make it with `bc:effects`, `bc:color-grade`,
   `bc:audio-mix` or `bc:captions-text`, let the user approve, then `library save-selection`.
4. **Write it with `library add`** when it is a recipe you can describe in numbers (below), or from a file you
   were given or made (a `.cube` LUT, a PNG, an audio file).
5. **Try it before calling it done**: `library apply` or `library place` it on a real clip, read `ui frame F`
   (several frames for motion), ask the user to listen for sound, then `timeline undo` unless they keep it. A wrong
   value: `library update ID --params '{...}'` (a new version).

### Writing each kind

`library get ID` on a built-in shows a working example of every kind; `library add --help` has every field.
Frames are timeline frames.

**effect-preset**: up to 32 steps run in order on the clip, up to 16 named parameters set on apply (`--set
name=value`); a step value `"$name"` takes the parameter. Positions are `t` (0–1, so the effect scales with the
clip) or `frame` (negative counts from the end).

```sh
bashcut library add --kind effect-preset --name "Shake hit" --tags punch,impact --params '{"parameters": {"zoom": {"default": 1.25, "min": 1.05, "max": 2}}, "steps": [{"op": "keyframes", "keys": {"zoom": [{"frame": 0, "value": "$zoom", "ease": "out"}, {"frame": 6, "value": 1}], "pan": [{"frame": 0, "value": -20}, {"frame": 2, "value": 20}, {"frame": 4, "value": -10}, {"frame": 6, "value": 0}]}}, {"op": "sfx", "sfx": "AUDIO_ITEM_ID", "frame": 0}]}'
bashcut library apply shake-hit --item CLIP --set zoom=1.4 --from 120 --to 150 --base-rev N
```

| op | fields |
|---|---|
| `motion` | `preset` (as `clip motion --preset`), or `focus` `[x, y, w, h]` (fractions) with `focusTo`, `ease` |
| `keyframes` | `keys` `{property: [{t or frame, value, ease}]}`: zoom, pan, tilt, rotation, opacity |
| `speed` / `speedCurve` | `speed`, `keepDuration`; `preset` or `points` |
| `reverse`, `freeze` | `freeze` holds the frame at `t` or `frame` |
| `patch` | item properties set as they are (`transform`, `opacity`, `crop`…) |
| `sfx` | `sfx` (an audio item ID, or the preset's own `--file`), `t` or `frame`, `volumeDb` |
| `text` | `text`, `textPreset`, `t` or `frame`, `duration` |

Speed steps break lip sync: tag such presets `b-roll`.

**transition-preset**: `kind` (any of the kinds in `bc:effects` "Transition kinds"), `duration` in frames (1–600),
`easing`, `sfx` (an audio item ID) or its own sound as `--file`.

```sh
bashcut library add --kind transition-preset --name "Snap whip" --params '{"kind": "whip", "duration": 6, "easing": "in", "sfx": "AUDIO_ITEM_ID"}'
```

**look**: `{"color": {...}}` with an optional `.cube` as `--file` (make one with `grade.py` in `bc:color-grade`;
look at its preview first).

**audio**: needs `--file`; `library add` measures length and picks music or sfx, `library analyze ID` (job) fills
BPM and loudness. Tag mood and use (`calm`, `whoosh`, `outro`) after the user listened (`library preview ID`).
`{"loopable": true}` only for a bed that loops without a click.

**sticker**: an emoji (`{"emoji": "🎉", "textPreset": "bold-outline"}`), or a PNG/WebP with transparency or a
`.mov` with alpha (HEVC alpha or ProRes 4444). GIFs place as their first frame for now; Lottie is not supported.
Pictures from the web: `bc:stock-images`.

**clip**: a B-roll shot or still kept for reuse (`--file`); other params (a generator's `model`, `prompt`) are
kept. `library place ID --track OVERLAY --at-frame F --duration N` copies it into `clips/`. Generated ones:
`library generate "<shot>" --kind clip` when a provider serves it (`bc:stock-images`).

**text-preset**: `textPreset`, `text`, optional `textStyle` and `animation` (a clip motion preset).
`save-selection` keeps size, position, outline, font, colours and the motion preset (hand-made keys are dropped).
A font from a project's `fonts/` folder is not copied with the preset: `fonts import` it in the next project
(`bc:captions-text`).

**brand**: `palette`, `fonts`, `logo` and `mascot` (sticker items: add the user's own images as stickers first),
`voice`, `disclosure`, every field optional. Only from what the user gave or approved; never invent a mascot and
present it as theirs. `library apply ID` (no `--item`) puts it on the whole project.

```sh
bashcut library add --kind brand --name "Acme" --params '{"palette": {"accent": "#F2B544", "text": "#2B1B0E", "background": "#EADBC4"}, "fonts": {"heading": "BeVietnamPro-Black"}, "logo": "acme-logo"}'
```

Every item: a clear English `--name` (the ID comes from it), `--tags` for mood and use, `--pack` for a set (the
user's channel).

## 2. After an edit: harvest

When the edit is done (after review, before or after export), look for work worth keeping. Never save silently.

1. From `timeline get`, list candidates:
   - a grade the user approved (adjustment or clip colour, with its LUT) → `look`;
   - a keyframed move, speed ramp or freeze you built by hand → `effect-preset`;
   - the same transition kind and length at 3+ cuts, or one In/Out used on many items → `transition-preset`;
   - an SFX or music bed that fit and is not already a library item → `audio`;
   - an image or alpha overlay used as a sticker → `sticker`.
2. Skip what came from the library already, one-off fixes (a crop for one bad shot) and anything the user
   complained about.
3. `library list --kind K` and `library stats --kind K`: skip a duplicate of a saved item; when it improves one,
   propose `library update ID` instead.
4. Propose at most five, each with name, kind, scope and why it is reusable. Save only what they say yes to, with `library save-selection --kind K
   --name N --item ID` (`--scope user` for their channel's items).

Nothing worth keeping: say so in one line.

## 3. Look after it

- **Correction.** The user changed an item's result by hand, or undid it right after `library apply` / `library
  place`: propose `library update ID --params '{...}'` (a new version; the old stays in its history). Built-in or
  plugin: `library update ID --as NEW_ID`, and record a preference to use the copy.
- **Wrong place.** `library move ID --to user` (approval) or `--to project`.
- **Prune.** `library stats` lists saved items nobody used and duplicates. At the end of a session offer to remove
  or merge them; never remove without a yes (`library remove ID`; user scope waits for approval). Removing keeps
  files the timeline still uses.
- **Share.** `library export-pack --output DIR --pack NAME`; the other side runs `library import-pack DIR --scope
  user`.

## Report

What was made or saved (name, kind, scope), what was tried and undone, what waits for the user's approval.
