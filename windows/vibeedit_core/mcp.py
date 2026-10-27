"""Minimal stdio MCP-style JSON-RPC server for the VibeEdit Windows MVP.

This is a real, working subset — not a mock: every tool call goes
through the same Project operations as the CLI and the web UI, and
every edit is saved to the project file. Tool names mirror the
original BashCut MCP tools (``bashcut_<group>_<command>``) with the
``vibeedit_`` prefix; the full original catalog has 249 tools, of
which Phase 1 implements the core timeline/project subset below.
Phase 2 added 14 more tools, Phase 3 another 15 (38 total),
Phase 4 another 16 (54 total), Phase 5 another 12 (66 total),
Phase 6 another 12 (78 total), and Phase 7 another 12 (90 total).
Later batches (original-app shell, finishing, media/timeline, and the
code-gap batch) brought the total to 123 real tools.

Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout.
Supported methods: ``initialize``, ``ping``, ``tools/list``,
``tools/call``. The server is single-project: start it with a project
folder (``python -m vibeedit_core.mcp <folder>`` or via the CLI
``vibeedit mcp``), and ``project open`` switches folders.
"""

from __future__ import annotations

import json
import sys

from .project import (Project, load_project, save_project, find_project_file,
                      PROJECT_FILENAME)

TOOLS = [
    {"name": "vibeedit_project_get",
     "description": "Read the whole open project document."},
    {"name": "vibeedit_project_create",
     "description": "Create a project folder and open it."},
    {"name": "vibeedit_project_open",
     "description": "Open a project.vibeedit.json file or its folder."},
    {"name": "vibeedit_project_save",
     "description": "Save the open project to disk."},
    {"name": "vibeedit_timeline_get",
     "description": "Read the timeline as text (like the original timeline get)."},
    {"name": "vibeedit_timeline_apply",
     "description": "Apply timeline operations: add_clip, add_text, trim, "
                    "split, move, delete, set_speed, set_fade."},
    {"name": "vibeedit_timeline_undo",
     "description": "Undo the last applied edit (one step, from the backup file)."},
    {"name": "vibeedit_media_list",
     "description": "List the project's media entries."},
    {"name": "vibeedit_export_start",
     "description": "Start an FFmpeg export (draft or full). Synchronous in Phase 1."},
    # Phase 2 tools — each calls a real Project operation below.
    {"name": "vibeedit_media_place",
     "description": "Place a media entry as a clip on a track."},
    {"name": "vibeedit_clip_trim",
     "description": "Trim a clip edge to a timeline frame."},
    {"name": "vibeedit_clip_split",
     "description": "Split a clip at a timeline frame."},
    {"name": "vibeedit_clip_move",
     "description": "Move a clip to another track and/or start frame."},
    {"name": "vibeedit_clip_delete",
     "description": "Delete a clip or text item."},
    {"name": "vibeedit_text_add",
     "description": "Add a text item to a text track."},
    {"name": "vibeedit_clip_speed",
     "description": "Set a clip's playback speed."},
    {"name": "vibeedit_transition_set",
     "description": "Set a transition between two consecutive main-track clips."},
    {"name": "vibeedit_transition_remove",
     "description": "Remove a transition by id."},
    {"name": "vibeedit_srt_import",
     "description": "Import SRT text onto a text track."},
    {"name": "vibeedit_srt_export",
     "description": "Export a text track as SRT text."},
    {"name": "vibeedit_export_status",
     "description": "Report the last export started by this server, if any."},
    {"name": "vibeedit_clip_keyframes",
     "description": "Replace a clip's keyframes (or add one keyframe)."},
    {"name": "vibeedit_clip_color",
     "description": "Set a clip's LUT file and/or colour preset."},
    # Phase 3 tools — each calls a real Project/export operation.
    {"name": "vibeedit_markers_add",
     "description": "Add a timeline marker."},
    {"name": "vibeedit_markers_list",
     "description": "List the project's markers."},
    {"name": "vibeedit_markers_remove",
     "description": "Remove a marker by id."},
    {"name": "vibeedit_transitions_list",
     "description": "List the project's transitions."},
    {"name": "vibeedit_keyframes_get",
     "description": "Read a clip's keyframes."},
    {"name": "vibeedit_clip_color_get",
     "description": "Read a clip's colour (LUT, preset, strength)."},
    {"name": "vibeedit_clip_fade",
     "description": "Set a clip's fade in/out (seconds)."},
    {"name": "vibeedit_project_info",
     "description": "Project name, revision, size, duration and counts."},
    {"name": "vibeedit_media_metadata",
     "description": "Stored + ffprobe metadata for one media entry."},
    {"name": "vibeedit_project_duplicate",
     "description": "Copy the open project folder under a new name."},
    {"name": "vibeedit_otio_export",
     "description": "Export the timeline as OpenTimelineIO JSON."},
    {"name": "vibeedit_batch_queue",
     "description": "Queue project folders for batch export."},
    {"name": "vibeedit_batch_run",
     "description": "Run the queued batch exports sequentially."},
    {"name": "vibeedit_batch_status",
     "description": "Report the queued batch and its last results."},
    {"name": "vibeedit_export_normalized",
     "description": "Export with single-pass loudnorm normalisation."},
    # Phase 4 tools — each calls a real Project/export operation.
    {"name": "vibeedit_otio_import",
     "description": "Import an OTIO JSON timeline into a new project folder (or merge into an existing project). Missing media is reported, never invented."},
    {"name": "vibeedit_karaoke_add",
     "description": "Attach per-word timings to a text item (karaoke)."},
    {"name": "vibeedit_karaoke_get",
     "description": "Read a text item's karaoke word timings."},
    {"name": "vibeedit_karaoke_export_ass",
     "description": "Export all karaoke items as a standalone .ass file."},
    {"name": "vibeedit_adjustment_add",
     "description": "Add an adjustment layer (colour preset and/or LUT) for a time range."},
    {"name": "vibeedit_adjustment_remove",
     "description": "Remove an adjustment layer by id."},
    {"name": "vibeedit_adjustment_list",
     "description": "List the project's adjustment layers."},
    {"name": "vibeedit_beat_detect",
     "description": "Detect beats from a media file's audio (energy-onset) and store the beat grid."},
    {"name": "vibeedit_beat_list",
     "description": "List the stored beat grid (seconds)."},
    {"name": "vibeedit_beat_snap",
     "description": "Snap a timeline frame to the nearest detected beat."},
    {"name": "vibeedit_beats_to_markers",
     "description": "Copy the stored beat grid into timeline markers."},
    {"name": "vibeedit_ducking_set",
     "description": "Configure music ducking (enabled, amount in dB, threshold, ratio)."},
    {"name": "vibeedit_ducking_get",
     "description": "Read the current music ducking configuration."},
    {"name": "vibeedit_project_stats",
     "description": "Counts for tracks, items, karaoke, adjustments, transitions, markers, beats."},
    {"name": "vibeedit_export_ducked",
     "description": "Export with music ducking forced on for this render."},
    {"name": "vibeedit_clip_tilt",
     "description": "Set tilt (rotation, degrees) keyframes on a clip."},
    # Phase 5 tools — each calls a real Project/render operation.
    {"name": "vibeedit_clip_color_preset_strength",
     "description": "Set a clip's eq colour preset strength (0..1); also sets the preset when given."},
    {"name": "vibeedit_tool_status",
     "description": "Report FFmpeg/FFprobe/font discovery status (paths found or missing, with the fix)."},
    {"name": "vibeedit_windows_check",
     "description": "Windows-readiness checks: Python version, FFmpeg/FFprobe, font, static UI, launcher and build scripts present."},
    {"name": "vibeedit_karaoke_syllable_add",
     "description": "Attach karaoke timings with per-syllable timings to a text item (syllables must join to the word)."},
    {"name": "vibeedit_agent_dock_info",
     "description": "Agent dock info: MCP launch command, tool count and tool names."},
    {"name": "vibeedit_project_validate",
     "description": "Validate the open project; returns ok plus an error list (content errors never raise)."},
    {"name": "vibeedit_track_list",
     "description": "List the project's tracks with item counts."},
    {"name": "vibeedit_clip_list",
     "description": "List clips/items, optionally on one track."},
    {"name": "vibeedit_color_preset_list",
     "description": "List eq colour presets with their filter strings."},
    {"name": "vibeedit_mcp_tools_list",
     "description": "List this server's MCP tools (names and descriptions)."},
    {"name": "vibeedit_text_list",
     "description": "List text items, optionally on one track."},
    {"name": "vibeedit_project_format",
     "description": "Read the open project's format (width, height, fps, sample rate)."},
    # Phase 6 tools — each calls a real Project/export operation.
    {"name": "vibeedit_clip_copy",
     "description": "Copy an item (clip or text) within the open project to another track and start frame, preserving keyframes, colour, fades, volume, speed, text style and karaoke."},
    {"name": "vibeedit_clip_paste_cross_project",
     "description": "Paste an item from the open project into another project folder (media entry copied with it; a missing media file on the destination is reported, never invented)."},
    {"name": "vibeedit_text_preset_list",
     "description": "List text presets (title, subtitle, lower_third, top_caption) with size/position."},
    {"name": "vibeedit_text_preset_apply",
     "description": "Apply a text preset (and optional explicit size/position overrides) to a text item."},
    {"name": "vibeedit_export_preset_list",
     "description": "List export presets (full: project resolution, fast, CRF 20; draft: half resolution, veryfast, CRF 28)."},
    {"name": "vibeedit_timeline_duration",
     "description": "Timeline duration in frames and seconds for the open project."},
    {"name": "vibeedit_media_duration",
     "description": "Stored + ffprobe duration for one media entry."},
    {"name": "vibeedit_project_backup",
     "description": "Copy the open project's file to a .bak backup and report its path."},
    {"name": "vibeedit_project_rename",
     "description": "Rename the open project (its folder name is unchanged)."},
    {"name": "vibeedit_clip_volume",
     "description": "Set a clip's volume in dB."},
    {"name": "vibeedit_text_set",
     "description": "Replace a text item's text."},
    {"name": "vibeedit_media_add",
     "description": "Add a media entry from a file path (ffprobe metadata when the file exists; otherwise stored with a warning)."},
    {"name": "vibeedit_clip_get",
     "description": "Read one timeline item by id, with its track."},
    {"name": "vibeedit_clip_duplicate",
     "description": "Duplicate a clip onto a track at a frame (same media, keyframes, colour, fades)."},
    {"name": "vibeedit_clip_keyframe_remove",
     "description": "Remove keyframes of one property (or all) from a clip."},
    {"name": "vibeedit_media_remove",
     "description": "Remove a media entry that no timeline item references."},
    {"name": "vibeedit_project_format_set",
     "description": "Set the project output format (width, height, fps)."},
    {"name": "vibeedit_track_add",
     "description": "Add a new empty track of a kind (video/text/audio)."},
    {"name": "vibeedit_karaoke_remove",
     "description": "Remove karaoke timings from a text item."},
    {"name": "vibeedit_adjustment_get",
     "description": "Read one adjustment layer by id."},
    {"name": "vibeedit_beat_count",
     "description": "Count detected beats in the project beat grid."},
    {"name": "vibeedit_text_style_get",
     "description": "Read a text item's style (size, position, preset)."},
    {"name": "vibeedit_export_preview",
     "description": "Export a draft preview (half resolution) and report its output path."},
    {"name": "vibeedit_project_rev",
     "description": "Read the project name, revision and format in one call."},
    {"name": "vibeedit_transition_preview",
     "description": "Render a still previewing one transition (draft render, frame at the transition midpoint)."},
    {"name": "vibeedit_review_get",
     "description": "Review panel data: project validation, stats, last export report, skipped and warnings."},
    {"name": "vibeedit_overlay_items",
     "description": "List overlay-track items, including still-image overlays, with their media kind."},
    {"name": "vibeedit_clip_position_set",
     "description": "Set a clip's position keyframes (x and/or y fractions) at a time in seconds."},
    {"name": "vibeedit_clip_scale_set",
     "description": "Set a clip's scale keyframe at a time in seconds."},
    {"name": "vibeedit_clip_opacity_set",
     "description": "Set a clip's opacity keyframe at a time in seconds."},
    {"name": "vibeedit_clip_fades_get",
     "description": "Read a clip's fade-in and fade-out durations."},
    {"name": "vibeedit_clip_speed_get",
     "description": "Read a clip's speed multiplier."},
    {"name": "vibeedit_marker_move",
     "description": "Move a marker to a new timeline frame."},
    {"name": "vibeedit_beat_grid_get",
     "description": "Read the project's detected beat grid (source media, beat times, method)."},
    {"name": "vibeedit_ducking_toggle",
     "description": "Flip music ducking on/off, keeping its amount and threshold."},
    {"name": "vibeedit_clip_keyframes_clear",
     "description": "Remove all keyframes from a clip."},
    {"name": "vibeedit_media_kind_list",
     "description": "List media entries filtered by kind (video, audio, image)."},
    {"name": "vibeedit_timeline_gaps",
     "description": "List gaps (black/silence stretches) on the main track."},
    {"name": "vibeedit_project_duration_frames",
     "description": "Read the project duration in frames and seconds."},
    {"name": "vibeedit_clip_at_time",
     "description": "Find the main-track clip covering a timeline frame, or null."},
    # Code-gap batch: 17 more real tools (106 -> 123). Each calls a
    # real Project operation or a real scan of the project document;
    # none returns canned data.
    {"name": "vibeedit_clip_color_eq",
     "description": "Set per-parameter eq colour (brightness/contrast/saturation/gamma) on a clip."},
    {"name": "vibeedit_clip_color_eq_get",
     "description": "Read a clip's per-parameter eq colour values (or {})."},
    {"name": "vibeedit_source_insert",
     "description": "Insert a marked source range (in/out frames) as a clip at a timeline frame."},
    {"name": "vibeedit_close_gaps",
     "description": "Close gaps on a track by shifting later clips left."},
    {"name": "vibeedit_project_list",
     "description": "List project folders next to the open project folder."},
    {"name": "vibeedit_track_rename",
     "description": "Rename a track (id, kind and role unchanged)."},
    {"name": "vibeedit_track_remove",
     "description": "Remove an empty, non-Main track."},
    {"name": "vibeedit_beat_nearest",
     "description": "Find the detected beat nearest to a time in seconds."},
    {"name": "vibeedit_marker_at_time",
     "description": "Find markers at or before a timeline frame."},
    {"name": "vibeedit_clip_overlap_check",
     "description": "Check whether a clip placed at a frame would overlap on a track."},
    {"name": "vibeedit_media_usage",
     "description": "List every clip that uses a given media id."},
    {"name": "vibeedit_project_search_text",
     "description": "Search text items whose text contains a query string."},
    {"name": "vibeedit_track_duration",
     "description": "Read a track's end frame and clip count."},
    {"name": "vibeedit_clip_text_get",
     "description": "Read a single item's text, or null for non-text items."},
    {"name": "vibeedit_clip_color_reset",
     "description": "Clear a clip's eq colour and LUT (keeps preset if set)."},
    {"name": "vibeedit_timeline_clip_count",
     "description": "Count clips per track and in total."},
    {"name": "vibeedit_source_overwrite",
     "description": "Overwrite the timeline at a frame with a marked source range (original Q)."},
    # Code-gap batch 2 tools — each calls a real Project/server
    # operation below; none returns canned data.
    {"name": "vibeedit_timeline_redo",
     "description": "Redo the last undone edit (one step, from the .redo file written by undo)."},
    # NOTE: vibeedit_marker_move and vibeedit_ducking_get already exist
    # in this list from earlier batches; they are not re-listed here.
    {"name": "vibeedit_adjustments_list",
     "description": "List the project's adjustment layers."},
    {"name": "vibeedit_beats_list",
     "description": "List detected beat times in seconds."},
    {"name": "vibeedit_track_get",
     "description": "Read one track by id."},
    {"name": "vibeedit_media_get",
     "description": "Read one media entry by id."},
    {"name": "vibeedit_speed_curve_apply",
     "description": "Apply an original speed-curve preset (montage/hero/bullet/jump-cut/flash-in/flash-out) to a clip."},
    {"name": "vibeedit_clip_reverse",
     "description": "Flag a clip to play backwards (or clear the flag)."},
    {"name": "vibeedit_clip_freeze",
     "description": "Append a freeze-frame segment after a clip."},
    {"name": "vibeedit_review_run",
     "description": "Run a review (validation + stats) and store it on the project."},
    {"name": "vibeedit_review_accept",
     "description": "Accept the last review run."},
    {"name": "vibeedit_review_verify",
     "description": "Re-run validation and compare issue counts with the last review."},
    {"name": "vibeedit_library_add",
     "description": "Save a clip/text item as a library item."},
    {"name": "vibeedit_library_list",
     "description": "List library items."},
    {"name": "vibeedit_library_place",
     "description": "Place a library item onto the timeline."},
    {"name": "vibeedit_library_remove",
     "description": "Remove a library item (data only, timeline untouched)."},
    {"name": "vibeedit_brand_set",
     "description": "Store brand colours and/or a logo media id on the project."},
    {"name": "vibeedit_brand_get",
     "description": "Read the project's brand kit."},
    {"name": "vibeedit_export_preset",
     "description": "Export with an original ExportPreset (youtube-1080, youtube-4k, prores, tiktok, feed-4x5, square, portrait-3x4, quick-draft)."},
    {"name": "vibeedit_plugin_list",
     "description": "List discovered plugins with enable state."},
    {"name": "vibeedit_plugin_enable",
     "description": "Enable a plugin by name."},
    {"name": "vibeedit_plugin_disable",
     "description": "Disable a plugin by name (listed, never run)."},
]


