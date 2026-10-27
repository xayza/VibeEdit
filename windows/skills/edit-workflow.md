---
name: edit-workflow
description: The engine for every BashCut edit, raw footage to export: intake, recipe, survey, the cut as one plan, sound, text, review, draft, through the user's gates with evidence and audits; names the skill per stage. Triggers: "dựng video", "cắt video", "làm vlog", "dựng giúp", "sửa lại video", "edit this", "bắt đầu từ đâu", "video quảng cáo".
---

# Editing a video in BashCut

Read **one section** when a step names it, never a whole file
(`sed -n '/^## Starting/,/^## [A-Z]/p' <skill_dir>/REFERENCE.md`):

- `<skill_dir>/REFERENCE.md`: Starting a project, Intake questions, The brief and the plan as data, Story, Screen
  recording with a presenter, Taste of the user, Working efficiently, Syntax the runs looked up, Run log, The
  hand-off report.
- `<skill_dir>/FULL.md`: Modes, Stages, checklist and gates, Gates, Audits, Review, draft and export, Learn.

A **recipe** (plugin skill) writes data into the plan; this skill runs the process.
Editorial numbers are **ranges with their source**: choose within them for this footage, say why in the plan
(`"deliberate": true` with the reason to leave one).

## Hard rules

- **Tool rules are BashCut's** (its instructions): `--base-rev`, [Scope], errors, library first, downloads, no
  ffmpeg. Stop only at gates. The syntax given here and in REFERENCE "Syntax the runs looked up" is enough: no
  `bashcut help`, `help <cmd>`, `--help` or `schema get` for a command this skill names.
- Downloads need no source or licence records. Install a plugin the edit needs (`plugins search --capability`,
  `plugins install`). Plugin skills are read-only (fixes: `bc:self-learn`).
