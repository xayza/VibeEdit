---
name: stock-images
description: Find and place pictures the footage lacks in a BashCut edit: stock photos and video (Pixabay, Pexels, Internet Archive), animated emoji, brand logos, Iconify icons, illustration sets in one style. Triggers: "ảnh minh hoạ", "video minh hoạ", "ảnh stock", "pexels", "lấy ảnh trên mạng", "icon", "emoji", "logo".
---

# Stock photos and video

## 0. Library first

`library list --kind sticker` / `--kind clip --query <words>` may hold the picture (Online resources downloads
too). A plugin may search stock: `library search "clay pot" --kind sticker` (a job); place with `library place ID
--at-frame F --size 0.6 --base-rev N`.

## 1. Search

- **All stock rows at once** (`plan.visuals` rows needing stock): `slots.json` `[{"slot": "pot", "query": "clay
  pot", "kind": "photo", "orientation": "portrait", "count": 8}, …]`, then `uv run <skill_dir>/fetch_stock.py
  --slots slots.json --dest <project>/media/stock --max-mb <cap>` downloads, saves to the library and draws numbered
  sheets. One look per sheet, then `--pick "pot=3@120;river=2@300:90"` places candidate n at a frame (:length);
  `--help` for single lookups. Ranges (tune): ≤ 30 s 4–8 slots × 6–8; 30–90 s 8–16 × 6–10; 1.5–5 min 16–40 × 6–10;
  longer 6–10 slots a minute × 5–8; video cap ~150 MB a minute.
- **Sources** (`--source`; default the first with a key, else `free`): `pexels`, `pixabay` (keys `PEXELS_API_KEY`,
  `PIXABAY_API_KEY`, environment only; the only vertical stock video; Pexels takes Vietnamese), `free` (Wikimedia +
  Openverse photos, licence per file), `nasa` (space, science; public domain), `archive` (Internet Archive photos,
  newsreels, home movies; by year, public domain), `documentary` (archive + Wikimedia + Openverse, news documentary
  only). No video key: say so, use stills with motion. Never place a Pixabay URL. Archive is slow (~0.3 MB/s):
  short items, trim to the moment.
- **No key** is no reason to skip: open `https://www.pexels.com/search/<q>/?orientation=portrait` (videos:
  `/search/videos/<q>/`) in a browser tool, read links and alt text, look at thumbnails before choosing. Photo ID =
  trailing number of `/photo/<slug>-<id>/`; download
  `https://images.pexels.com/photos/<id>/pexels-photo-<id>.jpeg?auto=compress&w=1080`.

## 2. Download

Into `media/stock/` (photos ~100–250 KB at 1080 px; vertical video 15–60 MB); record nothing (`--source URL` only
when at hand), the user handles rights. Avoid identifiable people. Reusable pictures go to the library:

```sh
bashcut library add --kind sticker --name "Clay pot" --file /abs/media/stock/x.jpg --tags food
```

## 3. Place

- **No credits** on the video or in its description unless the user asks; then import with `--origin stock` (`web`
  for a file from someone's own page, such as a CC BY clip) `--license … --source URL --author "Name"` (a second
  `media import` adds them to a file already in) and write the lines from `project credits`.
- **Stock video**: import, then `media place` on main (replaces a moment) or an overlay (illustrates one).
- **Stills**: `media import /abs/media/stock/photo.jpg --place --track OVERLAY --at-frame F --base-rev N`; placed
  for 3 s, trim to the words. Frame with `transform` (zoom < 1 for a card); a still that does not move looks frozen:
  `clip motion ITEM --preset zoom-in` (or `pan-left`/`pan-right`). Never convert photos to video files.
- **Generated B-roll** only when `capabilities get library.generate --kind clip` lists a provider (none is no reason
  to skip stock): `library generate "<shot, framing, light>" --kind clip` (paid: `--dry-run` first, say the price),
  `library add --from-result JOB:N`, `library place`. AI picture: the rules below apply, and `project credits`
  counts it in the AI share.

## 4. Rules

- **No labels on the picture.** Never write "minh hoạ", "stock", "AI", a source or a licence on the video: it makes
  the cut feel unnatural. Real footage stays the main picture; stock reads as illustration by context (over or
  between real shots, tied to the words), not by a caption. Never present stock as the real place in narration or
  titles.
