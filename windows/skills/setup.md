---
name: setup
description: Set up BashCut's recommended plugins (captions, Vietnamese voice, silence markers, pre-production, AI Editor), trusted automatically unless the user turned that off (then with one approval in the app), and check they work. Only when the user types /bc:setup. Triggers: "/bc:setup", "cài plugin đề xuất", "setup BashCut".
disable-model-invocation: true
---

# Setting up BashCut's recommended plugins

Plain words: the user may not be technical. Never paste raw JSON at them. The user typed `/bc:setup`, so they
want the recommended plugins. Plugins are trusted automatically unless the user turned that off (Settings ›
Plugins), then they approve in the app. Never turn a plugin on that the user turned off, never change that
setting, and never ask for API keys or passwords in the chat.

## 1. See what is missing

```sh
bashcut plugins bundles
```

The `starter` bundle (Recommended) lists each plugin (`installable`, `default`, `reason`, sizes). If nothing is
installable, say everything is already installed and go to step 4.

## 2. Tell the user what they get

One short line per installable plugin, from its name: what it does for their videos, not its ID. Say which ones
start unchecked (for example Antigravity) and the total download size. If the user already said they do not want
some, check only the rest with `--only`.

## 3. Install

```sh
bashcut plugins install --bundle starter
bashcut plugins install --bundle starter --only bashcut.whisper-captions,bashcut.vieneu-tts
```

`bashcut jobs wait JOB` gives `approval`:
- `approved`: the install already runs (default plugins or the `--only` ones). Say it is installing.
- `pending`: the Plugins window shows a checkbox per plugin. Tell the user: "Kiểm tra danh sách rồi bấm **Install**
  trong cửa sổ Plugins" (or the same in their language). They can uncheck any plugin.
- `queued` with `position`: another install runs first; this one starts after it. Do not ask again.
- `none`: everything is installed.

The install runs as the user's job (`plugins.install`) and can take minutes (models download). Wait with
`bashcut jobs status` (after `pending`, or ask the user to say when the Plugins window says it is installed),
then go to step 4. Never start another install while one runs.

## 4. Check they work

```sh
bashcut plugins list --health
bashcut capabilities get
```

For each plugin that is not `ready`, explain the health detail in one sentence and what comes next:
- An API key or login: the user enters it in Plugins › the plugin › Options (or signs in where the detail says).
  Do not ask them to send it to you.
- A missing tool or a failed setup: run `bashcut plugins setup PLUGIN` once; `approved`: wait for the job, then
  check `plugins list --health` again; `pending`: the user approves it in the app (Plugins › the plugin › Set
  Up…). If it fails again, say what the detail says instead of retrying.

Finish with what they can do now, for example "gõ: làm phụ đề cho video này" or "đọc lồng tiếng đoạn này".

## 5. Drive a plugin's panel when no command does the job

Prefer the typed command (`voice speak`, `captions generate`, `beats detect`, a plugin skill's own script), then
`plugins run ACTION`. Only a plugin with nothing else needs its view:
1. `bashcut plugins list --views` finds it.
2. `bashcut plugins view PLUGIN --view VIEW` gives its components as JSON: read it instead of a screenshot.
3. `bashcut plugins view-event PLUGIN --view VIEW --node ID [--type change|submit|select|action --value V]` acts
   and returns the new components: no second `view` call. A colour picker takes `#RRGGBB`, a font picker a font
   name.
4. `--open` (or `plugins show-view`) only when the user should see it. `plugins invoke CAPABILITY --params JSON`
   runs a capability raw (a job) when no command wraps it.