- **Every call resends the whole context** (cost ≈ calls × context): write `plan.cut` whole once, fix it on the
  plan (check, audits), then apply and render once. Keep what `context get` returned and what you wrote: no
  `project get`, `project data` or `timeline get` between steps. `--base-rev last` on every edit (it is the
  revision your session's last command saw, reads included): never read the project for `rev`. **One plan write
  per stage**: one `project set-data plan --merge` with every key that changed (`stage` too; a list is replaced
  whole, so send the whole list), never one per key.
- **Sub-agents run in the foreground** (`run_in_background: false`) and fix their own findings first. A fix
  round is a new foreground call, never `SendMessage`; never end a turn to wait. Every `plan apply`/`timeline
  apply` carries `--why` (and `--evidence`).
- You never certify yourself: `done` needs evidence, "fixed" needs `review verify`, "exported" needs the job, a
  pass needs an audit by someone else (or marked `self`). You cannot hear: say which sound you did not check.
- Kit scripts run with `uv`. Files named in English, lowercase, hyphens (`draft-v1`).

## The quick path (default)

Unless the user asked for the full process, the video runs over ~3 min, or `plan.mode` is `full` (then FULL.md).
Same gates and audits. Target: a 45 s ad or explainer in about 20 main calls (two system-diagram benches made
25 and 48; most of the rest were the lookups this path now gives).

1. **Bootstrap, one call** (no `ls`, `which`, `bashcut help` or `workflow gates`: `context get` has the gates and
   `next`; recipes are plugin skills `vlog-<kind>`):

   ```sh
   K=<skill_dir>/..; bashcut context get; bashcut knowledge get
   bashcut skills get vlog-<kind> --section "Plan data,Ranges,Review notes,Build,Structure,Sound" \
     | jq -r '.sections, .text'                           # every section you need, in this one read
   sed -n '/^## Before round 1/,/^## The loop/p' $K/review/SKILL.md
   sed -n '/^## The brief and the plan as data/,/^## Story/p' $K/edit-workflow/REFERENCE.md
   "$HOME/Library/Application Support/BashCut/Plugins/bashcut.hyperframes/bin/graphic" examples \
     | jq -r '.[]|"\(.name): \(.about)"'                 # widget names, only when the recipe uses graphics
   ```

   No recipe plugin: tell the user `/bc:setup`, use kit defaults. A widget's variables, an example's HTML and the
   recipe's "every field: `help plan check`" are `bc:graphics`' reading, never yours.
2. **Ask once** (≤4 questions, REFERENCE "Intake questions"), each led by "AI chọn: …". User away: write your
   choices `inferred`, never ask later.
3. **Project, sound and survey, two calls**: `project create --name N --dir D --footage FILE_OR_FOLDER --canvas
   landscape|portrait|square --fps 30 --language <tag> --import` (`--save-current` on "unsaved changes" of a
   project not yours) and the sound in the same call (step 4 "Sound"). Then the survey sub-agent (media and job
   IDs): `bc:surveyor`, else one briefed with `<skill_dir>/../footage-survey/SURVEYOR.md`, else that brief yourself.
   No footage (an explainer): no survey. **Never print a transcript or digest or
   open source frames**; its quotes resolve as they are (context: `media transcript --media M --ranges 640:652
   --as text`).
4. **Brief, plan, limits in one call** (music and SFX imported in step 3), then
   `project format --outputs <preset> --base-rev last`, `project set-data brief brief.json --base-rev last` (fields
   `{value, status: stated|inferred|confirmed, source}`) and `project set-data plan plan.json --merge --base-rev
   last` with `promise`, `sections`, `recipe`, `checks`, `decisions`, `ranges` and the whole **`cut`**:

   ```json
   {"cut": {"clips": [{"id": "c1", "media": "M", "quote": "exact words as transcribed", "section": "hook"},
                      {"id": "c2", "media": "M", "from": 642.8, "to": 648.0, "section": "proof", "zoom": 1.2,
                       "transition": "dissolve:9", "cover": [{"media": "M", "from": 950.0}]}],
            "titles": [{"id": "t1", "text": "HOOK LINE", "clip": "c1", "preset": "hook-title"},
                       {"id": "t2", "text": "Place", "section": "proof", "offset": 0.5, "seconds": 2.5,
                        "preset": "place-card", "style": {"positionY": 0.8}, "enter": "slide", "exit": "iris:8"}],
            "captions": {"from": "speech", "style": {"background": {"color": "#000000", "opacity": 0.6}},
                         "replace": {"misheard": "right"}},
            "music": {"media": "S"}, "sfx": [{"media": "W", "on": "t1", "offset": -0.1}],
            "review": {"minTextSize": 0.035, "minTextContrast": 3, "minShotSeconds": 0.6}}}
   ```

   Transitions live in the plan: `transition` on a clip or graphic row is the cut into it, `enter`/`exit` on a title
   or graphic its In/Out (`"kind"`, `"kind:frames"` or `"none"`; kinds in `bc:effects`). Later applies and graphic
   re-renders keep them; don't set them by hand afterwards. White text over daylight measured 1.2–2:1: plate
   captions and titles now; two texts at once need different `positionY`. **Sound**: a `music` bed unless the brief says none (one fixed level, set on apply 16 dB under the measured
   voice; `duck` only for silences of 2.5 s or more, `bc:audio-mix`); `sfx` only where a moment needs one (`offset`
   -0.1 peaks on it; `bc:audio-mix` "SFX"). Not in the library (`library list --kind audio --query <word>`; `library
   search` is a plugin job, not a library read): `uv run <skill_dir>/../audio-mix/fetch_audio.py --dest
   <project>/media/audio --music "chill electronic" --music-count 2 --min-seconds 50 --sfx whoosh,pop --sfx-count 1
   --import`, with **two genre words** (a four-word mood phrase found nothing in both benches and cost a retry;
   these are all its options, no `--help`). **Graphics** in a recipe that uses them: rows with `id`, `section`,
   `track` and `render.composition` (a name from the bootstrap list) plus what each shows and on which words in
   `plan.visuals`; `bc:graphics` fills `render.set`. **Review limits** (`review`) come from the recipe's `Ranges`
   and the review table: set every limit the table lists and `review-profile-unset` would name now, in this write
   (the benches added `blackMinSeconds`, `stillMotion`, `jumpCutChange` and caption limits in two or three later
   writes); one no source covers: choose it, say so in `ranges`. Request **G1** with the brief.
5. **Check once**: `plan check` resolves quotes on a scratch copy. An edit led by voiceover (lines, no clips)
   skips this step: `bc:voice` (step 7) fits the pauses to the length and runs the check, `bc:graphics` builds.
   Fix every problem it lists in **one** `plan check --patch '{"clips": {"c2": {"to": 953.0}}}'` (by entry ID; no scripts on plan files), check again
   only after that patch: `cut-in-word` gives `facts.before/after` for the edge; `same-framing` is a jump cut to
   come (a `zoom` 1.15–1.3 on the second clip, `bc:beat-cut` §5, never over text, or a `cover`). The **strategy
   audit** is yours (`--by self`): promise, sections, `inferred` brief fields, recipe checks.
6. **Build in the call that records it**: `run append audit --point strategy --verdict pass --findings N --by self
   --evidence "…"`, G2 unless skipped (`checkpoint request G2 --summary "…"`), `plan apply --base-rev last --sheet
   --why "…"` (`--patch` holds the check's fixes: a check saves nothing). Its storyboard sheet is for G3. Every
   later change is `plan apply --patch …`.
7. **Voice and graphics go to sub-agents** (recipe steps too), lines and rows in the plan: `bc:voice`, then
   `bc:graphics` (else sub-agents briefed with `<skill_dir>/../voiceover/VOICE.md` and
   `<skill_dir>/../motion-graphics/GRAPHICS.md`, else yourself). Give each the kit folder (`<skill_dir>/..`),
   project, IDs, facts, look, limits, and `bc:voice` the target length (it sets the pauses and returns the
   duration: no second round for length); each checks its own takes or frames. Never read their skills, renders or
   frames (`ui frame` on their work is the critic's), and never `project data plan` after they return: their
   report says what changed. Then only what the plan cannot say: colour, effects, a mix `audio mix-measure` finds
   off (one call: `J=$(bashcut audio mix-measure | jq -r .job); bashcut jobs wait $J --done --timeout 110`).
8. **Review**: `review run --measure --summary`. Fix every problem in one `plan apply --patch` (never `timeline
   apply` on plan-built items) with `review run` and `review verify all` in the same call. **Draft audit**:
   `bc:critic` (else a sub-agent briefed with `<skill_dir>/../review/CRITIC.md`, else `--by self`) gets the
   project, revision and your suspicions; it reads the plan and contact sheets and returns every finding as one
   `plan.cut` patch. Never open the packet: in **one call** `run append audit --point draft --by critic …`, `plan
   apply --patch … --base-rev last`, `review run --measure --summary`, `review verify all`. A new critic call only
   for an unproven blocker. Captions that split a phrase: a wider `captions.maxChars` (and `review.captionLineChars`)
   in that patch; hand groups only for a phrase still split (REFERENCE "Syntax the runs looked up"). Later
   `plan apply --patch` (music level too) keeps grouped captions.
9. **Draft**: `export start --preset quick-draft --name draft-v1 --include-srt --normalize-audio --wait --save`,
   then **G5** and REFERENCE "The hand-off report".

## The plan as data

Brief and plan are project data that `context get` summarises: after a reset resume from them and `run log`, not
memory. A recipe writes `recipe`, `promise`, `stages` (deviations only), `checks` (≤8), `askAtIntake`; you the rest.
Shapes: REFERENCE "The brief and the plan as data".

## Checklist, gates and audits in short

Stage ids: `intake`, `survey`, `story`, `rough-cut`, `rhythm`, `voiceover`, `visuals`, `sound`, `captions`,
`colour`, `effects`, `review`, `export`, `learn`. BashCut records `intake`, `survey`, `story`, `rough-cut`,
`captions`, `review`, `export`; optional stages left out need no entry; one by hand: `run append stage --stage
colour --status done --evidence "a;b"` in the call that finishes it (a long stage: `--text "…" --eta 120`). Request
every gate, any mode, with something cheap to look at (`checkpoint request G2 --summary "…" --attach sheet.png`,
then `checkpoint status --wait 100` while `awaiting_user`). Only the user answers a gate. Skipped G2 needs the
strategy audit, skipped G5 the draft audit. A stage the plan marks required (a tutorial's effects, sound with a
voiceover beside live speech) is done or logged skipped with the reason before review: BashCut answers
`stage_pending` to review done, G5 and the final export while one is open. Details: FULL "Stages, checklist and gates", "Gates", "Audits". `review
run` `incomplete` is never a pass.