class MCPServer:
    def __init__(self, folder: str | None = None):
        self.folder = folder
        self.project: Project | None = None
        self.path: str | None = None
        self.last_export: dict | None = None
        self.batch_queue: list[str] = []
        self.batch_results: list[dict] = []
        if folder:
            self.open(folder)

    def open(self, path: str) -> dict:
        import os
        found = path
        if os.path.isdir(path):
            found = find_project_file(path)
            if not found:
                raise FileNotFoundError(f"No project file in folder: {path}")
        data = load_project(found)
        self.project = Project(data, os.path.dirname(os.path.abspath(found)))
        self.path = found
        return {"path": found, "name": data.get("name"), "rev": data.get("rev")}

    def _require(self) -> Project:
        if self.project is None:
            raise RuntimeError("No project open; call vibeedit_project_open first")
        return self.project

    def _save(self) -> None:
        assert self.project is not None and self.path is not None
        save_project(self.project.data, self.path)

    def call(self, name: str, args: dict) -> dict:
        if name == "vibeedit_project_get":
            proj = self._require()
            return {"project": proj.data}
        if name == "vibeedit_project_open":
            return self.open(args["path"])
        if name == "vibeedit_project_save":
            self._save()
            return {"saved": self.path, "rev": self._require().rev}
        if name == "vibeedit_timeline_get":
            return {"timeline": self._require().timeline_text()}
        if name == "vibeedit_media_list":
            return {"media": self._require().data["media"]}
        if name == "vibeedit_timeline_undo":
            import os
            import shutil
            if self.path is None:
                raise RuntimeError("No project open")
            bak = self.path + ".bak"
            if not os.path.isfile(bak):
                raise RuntimeError("Nothing to undo (no backup file)")
            # Save the pre-undo state so redo can restore it.
            shutil.copyfile(self.path, self.path + ".redo")
            data = load_project(bak)
            assert self.project is not None
            self.project.restore(data)
            self._save()
            return {"rev": self.project.rev}
        if name == "vibeedit_timeline_redo":
            import os
            if self.path is None:
                raise RuntimeError("No project open")
            redo = self.path + ".redo"
            if not os.path.isfile(redo):
                raise RuntimeError(
                    "Nothing to redo (undo first; redo restores the "
                    "state saved at undo time)")
            data = load_project(redo)
            assert self.project is not None
            self.project.restore(data)
            self._save()
            return {"rev": self.project.rev}
        if name == "vibeedit_adjustments_list":
            return {"adjustments": self._require().list_adjustments()}
        if name == "vibeedit_beats_list":
            return {"beats": self._require().beat_list()}
        if name == "vibeedit_track_get":
            return {"track": self._require().track(args["track"])}
        if name == "vibeedit_media_get":
            return {"media": self._require().media(args["media"])}
        if name == "vibeedit_speed_curve_apply":
            proj = self._require()
            result = proj.apply_speed_curve(args["item"], args["preset"])
            self._save()
            return result
        if name == "vibeedit_clip_reverse":
            proj = self._require()
            result = proj.set_reverse(args["item"],
                                      bool(args.get("reverse", True)))
            self._save()
            return result
        if name == "vibeedit_clip_freeze":
            proj = self._require()
            result = proj.freeze_clip(args["item"],
                                      int(args.get("frames", 30)))
            self._save()
            return result
        if name == "vibeedit_review_run":
            proj = self._require()
            result = proj.run_review()
            self._save()
            return result
        if name == "vibeedit_review_accept":
            proj = self._require()
            result = proj.accept_review()
            self._save()
            return result
        if name == "vibeedit_review_verify":
            proj = self._require()
            result = proj.verify_review()
            self._save()
            return result
        if name == "vibeedit_library_add":
            proj = self._require()
            result = proj.library_add(args["item"], args.get("name", ""))
            self._save()
            return result
        if name == "vibeedit_library_list":
            return {"items": self._require().library_list()}
        if name == "vibeedit_library_place":
            proj = self._require()
            result = proj.library_place(
                args["entry"], args.get("track"),
                int(args["at"]) if args.get("at") is not None else None)
            self._save()
            return result
        if name == "vibeedit_library_remove":
            proj = self._require()
            result = proj.library_remove(args["entry"])
            self._save()
            return result
        if name == "vibeedit_brand_set":
            proj = self._require()
            result = proj.brand_set(args.get("colours"),
                                    args.get("logo_media"))
            self._save()
            return result
        if name == "vibeedit_brand_get":
            return self._require().brand_get()
        if name == "vibeedit_export_preset":
            from .render import render, export_preset_info
            import os
            proj = self._require()
            info = export_preset_info(
                args["preset"], proj.width(), proj.height())
            out = os.path.join(proj.folder, "render",
                               f"export-{args['preset']}.{info['ext']}")
            report = render(proj.data, proj.folder, out, preset="full",
                            export_preset=args["preset"])
            self.last_export = report
            return report
        if name == "vibeedit_plugin_list":
            from .plugins import list_plugins
            return {"plugins": list_plugins()}
        if name == "vibeedit_plugin_enable":
            from .plugins import set_plugin_enabled
            return set_plugin_enabled(args["plugin"], True)
        if name == "vibeedit_plugin_disable":
            from .plugins import set_plugin_enabled
            return set_plugin_enabled(args["plugin"], False)
        if name == "vibeedit_project_create":
            from .project import new_project
            import os
            folder = os.path.join(args.get("directory", "projects"),
                                  args["name"])
            os.makedirs(os.path.join(folder, "media"), exist_ok=True)
            os.makedirs(os.path.join(folder, "render"), exist_ok=True)
            data = new_project(args["name"])
            path = os.path.join(folder, PROJECT_FILENAME)
            save_project(data, path)
            return self.open(folder)
        if name == "vibeedit_timeline_apply":
            proj = self._require()
            results = []
            for op in args.get("ops", []):
                kind = op["op"]
                if kind == "add_clip":
                    results.append(proj.add_clip(
                        op["media"], op["track"], int(op["at"]),
                        int(op.get("in", 0)),
                        int(op["dur"]) if op.get("dur") is not None else None,
                        float(op.get("speed", 1.0))))
                elif kind == "add_text":
                    results.append(proj.add_text(
                        op["track"], op["text"], int(op["at"]), int(op["dur"])))
                elif kind == "trim":
                    results.append(proj.trim(op["item"], op["edge"],
                                             int(op["toFrame"])))
                elif kind == "split":
                    results.append(proj.split(op["item"], int(op["atFrame"])))
                elif kind == "move":
                    results.append(proj.move(op["item"], op["track"],
                                             int(op["at"])))
                elif kind == "delete":
                    proj.delete(op["item"])
                    results.append({"deleted": op["item"]})
                elif kind == "set_speed":
                    results.append(proj.set_speed(op["item"], float(op["speed"])))
                elif kind == "set_fade":
                    results.append(proj.set_fade(
                        op["item"], op.get("fadeIn"), op.get("fadeOut")))
                elif kind == "set_volume":
                    results.append(proj.set_volume(op["item"],
                                                   float(op["volume"])))
                elif kind == "set_text":
                    results.append(proj.set_text(op["item"], op["text"]))
                elif kind == "set_keyframes":
                    results.append(proj.set_keyframes(op["item"],
                                                      op["keyframes"]))
                elif kind == "set_color":
                    results.append(proj.set_color(op["item"], op.get("lut"),
                                                  op.get("preset"),
                                                  op.get("strength"),
                                                  op.get("preset_strength")))
                elif kind == "add_marker":
                    results.append(proj.add_marker(op["text"],
                                                   int(op["at"])))
                elif kind == "remove_marker":
                    proj.remove_marker(op["marker"])
                    results.append({"deleted": op["marker"]})
                elif kind == "add_transition":
                    results.append(proj.add_transition(
                        op["from"], op["to"], op["kind"],
                        float(op["duration"])))
                elif kind == "remove_transition":
                    proj.remove_transition(op["transition"])
                    results.append({"deleted": op["transition"]})
                else:
                    raise ValueError(f"Unknown operation: {kind}")
            self._save()
            return {"rev": proj.rev, "results": results}
        if name == "vibeedit_export_start":
            from .render import render
            import os
            proj = self._require()
            preset = args.get("preset", "full")
            out = os.path.join(proj.folder, "render",
                               f"export-{preset}.mp4")
            report = render(proj.data, proj.folder, out, preset=preset)
            self.last_export = report
            return report
        if name == "vibeedit_export_status":
            return {"last_export": self.last_export}
        if name == "vibeedit_media_place":
            proj = self._require()
            result = proj.add_clip(args["media"], args["track"],
                                   int(args["at"]), int(args.get("in", 0)),
                                   int(args["dur"]) if args.get("dur") is not None else None,
                                   float(args.get("speed", 1.0)))
            self._save()
            return result
        if name == "vibeedit_clip_trim":
            proj = self._require()
            result = proj.trim(args["item"], args["edge"], int(args["toFrame"]))
            self._save()
            return result
        if name == "vibeedit_clip_split":
            proj = self._require()
            result = proj.split(args["item"], int(args["atFrame"]))
            self._save()
            return result
        if name == "vibeedit_clip_move":
            proj = self._require()
            result = proj.move(args["item"], args["track"], int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_clip_delete":
            proj = self._require()
            proj.delete(args["item"])
            self._save()
            return {"deleted": args["item"]}
        if name == "vibeedit_text_add":
            proj = self._require()
            result = proj.add_text(args["track"], args["text"],
                                   int(args["at"]), int(args["dur"]))
            self._save()
            return result
        if name == "vibeedit_clip_speed":
            proj = self._require()
            result = proj.set_speed(args["item"], float(args["speed"]))
            self._save()
            return result
        if name == "vibeedit_transition_set":
            proj = self._require()
            result = proj.add_transition(args["from"], args["to"],
                                         args["kind"], float(args["duration"]))
            self._save()
            return result
        if name == "vibeedit_transition_remove":
            proj = self._require()
            proj.remove_transition(args["transition"])
            self._save()
            return {"deleted": args["transition"]}
        if name == "vibeedit_srt_import":
            proj = self._require()
            result = proj.import_srt(args.get("track", "t1"), args["srt"])
            self._save()
            return {"imported": len(result)}
        if name == "vibeedit_srt_export":
            proj = self._require()
            return {"srt": proj.export_srt(args.get("track", "t1"))}
        if name == "vibeedit_clip_keyframes":
            proj = self._require()
            if "keyframes" in args:
                result = proj.set_keyframes(args["item"], args["keyframes"])
            else:
                result = proj.add_keyframe(args["item"], float(args["at"]),
                                           args["property"],
                                           float(args["value"]))
            self._save()
            return result
        if name == "vibeedit_clip_color":
            proj = self._require()
            result = proj.set_color(args["item"], args.get("lut"),
                                    args.get("preset"),
                                    args.get("strength"),
                                    args.get("preset_strength"))
            self._save()
            return result
        if name == "vibeedit_markers_add":
            proj = self._require()
            result = proj.add_marker(args["text"], int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_markers_list":
            return {"markers": self._require().data.get("markers", [])}
        if name == "vibeedit_markers_remove":
            proj = self._require()
            proj.remove_marker(args["marker"])
            self._save()
            return {"deleted": args["marker"]}
        if name == "vibeedit_transitions_list":
            return {"transitions": self._require().data.get("transitions", [])}
        if name == "vibeedit_keyframes_get":
            _, item = self._require().item(args["item"])
            return {"keyframes": item.get("keyframes") or []}
        if name == "vibeedit_clip_color_get":
            _, item = self._require().item(args["item"])
            return {"color": item.get("color") or {}}
        if name == "vibeedit_clip_fade":
            proj = self._require()
            result = proj.set_fade(args["item"], args.get("fadeIn"),
                                   args.get("fadeOut"))
            self._save()
            return result
        if name == "vibeedit_project_info":
            proj = self._require()
            return {"name": proj.data.get("name"), "rev": proj.rev,
                    "width": proj.width, "height": proj.height,
                    "duration_seconds": round(proj.duration_seconds(), 3),
                    "media": len(proj.data["media"]),
                    "tracks": len(proj.data["tracks"]),
                    "transitions": len(proj.data.get("transitions", [])),
                    "markers": len(proj.data.get("markers", []))}
        if name == "vibeedit_media_metadata":
            from .export_ops import media_metadata
            proj = self._require()
            return media_metadata(proj.data, proj.folder, args["media"])
        if name == "vibeedit_project_duplicate":
            from .export_ops import duplicate_project
            import os
            proj = self._require()
            dest = os.path.join(
                os.path.dirname(os.path.abspath(proj.folder)),
                args["name"])
            return {"path": duplicate_project(proj.folder, dest,
                                              args["name"])}
        if name == "vibeedit_otio_export":
            from .export_ops import export_otio
            import os
            proj = self._require()
            out = args.get("out") or os.path.join(
                proj.folder, "render", "timeline.otio")
            return export_otio(proj.data, proj.folder, out)
        if name == "vibeedit_batch_queue":
            self.batch_queue = list(args.get("folders", []))
            self.batch_results = []
            return {"queued": self.batch_queue}
        if name == "vibeedit_batch_run":
            from .export_ops import batch_export
            self.batch_results = batch_export(
                self.batch_queue, preset=args.get("preset", "full"),
                normalize_audio=bool(args.get("normalize", False)))
            return {"results": self.batch_results}
        if name == "vibeedit_batch_status":
            return {"queued": self.batch_queue,
                    "results": self.batch_results}
        if name == "vibeedit_export_normalized":
            from .render import render
            import os
            proj = self._require()
            out = os.path.join(proj.folder, "render", "export-normalized.mp4")
            report = render(proj.data, proj.folder, out, preset="full",
                            normalize_audio=True)
            self.last_export = report
            return report
        if name == "vibeedit_otio_import":
            from .export_ops import import_otio
            return import_otio(args["otio"], args["dest"],
                               merge=bool(args.get("merge", False)))
        if name == "vibeedit_karaoke_add":
            proj = self._require()
            result = proj.add_karaoke(args["item"], args["words"])
            self._save()
            return result
        if name == "vibeedit_karaoke_get":
            return self._require().karaoke_get(args["item"])
        if name == "vibeedit_karaoke_export_ass":
            from .export_ops import export_karaoke_ass
            import os
            proj = self._require()
            out = args.get("out") or os.path.join(
                proj.folder, "render", "karaoke.ass")
            return export_karaoke_ass(proj.data, out)
        if name == "vibeedit_adjustment_add":
            proj = self._require()
            result = proj.add_adjustment(int(args["at"]), int(args["dur"]),
                                         args.get("preset"), args.get("lut"),
                                         args.get("strength"))
            self._save()
            return result
        if name == "vibeedit_adjustment_remove":
            proj = self._require()
            proj.remove_adjustment(args["item"])
            self._save()
            return {"deleted": args["item"]}
        if name == "vibeedit_adjustment_list":
            return {"adjustments": self._require().list_adjustments()}
        if name == "vibeedit_beat_detect":
            proj = self._require()
            result = proj.detect_beats(args["media"],
                                       min_gap_s=float(args.get("min_gap", 0.3)))
            self._save()
            return result
        if name == "vibeedit_beat_list":
            return {"beats": self._require().beat_list()}
        if name == "vibeedit_beat_snap":
            proj = self._require()
            return {"frame": int(args["frame"]),
                    "snapped": proj.snap_frame(int(args["frame"]))}
        if name == "vibeedit_beats_to_markers":
            proj = self._require()
            result = proj.beats_to_markers()
            self._save()
            return {"markers": result}
        if name == "vibeedit_ducking_set":
            proj = self._require()
            result = proj.set_ducking(
                bool(args.get("enabled", True)),
                amount_db=float(args.get("amount_db", 6.0)),
                threshold=float(args.get("threshold", 0.02)),
                ratio=args.get("ratio"),
                attack=float(args.get("attack", 20.0)),
                release=float(args.get("release", 250.0)))
            self._save()
            return result
        if name == "vibeedit_ducking_get":
            return self._require().ducking_get()
        if name == "vibeedit_project_stats":
            return self._require().project_stats()
        if name == "vibeedit_export_ducked":
            from .render import render
            import os
            proj = self._require()
            out = os.path.join(proj.folder, "render", "export-ducked.mp4")
            report = render(proj.data, proj.folder, out, preset="full",
                            ducking=True)
            self.last_export = report
            return report
        if name == "vibeedit_clip_tilt":
            proj = self._require()
            result = None
            for kf in args["keyframes"]:
                result = proj.add_keyframe(args["item"], float(kf["at"]),
                                           "tilt", float(kf["tilt"]))
            self._save()
            return result
        if name == "vibeedit_clip_color_preset_strength":
            proj = self._require()
            result = proj.set_color(args["item"],
                                    preset=args.get("preset"),
                                    preset_strength=float(
                                        args["preset_strength"]))
            self._save()
            return result
        if name == "vibeedit_tool_status":
            from .render import find_font, find_tool
            import os
            status: dict = {"ffmpeg_dir_env": os.environ.get(
                "VIBEEDIT_FFMPEG_DIR"),
                "font_env": os.environ.get("VIBEEDIT_FONT")}
            for tool in ("ffmpeg", "ffprobe"):
                try:
                    status[tool] = find_tool(tool)
                except FileNotFoundError as exc:
                    status[tool] = None
                    status[tool + "_error"] = str(exc)
            try:
                status["font"] = find_font()
            except FileNotFoundError as exc:
                status["font"] = None
                status["font_error"] = str(exc)
            return status
        if name == "vibeedit_windows_check":
            from .render import find_font, find_tool
            import os
            import sys
            windows_dir = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))
            checks: dict = {"python": sys.version.split()[0]}
            for tool in ("ffmpeg", "ffprobe"):
                try:
                    checks[tool] = find_tool(tool)
                except FileNotFoundError:
                    checks[tool] = None
            try:
                checks["font"] = find_font()
            except FileNotFoundError:
                checks["font"] = None
            for rel in ("run_vibeedit.bat", "run_vibeedit.ps1",
                        "build_windows.bat", "vibeedit.spec",
                        "vibeedit.py",
                        os.path.join("scripts", "install_shortcuts.ps1"),
                        os.path.join("static", "index.html")):
                checks["file:" + rel] = os.path.isfile(
                    os.path.join(windows_dir, rel))
            checks["ok"] = bool(
                checks["ffmpeg"] and checks["ffprobe"]
                and all(v for k, v in checks.items()
                        if k.startswith("file:")))
            return checks
        if name == "vibeedit_karaoke_syllable_add":
            proj = self._require()
            result = proj.add_karaoke(args["item"], args["words"])
            self._save()
            return result
        if name == "vibeedit_agent_dock_info":
            return {
                "command": "python windows/vibeedit.py mcp "
                           "<project-folder>",
                "protocol": "newline-delimited JSON-RPC 2.0 on "
                            "stdin/stdout (initialize, ping, "
                            "tools/list, tools/call)",
                "tool_count": len(TOOLS),
                "tools": [t["name"] for t in TOOLS]}
        if name == "vibeedit_project_validate":
            return self._require().validate()
        if name == "vibeedit_track_list":
            proj = self._require()
            return {"tracks": [
                {"id": t["id"], "kind": t["kind"],
                 "role": t.get("role"), "name": t.get("name"),
                 "items": len(t["items"])}
                for t in proj.data["tracks"]]}
        if name == "vibeedit_clip_list":
            proj = self._require()
            track_id = args.get("track")
            items = []
            for track in proj.data["tracks"]:
                if track_id and track["id"] != track_id:
                    continue
                for item in track["items"]:
                    items.append({"track": track["id"], "id": item["id"],
                                  "at": item["at"], "dur": item["dur"],
                                  "media": item.get("media"),
                                  "text": item.get("text")})
            return {"items": items}
        if name == "vibeedit_color_preset_list":
            from .project import COLOR_PRESETS
            return {"presets": dict(COLOR_PRESETS)}
        if name == "vibeedit_mcp_tools_list":
            return {"tools": TOOLS, "count": len(TOOLS)}
        if name == "vibeedit_text_list":
            proj = self._require()
            track_id = args.get("track")
            items = []
            for track in proj.data["tracks"]:
                if track_id and track["id"] != track_id:
                    continue
                for item in track["items"]:
                    if "text" in item:
                        items.append({"track": track["id"],
                                      "id": item["id"], "at": item["at"],
                                      "dur": item["dur"],
                                      "text": item["text"]})
            return {"items": items}
        if name == "vibeedit_project_format":
            return {"format": self._require().data["format"]}
        if name == "vibeedit_clip_copy":
            proj = self._require()
            result = proj.duplicate_item(args["item"], args["track"],
                                         int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_clip_paste_cross_project":
            import os
            from .export_ops import media_metadata  # noqa: F401 - noqa
            src = self._require()
            _, item = src.item(args["item"])
            dest_folder = args["dest"]
            found = find_project_file(dest_folder)
            if not found:
                raise FileNotFoundError(
                    f"No project file in folder: {dest_folder}")
            dest = Project(load_project(found),
                           os.path.dirname(os.path.abspath(found)))
            warning = None
            if "media" in item:
                medium = src.media(item["media"])
                if not any(m["id"] == medium["id"]
                           for m in dest.data["media"]):
                    dest.data["media"].append(dict(medium))
                dest_path = medium["path"]
                dest_abs = (dest_path if os.path.isabs(dest_path)
                            else os.path.join(dest.folder, dest_path))
                if not os.path.isfile(dest_abs):
                    warning = (f"Media file not found relative to "
                               f"destination project: {dest_abs}")
            result = dest.copy_item_data(item, args["track"],
                                         int(args["at"]))
            save_project(dest.data, found)
            out = dict(result)
            if warning:
                out["media_warning"] = warning
            out["destination_project"] = found
            return out
        if name == "vibeedit_text_preset_list":
            from .project import TEXT_PRESETS
            return {"presets": dict(TEXT_PRESETS)}
        if name == "vibeedit_text_preset_apply":
            proj = self._require()
            result = proj.set_text_style(
                args["item"], preset=args.get("preset"),
                size=args.get("size"), position_x=args.get("position_x"),
                position_y=args.get("position_y"))
            self._save()
            return result
        if name == "vibeedit_export_preset_list":
            proj = self._require()
            return {"presets": {
                "full": {"width": proj.width, "height": proj.height,
                         "ffmpeg_preset": "fast", "crf": "20"},
                "draft": {"width": proj.width // 2,
                          "height": proj.height // 2,
                          "ffmpeg_preset": "veryfast", "crf": "28"}}}
        if name == "vibeedit_timeline_duration":
            proj = self._require()
            return {"frames": proj.duration_frames(),
                    "seconds": round(proj.duration_seconds(), 3)}
        if name == "vibeedit_media_duration":
            from .export_ops import media_metadata
            proj = self._require()
            meta = media_metadata(proj.data, proj.folder, args["media"])
            return {"media": args["media"],
                    "duration": meta.get("duration"),
                    "probed": meta.get("probed", False),
                    "warning": meta.get("warning"),
                    "probe_error": meta.get("probe_error")}
        if name == "vibeedit_project_backup":
            import os
            import shutil
            if self.path is None:
                raise RuntimeError("No project file open to back up")
            backup = self.path + ".bak"
            shutil.copyfile(self.path, backup)
            return {"backup": backup}
        if name == "vibeedit_project_rename":
            proj = self._require()
            proj.data["name"] = args["name"]
            proj._bump()
            self._save()
            return {"name": proj.data["name"], "rev": proj.rev}
        if name == "vibeedit_clip_volume":
            proj = self._require()
            result = proj.set_volume(args["item"], float(args["volume"]))
            self._save()
            return result
        if name == "vibeedit_text_set":
            proj = self._require()
            result = proj.set_text(args["item"], args["text"])
            self._save()
            return result
        if name == "vibeedit_media_add":
            import os
            proj = self._require()
            path = args["path"]
            abs_path = (path if os.path.isabs(path)
                        else os.path.join(proj.folder, path))
            meta: dict = {}
            warning = None
            if os.path.isfile(abs_path):
                from .render import probe_media
                meta = probe_media(abs_path)
            else:
                warning = f"Media file not found on disk: {abs_path}"
            medium = proj.add_media(
                path, kind=args.get("kind") or
                ("video" if meta.get("width") else "audio"),
                **{k: v for k, v in meta.items() if k in
                   ("width", "height", "fps", "frames", "duration",
                    "hasAudio")})
            self._save()
            out = dict(medium)
            if warning:
                out["warning"] = warning
            return out
        if name == "vibeedit_clip_get":
            proj = self._require()
            track, item = proj.item(args["item"])
            return {"track": track["id"], "item": item}
        if name == "vibeedit_clip_duplicate":
            proj = self._require()
            result = proj.duplicate_item(args["item"], args["track"],
                                         int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_clip_keyframe_remove":
            proj = self._require()
            _, item = proj.item(args["item"])
            prop = args.get("property")
            # Keyframe entries store the property as a key
            # ({"at": 30, "scale": 2.0}), not as a "property" field.
            # Removing one property strips just that key; an entry
            # left with only "at" is dropped.
            if prop is None:
                kept = []
            else:
                kept = []
                for kf in item.get("keyframes", []):
                    rest = {k: v for k, v in kf.items() if k != prop}
                    if len(rest) > 1:
                        kept.append(rest)
            result = proj.set_keyframes(args["item"], kept)
            self._save()
            return result
        if name == "vibeedit_media_remove":
            proj = self._require()
            used = [i["id"] for t in proj.data["tracks"]
                    for i in t["items"] if i.get("media") == args["media"]]
            if used:
                raise ValueError(
                    f"Media {args['media']!r} is still used by items: "
                    f"{', '.join(used)}")
            before = len(proj.data["media"])
            proj.data["media"] = [m for m in proj.data["media"]
                                  if m["id"] != args["media"]]
            if len(proj.data["media"]) == before:
                raise KeyError(f"Media not found: {args['media']}")
            proj._bump()
            self._save()
            return {"removed": args["media"]}
        if name == "vibeedit_project_format_set":
            proj = self._require()
            fmt = proj.data.setdefault("format", {})
            if args.get("width") is not None:
                fmt["width"] = int(args["width"])
            if args.get("height") is not None:
                fmt["height"] = int(args["height"])
            if args.get("fps") is not None:
                fmt["fps"] = args["fps"]
            if int(fmt.get("width", 0)) <= 0 or int(fmt.get("height", 0)) <= 0:
                raise ValueError("Format width and height must be positive")
            proj._bump()
            self._save()
            return {"format": fmt}
        if name == "vibeedit_track_add":
            proj = self._require()
            kind = args.get("kind", "video")
            if kind not in ("video", "text", "audio"):
                raise ValueError(f"Unknown track kind: {kind!r}")
            used = {t["id"] for t in proj.data["tracks"]}
            n = 1
            while f"t{n}" in used:
                n += 1
            track = {"id": f"t{n}", "kind": kind,
                     "role": args.get("role", ""),
                     "name": args.get("name", kind), "items": []}
            proj.data["tracks"].append(track)
            proj._bump()
            self._save()
            return {"track": track}
        if name == "vibeedit_karaoke_remove":
            proj = self._require()
            _, item = proj.item(args["item"])
            if "karaoke" not in item:
                raise ValueError(f"Item {args['item']!r} has no karaoke data")
            del item["karaoke"]
            proj._bump()
            self._save()
            return {"removed": args["item"]}
        if name == "vibeedit_adjustment_get":
            proj = self._require()
            for layer in proj.list_adjustments():
                if layer["id"] == args["item"]:
                    return {"adjustment": layer}
            raise KeyError(f"Adjustment layer not found: {args['item']}")
        if name == "vibeedit_beat_count":
            proj = self._require()
            return {"beats": len(proj.beat_list()),
                    "source": proj.data.get("beatGrid", {}).get("source")}
        if name == "vibeedit_text_style_get":
            proj = self._require()
            _, item = proj.item(args["item"])
            return {"item": args["item"], "text": item.get("text"),
                    "textStyle": item.get("textStyle") or {}}
        if name == "vibeedit_export_preview":
            from .render import render
            import os
            proj = self._require()
            out = os.path.join(proj.folder, "render", "export-draft.mp4")
            report = render(proj.data, proj.folder, out, preset="draft")
            self.last_export = report
            return report
        if name == "vibeedit_project_rev":
            proj = self._require()
            return {"name": proj.data.get("name"), "rev": proj.rev,
                    "format": proj.data.get("format"),
                    "path": self.path}
        if name == "vibeedit_transition_preview":
            from .export_ops import transition_preview
            proj = self._require()
            return transition_preview(proj.data, proj.folder,
                                      args["transition"])
        if name == "vibeedit_review_get":
            proj = self._require()
            report = self.last_export or {}
            return {"validation": proj.validate(),
                    "stats": proj.project_stats(),
                    "last_export": report,
                    "skipped": report.get("skipped", []),
                    "warnings": report.get("warnings", [])}
        if name == "vibeedit_overlay_items":
            proj = self._require()
            media = {m["id"]: m for m in proj.data["media"]}
            out = []
            for track in proj.data["tracks"]:
                if track["kind"] != "video" or track.get("role") == "main":
                    continue
                for item in track["items"]:
                    medium = media.get(item.get("media"))
                    out.append({"track": track["id"], "item": item,
                                "media_kind": medium["kind"]
                                if medium else None})
            return {"overlay_items": out}
        if name == "vibeedit_clip_position_set":
            proj = self._require()
            result = {}
            if "x" in args:
                result["x"] = proj.add_keyframe(
                    args["item"], float(args["at"]), "x", float(args["x"]))
            if "y" in args:
                result["y"] = proj.add_keyframe(
                    args["item"], float(args["at"]), "y", float(args["y"]))
            self._save()
            return result
        if name == "vibeedit_clip_scale_set":
            proj = self._require()
            result = proj.add_keyframe(args["item"], float(args["at"]),
                                       "scale", float(args["scale"]))
            self._save()
            return result
        if name == "vibeedit_clip_opacity_set":
            proj = self._require()
            result = proj.add_keyframe(args["item"], float(args["at"]),
                                       "opacity", float(args["opacity"]))
            self._save()
            return result
        if name == "vibeedit_clip_fades_get":
            _, item = self._require().item(args["item"])
            return {"fadeIn": item.get("fadeIn", 0),
                    "fadeOut": item.get("fadeOut", 0)}
        if name == "vibeedit_clip_speed_get":
            _, item = self._require().item(args["item"])
            return {"speed": float(item.get("speed", 1.0))}
        if name == "vibeedit_marker_move":
            proj = self._require()
            result = proj.move_marker(args["marker"], int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_beat_grid_get":
            return {"beatGrid": self._require().data.get("beatGrid"),
                    "beats": self._require().beat_list()}
        if name == "vibeedit_ducking_toggle":
            proj = self._require()
            current = proj.ducking_get()
            result = proj.set_ducking(not bool(current.get("enabled")),
                                      amount_db=float(
                                          current.get("amountDb", 6.0)))
            self._save()
            return result
        if name == "vibeedit_clip_keyframes_clear":
            proj = self._require()
            result = proj.set_keyframes(args["item"], [])
            self._save()
            return result
        if name == "vibeedit_media_kind_list":
            kind = args.get("kind")
            media = self._require().data["media"]
            return {"media": [m for m in media
                              if kind is None or m.get("kind") == kind]}
        if name == "vibeedit_timeline_gaps":
            proj = self._require()
            gaps = []
            cursor = 0
            for track in proj.data["tracks"]:
                if track.get("role") != "main" or track["kind"] != "video":
                    continue
                for item in sorted(track["items"], key=lambda i: i["at"]):
                    if int(item["at"]) > cursor:
                        gaps.append({"start": cursor, "end": int(item["at"]),
                                     "frames": int(item["at"]) - cursor})
                    cursor = max(cursor,
                                 int(item["at"]) + int(item["dur"]))
            return {"gaps": gaps}
        if name == "vibeedit_project_duration_frames":
            proj = self._require()
            return {"frames": proj.duration_frames(),
                    "seconds": round(proj.duration_seconds(), 3)}
        if name == "vibeedit_clip_at_time":
            return {"clip": self._require().clip_at_time(int(args["frame"]))}
        # Code-gap batch tools (real implementations only).
        if name == "vibeedit_clip_color_eq":
            proj = self._require()
            result = proj.set_color(args["item"], eq=args.get("eq") or {})
            self._save()
            return result
        if name == "vibeedit_clip_color_eq_get":
            _, item = self._require().item(args["item"])
            return {"eq": (item.get("color") or {}).get("eq") or {}}
        if name == "vibeedit_source_insert":
            proj = self._require()
            in_frame = int(args.get("in", 0))
            out_frame = int(args["out"])
            if out_frame <= in_frame:
                raise ValueError("Source Out must be after Source In")
            track_id = args.get("track")
            if not track_id:
                medium = proj.media(args["media"])
                want_kind = medium.get("kind") or "video"
                if want_kind == "video":
                    track_id = next(
                        (t["id"] for t in proj.data["tracks"]
                         if t["kind"] == "video" and t.get("role") == "main"),
                        None)
                if not track_id:
                    track_id = next(
                        (t["id"] for t in proj.data["tracks"]
                         if t["kind"] == want_kind),
                        proj.data["tracks"][0]["id"])
            result = proj.add_clip(args["media"], track_id,
                                   int(args.get("at", 0)), in_frame,
                                   out_frame - in_frame,
                                   float(args.get("speed", 1.0)))
            self._save()
            return result
        if name == "vibeedit_close_gaps":
            proj = self._require()
            result = proj.close_gaps(args.get("track"))
            self._save()
            return result
        if name == "vibeedit_project_list":
            import os
            proj = self._require()
            root = os.path.dirname(os.path.abspath(proj.folder))
            out = []
            if os.path.isdir(root):
                for entry in sorted(os.listdir(root)):
                    folder = os.path.join(root, entry)
                    if not os.path.isdir(folder):
                        continue
                    found = find_project_file(folder)
                    if found:
                        out.append({"name": entry, "folder": folder,
                                    "current": os.path.abspath(folder)
                                    == os.path.abspath(proj.folder)})
            return {"projects": out, "root": root}
        if name == "vibeedit_track_rename":
            proj = self._require()
            result = proj.rename_track(args["track"], args["name"])
            self._save()
            return result
        if name == "vibeedit_track_remove":
            proj = self._require()
            result = proj.remove_track(args["track"])
            self._save()
            return result
        if name == "vibeedit_beat_nearest":
            return {"beat": self._require().nearest_beat(
                float(args["seconds"]))}
        if name == "vibeedit_marker_at_time":
            frame = int(args["frame"])
            markers = [m for m in self._require().data.get("markers", [])
                       if int(m.get("at", 0)) <= frame]
            markers.sort(key=lambda m: int(m.get("at", 0)))
            return {"markers": markers}
        if name == "vibeedit_clip_overlap_check":
            proj = self._require()
            track = proj.track(args["track"])
            at = int(args["at"])
            dur = int(args.get("dur", 0))
            overlap = []
            for item in track["items"]:
                if at < item["at"] + item["dur"] and \
                        at + dur > item["at"]:
                    overlap.append(item["id"])
            return {"overlap": overlap, "free": not overlap}
        if name == "vibeedit_media_usage":
            proj = self._require()
            media_id = args["media"]
            used = []
            for track in proj.data["tracks"]:
                for item in track["items"]:
                    if item.get("media") == media_id:
                        used.append({"track": track["id"],
                                     "id": item["id"], "at": item["at"],
                                     "dur": item["dur"]})
            return {"media": media_id, "clips": used}
        if name == "vibeedit_project_search_text":
            query = (args.get("query") or "").lower()
            found = []
            for track in self._require().data["tracks"]:
                for item in track["items"]:
                    if query and query in (item.get("text") or "").lower():
                        found.append({"track": track["id"],
                                      "id": item["id"],
                                      "text": item["text"]})
            return {"items": found}
        if name == "vibeedit_track_duration":
            proj = self._require()
            track = proj.track(args["track"])
            end = max((item["at"] + item["dur"] for item in track["items"]),
                      default=0)
            return {"track": track["id"], "end_frame": end,
                    "clips": len(track["items"])}
        if name == "vibeedit_clip_text_get":
            _, item = self._require().item(args["item"])
            return {"text": item.get("text")}
        if name == "vibeedit_clip_color_reset":
            proj = self._require()
            result = proj.set_color(args["item"], clear_eq=True,
                                    clear_lut=True)
            self._save()
            return result
        if name == "vibeedit_timeline_clip_count":
            proj = self._require()
            per_track = {t["id"]: len(t["items"])
                         for t in proj.data["tracks"]}
            return {"per_track": per_track,
                    "total": sum(per_track.values())}
        if name == "vibeedit_source_overwrite":
            proj = self._require()
            result = proj.overwrite_insert(
                args["media"], int(args.get("in", 0)), int(args["out"]),
                int(args.get("at", 0)), args.get("track"))
            self._save()
            return result
        raise ValueError(f"Unknown tool: {name}")


def handle(server: MCPServer, request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")
    try:
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "vibeedit-mcp", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params", {})
            result = server.call(params["name"], params.get("arguments", {}))
        else:
            raise ValueError(f"Unknown method: {method}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:  # noqa: BLE001 - surfaced to the MCP client
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32603, "message": str(exc)}}


def serve(folder: str | None = None) -> None:
    server = MCPServer(folder)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": None,
                 "error": {"code": -32700, "message": str(exc)}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(handle(server, request)) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    serve(sys.argv[1] if len(sys.argv) > 1 else None)