- Tie each picture to its words ("nồi đất" → clay pot); 1.4–2 s each, a soft pop sound.
- How many: the `stock` and `icon` rows of `plan.visuals`; without one, 2–3 per video at most. Always off faces.

## Icons (Iconify)

For a small illustration (money, pin, clock, check, arrow) an icon reads better than a photo. Iconify: 200k+
vector icons, free API, no key, ~0.2 s per call (tested October 2026):

```sh
curl -s "https://api.iconify.design/search?query=cash&limit=20"           # → icons ["mdi:cash", "solar:wallet-bold", …]
curl -s "https://api.iconify.design/collections?prefixes=mdi,solar"       # → each set's licence
curl -s -o cash.svg "https://api.iconify.design/mdi/cash.svg?color=%23FFD400&height=512"
rsvg-convert -w 512 -h 512 cash.svg -o cash.png    # transparent PNG; or: magick -background none -density 1536 cash.svg -resize 512x512 cash.png
```

- BashCut imports PNG, not SVG. Never convert with `qlmanage`: it paints a white background.
- Prefer filled sets (`solid`, `fill`, `bold`; `fluent-emoji-flat` for colour emoji): thin outlines vanish on a
  phone. `?color=` recolours one-colour icons only.
- Save under `media/stock/icons/`, place like a still, 512 px, small (zoom ~0.25–0.4), with a pop; keep good ones
  as library stickers.

## Emoji for keyword pops (Noto Animated, OpenMoji)

All pops in one call: `uv run <skill_dir>/fetch_emoji.py --words "wow,money,fire,tiền" --dest <project>/media/emoji`
draws one sheet, a row per word. One look, then `--pick "wow=1@120:30;money=2@300:30"` saves and places each. Land
it on the payoff word, off faces, with a pop; length from `bc:effects`.

## Brand and tool logos (Simple Icons)

`uv run <skill_dir>/fetch_logos.py --brands "figma@120:90,notion@210:90" --dest <project>/media/logos --on dark`
renders, saves and places each in the brand colour (white/black under 3:1 contrast); no look needed. A near miss
prints close slugs: rerun with the slug. Logos are trademarks: only to name the product shown or reviewed, never to
suggest sponsorship, endorsement or partnership, never recoloured to the channel's palette or altered.

## Illustrations in one style (open sets)

For explainers and promos an open set beats `image.generate`: no cost, one style. Generate only
what no set draws (a named place, a product, a mascot). Sets: `undraw` (~1,800 flat topic scenes, one accent; the
widest for explainers), `humaaans` (90 flat people), `open-peeps` (93 hand-drawn people with faces),
`open-doodles` (33 sketchy scenes). One set per video, never mixed (the first `--set` is stored).

`slots.txt` (`slot: words` lines), then `uv run <skill_dir>/fetch_illustrations.py --slots slots.txt --dest
<project>/media/illustrations --set undraw --palette "#accent,#second"` (brand palette, else two plan colours)
draws numbered sheets. One look per sheet, then `--pick "hook=1@0:90;idea=3@300:75"` places a transparent PNG; a
bare n prints its ID and file (HyperFrames input). Never write or read SVG.

Generated pictures (an `image.generate` plugin): set the style once, `bashcut image style --style "<style>"
--references <character.png>`, then all scenes in one job, `bashcut image generate
prompts.json` (scene prompts only; the lock adds the style). One look at its contact sheet, re-generate only
`failed` or off-model scenes, `media place`. No AI label on the video (it looks unnatural): no `--disclosure`, no `image disclose`
unless the user asks; AI disclosure is the platform's upload toggle (`bashcut.vlog:publish`).
Mascot poses: `bashcut library brand-pose <kit> --pose thinking --image photo.jpg`.

## Free fallback: blurred own footage

For a background (horizontal clip in a vertical frame, split moment, info card): a copy of the clip on the layer
below, zoomed to fill, darkened and softened with an adjustment until the subject reads. No value fits all; as an
example only, zoom ~1.8, `exposure` −1, `saturation` 0.7 worked; a bright, busy background needs more, a dark one
less. Check with `ui frame F --phone`. Same colours, no licence question.
