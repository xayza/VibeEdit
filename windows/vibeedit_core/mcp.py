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
                      write_backup,
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

# Phase B1 tools (real wrappers + honest check-and-error tools).
TOOLS.extend([
    {"name": "vibeedit_timeline_split", "description": "Split a clip at a frame (the playhead when no item/frame is given)."},
    {"name": "vibeedit_timeline_move", "description": "Move a clip to another track and/or start frame."},
    {"name": "vibeedit_timeline_delete", "description": "Delete a timeline item by id."},
    {"name": "vibeedit_timeline_cut_range", "description": "Cut a frame range: split at its edges and delete the middle segments."},
    {"name": "vibeedit_timeline_close_gap", "description": "Singular alias of close_gaps: close gaps on a track."},
    {"name": "vibeedit_timeline_select_all", "description": "Select every timeline item in this server session."},
    {"name": "vibeedit_timeline_deselect", "description": "Clear the server session selection."},
    {"name": "vibeedit_timeline_snap", "description": "Snap a frame to the nearest detected beat."},
    {"name": "vibeedit_timeline_zoom_in", "description": "Increase the server session timeline zoom (px/s)."},
    {"name": "vibeedit_timeline_zoom_out", "description": "Decrease the server session timeline zoom (px/s)."},
    {"name": "vibeedit_timeline_zoom_fit", "description": "Fit the whole timeline into the session zoom (1200px viewport assumed, stated in the result)."},
    {"name": "vibeedit_timeline_move_items", "description": "Move several items with the existing per-item move op, rolling back on failure."},
    {"name": "vibeedit_timeline_changes", "description": "Undo/redo history state: backup and redo files, revision."},
    {"name": "vibeedit_timeline_refresh_waveforms", "description": "Recompute waveform peaks for project media with real files, cached in this session."},
    {"name": "vibeedit_timeline_sheet", "description": "Timeline as text (same readout as timeline_get)."},
    {"name": "vibeedit_timeline_lift", "description": "Lift an item: copy it to the server clipboard, then delete it."},
    {"name": "vibeedit_clip_cut", "description": "Cut a clip at a frame (alias of split)."},
    {"name": "vibeedit_clip_mute", "description": "Mute a clip by setting its volume to -60 dB and recording muted=true."},
    {"name": "vibeedit_clip_speed_up", "description": "Double a clip's current speed."},
    {"name": "vibeedit_clip_speed_down", "description": "Halve a clip's current speed."},
    {"name": "vibeedit_clip_speed_reset", "description": "Reset a clip's speed to 1.0."},
    {"name": "vibeedit_clip_slow_down", "description": "Alias of speed_down: halve a clip's current speed."},
    {"name": "vibeedit_clip_paste", "description": "Paste a copied item onto a track at a frame (duplicate_item)."},
    {"name": "vibeedit_clip_transition", "description": "Set a transition between two clips."},
    {"name": "vibeedit_clip_keyframe", "description": "Add one keyframe to a clip."},
    {"name": "vibeedit_source_mark_in", "description": "Mark the source In frame in this server session."},
    {"name": "vibeedit_source_mark_out", "description": "Mark the source Out frame in this server session."},
    {"name": "vibeedit_source_next_frame", "description": "Step the server session source frame forward by one."},
    {"name": "vibeedit_source_previous_frame", "description": "Step the server session source frame back by one."},
    {"name": "vibeedit_source_close", "description": "Clear the server session source marks/frame."},
    {"name": "vibeedit_source_show", "description": "Read the server session source marks and frame."},
    {"name": "vibeedit_playhead_next_frame", "description": "Step the server session playhead forward by one frame."},
    {"name": "vibeedit_playhead_previous_frame", "description": "Step the server session playhead back by one frame."},
    {"name": "vibeedit_playhead_forward_second", "description": "Step the server session playhead forward by one second."},
    {"name": "vibeedit_playhead_back_second", "description": "Step the server session playhead back by one second."},
    {"name": "vibeedit_layer_add_video", "description": "Add an empty video track."},
    {"name": "vibeedit_layer_add_audio", "description": "Add an empty audio track."},
    {"name": "vibeedit_layer_add_text", "description": "Add an empty text track."},
    {"name": "vibeedit_layer_add_adjustment", "description": "Add an adjustment layer for a time range."},
    {"name": "vibeedit_layer_delete", "description": "Delete an empty, non-Main track."},
    {"name": "vibeedit_layer_up", "description": "Move a track one position up in track order."},
    {"name": "vibeedit_layer_down", "description": "Move a track one position down in track order."},
    {"name": "vibeedit_layers_add", "description": "Add a new empty track of a kind (alias of track_add)."},
    {"name": "vibeedit_layers_set", "description": "Rename a track (alias of track_rename)."},
    {"name": "vibeedit_captions_export", "description": "Export a text track as SRT text (alias of srt_export)."},
    {"name": "vibeedit_captions_import", "description": "Import SRT text onto a text track (alias of srt_import)."},
    {"name": "vibeedit_captions_find", "description": "Find text items containing a query string."},
    {"name": "vibeedit_captions_replace", "description": "Replace text in matching text items and report the count changed."},
    {"name": "vibeedit_captions_style", "description": "Apply a text preset/size/position to a text item."},
    {"name": "vibeedit_captions_words", "description": "Split text items into words with evenly distributed frame ranges (computed, not stored)."},
    {"name": "vibeedit_captions_group", "description": "Group text items by track and report their combined span (computed grouping, not persisted)."},
    {"name": "vibeedit_text_line_style", "description": "Store a line style on a text item's textStyle."},
    {"name": "vibeedit_project_new", "description": "Create a project folder and open it (alias of project_create)."},
    {"name": "vibeedit_project_close", "description": "Close the open project in this server session."},
    {"name": "vibeedit_project_recents", "description": "Read the sibling .recent.json recents file when one exists."},
    {"name": "vibeedit_project_folder", "description": "Return the open project's folder and file path."},
    {"name": "vibeedit_project_history", "description": "Backup history: .bak file, backups/ folder and revision."},
    {"name": "vibeedit_project_data", "description": "Read the whole open project document (alias of project_get)."},
    {"name": "vibeedit_project_set_data", "description": "Set one allowlisted project field (name or contentLanguage)."},
    {"name": "vibeedit_project_credits", "description": "Project credits from real project data: name, schema, revision, format, counts (no author is stored)."},
    {"name": "vibeedit_project_derive", "description": "Copy the open project folder under a new name (alias of project_duplicate)."},
    {"name": "vibeedit_project_import_media", "description": "Import a media file: copy it into the project media folder when outside, then add the entry."},
    {"name": "vibeedit_project_clear_recents", "description": "Delete the sibling .recent.json recents file (app-owned state only, never project media)."},
    {"name": "vibeedit_project_show_recents", "description": "Read the sibling .recent.json recents file (errors when none exists)."},
    {"name": "vibeedit_export_otio", "description": "Export the timeline as OpenTimelineIO JSON (alias of otio_export)."},
    {"name": "vibeedit_export_chapters", "description": "Chapters computed from timeline markers (start seconds, marker text)."},
    {"name": "vibeedit_export_cover", "description": "Cover frame: first-frame thumbnail path for the first main-track clip."},
    {"name": "vibeedit_export_history", "description": "Export history: last export report plus batch results."},
    {"name": "vibeedit_export_link", "description": "Path of the last export output (errors when no export exists; never invented)."},
    {"name": "vibeedit_export_open_output", "description": "Path of the last export output (headless: returned, not opened; errors when none exists)."},
    {"name": "vibeedit_export_reveal_output", "description": "Path of the last export output (headless: returned, not revealed; errors when none exists)."},
    {"name": "vibeedit_export_cancel", "description": "Cancel the queued batch; a synchronous export already running cannot be interrupted."},
    {"name": "vibeedit_export_dismiss_notice", "description": "Dismiss the last-export notice held by this server."},
    {"name": "vibeedit_plugins_list", "description": "List discovered plugins with enable state (alias of plugin_list)."},
    {"name": "vibeedit_plugins_reload", "description": "Re-scan the plugins folder and list discovered plugins."},
    {"name": "vibeedit_plugins_validate", "description": "Validate discovered plugins: list them plus any load errors."},
    {"name": "vibeedit_plugins_hooks", "description": "Hooks exposed by each discovered plugin."},
    {"name": "vibeedit_plugins_bundles", "description": "Plugin bundles: plugins folder path and discovered plugin names."},
    {"name": "vibeedit_jobs_status", "description": "Batch/export job status held by this server."},
    {"name": "vibeedit_jobs_cancel", "description": "Cancel the queued batch jobs."},
    {"name": "vibeedit_jobs_wait", "description": "Wait result for batch jobs: the synchronous batch status (no background job exists)."},
    {"name": "vibeedit_capabilities_get", "description": "Provider capabilities map copied verbatim from the original CommandCatalog.capabilities, labelled as capability names."},
    {"name": "vibeedit_schema_get", "description": "Project schema name and legacy schema name from project.py, plus the open project's format."},
    {"name": "vibeedit_app_version", "description": "MCP server version (0.1.0, the serverInfo version in this file), Python version and project schema; no Windows app version constant exists in this build."},
    {"name": "vibeedit_storage_get", "description": "App-owned cache/state inventory: thumbs cache, backup, redo file, batch queue (never project media)."},
    {"name": "vibeedit_storage_clear", "description": "Clear app-owned cache only: render/thumbs PNGs and the in-session waveform cache (never project media)."},
    {"name": "vibeedit_fonts_list", "description": "Fonts the renderer can actually find on this machine, with the search candidates."},
    {"name": "vibeedit_luts_import", "description": "Validate a .cube file and copy it into the project's luts/ store."},
    {"name": "vibeedit_review_compare", "description": "Compare the last review run against a fresh validation/stats run (requires a prior review run)."},
    {"name": "vibeedit_review_coverage", "description": "Coverage from the last review run plus real project counts: media used vs stored, items, markers."},
    {"name": "vibeedit_review_layout", "description": "Layout from the last review run: format, tracks and item positions."},
    {"name": "vibeedit_review_measure", "description": "Measurements from the last review run: duration, counts, issue count."},
    {"name": "vibeedit_review_packet", "description": "Full review packet: the stored review run plus the last export summary."},
    {"name": "vibeedit_review_picture", "description": "Picture data for the last review run: main-track clips with media kinds."},
    {"name": "vibeedit_review_shots", "description": "Shots for the last review run: main-track clips as at/duration/media shots."},
    {"name": "vibeedit_review_sync", "description": "Sync data for the last review run: ducking config, beat grid and audio tracks."},
    {"name": "vibeedit_review_window", "description": "Review window: reviewed revision and the timeline start/end frames."},
    {"name": "vibeedit_media_frame", "description": "First-frame info for a media entry via the existing thumbnail code path."},
    {"name": "vibeedit_media_frames", "description": "First-frame info plus stored/probed media metadata for a media entry."},
    {"name": "vibeedit_media_import", "description": "Import a media file into the project (alias of project_import_media)."},
    {"name": "vibeedit_media_transcript", "description": "Transcript from the project's text items, or a clean error when the project has none."},
    {"name": "vibeedit_media_inventory", "description": "Media inventory: every entry with the number of clips using it."},
    {"name": "vibeedit_media_resolve_range", "description": "Resolve an in/out frame range for a media entry or clip into frames and seconds, validated against stored duration."},
    {"name": "vibeedit_beats_grid", "description": "Read the project's detected beat grid (alias of beat_grid_get)."},
    {"name": "vibeedit_audio_beats", "description": "Detected beat times in seconds (alias of beats_list)."},
    {"name": "vibeedit_audio_energy", "description": "Real audio energy for a media file: RMS and peak from FFmpeg-decoded mono samples."},
    {"name": "vibeedit_audio_loudness", "description": "Real FFmpeg loudnorm measurement for a media file (errors when FFmpeg or audio is missing)."},
    {"name": "vibeedit_audio_measure", "description": "Real audio measurement: probe duration plus RMS/peak energy for a media file."},
    {"name": "vibeedit_audio_mix_measure", "description": "Mix measurement: ducking config, audio-track items and their volumes."},
    {"name": "vibeedit_color_measure", "description": "Colour measurement: a clip's stored eq/preset filter state (FFmpeg signalstats extraction is attempted only when no eq state exists, and errors cleanly when it cannot be parsed)."},
    {"name": "vibeedit_doctor_run", "description": "Real environment check: Python, FFmpeg, FFprobe presence and versions, font, plugins folder, project path."},
    {"name": "vibeedit_edl_import", "description": "Parse a CMX3600-style EDL file into events (and optionally apply them when a reel-to-media map is given)."},
    {"name": "vibeedit_selects_list", "description": "List project selects stored in project data."},
    {"name": "vibeedit_selects_set", "description": "Store a select (media, in/out frames, name) in project data."},
    {"name": "vibeedit_selects_place", "description": "Place a stored select as a clip on a track."},
    {"name": "vibeedit_variants_list", "description": "List project variants stored as snapshots in project data."},
    {"name": "vibeedit_variants_create", "description": "Store a snapshot of the current project as a named variant."},
    {"name": "vibeedit_variants_diff", "description": "Diff a stored variant snapshot against the current project (revision, counts, item ids)."},
    {"name": "vibeedit_script_check", "description": "Check a script text against the project: which text items appear in it, and coverage."},
    {"name": "vibeedit_plan_check", "description": "Validate an edit plan (timeline ops) against project data without applying it."},
    {"name": "vibeedit_plan_apply", "description": "Apply an edit plan via the existing timeline_apply operation."},
    {"name": "vibeedit_workflow_gates", "description": "Read the real review gates stored in project data (errors when none have been set)."},
    {"name": "vibeedit_workflow_set_gates", "description": "Store review gates in project data."},
    {"name": "vibeedit_checkpoint_request", "description": "Request a checkpoint: write a project backup and report its path."},
    {"name": "vibeedit_checkpoint_status", "description": "Checkpoint status: backup file, its mtime, and the backups/ folder contents."},
    {"name": "vibeedit_run_status", "description": "Run status: batch queue/results plus the last export report."},
    {"name": "vibeedit_run_log", "description": "Run log: batch results and the last export report held by this server."},
    {"name": "vibeedit_run_show", "description": "Show the current run state: batch queue/results plus the last export."},
    {"name": "vibeedit_run_stop", "description": "Stop the run queue: clear the queued batch (synchronous exports cannot be interrupted mid-render)."},
    {"name": "vibeedit_batch_cancel", "description": "Cancel the queued batch (clears the server batch queue)."},
    {"name": "vibeedit_batch_presets", "description": "Batch export presets: the full/draft preset definitions."},
    {"name": "vibeedit_batch_retry", "description": "Retry the queued batch exports (errors when the queue is empty)."},
    {"name": "vibeedit_library_get", "description": "Read one library item by id."},
    {"name": "vibeedit_library_stats", "description": "Library statistics: item count and items per kind."},
    {"name": "vibeedit_library_preview", "description": "Preview data for one library item (its stored item copy)."},
    {"name": "vibeedit_library_favorite", "description": "Mark a library item as a favourite in project data."},
    {"name": "vibeedit_library_update", "description": "Rename a library item in project data."},
    {"name": "vibeedit_library_apply", "description": "Apply a library item: place it on the timeline (alias of library_place)."},
    {"name": "vibeedit_library_move", "description": "Move a library item to a new position in the library list."},
    {"name": "vibeedit_agent_open", "description": "Not available in this Windows build: no agent terminal is managed by this headless MCP server; use an external terminal running `python windows/vibeedit.py mcp <project-folder>`."},
    {"name": "vibeedit_agent_open_chat", "description": "Not available in this Windows build: no in-app chat UI exists in this headless server; the original also removed its model-API panel, so external agent via MCP is the parity path."},
    {"name": "vibeedit_agent_open_claude", "description": "Not available in this Windows build: no Claude terminal is managed here; run Claude in an external terminal against this MCP server."},
    {"name": "vibeedit_agent_open_codex", "description": "Not available in this Windows build: no Codex terminal is managed here; run Codex in an external terminal against this MCP server."},
    {"name": "vibeedit_agent_open_shell", "description": "Not available in this Windows build: no shell terminal is managed by this headless server; use an external terminal."},
    {"name": "vibeedit_agent_terminals", "description": "Not available in this Windows build: no terminal list exists in this headless server; terminals live outside it."},
    {"name": "vibeedit_agent_toggle_dock", "description": "Not available in this Windows build: no dock UI exists in this headless server; the web UI Agent dock is a separate browser view."},
    {"name": "vibeedit_agent_ask", "description": "Not available in this Windows build: in-app LLM chat is not present (parity-by-design: the original removed its model-API panel); use an external agent via MCP."},
    {"name": "vibeedit_agent_kit_check", "description": "Not available in this Windows build: no agent-kit/skills store module exists in vibeedit_core to check against."},
    {"name": "vibeedit_agent_kit_install", "description": "Not available in this Windows build: agent-kit install is tied to the skills store, which does not exist in vibeedit_core."},
    {"name": "vibeedit_agent_kit_update", "description": "Not available in this Windows build: agent-kit update is tied to the skills store, which does not exist in vibeedit_core."},
    {"name": "vibeedit_agent_kit_later", "description": "Not available in this Windows build: agent-kit update is tied to the skills store, which does not exist in vibeedit_core."},
    {"name": "vibeedit_agent_status", "description": "Not available in this Windows build: no agent terminal session is managed by this headless server."},
    {"name": "vibeedit_agent_setup", "description": "Not available in this Windows build: no agent terminal setup exists in this headless server."},
    {"name": "vibeedit_agent_setup_show", "description": "Not available in this Windows build: no agent setup view exists in this headless server."},
    {"name": "vibeedit_agent_restart_tab", "description": "Not available in this Windows build: no agent tab exists in this headless server."},
    {"name": "vibeedit_agent_quick_edit", "description": "Not available in this Windows build: no quick-edit UI exists in this headless server; edits go through timeline_apply."},
    {"name": "vibeedit_agent_show_changes", "description": "Not available in this Windows build: no agent-changes view exists in this headless server; use timeline/project reads and the backup file."},
    {"name": "vibeedit_agent_dismiss_changes", "description": "Not available in this Windows build: no agent-changes view exists in this headless server."},
    {"name": "vibeedit_agent_undo_changes", "description": "Not available in this Windows build: no agent-changes view exists in this headless server; use timeline_undo."},
    {"name": "vibeedit_agent_detach", "description": "Not available in this Windows build: no agent session is attached to this headless server."},
    {"name": "vibeedit_agent_tools_install", "description": "Not available in this Windows build: no agent tool installer exists in this build; MCP tools are served by this file."},
    {"name": "vibeedit_chat_send", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_command", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_commands", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_attach", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_detach", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_reset", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_status", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_chat_transcript", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_show_about", "description": "Not available in this Windows build: no About dialog exists in this headless server; use app_version for version data."},
    {"name": "vibeedit_show_commands", "description": "Not available in this Windows build: no commands dialog exists in this headless server; use mcp_tools_list."},
    {"name": "vibeedit_show_shortcuts", "description": "Not available in this Windows build: no shortcuts dialog exists in this headless server."},
    {"name": "vibeedit_show_settings", "description": "Not available in this Windows build: no settings dialog exists in this headless server."},
    {"name": "vibeedit_show_plugins", "description": "Not available in this Windows build: no plugins dialog exists in this headless server; use plugins_list."},
    {"name": "vibeedit_show_review", "description": "Not available in this Windows build: no review dialog exists in this headless server; use review_run/review_get for the data."},
    {"name": "vibeedit_show_history", "description": "Not available in this Windows build: no history dialog exists in this headless server; use project_history."},
    {"name": "vibeedit_show_sections", "description": "Not available in this Windows build: no sections dialog exists in this headless server."},
    {"name": "vibeedit_show_batch", "description": "Not available in this Windows build: no batch dialog exists in this headless server; use batch_status."},
    {"name": "vibeedit_show_export", "description": "Not available in this Windows build: no export dialog exists in this headless server; use export_status."},
    {"name": "vibeedit_show_export_progress", "description": "Not available in this Windows build: no export progress view exists in this headless server; exports here are synchronous."},
    {"name": "vibeedit_show_updates", "description": "Not available in this Windows build: no updates dialog exists in this headless server; no updater is configured in this build."},
    {"name": "vibeedit_show_assets", "description": "Not available in this Windows build: no assets dialog exists in this headless server; use media_list."},
    {"name": "vibeedit_show_agent_kit", "description": "Not available in this Windows build: no agent-kit view exists in this headless server; the skills store is another agent's job."},
    {"name": "vibeedit_show_doctor", "description": "Not available in this Windows build: no doctor dialog exists in this headless server; use doctor_run for the check data."},
    {"name": "vibeedit_ui_action", "description": "Not available in this Windows build: no live UI session exists for this headless server to act on."},
    {"name": "vibeedit_ui_dialog", "description": "Not available in this Windows build: no live UI session exists for this headless server to show a dialog in."},
    {"name": "vibeedit_ui_view", "description": "Not available in this Windows build: no live UI session exists for this headless server."},
    {"name": "vibeedit_ui_select", "description": "Not available in this Windows build: no live UI selection exists in this headless server; use timeline_select_all for the server selection."},
    {"name": "vibeedit_ui_seek", "description": "Not available in this Windows build: no live player exists in this headless server; use playhead_* tools for the session playhead."},
    {"name": "vibeedit_ui_frame", "description": "Not available in this Windows build: no live player frame exists in this headless server; use media_frame for a media first frame."},
    {"name": "vibeedit_ui_frames", "description": "Not available in this Windows build: no live player frames exist in this headless server."},
    {"name": "vibeedit_ui_respond", "description": "Not available in this Windows build: no live UI session exists for this headless server to respond in."},
    {"name": "vibeedit_ui_actions", "description": "Not available in this Windows build: no live UI session exists for this headless server."},
    {"name": "vibeedit_playback_toggle", "description": "Not available in this Windows build: no playback engine exists in this headless server."},
    {"name": "vibeedit_playback_stop", "description": "Not available in this Windows build: no playback engine exists in this headless server."},
    {"name": "vibeedit_playback_shuttle_forward", "description": "Not available in this Windows build: no playback engine exists in this headless server."},
    {"name": "vibeedit_playback_shuttle_back", "description": "Not available in this Windows build: no playback engine exists in this headless server."},
    {"name": "vibeedit_view_fullscreen", "description": "Not available in this Windows build: no window exists in this headless server."},
    {"name": "vibeedit_view_inspector_pane", "description": "Not available in this Windows build: no inspector pane exists in this headless server; the web UI inspector is a separate browser view."},
    {"name": "vibeedit_view_library_pane", "description": "Not available in this Windows build: no library pane exists in this headless server; use library_list for the data."},
    {"name": "vibeedit_app_update", "description": "Not available in this Windows build: the updater framework can check/download/verify a release and write an installer handoff script (app_update_check/app_update_download/app_update_prepare) but cannot replace the running app by itself; quit VibeEdit, then run the handoff script to install."},
    {"name": "vibeedit_app_update_prepare", "description": "Download a release asset, verify its SHA-256 when given, and write the Windows handoff script (vibeedit-update-run.bat) that waits for the app process to exit and then starts the installer; the script is never executed by the app itself."},
    {"name": "vibeedit_app_update_check", "description": "Report update status: current version and the fact that no updater channel is configured in this build."},
    {"name": "vibeedit_app_update_download", "description": "Download a release asset to a file and verify its SHA-256 when given (never executes it; install manually after quitting VibeEdit)."},
    {"name": "vibeedit_vision_cutout_model", "description": "Cut out the foreground with a user-supplied ONNX segmentation model file (clear error when the model file or ONNX Runtime is absent; never falls back silently to grabCut)."},
    {"name": "vibeedit_app_update_later", "description": "Defer an update: record that a version should be offered again only after remind_after (now + remind_in_days, default 7); stored in updater.json next to vibeedit_core, no channel needed."},
    {"name": "vibeedit_app_update_skip", "description": "Skip an update: record a version in updater.json so it is never offered again; stored next to vibeedit_core, no channel needed."},
    {"name": "vibeedit_voice_clone_add", "description": "Not available in this Windows build: voice cloning needs a cloning provider model and none is available here (generation via Edge/Piper is wired; cloning is not)."},
    {"name": "vibeedit_voice_clone_list", "description": "Not available in this Windows build: no saved voice clones exist because no cloning provider model is available here."},
    {"name": "vibeedit_voice_clone_remove", "description": "Not available in this Windows build: no saved voice clones exist because no cloning provider model is available here."},
    {"name": "vibeedit_voice_synthesize", "description": "Synthesize text to a WAV with Edge TTS or Piper and add it as project media (clear error when the chosen backend is absent)."},
    {"name": "vibeedit_voice_speak", "description": "Synthesize a voice take (alias of voice_synthesize; measurement against the script is a separate transcribe step)."},
    {"name": "vibeedit_voice_lines", "description": "Synthesize every line of a script, one take per line, with Edge TTS or Piper."},
    {"name": "vibeedit_voice_check", "description": "Check which voice backends are available on this machine (piper binary, edge-tts module) and count voiceover takes in the open project."},
    {"name": "vibeedit_voice_use", "description": "Choose the project voice (provider/voice/model stored in project data and used as the default for synthesis)."},
    {"name": "vibeedit_voice_fit", "description": "Change a voiceover item speed (pitch kept by the renderer) so it lasts the given frames, within optional min/max ratios."},
    {"name": "vibeedit_voice_place", "description": "Place a generated audio media item on the Voiceover track (creating the track when the project has none)."},
    {"name": "vibeedit_image_generate", "description": "Not available in this Windows build: no image-generation provider/model is wired in this build."},
    {"name": "vibeedit_image_generate_list", "description": "Not available in this Windows build: no image-generation provider/model is wired in this build."},
    {"name": "vibeedit_image_style", "description": "Not available in this Windows build: no image-generation provider/model is wired in this build."},
    {"name": "vibeedit_image_disclose", "description": "Not available in this Windows build: no image-generation provider/model is wired in this build."},
    {"name": "vibeedit_image_cutout", "description": "Cut out the foreground of an image with OpenCV grabCut (raises a clear error naming the missing backend when OpenCV is absent)."},
    {"name": "vibeedit_library_search", "description": "Search the project's saved library items by name, text or media id (local project data only; no provider)."},
    {"name": "vibeedit_library_generate", "description": "Not available in this Windows build: no library generation provider is wired in this build."},
    {"name": "vibeedit_library_brand_pose", "description": "Not available in this Windows build: no brand-pose engine is wired in this build."},
    {"name": "vibeedit_library_export_pack", "description": "Not available in this Windows build: no library pack exporter is wired in this build."},
    {"name": "vibeedit_library_import_pack", "description": "Not available in this Windows build: no library pack importer is wired in this build."},
    {"name": "vibeedit_library_analyze", "description": "Not available in this Windows build: no library analyzer is wired in this build."},
    {"name": "vibeedit_media_ocr", "description": "Recognise text in a project media entry or image file with Tesseract (alias of vision_text; clear error when Tesseract is absent)."},
    {"name": "vibeedit_media_subjects", "description": "Detect faces in a project media entry or image file with OpenCV Haar cascades (alias of vision_faces; clear error when OpenCV is absent)."},
    {"name": "vibeedit_media_describe", "description": "Not available in this Windows build: no vision/provider description is wired in this build."},
    {"name": "vibeedit_media_description", "description": "Not available in this Windows build: no vision/provider description is wired in this build."},
    {"name": "vibeedit_media_digest", "description": "Not available in this Windows build: no media analysis provider is wired in this build."},
    {"name": "vibeedit_media_cuts", "description": "Not available in this Windows build: no cut-detection provider is wired in this build."},
    {"name": "vibeedit_media_sync", "description": "Not available in this Windows build: no audio-sync provider is wired in this build."},
    {"name": "vibeedit_media_speech_map", "description": "Not available in this Windows build: no speech-mapping provider is wired in this build."},
    {"name": "vibeedit_media_strip", "description": "Not available in this Windows build: no media-strip provider is wired in this build."},
    {"name": "vibeedit_media_proxy", "description": "Generate a low-resolution proxy file for a project video entry with FFmpeg (H.264, scaled to the given width, default 540px; the proxy is a derived file, not a new timeline media entry)."},
    {"name": "vibeedit_media_analysis", "description": "Media analysis for a project media entry: stored metadata enriched with a live ffprobe probe (streams, duration, resolution) when the file exists."},
    {"name": "vibeedit_media_analyze", "description": "Media analysis for a project media entry: stored metadata enriched with a live ffprobe probe (streams, duration, resolution) when the file exists."},
    {"name": "vibeedit_knowledge_add_lesson", "description": "Add a caller-supplied lesson to the project knowledge store (starts proposed)."},
    {"name": "vibeedit_knowledge_approve", "description": "Approve a lesson or proposal (args: lesson= or proposal=)."},
    {"name": "vibeedit_knowledge_claims", "description": "List claims in the project knowledge store."},
    {"name": "vibeedit_knowledge_facts", "description": "List facts in the project knowledge store."},
    {"name": "vibeedit_knowledge_get", "description": "Get one lesson from the project knowledge store."},
    {"name": "vibeedit_knowledge_history", "description": "List knowledge mutation history (no snapshots exposed)."},
    {"name": "vibeedit_knowledge_lessons", "description": "List lessons in the project knowledge store."},
    {"name": "vibeedit_knowledge_memo", "description": "Get the knowledge memo, or set it when text= is given."},
    {"name": "vibeedit_knowledge_migrate", "description": "Migrate legacy knowledge_notes into the memo (no-op reported honestly otherwise)."},
    {"name": "vibeedit_knowledge_prefs", "description": "List prefs in the project knowledge store."},
    {"name": "vibeedit_knowledge_proposals", "description": "List knowledge proposals."},
    {"name": "vibeedit_knowledge_reject", "description": "Reject a lesson or proposal (args: lesson= or proposal=)."},
    {"name": "vibeedit_knowledge_remove_lesson", "description": "Remove a lesson from the project knowledge store."},
    {"name": "vibeedit_knowledge_revert", "description": "Revert the knowledge store by N recorded mutations."},
    {"name": "vibeedit_knowledge_set_claim", "description": "Set a claim in the project knowledge store."},
    {"name": "vibeedit_knowledge_set_fact", "description": "Set a fact in the project knowledge store."},
    {"name": "vibeedit_knowledge_set_pref", "description": "Set a pref in the project knowledge store."},
    {"name": "vibeedit_knowledge_skill", "description": "Get a skill from the local skills store (knowledge.skill maps to the skills store)."},
    {"name": "vibeedit_knowledge_split_memo", "description": "Split the knowledge memo at blank lines into proposed lessons."},
    {"name": "vibeedit_knowledge_update_lesson", "description": "Update a lesson's text in the project knowledge store."},
    {"name": "vibeedit_knowledge_verdicts", "description": "List proposal outcomes (approved/rejected)."},
    {"name": "vibeedit_skills_disable", "description": "Disable a skill by id (state in skills.json next to the skills folder)."},
    {"name": "vibeedit_skills_enable", "description": "Enable a skill by id (state in skills.json next to the skills folder)."},
    {"name": "vibeedit_skills_export", "description": "Export a skill verbatim (content, or copy to dest=)."},
    {"name": "vibeedit_skills_get", "description": "Get one skill's full markdown from the local skills store."},
    {"name": "vibeedit_skills_list", "description": "List skills in the local skills store (windows/skills/)."},
    {"name": "vibeedit_skills_propose", "description": "Store a caller-supplied skill draft as a pending proposal (not an active skill)."},
    {"name": "vibeedit_skills_remove", "description": "Delete a skill file (requires confirm=true)."},
    {"name": "vibeedit_skills_save", "description": "Write a caller-supplied skill file (user-written provenance header; refuses overwrite unless overwrite=true)."},
    {"name": "vibeedit_plugins_install", "description": "Install a plugin from a local folder or .zip bundle (manifest validated before copying; URL sources must be downloaded first with plugins_download)."},
    {"name": "vibeedit_plugins_updates", "description": "Check a plugin for update metadata (no network; unknown unless the installed manifest carries update metadata)."},
    {"name": "vibeedit_plugins_search", "description": "Search locally discovered plugins by name, description or hook (local plugins folder only; no registry)."},
    {"name": "vibeedit_plugins_setup", "description": "Not available in this Windows build: plugin setup is not supported in this build."},
    {"name": "vibeedit_plugins_set", "description": "Not available in this Windows build: plugin setting is not supported in this build; use plugin_enable/plugin_disable for enable state."},
    {"name": "vibeedit_plugins_set_overlays", "description": "Not available in this Windows build: plugin overlays are not supported in this build."},
    {"name": "vibeedit_plugins_overlays", "description": "Not available in this Windows build: plugin overlays are not supported in this build."},
    {"name": "vibeedit_plugins_view", "description": "Not available in this Windows build: no plugin view host exists in this headless server."},
    {"name": "vibeedit_plugins_view_event", "description": "Not available in this Windows build: no plugin view host exists in this headless server."},
    {"name": "vibeedit_plugins_proposal", "description": "Not available in this Windows build: no plugin proposal workflow exists in this build."},
    {"name": "vibeedit_plugins_replace", "description": "Not available in this Windows build: plugin replacement is not supported in this build."},
    {"name": "vibeedit_plugins_remove", "description": "Remove an installed plugin folder (refuses while the plugin is enabled; disable first)."},
    {"name": "vibeedit_plugins_run", "description": "Run one declared hook of an enabled plugin on a timeline item via apply_plugin (only declared hooks of enabled plugins run; disabled plugins are refused)."},
    {"name": "vibeedit_plugins_invoke", "description": "Run one declared hook of an enabled plugin on a timeline item via apply_plugin (only declared hooks of enabled plugins run; disabled plugins are refused)."},
    {"name": "vibeedit_plugins_actions", "description": "Not available in this Windows build: no plugin action host exists in this headless server."},
    {"name": "vibeedit_plugins_option", "description": "Not available in this Windows build: no plugin option host exists in this headless server."},
    {"name": "vibeedit_plugins_options", "description": "Not available in this Windows build: no plugin option host exists in this headless server."},
    {"name": "vibeedit_plugins_show_view", "description": "Not available in this Windows build: no plugin view host exists in this headless server."},
    {"name": "vibeedit_clip_motion", "description": "Not available in this Windows build: motion editing is another agent's job; no motion state exists on clips in this build."},
    {"name": "vibeedit_clip_backdrop", "description": "Not available in this Windows build: backdrop editing is another agent's job; no backdrop state exists on clips in this build."},
    {"name": "vibeedit_clip_change_framing", "description": "Not available in this Windows build: reframing is another agent's job; no framing state exists on clips in this build."},
    {"name": "vibeedit_clip_reframe", "description": "Set (or clear with null) a media clip's reframe window; rendered as a crop before scaling, never stretched."},
    {"name": "vibeedit_clip_send_to_agent", "description": "Not available in this Windows build: no agent session exists in this headless server to send a clip to."},
    {"name": "vibeedit_clip_unlink_audio", "description": "Unlink a clip's linked audio: clear linked_audio on the video item and linked_video on each audio partner (errors when the item has no linked audio)."},
    {"name": "vibeedit_music_replace", "description": "Not available in this Windows build: no music-replacement workflow exists in this build; replace music clips with timeline move/delete/add ops."},
    {"name": "vibeedit_narration_windows", "description": "Not available in this Windows build: no narration-window workflow exists in this build."},
    {"name": "vibeedit_outcomes_import", "description": "Not available in this Windows build: no outcomes store exists in this build."},
    {"name": "vibeedit_outcomes_map", "description": "Not available in this Windows build: no outcomes store exists in this build."},
    {"name": "vibeedit_run_append", "description": "Not available in this Windows build: no workflow runner exists in this build to append a run to."},
    {"name": "vibeedit_run_checklist", "description": "Not available in this Windows build: no workflow runner exists in this build; use review_run for the review checklist data."},
    {"name": "vibeedit_run_dismiss", "description": "Not available in this Windows build: no workflow runner exists in this build."},
    {"name": "vibeedit_run_fix_issues", "description": "Not available in this Windows build: no workflow runner exists in this build; fix issues with timeline ops, then review_verify."},
    {"name": "vibeedit_run_follow", "description": "Not available in this Windows build: no workflow runner exists in this build."},
    {"name": "vibeedit_run_toggle", "description": "Not available in this Windows build: no workflow runner exists in this build."},
    {"name": "vibeedit_run_another_recipe", "description": "Not available in this Windows build: no workflow runner exists in this build."},
    {"name": "vibeedit_acme_voice_fast", "description": "Not available in this Windows build: no voice provider is wired in this build."},
    {"name": "vibeedit_speech_rate", "description": "Not available in this Windows build: no voice provider is wired in this build, so no speech rate can be set."},
    {"name": "vibeedit_app_vibeedit", "description": "Not available in this Windows build: no app-level automation client exists in this headless server."},
    {"name": "vibeedit_app_vibeedit_automation_clients", "description": "Not available in this Windows build: no app-level automation clients exist in this headless server."},
    {"name": "vibeedit_app_vibeedit_debug_log", "description": "Not available in this Windows build: no app debug log is kept by this headless server."},
    {"name": "vibeedit_platforms_get", "description": "Not available in this Windows build: no platform-client registry exists in this headless server."},
    {"name": "vibeedit_context_get", "description": "Not available in this Windows build: no live editor context exists in this headless server; use project_get, timeline_get and the playhead_* tools."},
    {"name": "vibeedit_source_toggle_playback", "description": "Not available in this Windows build: no playback engine exists in this headless server."},
    {"name": "vibeedit_timeline_header_compact", "description": "Not available in this Windows build: no timeline header UI exists in this headless server."},
    {"name": "vibeedit_vision_cutout", "description": "Cut out the foreground of an image with OpenCV grabCut (raises a clear error naming the missing backend when OpenCV is absent)."},
    {"name": "vibeedit_vision_faces", "description": "Detect faces in an image with OpenCV Haar cascades (raises a clear error naming the missing backend when OpenCV is absent)."},
    {"name": "vibeedit_vision_text", "description": "Recognise text in an image with Tesseract (raises a clear error naming the missing backend when Tesseract is absent)."},
    {"name": "vibeedit_clip_link_audio", "description": "Link a Dialogue audio clip to a video clip so linked edits move together."},
    {"name": "vibeedit_project_magnetic_get", "description": "Report whether magnetic Main editing is on for this project."},
    {"name": "vibeedit_project_magnetic_set", "description": "Turn magnetic Main editing on or off (stored in project data)."},
    {"name": "vibeedit_transitions_renderability", "description": "List every known transition kind with an honest renders true/false flag."},
    {"name": "vibeedit_skills_search", "description": "Search the local skills store by substring over titles and bodies."},
    {"name": "vibeedit_plugins_download", "description": "Download a plugin .zip bundle to a temp file (gated step before plugins_install; never installs or executes anything)."},
    {"name": "vibeedit_captions_transcribe", "description": "Transcribe a project media item with faster-whisper into a text track (clear error when faster-whisper is absent)."},
    {"name": "vibeedit_captions_generate", "description": "Transcribe a media item and return the generated SRT text."},
    {"name": "vibeedit_captions_align", "description": "Re-time a text track's items to faster-whisper speech segments (clear error when faster-whisper is absent)."},
    {"name": "vibeedit_media_transcribe", "description": "Transcribe a project media item with faster-whisper into a text track (alias of captions_transcribe)."},
    {"name": "vibeedit_fonts_import", "description": "Import a .ttf/.otf font file into the app fonts folder (unique stored name, never overwrites)."},
    {"name": "vibeedit_timeline_reorder", "description": "Magnetic reorder: move a Main clip before another Main clip (or to the end), shifting intervening clips with their linked audio."},
    {"name": "vibeedit_chat_stop", "description": "Not available in this Windows build: no in-app chat session exists to stop (the original also removed its model-API panel; agents run in an external terminal via MCP)."},
    {"name": "vibeedit_view_compare", "description": "Not available as an MCP tool: Compare is a web-UI view (the UI Compare split view already exists); the headless MCP server has no viewer to toggle."},
    {"name": "vibeedit_view_safe_area", "description": "Not available as an MCP tool: Safe-area is a web-UI overlay toggle (the UI toggle already exists); the headless MCP server has no viewer to toggle."},
    # Round 3: the last four original spec names with no exact
    # normalized match in this registry. Each is a real alias of an
    # existing real tool (the original itself shares handlers this
    # way — e.g. voice.speak and voice.lines both map to the
    # voice.synthesize handler): beats.detect -> beat_detect,
    # clip.speed-curve -> speed_curve_apply, transcript.words ->
    # captions_words, library.save-selection -> library_add (save
    # the selected clip/text item into the library). With these,
    # all 249 original spec names have a normalized match here.
    {"name": "vibeedit_beats_detect", "description": "Detect beats in a project media item (alias of beat_detect)."},
    {"name": "vibeedit_clip_speed_curve", "description": "Apply a speed-curve preset to a clip (alias of speed_curve_apply)."},
    {"name": "vibeedit_transcript_words", "description": "Split text items into words (alias of captions_words)."},
    {"name": "vibeedit_library_save_selection", "description": "Save the selected clip/text item into the library (alias of library_add)."},
])


class MCPServer:
    def __init__(self, folder: str | None = None):
        self.folder = folder
        self.project: Project | None = None
        self.path: str | None = None
        self.last_export: dict | None = None
        self.batch_queue: list[str] = []
        self.batch_results: list[dict] = []
        # Phase B1 session state: the headless server has no live
        # player/UI, so playhead, selection, source marks and zoom
        # are held here (reset on open) instead of being invented
        # as project fields.
        self.playhead_frame = 0
        self.selection: list[str] = []
        self.source_marks: dict = {}
        self.source_frame = 0
        self.zoom_px_per_s = 50.0
        self.clipboard: dict | None = None
        self.waveform_cache: dict = {}
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
        self._needs_first_backup = True
        self.playhead_frame = 0
        self.selection = []
        self.source_marks = {}
        self.source_frame = 0
        return {"path": found, "name": data.get("name"), "rev": data.get("rev")}

    def _require(self) -> Project:
        if self.project is None:
            raise RuntimeError("No project open; call vibeedit_project_open first")
        return self.project

    def _save(self) -> None:
        assert self.project is not None and self.path is not None
        # Phase 0 backup rule, same as the web server: autosave
        # creates no backup; only the first save after opening does.
        if getattr(self, "_needs_first_backup", False):
            try:
                write_backup(self.path)
            except Exception:
                pass
            self._needs_first_backup = False
        save_project(self.project.data, self.path)

    # -- Phase B1 helpers -------------------------------------------
    def _na(self, tool: str, blocker: str) -> ValueError:
        return ValueError(
            f"NOT_AVAILABLE: {tool} is not available in this Windows "
            f"build: {blocker}")

    def _review(self) -> dict:
        proj = self._require()
        review = proj.data.get("review")
        if not review:
            raise ValueError(
                "No review run yet; call vibeedit_review_run first "
                "and never invent a verdict")
        return review

    def _export_output(self) -> str:
        if not self.last_export or not self.last_export.get("output"):
            raise ValueError(
                "No export exists yet; run an export tool first "
                "(no output path is invented)")
        return self.last_export["output"]

    def _backup_path(self) -> str | None:
        """Real backup location from project.py: <folder>/project.json.bak."""
        import os
        from .project import BACKUP_BASENAME
        proj = self._require()
        return os.path.join(proj.folder, BACKUP_BASENAME)

    def _media_abs(self, proj, medium: dict) -> str:
        import os
        path = medium["path"]
        return path if os.path.isabs(path) else os.path.join(
            proj.folder, path)
        import os
        path = medium["path"]
        return path if os.path.isabs(path) else os.path.join(
            proj.folder, path)

    def _fps_value(self, proj) -> float:
        from .project import fps_value
        return fps_value(proj.fps)

    def _main_clip_media(self, proj):
        for track in proj.data["tracks"]:
            if track.get("role") == "main" and track["kind"] == "video":
                for item in sorted(track["items"],
                                   key=lambda i: i["at"]):
                    if item.get("media"):
                        return proj.media(item["media"]), item
        return None, None

    def _recents_path(self) -> str:
        import os
        proj = self._require()
        return os.path.join(os.path.dirname(
            os.path.abspath(proj.folder)), ".recent.json")

    def _import_media(self, proj, path: str, kind: str | None = None):
        """Copy an outside file into media/ (unique name, never
        overwriting) and add the entry; an inside file is added
        as-is. Returns the entry."""
        import os
        import shutil
        from .project import unique_media_name
        from .render import probe_media
        abs_path = path if os.path.isabs(path) else os.path.join(
            proj.folder, path)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"Media file not found: {abs_path}")
        media_dir = os.path.join(proj.folder, "media")
        os.makedirs(media_dir, exist_ok=True)
        if os.path.abspath(abs_path).startswith(
                os.path.abspath(proj.folder) + os.sep):
            stored = os.path.relpath(abs_path, proj.folder)
        else:
            stored_name = unique_media_name(
                media_dir, os.path.basename(abs_path))
            shutil.copyfile(abs_path, os.path.join(media_dir,
                                                   stored_name))
            stored = os.path.join("media", stored_name)
        meta = probe_media(abs_path)
        return proj.add_media(
            stored, kind=kind or
            ("video" if meta.get("width") else "audio"),
            **{k: v for k, v in meta.items() if k in
               ("width", "height", "fps", "frames", "duration",
                "hasAudio")})

    def _raise_honest(self, name: str) -> None:
        """Honest check-and-error tools: perform the real check the
        tool can perform, then raise a structured NOT_AVAILABLE
        error. Never returns a fake success."""
        import importlib.util
        if name.startswith("vibeedit_knowledge_"):
            found = importlib.util.find_spec("vibeedit_core.knowledge")
            raise self._na(name, "knowledge store module missing "
                           f"(vibeedit_core.knowledge found: {found is not None}); "
                           "the knowledge store is another agent's job; "
                           "no lesson/fact content is invented")
        if name.startswith("vibeedit_skills_"):
            found = importlib.util.find_spec("vibeedit_core.skills")
            raise self._na(name, "skills store module missing "
                           f"(vibeedit_core.skills found: {found is not None}); "
                           "the skills store is another agent's job")
        if name.startswith("vibeedit_plugins_"):
            from .plugins import list_plugins
            available = [p["name"] for p in list_plugins()
                         if p["name"] != "_errors"]
            raise self._na(name, "plugin setup/view/overlay/proposal/"
                           "replacement workflows are not supported in "
                           "this build; the local plugin system holds: "
                           f"{available or 'none'}. "
                           "Plugin install, search and hook execution "
                           "are real (plugins_install/plugins_search/"
                           "plugins_run); no untrusted code is copied "
                           "or executed outside those paths")
        if name.startswith("vibeedit_voice_") or name in (
                "vibeedit_acme_voice_fast", "vibeedit_speech_rate"):
            found = importlib.util.find_spec("vibeedit_core.voice")
            raise self._na(name, "no voice cloning provider is "
                           "wired in this build (generation via Edge/Piper "
                           "is wired separately); nothing is cloned")
        if name.startswith("vibeedit_agent_kit"):
            raise self._na(name, "agent-kit install/update is a "
                           "separate original workflow with no "
                           "equivalent in this build; the skills store "
                           "(vibeedit_core.skills) exists separately "
                           "and is covered by the real skills_* tools")
        # Every other honest tool: its description (in TOOLS) already
        # states the exact blocker; the raised error repeats it.
        desc = next((t["description"] for t in TOOLS
                     if t["name"] == name), name)
        raise ValueError(f"NOT_AVAILABLE: {desc}")

    # MCP tools that delete items/tracks/media or rewrite positions
    # or format: back up the saved file before the tool runs.
    DESTRUCTIVE_TOOLS = frozenset({
        "vibeedit_clip_delete", "vibeedit_transition_remove",
        "vibeedit_markers_remove", "vibeedit_adjustment_remove",
        "vibeedit_track_remove", "vibeedit_media_remove",
        "vibeedit_clip_keyframe_remove", "vibeedit_karaoke_remove",
        "vibeedit_library_remove", "vibeedit_source_overwrite",
        "vibeedit_close_gaps", "vibeedit_project_format_set",
        "vibeedit_timeline_delete", "vibeedit_timeline_cut_range",
        "vibeedit_timeline_lift", "vibeedit_timeline_move_items",
        "vibeedit_layer_delete", "vibeedit_captions_replace"})

    # Round 3 aliases: original spec names that map to an existing
    # real handler (see the TOOLS entries above). Applied before
    # dispatch so the orphan-scan test and every caller see the
    # alias behave exactly like its canonical tool.
    ALIASES = {
        "vibeedit_beats_detect": "vibeedit_beat_detect",
        "vibeedit_clip_speed_curve": "vibeedit_speed_curve_apply",
        "vibeedit_transcript_words": "vibeedit_captions_words",
        "vibeedit_library_save_selection": "vibeedit_library_add",
        "vibeedit_voice_speak": "vibeedit_voice_synthesize",
        # Round 5 aliases: original dotted names for vision tools
        # that already exist under their vision_* names.
        "vibeedit_media_ocr": "vibeedit_vision_text",
        "vibeedit_media_subjects": "vibeedit_vision_faces",
    }

    def call(self, name: str, args: dict) -> dict:
        name = self.ALIASES.get(name, name)
        if name in self.DESTRUCTIVE_TOOLS and self.path:
            try:
                write_backup(self.path)
            except Exception:
                pass
            self._needs_first_backup = False
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
        if name == "vibeedit_library_search":
            proj = self._require()
            query = str(args.get("query", "") or "").strip().lower()
            items = proj.library_list()
            if query:
                def _matches(entry):
                    inner = entry.get("item", {}) or {}
                    hay = " ".join(str(v) for v in (
                        entry.get("id", ""), entry.get("name", ""),
                        inner.get("id", ""), inner.get("text", ""),
                        inner.get("media", ""))).lower()
                    return query in hay
                items = [e for e in items if _matches(e)]
            return {"query": args.get("query", ""), "items": items,
                    "count": len(items)}
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
        if name in ("vibeedit_media_analysis", "vibeedit_media_analyze"):
            # Round 5: ffprobe-based analysis is the analysis the
            # build can actually do — same data as media_metadata.
            from .export_ops import media_metadata
            if not args.get("media"):
                raise ValueError("media_analysis needs media")
            proj = self._require()
            return media_metadata(proj.data, proj.folder, args["media"])
        if name == "vibeedit_media_proxy":
            from .render import generate_proxy
            if not args.get("media"):
                raise ValueError("media_proxy needs media")
            proj = self._require()
            medium = proj.media(args["media"])
            src = self._media_abs(proj, medium)
            import os as _os
            out = args.get("out") or _os.path.join(
                proj.folder, "render", medium["id"] + "_proxy.mp4")
            return generate_proxy(src, out, args.get("width", 540))
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
        # Phase B1 real wrappers: timeline / clip / source / playhead.
        if name == "vibeedit_timeline_split":
            proj = self._require()
            item_id = args.get("item")
            if item_id is None:
                clip = proj.clip_at_time(self.playhead_frame)
                if clip is None:
                    raise ValueError("No clip at the playhead to split")
                item_id = clip["id"]
            frame = int(args["atFrame"]) if args.get("atFrame") is not None else self.playhead_frame
            result = proj.split(item_id, frame)
            self._save()
            return result
        if name == "vibeedit_timeline_move":
            proj = self._require()
            result = proj.move(args["item"], args["track"], int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_timeline_delete":
            proj = self._require()
            proj.delete(args["item"])
            self._save()
            return {"deleted": args["item"]}
        if name == "vibeedit_timeline_cut_range":
            proj = self._require()
            start, end = int(args["start"]), int(args["end"])
            if end <= start:
                raise ValueError("cut_range end must be after start")
            snap = proj.snapshot()
            try:
                deleted = []
                for track in list(proj.data["tracks"]):
                    for item in sorted(list(track["items"]),
                                       key=lambda i: i["at"]):
                        istart, iend = int(item["at"]), int(item["at"]) + int(item["dur"])
                        if iend <= start or istart >= end:
                            continue
                        if istart < start:
                            proj.split(item["id"], start)
                        # Re-find the segment now covering the range.
                        for cand in list(track["items"]):
                            cstart, cend = int(cand["at"]), int(cand["at"]) + int(cand["dur"])
                            if cstart < end and cend > start and cstart >= start:
                                if cend > end:
                                    proj.split(cand["id"], end)
                                proj.delete(cand["id"])
                                deleted.append(cand["id"])
                                break
                self._save()
                return {"deleted": deleted, "start": start, "end": end}
            except Exception:
                proj.restore(snap)
                raise
        if name == "vibeedit_timeline_close_gap":
            proj = self._require()
            result = proj.close_gaps(args.get("track"))
            self._save()
            return result
        if name == "vibeedit_timeline_select_all":
            proj = self._require()
            self.selection = [i["id"] for t in proj.data["tracks"]
                              for i in t["items"]]
            return {"selection": self.selection}
        if name == "vibeedit_timeline_deselect":
            self.selection = []
            return {"selection": []}
        if name == "vibeedit_timeline_snap":
            proj = self._require()
            return {"frame": int(args["frame"]),
                    "snapped": proj.snap_frame(int(args["frame"]))}
        if name == "vibeedit_timeline_zoom_in":
            self.zoom_px_per_s = min(1000.0, self.zoom_px_per_s * 1.25)
            return {"zoom_px_per_s": self.zoom_px_per_s}
        if name == "vibeedit_timeline_zoom_out":
            self.zoom_px_per_s = max(1.0, self.zoom_px_per_s / 1.25)
            return {"zoom_px_per_s": self.zoom_px_per_s}
        if name == "vibeedit_timeline_zoom_fit":
            proj = self._require()
            dur = proj.duration_seconds()
            if dur <= 0:
                raise ValueError("Timeline is empty; nothing to fit")
            self.zoom_px_per_s = 1200.0 / dur
            return {"zoom_px_per_s": self.zoom_px_per_s,
                    "viewport_px_assumed": 1200,
                    "duration_seconds": round(dur, 3),
                    "note": "Fit is viewport-dependent in the UI; this "
                            "headless value assumes a 1200px strip"}
        if name == "vibeedit_timeline_move_items":
            proj = self._require()
            snap = proj.snapshot()
            try:
                moved = []
                for mv in args["items"]:
                    moved.append(proj.move(mv["item"], mv["track"],
                                           int(mv["at"])))
                self._save()
                return {"moved": moved}
            except Exception:
                proj.restore(snap)
                raise
        if name == "vibeedit_timeline_changes":
            import os
            bak = self._backup_path()
            undo_file = self.path + ".bak" if self.path else None
            redo = self.path + ".redo" if self.path else None
            return {"rev": self._require().rev,
                    "can_undo": bool(undo_file and os.path.isfile(undo_file)),
                    "undo_file": undo_file if undo_file and os.path.isfile(undo_file) else None,
                    "can_redo": bool(redo and os.path.isfile(redo)),
                    "backup": bak if bak and os.path.isfile(bak) else None,
                    "redo_file": redo if redo and os.path.isfile(redo) else None}
        if name == "vibeedit_timeline_refresh_waveforms":
            from .waveform import waveform_peaks
            proj = self._require()
            out, errors = {}, {}
            for medium in proj.data["media"]:
                path = self._media_abs(proj, medium)
                try:
                    peaks = waveform_peaks(path, int(args.get("buckets", 64)))
                    self.waveform_cache[medium["id"]] = peaks
                    out[medium["id"]] = len(peaks)
                except Exception as exc:  # noqa: BLE001 - per-media report
                    errors[medium["id"]] = str(exc)
            return {"waveforms": out, "errors": errors}
        if name == "vibeedit_timeline_sheet":
            return {"timeline": self._require().timeline_text()}
        if name == "vibeedit_timeline_lift":
            proj = self._require()
            _, item = proj.item(args["item"])
            import copy as _copy
            self.clipboard = _copy.deepcopy(item)
            proj.delete(args["item"])
            self._save()
            return {"lifted": args["item"], "clipboard": True}
        if name == "vibeedit_clip_cut":
            proj = self._require()
            result = proj.split(args["item"], int(args["atFrame"]))
            self._save()
            return result
        if name == "vibeedit_clip_mute":
            proj = self._require()
            _, item = proj.item(args["item"])
            result = proj.set_volume(args["item"], -60.0)
            item["muted"] = True
            self._save()
            return result
        if name == "vibeedit_clip_speed_up":
            proj = self._require()
            _, item = proj.item(args["item"])
            result = proj.set_speed(args["item"],
                                    float(item.get("speed", 1.0)) * 2.0)
            self._save()
            return result
        if name == "vibeedit_clip_speed_down" or name == "vibeedit_clip_slow_down":
            proj = self._require()
            _, item = proj.item(args["item"])
            result = proj.set_speed(args["item"],
                                    float(item.get("speed", 1.0)) * 0.5)
            self._save()
            return result
        if name == "vibeedit_clip_speed_reset":
            proj = self._require()
            result = proj.set_speed(args["item"], 1.0)
            self._save()
            return result
        if name == "vibeedit_clip_paste":
            proj = self._require()
            src_id = args.get("item")
            if src_id is None:
                if self.clipboard is None:
                    raise ValueError("Nothing on the clipboard to paste; "
                                     "pass an item id or lift/copy first")
                result = proj.copy_item_data(self.clipboard, args["track"],
                                             int(args["at"]))
            else:
                result = proj.duplicate_item(src_id, args["track"],
                                             int(args["at"]))
            self._save()
            return result
        if name == "vibeedit_clip_transition":
            proj = self._require()
            result = proj.add_transition(args["from"], args["to"],
                                         args["kind"],
                                         float(args["duration"]))
            self._save()
            return result
        if name == "vibeedit_clip_keyframe":
            proj = self._require()
            result = proj.add_keyframe(args["item"], float(args["at"]),
                                       args["property"],
                                       float(args["value"]))
            self._save()
            return result
        if name == "vibeedit_source_mark_in":
            self.source_marks["in"] = int(args["frame"])
            if args.get("media"):
                self.source_marks["media"] = args["media"]
            return {"source_marks": self.source_marks}
        if name == "vibeedit_source_mark_out":
            self.source_marks["out"] = int(args["frame"])
            if args.get("media"):
                self.source_marks["media"] = args["media"]
            return {"source_marks": self.source_marks}
        if name == "vibeedit_source_next_frame":
            self.source_frame += 1
            return {"source_frame": self.source_frame}
        if name == "vibeedit_source_previous_frame":
            self.source_frame = max(0, self.source_frame - 1)
            return {"source_frame": self.source_frame}
        if name == "vibeedit_source_close":
            self.source_marks, self.source_frame = {}, 0
            return {"source_marks": {}, "source_frame": 0}
        if name == "vibeedit_source_show":
            return {"source_marks": self.source_marks,
                    "source_frame": self.source_frame}
        if name == "vibeedit_playhead_next_frame":
            self.playhead_frame += 1
            return {"frame": self.playhead_frame}
        if name == "vibeedit_playhead_previous_frame":
            self.playhead_frame = max(0, self.playhead_frame - 1)
            return {"frame": self.playhead_frame}
        if name == "vibeedit_playhead_forward_second":
            proj = self._require()
            self.playhead_frame += int(round(self._fps_value(proj)))
            return {"frame": self.playhead_frame}
        if name == "vibeedit_playhead_back_second":
            proj = self._require()
            self.playhead_frame = max(
                0, self.playhead_frame - int(round(self._fps_value(proj))))
            return {"frame": self.playhead_frame}
        if name == "vibeedit_layer_add_video":
            proj = self._require()
            track = proj.add_track("video", args.get("role", ""),
                                   args.get("name", "video"))
            self._save()
            return {"track": track}
        if name == "vibeedit_layer_add_audio":
            proj = self._require()
            track = proj.add_track("audio", args.get("role", ""),
                                   args.get("name", "audio"))
            self._save()
            return {"track": track}
        if name == "vibeedit_layer_add_text":
            proj = self._require()
            track = proj.add_track("text", args.get("role", ""),
                                   args.get("name", "text"))
            self._save()
            return {"track": track}
        if name == "vibeedit_layer_add_adjustment":
            proj = self._require()
            result = proj.add_adjustment(int(args.get("at", 0)),
                                         int(args.get("dur", 0)) or max(
                                             proj.duration_frames(), 1),
                                         args.get("preset"), args.get("lut"),
                                         args.get("strength"))
            self._save()
            return result
        if name == "vibeedit_layer_delete":
            proj = self._require()
            result = proj.remove_track(args["track"])
            self._save()
            return result
        if name in ("vibeedit_layer_up", "vibeedit_layer_down"):
            proj = self._require()
            tracks = proj.data["tracks"]
            idx = next(i for i, t in enumerate(tracks)
                       if t["id"] == args["track"])
            j = idx - 1 if name.endswith("_up") else idx + 1
            if j < 0 or j >= len(tracks):
                raise ValueError("Track is already at the edge")
            tracks[idx], tracks[j] = tracks[j], tracks[idx]
            proj._bump()
            self._save()
            return {"track": args["track"], "order": [t["id"] for t in tracks]}
        if name == "vibeedit_layers_add":
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
        if name == "vibeedit_layers_set":
            proj = self._require()
            result = proj.rename_track(args["track"], args["name"])
            self._save()
            return result
        if name == "vibeedit_captions_export":
            proj = self._require()
            return {"srt": proj.export_srt(args.get("track", "t1"))}
        if name == "vibeedit_captions_import":
            proj = self._require()
            result = proj.import_srt(args.get("track", "t1"), args["srt"])
            self._save()
            return {"imported": len(result)}
        if name == "vibeedit_captions_find":
            query = (args.get("query") or "").lower()
            found = []
            for track in self._require().data["tracks"]:
                for item in track["items"]:
                    if query and query in (item.get("text") or "").lower():
                        found.append({"track": track["id"],
                                      "id": item["id"],
                                      "text": item["text"]})
            return {"items": found}
        if name == "vibeedit_captions_replace":
            proj = self._require()
            query, repl = args["query"], args["replacement"]
            changed = []
            for track in proj.data["tracks"]:
                for item in track["items"]:
                    if "text" in item and query in item["text"]:
                        item["text"] = item["text"].replace(query, repl)
                        changed.append(item["id"])
            if changed:
                proj._bump()
                self._save()
            return {"changed": changed}
        if name == "vibeedit_captions_style":
            proj = self._require()
            result = proj.set_text_style(
                args["item"], preset=args.get("preset"),
                size=args.get("size"), position_x=args.get("position_x"),
                position_y=args.get("position_y"))
            self._save()
            return result
        if name == "vibeedit_captions_words":
            proj = self._require()
            words = []
            for track in proj.data["tracks"]:
                for item in track["items"]:
                    if "text" not in item:
                        continue
                    parts = item["text"].split()
                    if not parts:
                        continue
                    per = item["dur"] / len(parts)
                    for i, word in enumerate(parts):
                        words.append({"item": item["id"],
                                      "word": word,
                                      "at": int(item["at"] + i * per),
                                      "dur": per})
            return {"words": words}
        if name == "vibeedit_captions_group":
            proj = self._require()
            groups = {}
            for track in proj.data["tracks"]:
                texts = [i for i in track["items"] if "text" in i]
                if texts:
                    groups[track["id"]] = {
                        "ids": [i["id"] for i in texts],
                        "text": " ".join(i["text"] for i in texts),
                        "start": min(i["at"] for i in texts),
                        "end": max(i["at"] + i["dur"] for i in texts)}
            return {"groups": groups,
                    "note": "Computed grouping; not persisted to the project"}
        if name == "vibeedit_text_line_style":
            proj = self._require()
            _, item = proj.item(args["item"])
            if "text" not in item:
                raise ValueError("Item has no text field")
            style = item.setdefault("textStyle", {})
            style["lineStyle"] = args["line_style"]
            proj._bump()
            self._save()
            return {"item": args["item"], "textStyle": style}
        # Phase B1 real wrappers: project / export / plugins / jobs.
        if name == "vibeedit_project_new":
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
        if name == "vibeedit_project_close":
            closed = self.path
            self.project, self.path = None, None
            self.playhead_frame, self.selection = 0, []
            return {"closed": closed}
        if name in ("vibeedit_project_recents", "vibeedit_project_show_recents"):
            import json as _json
            import os
            recents_path = self._recents_path()
            if not os.path.isfile(recents_path):
                if name == "vibeedit_project_show_recents":
                    raise ValueError(
                        f"No recents file exists: {recents_path}")
                return {"recent": [], "path": recents_path}
            with open(recents_path, encoding="utf-8") as fh:
                return {"recent": _json.load(fh), "path": recents_path}
        if name == "vibeedit_project_clear_recents":
            import os
            recents_path = self._recents_path()
            if not os.path.isfile(recents_path):
                raise ValueError(
                    f"No recents file to clear: {recents_path}")
            os.remove(recents_path)
            return {"cleared": recents_path}
        if name == "vibeedit_project_folder":
            proj = self._require()
            return {"folder": proj.folder, "path": self.path}
        if name == "vibeedit_project_history":
            import os
            proj = self._require()
            bak = self._backup_path()
            backups_dir = os.path.join(proj.folder, "backups")
            backups = sorted(os.listdir(backups_dir)) if os.path.isdir(
                backups_dir) else []
            return {"rev": proj.rev,
                    "backup": bak if bak and os.path.isfile(bak) else None,
                    "backups": backups}
        if name == "vibeedit_project_data":
            return {"project": self._require().data}
        if name == "vibeedit_project_set_data":
            proj = self._require()
            key, value = args["key"], args["value"]
            if key not in ("name", "contentLanguage"):
                raise ValueError(
                    "set_data only allows 'name' and 'contentLanguage'; "
                    "use the typed tools for everything else")
            proj.data[key] = value
            proj._bump()
            self._save()
            return {"key": key, "value": value, "rev": proj.rev}
        if name == "vibeedit_project_credits":
            proj = self._require()
            return {"name": proj.data.get("name"),
                    "schema": proj.data.get("schema"),
                    "rev": proj.rev, "format": proj.data.get("format"),
                    "media": len(proj.data["media"]),
                    "tracks": len(proj.data["tracks"]),
                    "note": "No author credits are stored in this "
                            "project format; nothing is invented here"}
        if name == "vibeedit_project_derive":
            from .export_ops import duplicate_project
            import os
            proj = self._require()
            dest = os.path.join(
                os.path.dirname(os.path.abspath(proj.folder)),
                args["name"])
            return {"path": duplicate_project(proj.folder, dest,
                                              args["name"])}
        if name in ("vibeedit_project_import_media", "vibeedit_media_import"):
            proj = self._require()
            result = self._import_media(proj, args["path"],
                                        args.get("kind"))
            self._save()
            return result
        if name == "vibeedit_export_otio":
            from .export_ops import export_otio
            import os
            proj = self._require()
            out = args.get("out") or os.path.join(
                proj.folder, "render", "timeline.otio")
            return export_otio(proj.data, proj.folder, out)
        if name == "vibeedit_export_chapters":
            proj = self._require()
            fps = self._fps_value(proj)
            chapters = [{"start_seconds": round(m["at"] / fps, 3),
                         "text": m.get("text", "")}
                        for m in proj.data.get("markers", [])]
            return {"chapters": chapters}
        if name == "vibeedit_export_cover":
            from .thumbnail import generate_thumbnail, thumbnail_path
            proj = self._require()
            medium, _item = self._main_clip_media(proj)
            if medium is None:
                raise ValueError("No main-track clip to take a cover from")
            src = self._media_abs(proj, medium)
            cover = generate_thumbnail(
                src, thumbnail_path(proj.folder, medium["id"]),
                medium.get("kind", "video"))
            return {"cover": cover, "media": medium["id"]}
        if name == "vibeedit_export_history":
            return {"last_export": self.last_export,
                    "batch_results": self.batch_results}
        if name in ("vibeedit_export_link", "vibeedit_export_open_output",
                    "vibeedit_export_reveal_output"):
            out = self._export_output()
            return {"output": out, "exists": __import__("os").path.isfile(out),
                    "note": "Headless server: path returned, not opened"}
        if name == "vibeedit_export_cancel":
            self.batch_queue = []
            return {"cancelled": True,
                    "note": "Queued batch cleared; a synchronous export "
                            "already running cannot be interrupted"}
        if name == "vibeedit_export_dismiss_notice":
            self.last_export = None
            return {"dismissed": True}
        if name in ("vibeedit_plugins_list", "vibeedit_plugins_reload"):
            from .plugins import list_plugins
            return {"plugins": list_plugins()}
        if name == "vibeedit_plugins_search":
            from .plugins import list_plugins
            query = str(args.get("query", "") or "").strip().lower()
            plugins = [p for p in list_plugins(args.get("plugins_dir"))
                       if p["name"] != "_errors"]
            if query:
                plugins = [p for p in plugins
                           if query in p["name"].lower()
                           or query in p.get("description", "").lower()
                           or any(query in h.lower()
                                  for h in p.get("hooks", []))]
            return {"query": args.get("query", ""), "plugins": plugins,
                    "count": len(plugins)}
        if name in ("vibeedit_plugins_run", "vibeedit_plugins_invoke"):
            # Round 5: run one DECLARED hook of an ENABLED plugin
            # via the round-4 apply_plugin path (disabled plugins
            # are refused there; undeclared hooks are refused
            # there). This is not arbitrary code execution beyond
            # that documented path.
            from .plugins import apply_plugin
            plugin = args.get("plugin") or args.get("plugin_id")
            hook = args.get("hook")
            item = args.get("item") or args.get("item_id")
            if not plugin or not hook or not item:
                raise ValueError(
                    "plugins_run needs plugin, hook and item")
            proj = self._require()
            result = apply_plugin(proj, plugin, hook, item,
                                  plugins_dir=args.get("plugins_dir"))
            self._save()
            return {"plugin": plugin, "hook": hook, "item": result}
        if name == "vibeedit_plugins_validate":
            from .plugins import load_plugins, load_plugin_state
            plugins = load_plugins()
            errors = plugins.pop("_errors", {})
            disabled = set(load_plugin_state().get("disabled", []))
            return {"plugins": sorted(k for k in plugins),
                    "disabled": sorted(disabled), "errors": errors,
                    "valid": not errors}
        if name == "vibeedit_plugins_hooks":
            from .plugins import list_plugins
            return {"plugins": [
                {"name": p["name"], "hooks": p["hooks"]}
                for p in list_plugins() if p["name"] != "_errors"]}
        if name == "vibeedit_plugins_bundles":
            from .plugins import PLUGINS_DIR, list_plugins
            return {"plugins_dir": PLUGINS_DIR,
                    "plugins": [p["name"] for p in list_plugins()
                                if p["name"] != "_errors"]}
        if name in ("vibeedit_jobs_status", "vibeedit_run_status"):
            return {"queued": self.batch_queue,
                    "results": self.batch_results,
                    "last_export": self.last_export}
        if name in ("vibeedit_jobs_cancel", "vibeedit_run_stop"):
            self.batch_queue = []
            return {"cancelled": True}
        if name == "vibeedit_jobs_wait":
            return {"queued": self.batch_queue,
                    "results": self.batch_results,
                    "note": "Exports in this build are synchronous, so "
                            "there is no background job to wait on"}
        if name == "vibeedit_capabilities_get":
            # Verbatim from the original CommandCatalog.capabilities
            # (CommandCatalog.swift): command -> capability name.
            return {"capabilities": {
                "captions.generate": "captions.transcribe",
                "media.transcribe": "captions.transcribe",
                "voice.check": "captions.transcribe",
                "captions.align": "captions.transcribe",
                "beats.detect": "audio.beats",
                "voice.speak": "voice.synthesize",
                "voice.lines": "voice.synthesize",
                "image.generate": "image.generate",
                "audio.measure": "audio.loudness",
                "audio.mix-measure": "audio.loudness",
                "media.sync": "audio.sync",
                "audio.energy": "audio.energy",
                "library.search": "library.search",
                "library.generate": "library.generate",
                "media.subjects": "vision.faces",
                "media.ocr": "vision.text",
                "image.cutout": "vision.cutout"},
                    "source": "original CommandCatalog.capabilities",
                    "note": "Values are capability names, not providers; "
                            "a capability with no provider in this build "
                            "still reports its name, not a fake provider"}
        if name == "vibeedit_schema_get":
            from .project import SCHEMA, LEGACY_SCHEMA
            proj = self._require()
            return {"schema": SCHEMA, "legacy_schema": LEGACY_SCHEMA,
                    "project_schema": proj.data.get("schema"),
                    "format": proj.data.get("format")}
        if name == "vibeedit_app_version":
            import sys
            from .project import SCHEMA
            return {"name": "vibeedit-mcp", "version": "0.1.0",
                    "python": sys.version.split()[0],
                    "schema": SCHEMA,
                    "note": "This is the MCP server version from "
                            "handle(); no Windows app version constant "
                            "exists in this build"}
        if name == "vibeedit_storage_get":
            import os
            proj = self._require()
            thumbs_dir = os.path.join(proj.folder, "render", "thumbs")
            thumbs = os.listdir(thumbs_dir) if os.path.isdir(
                thumbs_dir) else []
            bak = self._backup_path()
            return {"thumbs_dir": thumbs_dir, "thumbs": thumbs,
                    "backup": bak if bak and os.path.isfile(bak) else None,
                    "batch_queued": len(self.batch_queue),
                    "waveform_cached": list(self.waveform_cache)}
        if name == "vibeedit_storage_clear":
            import glob
            import os
            proj = self._require()
            thumbs_dir = os.path.join(proj.folder, "render", "thumbs")
            removed = 0
            if os.path.isdir(thumbs_dir):
                for path in glob.glob(os.path.join(thumbs_dir, "*.png")):
                    os.remove(path)
                    removed += 1
            self.waveform_cache.clear()
            return {"thumbs_removed": removed,
                    "note": "Only render/thumbs cache and the in-session "
                            "waveform cache were cleared; project media "
                            "and project files were not touched"}
        if name == "vibeedit_fonts_list":
            from .render import font_candidates, find_font
            import os
            found = [p for p in font_candidates() if os.path.isfile(p)]
            return {"fonts": found, "default": find_font(),
                    "candidates": font_candidates()}
        if name == "vibeedit_luts_import":
            import os
            import shutil
            from .project import validate_cube
            proj = self._require()
            src = args["path"]
            size = validate_cube(src)
            store = os.path.join(proj.folder, "luts")
            os.makedirs(store, exist_ok=True)
            dest = os.path.join(store, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dest):
                shutil.copyfile(src, dest)
            return {"lut": dest, "size": size, "store": store}
        # Phase B1 real wrappers: review / media / audio / colour /
        # doctor / selects / variants / plans / checkpoints / runs.
        if name == "vibeedit_review_compare":
            proj = self._require()
            old = self._review()
            fresh_validation = proj.validate()
            fresh_issues = list(fresh_validation.get("errors", []))
            return {"previous_issue_count": old.get("issue_count"),
                    "current_issue_count": len(fresh_issues),
                    "changed": len(fresh_issues) != old.get("issue_count"),
                    "current_issues": fresh_issues,
                    "previous_stats": old.get("stats"),
                    "current_stats": proj.project_stats()}
        if name == "vibeedit_review_coverage":
            proj = self._require()
            review = self._review()
            used = {i.get("media") for t in proj.data["tracks"]
                    for i in t["items"] if i.get("media")}
            return {"review": review,
                    "media_total": len(proj.data["media"]),
                    "media_used": len(used),
                    "items": review.get("stats", {}).get("items"),
                    "markers": review.get("stats", {}).get("markers")}
        if name == "vibeedit_review_layout":
            proj = self._require()
            self._review()
            return {"format": proj.data.get("format"),
                    "tracks": [{"id": t["id"], "kind": t["kind"],
                                "role": t.get("role"),
                                "items": [{"id": i["id"], "at": i["at"],
                                         "dur": i["dur"]}
                                        for i in t["items"]]}
                               for t in proj.data["tracks"]]}
        if name == "vibeedit_review_measure":
            proj = self._require()
            review = self._review()
            return {"review": review,
                    "duration_frames": proj.duration_frames(),
                    "duration_seconds": round(proj.duration_seconds(), 3),
                    "stats": proj.project_stats()}
        if name == "vibeedit_review_packet":
            review = self._review()
            return {"review": review, "last_export": self.last_export}
        if name == "vibeedit_review_picture":
            proj = self._require()
            self._review()
            media = {m["id"]: m for m in proj.data["media"]}
            clips = []
            for track in proj.data["tracks"]:
                if track.get("role") != "main":
                    continue
                for item in track["items"]:
                    medium = media.get(item.get("media"))
                    clips.append({"id": item["id"], "at": item["at"],
                                  "dur": item["dur"],
                                  "media_kind": medium["kind"]
                                  if medium else None})
            return {"main_clips": clips}
        if name == "vibeedit_review_shots":
            proj = self._require()
            self._review()
            shots = []
            for track in proj.data["tracks"]:
                if track.get("role") != "main":
                    continue
                for item in sorted(track["items"], key=lambda i: i["at"]):
                    shots.append({"id": item["id"], "at": item["at"],
                                  "dur": item["dur"],
                                  "media": item.get("media")})
            return {"shots": shots}
        if name == "vibeedit_review_sync":
            proj = self._require()
            self._review()
            return {"ducking": proj.ducking_get(),
                    "beatGrid": proj.data.get("beatGrid"),
                    "audio_tracks": [{"id": t["id"], "items": len(t["items"])}
                                     for t in proj.data["tracks"]
                                     if t["kind"] == "audio"]}
        if name == "vibeedit_review_window":
            proj = self._require()
            review = self._review()
            return {"reviewed_rev": review.get("rev"),
                    "current_rev": proj.rev,
                    "start_frame": 0,
                    "end_frame": proj.duration_frames()}
        if name in ("vibeedit_media_frame", "vibeedit_media_frames"):
            from .thumbnail import generate_thumbnail, thumbnail_path
            proj = self._require()
            medium = proj.media(args["media"])
            src = self._media_abs(proj, medium)
            thumb = generate_thumbnail(
                src, thumbnail_path(proj.folder, medium["id"]),
                medium.get("kind", "video"))
            out = {"media": medium["id"], "thumbnail": thumb,
                   "kind": medium.get("kind")}
            if name == "vibeedit_media_frames":
                from .export_ops import media_metadata
                out["metadata"] = media_metadata(proj.data, proj.folder,
                                                 args["media"])
                out["note"] = "Only the first frame is available via "
                "the thumbnail path; no frame sequence extractor "
                "exists in this build"
            return out
        if name == "vibeedit_media_transcript":
            proj = self._require()
            texts = []
            for track in proj.data["tracks"]:
                for item in sorted(track["items"], key=lambda i: i["at"]):
                    if "text" in item:
                        texts.append({"track": track["id"],
                                      "id": item["id"], "at": item["at"],
                                      "dur": item["dur"],
                                      "text": item["text"]})
            if not texts:
                raise ValueError(
                    "Project has no text items, so it has no stored "
                    "transcript; transcribe first (transcribe op) or "
                    "import captions")
            return {"transcript": texts,
                    "text": " ".join(t["text"] for t in texts)}
        if name == "vibeedit_media_inventory":
            proj = self._require()
            inv = []
            for medium in proj.data["media"]:
                used = sum(1 for t in proj.data["tracks"]
                           for i in t["items"]
                           if i.get("media") == medium["id"])
                inv.append({**medium, "clips_using": used})
            return {"inventory": inv}
        if name == "vibeedit_media_resolve_range":
            proj = self._require()
            fps = self._fps_value(proj)
            if args.get("item"):
                _, item = proj.item(args["item"])
                in_f, dur = int(item.get("in", 0)), int(item["dur"])
            else:
                medium = proj.media(args["media"])
                in_f = int(args.get("in", 0))
                dur = int(args["dur"]) if args.get("dur") is not None else 0
                if not dur and medium.get("duration"):
                    dur = int(round(float(medium["duration"]) * fps))
                if not dur and medium.get("frames"):
                    dur = int(medium["frames"])
            if dur <= 0:
                raise ValueError("Range duration must be positive and "
                                 "resolvable from the media or item")
            return {"in_frame": in_f, "duration_frames": dur,
                    "start_seconds": round(in_f / fps, 3),
                    "duration_seconds": round(dur / fps, 3)}
        if name == "vibeedit_beats_grid":
            return {"beatGrid": self._require().data.get("beatGrid"),
                    "beats": self._require().beat_list()}
        if name == "vibeedit_audio_beats":
            return {"beats": self._require().beat_list()}
        if name in ("vibeedit_audio_energy", "vibeedit_audio_measure"):
            import math
            from .beats import decode_mono
            proj = self._require()
            medium = proj.media(args["media"])
            samples = decode_mono(self._media_abs(proj, medium))
            if not samples:
                raise ValueError("Media has no decodable audio samples")
            rms = math.sqrt(sum(v * v for v in samples) / len(samples))
            out = {"media": medium["id"], "rms": round(rms, 4),
                   "peak": round(max(abs(v) for v in samples), 4),
                   "samples": len(samples)}
            if name == "vibeedit_audio_measure":
                from .export_ops import media_metadata
                out["metadata"] = media_metadata(proj.data, proj.folder,
                                                 args["media"])
            return out
        if name == "vibeedit_audio_loudness":
            import json as _json
            import subprocess
            from .render import find_tool
            proj = self._require()
            medium = proj.media(args["media"])
            if not medium.get("hasAudio"):
                # Stored flag may be absent for older entries; probe
                # instead of trusting it, and let FFmpeg decide.
                pass
            ffmpeg = find_tool("ffmpeg")
            cmd = [ffmpeg, "-v", "info", "-i",
                   self._media_abs(proj, medium), "-af",
                   "loudnorm=print_format=json", "-f", "null", "-"]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace",
                                  timeout=120)
            text = proc.stderr
            start = text.rfind("{")
            end = text.rfind("}")
            if start < 0 or end < 0:
                raise RuntimeError(
                    "FFmpeg loudnorm measurement produced no JSON; "
                    "the file may have no audio stream")
            return {"media": medium["id"],
                    "loudnorm": _json.loads(text[start:end + 1])}
        if name == "vibeedit_audio_mix_measure":
            proj = self._require()
            audio = []
            for track in proj.data["tracks"]:
                if track["kind"] != "audio":
                    continue
                audio.append({"track": track["id"],
                              "items": [{"id": i["id"],
                                        "volume": i.get("volume")}
                                       for i in track["items"]]})
            return {"ducking": proj.ducking_get(), "audio": audio}
        if name == "vibeedit_color_measure":
            proj = self._require()
            _, item = proj.item(args["item"])
            color = item.get("color") or {}
            if color.get("eq") or color.get("preset"):
                from .project import eq_preset_filter
                filt = None
                if color.get("preset"):
                    filt = eq_preset_filter(
                        color["preset"],
                        float(color.get("preset_strength", 1.0)))
                return {"item": args["item"], "eq": color.get("eq") or {},
                        "preset": color.get("preset"),
                        "eq_filter": filt}
            raise ValueError(
                "Clip has no stored eq/preset colour state and "
                "FFmpeg signalstats extraction is not wired in this "
                "build; set eq colour first (clip_color_eq)")
        if name == "vibeedit_doctor_run":
            from .render import find_font, find_tool
            import os
            import sys
            checks: dict = {"python": sys.version.split()[0]}
            for tool in ("ffmpeg", "ffprobe"):
                try:
                    checks[tool] = find_tool(tool)
                    import subprocess
                    ver = subprocess.run(
                        [checks[tool], "-version"], capture_output=True,
                        text=True, encoding="utf-8", errors="replace",
                        timeout=30).stdout.splitlines()
                    checks[tool + "_version"] = ver[0] if ver else None
                except Exception as exc:  # noqa: BLE001 - doctor report
                    checks[tool] = None
                    checks[tool + "_error"] = str(exc)
            try:
                checks["font"] = find_font()
            except Exception as exc:  # noqa: BLE001 - doctor report
                checks["font"] = None
                checks["font_error"] = str(exc)
            from .plugins import PLUGINS_DIR
            checks["plugins_dir"] = PLUGINS_DIR
            checks["plugins_dir_exists"] = os.path.isdir(PLUGINS_DIR)
            checks["project_path"] = self.path
            checks["ok"] = bool(checks.get("ffmpeg")
                                and checks.get("ffprobe"))
            return checks
        if name == "vibeedit_edl_import":
            import re as _re
            proj = self._require()
            with open(args["path"], encoding="utf-8",
                      errors="replace") as fh:
                text = fh.read()
            events = []
            for line in text.splitlines():
                m = _re.match(
                    r"\s*(\d+)\s+(\S+)\s+([VA]+)\s+\S+\s+"
                    r"(\d\d:\d\d:\d\d:\d\d)\s+(\d\d:\d\d:\d\d:\d\d)\s+"
                    r"(\d\d:\d\d:\d\d:\d\d)\s+(\d\d:\d\d:\d\d:\d\d)",
                    line)
                if not m:
                    continue
                def _tc(s):
                    h, mi, s2, f = (int(x) for x in s.split(":"))
                    return ((h * 3600 + mi * 60 + s2)
                            * int(round(self._fps_value(proj))) + f)
                events.append({"event": int(m.group(1)),
                               "reel": m.group(2),
                               "tracks": m.group(3),
                               "source_in": _tc(m.group(4)),
                               "source_out": _tc(m.group(5)),
                               "record_in": _tc(m.group(6)),
                               "record_out": _tc(m.group(7))})
            if not events:
                raise ValueError("No CMX3600-style events found in the EDL")
            placed = []
            mapping = args.get("media_map") or {}
            if mapping:
                for ev in events:
                    media_id = mapping.get(ev["reel"])
                    if not media_id:
                        continue
                    placed.append(proj.add_clip(
                        media_id, args.get("track", "v1"),
                        ev["record_in"], ev["source_in"],
                        ev["record_out"] - ev["record_in"]))
                self._save()
            return {"events": events, "placed": placed}
        if name == "vibeedit_selects_list":
            return {"selects": self._require().data.get("selects", [])}
        if name == "vibeedit_selects_set":
            proj = self._require()
            select = {"id": args.get("id") or args["name"],
                      "name": args["name"], "media": args["media"],
                      "in": int(args.get("in", 0)),
                      "out": int(args["out"]) if args.get("out") is not None else None}
            selects = proj.data.setdefault("selects", [])
            selects[:] = [s for s in selects if s["id"] != select["id"]]
            selects.append(select)
            proj._bump()
            self._save()
            return {"select": select}
        if name == "vibeedit_selects_place":
            proj = self._require()
            select = next((s for s in proj.data.get("selects", [])
                           if s["id"] == args["select"]), None)
            if select is None:
                raise KeyError(f"Unknown select: {args['select']}")
            if select.get("out") is None:
                raise ValueError("Select has no Out frame; set one first")
            result = proj.add_clip(select["media"], args.get("track", "v1"),
                                   int(args.get("at", 0)), select["in"],
                                   select["out"] - select["in"])
            self._save()
            return result
        if name == "vibeedit_variants_list":
            proj = self._require()
            variants = proj.data.get("variants", {})
            return {"variants": [{"name": k, "rev": v.get("rev"),
                                  "items": sum(len(t["items"]) for t in
                                               v.get("tracks", []))}
                                 for k, v in variants.items()]}
        if name == "vibeedit_variants_create":
            import copy as _copy
            proj = self._require()
            variants = proj.data.setdefault("variants", {})
            variants[args["name"]] = _copy.deepcopy(proj.data)
            # The snapshot must not nest variants inside itself.
            variants[args["name"]].pop("variants", None)
            proj._bump()
            self._save()
            return {"variant": args["name"], "rev": proj.rev}
        if name == "vibeedit_variants_diff":
            proj = self._require()
            variant = (proj.data.get("variants") or {}).get(args["name"])
            if variant is None:
                raise KeyError(f"Unknown variant: {args['name']}")
            cur_ids = {i["id"] for t in proj.data["tracks"]
                       for i in t["items"]}
            var_ids = {i["id"] for t in variant.get("tracks", [])
                       for i in t["items"]}
            return {"variant": args["name"], "variant_rev": variant.get("rev"),
                    "current_rev": proj.rev,
                    "only_in_current": sorted(cur_ids - var_ids),
                    "only_in_variant": sorted(var_ids - cur_ids)}
        if name == "vibeedit_script_check":
            proj = self._require()
            script = args["text"]
            found, missing = [], []
            for track in proj.data["tracks"]:
                for item in track["items"]:
                    if "text" not in item:
                        continue
                    (found if item["text"] in script else missing).append(
                        {"id": item["id"], "text": item["text"]})
            total = len(found) + len(missing)
            return {"found": found, "missing": missing,
                    "coverage": round(len(found) / total, 3) if total else 0.0}
        if name == "vibeedit_plan_check":
            proj = self._require()
            problems = []
            for op in args.get("ops", []):
                kind = op.get("op")
                if kind not in ("add_clip", "add_text", "trim", "split",
                                "move", "delete", "set_speed", "set_fade",
                                "set_volume", "set_text", "set_keyframes",
                                "set_color", "add_marker", "remove_marker",
                                "add_transition", "remove_transition"):
                    problems.append(f"Unknown operation: {kind}")
                    continue
                for key in ("item", "media", "track"):
                    if key in op:
                        try:
                            if key == "item":
                                proj.item(op[key])
                            elif key == "media":
                                proj.media(op[key])
                            else:
                                proj.track(op[key])
                        except (KeyError, ValueError):
                            problems.append(
                                f"Unknown {key}: {op[key]!r}")
            return {"ok": not problems, "problems": problems}
        if name == "vibeedit_plan_apply":
            return self.call("vibeedit_timeline_apply",
                             {"ops": args.get("ops", [])})
        if name == "vibeedit_workflow_gates":
            proj = self._require()
            gates = proj.data.get("workflowGates")
            if gates is None:
                raise ValueError(
                    "No review gates have been set; call "
                    "vibeedit_workflow_set_gates first")
            return {"gates": gates}
        if name == "vibeedit_workflow_set_gates":
            proj = self._require()
            gates = args["gates"]
            if not isinstance(gates, dict):
                raise ValueError("gates must be an object")
            proj.data["workflowGates"] = gates
            proj._bump()
            self._save()
            return {"gates": gates}
        if name == "vibeedit_checkpoint_request":
            if self.path is None:
                raise RuntimeError("No project open")
            info = write_backup(self.path)
            return {"checkpoint": info}
        if name == "vibeedit_checkpoint_status":
            import os
            proj = self._require()
            bak = self._backup_path()
            backups_dir = os.path.join(proj.folder, "backups")
            return {"backup": bak if bak and os.path.isfile(bak) else None,
                    "backup_mtime": os.path.getmtime(bak)
                    if bak and os.path.isfile(bak) else None,
                    "backups": sorted(os.listdir(backups_dir))
                    if os.path.isdir(backups_dir) else []}
        if name == "vibeedit_run_log":
            return {"batch_results": self.batch_results,
                    "last_export": self.last_export}
        if name == "vibeedit_run_show":
            return {"queued": self.batch_queue,
                    "results": self.batch_results,
                    "last_export": self.last_export}
        if name == "vibeedit_batch_cancel":
            self.batch_queue = []
            return {"cancelled": True}
        if name == "vibeedit_batch_presets":
            proj = self._require()
            return {"presets": {
                "full": {"width": proj.width, "height": proj.height,
                         "ffmpeg_preset": "fast", "crf": "20"},
                "draft": {"width": proj.width // 2,
                          "height": proj.height // 2,
                          "ffmpeg_preset": "veryfast", "crf": "28"}}}
        if name == "vibeedit_batch_retry":
            from .export_ops import batch_export
            if not self.batch_queue:
                raise ValueError("Batch queue is empty; nothing to retry")
            self.batch_results = batch_export(
                self.batch_queue, preset=args.get("preset", "full"),
                normalize_audio=bool(args.get("normalize", False)))
            return {"results": self.batch_results}
        if name == "vibeedit_library_get":
            for entry in self._require().library_list():
                if entry["id"] == args["entry"]:
                    return {"entry": entry}
            raise KeyError(f"Unknown library item: {args['entry']}")
        if name == "vibeedit_library_stats":
            items = self._require().library_list()
            kinds = {}
            for entry in items:
                kind = "text" if "text" in (entry.get("item") or {}) else "clip"
                kinds[kind] = kinds.get(kind, 0) + 1
            return {"count": len(items), "kinds": kinds}
        if name == "vibeedit_library_preview":
            for entry in self._require().library_list():
                if entry["id"] == args["entry"]:
                    return {"entry": entry}
            raise KeyError(f"Unknown library item: {args['entry']}")
        if name == "vibeedit_library_favorite":
            proj = self._require()
            for entry in proj.data.get("library", []):
                if entry["id"] == args["entry"]:
                    entry["favorite"] = True
                    proj._bump()
                    self._save()
                    return {"entry": entry}
            raise KeyError(f"Unknown library item: {args['entry']}")
        if name == "vibeedit_library_update":
            proj = self._require()
            for entry in proj.data.get("library", []):
                if entry["id"] == args["entry"]:
                    entry["name"] = args["name"]
                    proj._bump()
                    self._save()
                    return {"entry": entry}
            raise KeyError(f"Unknown library item: {args['entry']}")
        if name == "vibeedit_library_apply":
            proj = self._require()
            result = proj.library_place(
                args["entry"], args.get("track"),
                int(args["at"]) if args.get("at") is not None else None)
            self._save()
            return result
        if name == "vibeedit_library_move":
            proj = self._require()
            library = proj.data.get("library", [])
            idx = next((i for i, e in enumerate(library)
                        if e["id"] == args["entry"]), None)
            if idx is None:
                raise KeyError(f"Unknown library item: {args['entry']}")
            entry = library.pop(idx)
            pos = max(0, min(int(args["to"]), len(library)))
            library.insert(pos, entry)
            proj._bump()
            self._save()
            return {"entry": entry["id"],
                    "order": [e["id"] for e in library]}
        if name == "vibeedit_clip_unlink_audio":
            proj = self._require()
            _, item = proj.item(args["item"])
            audio_ids = list(item.get("linked_audio") or [])
            video_id = item.get("linked_video")
            if not audio_ids and not video_id:
                raise ValueError(
                    f"Item {args['item']!r} has no linked audio to unlink")
            unlinked = []
            for audio_id in audio_ids:
                try:
                    _, partner = proj.item(audio_id)
                except KeyError:
                    continue
                if partner.get("linked_video") == item["id"]:
                    partner.pop("linked_video", None)
                unlinked.append(audio_id)
            if audio_ids:
                item.pop("linked_audio", None)
            if video_id:
                try:
                    _, video = proj.item(video_id)
                    remaining = [a for a in (video.get("linked_audio") or [])
                                 if a != item["id"]]
                    if remaining:
                        video["linked_audio"] = remaining
                    else:
                        video.pop("linked_audio", None)
                except KeyError:
                    pass
                item.pop("linked_video", None)
            proj._bump()
            self._save()
            return {"unlinked": unlinked, "item": args["item"]}
        # Phase B integration: skills (read side), vision, plugin
        # install/remove/update, linked audio, magnetic toggle,
        # reframe, transition renderability. These convert B1 honest
        # tools into real ones now that skills.py, vision.py and the
        # B3 install functions exist.
        if name == "vibeedit_skills_list":
            from .skills import list_skills
            return {"skills": list_skills(args.get("skills_dir"))}
        if name == "vibeedit_skills_get":
            from .skills import get_skill
            return {"skill": get_skill(args.get("skills_dir"),
                                       args["skill"])}
        if name == "vibeedit_skills_search":
            from .skills import search_skills
            return {"skills": search_skills(args.get("skills_dir"),
                                            args.get("query", ""))}
        if name in ("vibeedit_vision_text", "vibeedit_vision_faces",
                    "vibeedit_vision_cutout", "vibeedit_image_cutout"):
            from .vision import VisionUnavailable, cutout as _cut, \
                detect_faces as _faces, ocr_image as _ocr
            if args.get("media"):
                proj = self._require()
                path = self._media_abs(proj, proj.media(args["media"]))
            elif args.get("path"):
                path = args["path"]
            else:
                raise ValueError("vision tool needs 'media' or 'path'")
            try:
                if name == "vibeedit_vision_text":
                    return _ocr(path)
                if name == "vibeedit_vision_faces":
                    return _faces(path)
                out = args.get("output")
                if out is None and self.project is not None:
                    import os as _os
                    out = _os.path.join(
                        self.project.folder, "render",
                        _os.path.splitext(_os.path.basename(path))[0]
                        + "_cutout.png")
                return _cut(path, out)
            except VisionUnavailable as exc:
                raise ValueError(f"NOT_AVAILABLE: vision backend missing: {exc}")
        if name == "vibeedit_plugins_install":
            from .plugins import install_plugin
            return install_plugin(args["source"],
                                  plugins_dir=args.get("plugins_dir"),
                                  overwrite=bool(args.get("overwrite", False)),
                                  source_label=args.get("source_label"))
        if name == "vibeedit_plugins_download":
            import os as _os
            import tempfile as _tf
            from .plugins import download_plugin_bundle
            dest = args.get("dest") or _os.path.join(
                _tf.gettempdir(), "vibeedit-plugin-bundle.zip")
            return download_plugin_bundle(args["url"], dest)
        if name == "vibeedit_plugins_remove":
            from .plugins import remove_plugin
            return remove_plugin(args["plugin"],
                                 plugins_dir=args.get("plugins_dir"))
        if name == "vibeedit_plugins_updates":
            from .plugins import check_plugin_update
            return check_plugin_update(args["plugin"],
                                       plugins_dir=args.get("plugins_dir"))
        if name == "vibeedit_clip_link_audio":
            proj = self._require()
            result = proj.link_audio(args["video"], args["audio"])
            self._save()
            return result
        if name == "vibeedit_project_magnetic_get":
            return {"magnetic": self._require().magnetic_enabled}
        if name == "vibeedit_project_magnetic_set":
            proj = self._require()
            proj.set_magnetic(bool(args["enabled"]))
            self._save()
            return {"magnetic": proj.magnetic_enabled}
        if name == "vibeedit_clip_reframe":
            proj = self._require()
            result = proj.set_reframe(args["item"], args.get("window"))
            self._save()
            return result
        if name == "vibeedit_transitions_renderability":
            from .render import list_transition_renderability
            return {"transitions": list_transition_renderability()}
        # Round 2: knowledge store, skills write-side, voice/update
        # checks, caption transcription/generation/alignment, font
        # import, magnetic reorder.
        if name.startswith("vibeedit_knowledge_"):
            from . import knowledge as _k
            proj = self._require()
            data = proj.data
            sub = name[len("vibeedit_knowledge_"):]
            if sub == "add_lesson":
                res = _k.add_lesson(data, args["text"], args.get("title"))
            elif sub == "lessons":
                res = {"lessons": _k.lessons(data)}
            elif sub == "get":
                res = _k.get_lesson(data, args["lesson"])
            elif sub == "update_lesson":
                res = _k.update_lesson(data, args["lesson"], args["text"])
            elif sub == "remove_lesson":
                res = _k.remove_lesson(data, args["lesson"])
            elif sub == "approve":
                if args.get("proposal"):
                    res = _k.approve_proposal(data, args["proposal"])
                else:
                    res = _k.approve_lesson(data, args["lesson"])
            elif sub == "reject":
                if args.get("proposal"):
                    res = _k.reject_proposal(data, args["proposal"])
                else:
                    res = _k.reject_lesson(data, args["lesson"])
            elif sub == "facts":
                res = {"facts": _k.facts(data)}
            elif sub == "set_fact":
                res = _k.set_fact(data, args["key"], args["value"])
            elif sub == "prefs":
                res = {"prefs": _k.prefs(data)}
            elif sub == "set_pref":
                res = _k.set_pref(data, args["key"], args["value"])
            elif sub == "claims":
                res = {"claims": _k.claims(data)}
            elif sub == "set_claim":
                res = _k.set_claim(data, args["key"], args["statement"])
            elif sub == "memo":
                if "text" in args:
                    res = _k.set_memo(data, args["text"])
                else:
                    res = {"memo": _k.get_memo(data)}
            elif sub == "split_memo":
                res = _k.split_memo(data)
            elif sub == "proposals":
                res = {"proposals": _k.proposals(data)}
            elif sub == "verdicts":
                res = {"verdicts": _k.verdicts(data)}
            elif sub == "history":
                res = {"history": _k.history(data)}
            elif sub == "revert":
                res = _k.revert(data, int(args.get("steps", 1)))
            elif sub == "migrate":
                res = _k.migrate(data)
            elif sub == "skill":
                from .skills import get_skill as _gs
                res = {"skill": _gs(args.get("skills_dir"),
                                    args["skill"])}
            else:
                raise ValueError(f"Unknown knowledge tool: {name}")
            self._save()
            return res
        if name == "vibeedit_skills_save":
            from .skills import save_skill
            return save_skill(args.get("skills_dir"), args["skill"],
                              args.get("title", ""), args["body"],
                              overwrite=bool(args.get("overwrite", False)))
        if name == "vibeedit_skills_enable":
            from .skills import set_skill_enabled
            return set_skill_enabled(args.get("skills_dir"),
                                     args["skill"], True)
        if name == "vibeedit_skills_disable":
            from .skills import set_skill_enabled
            return set_skill_enabled(args.get("skills_dir"),
                                     args["skill"], False)
        if name == "vibeedit_skills_export":
            from .skills import export_skill
            return export_skill(args.get("skills_dir"), args["skill"],
                                args.get("dest"))
        if name == "vibeedit_skills_remove":
            from .skills import remove_skill
            return remove_skill(args.get("skills_dir"), args["skill"],
                                confirm=bool(args.get("confirm", False)))
        if name == "vibeedit_skills_propose":
            from .skills import propose_skill
            return propose_skill(args.get("skills_dir"), args["skill"],
                                 args.get("title", ""), args["body"])
        if name == "vibeedit_voice_check":
            import importlib.util as _ilu
            import shutil as _sh
            backends = {"piper": _sh.which("piper") is not None,
                        "edge_tts": _ilu.find_spec("edge_tts") is not None}
            takes = None
            if self.project is not None:
                proj = self._require()
                takes = 0
                for track in proj.data["tracks"]:
                    if track.get("role") == "voiceover":
                        takes += len(track.get("items", []))
            return {"backends": backends, "voiceover_takes": takes,
                    "note": "Generation is wired (Edge TTS / Piper) via "
                            "voice_synthesize; cloning is not wired (no "
                            "cloning provider model)."}
        if name == "vibeedit_app_update_check":
            from .updater import check_latest, update_status
            if args.get("check"):
                return check_latest(args.get("channel"))
            return update_status()
        if name == "vibeedit_app_update_download":
            from .updater import download_release
            if not args.get("url") or not args.get("dest"):
                raise ValueError("app_update_download needs url and dest")
            return download_release(args["url"], args["dest"],
                                    args.get("sha256"))
        if name == "vibeedit_app_update_prepare":
            from .updater import prepare_update
            if not args.get("url") or not args.get("dest"):
                raise ValueError("app_update_prepare needs url and dest")
            return prepare_update(args["url"], args["dest"],
                                  args.get("sha256"),
                                  args.get("app_pid"))
        if name == "vibeedit_app_update_later":
            from .updater import defer_update
            version = args.get("version") or args.get("latest_version")
            if not version:
                raise ValueError("app_update_later needs version")
            return defer_update(version,
                                args.get("remind_in_days", 7))
        if name == "vibeedit_app_update_skip":
            from .updater import skip_update
            version = args.get("version") or args.get("latest_version")
            if not version:
                raise ValueError("app_update_skip needs version")
            return skip_update(version)
        if name in ("vibeedit_captions_transcribe",
                    "vibeedit_media_transcribe"):
            from .transcribe import transcribe_media
            proj = self._require()
            medium = proj.media(args["media"])
            mpath = medium["path"]
            import os as _os
            if not _os.path.isabs(mpath):
                mpath = _os.path.join(proj.folder, mpath)
            added = transcribe_media(proj, mpath,
                                     args.get("track", "t1"),
                                     model=args.get("model", "tiny"))
            self._save()
            return {"added": [it["id"] for it in added]}
        if name == "vibeedit_captions_generate":
            from .transcribe import transcribe_media
            proj = self._require()
            medium = proj.media(args["media"])
            mpath = medium["path"]
            import os as _os
            if not _os.path.isabs(mpath):
                mpath = _os.path.join(proj.folder, mpath)
            track = args.get("track", "t1")
            added = transcribe_media(proj, mpath, track,
                                     model=args.get("model", "tiny"))
            self._save()
            return {"added": [it["id"] for it in added],
                    "srt": proj.export_srt(track)}
        if name == "vibeedit_captions_align":
            from .transcribe import align_captions
            proj = self._require()
            medium = proj.media(args["media"])
            mpath = medium["path"]
            import os as _os
            if not _os.path.isabs(mpath):
                mpath = _os.path.join(proj.folder, mpath)
            res = align_captions(proj, args.get("track", "t1"), mpath,
                                 model=args.get("model", "tiny"))
            self._save()
            return res
        if name == "vibeedit_fonts_import":
            from .render import import_font
            return import_font(args["path"],
                               fonts_dir=args.get("fonts_dir"))
        if name == "vibeedit_timeline_reorder":
            proj = self._require()
            res = proj.reorder_main(args["item"], args.get("before"))
            self._save()
            return res
        # Round 3 learned-segmentation backend slot (real ONNX
        # run when the user supplies a model file + runtime).
        if name == "vibeedit_vision_cutout_model":
            from .vision import cutout_segmented as _seg
            proj = self._require()
            medium = proj.media(args["media"])
            import os as _os
            mpath = medium["path"]
            if not _os.path.isabs(mpath):
                mpath = _os.path.join(proj.folder, mpath)
            return _seg(mpath, args["model"],
                        args.get("output"))
        # Round 3 voice generation (real providers in
        # vibeedit_core.voice; cloning stays honest-error: no
        # cloning provider model exists in this build).
        if name == "vibeedit_voice_synthesize":
            from .voice import synthesize as _synth
            proj = self._require()
            if not args.get("text"):
                raise ValueError("voice_synthesize needs text")
            import os as _os
            out = _os.path.join(proj.folder, "media",
                                args.get("file") or "voice_take.wav")
            res = _synth(args["text"], out,
                         provider=args.get("provider"),
                         voice=args.get("voice"),
                         model=args.get("model"))
            medium = proj.add_media(res["path"], kind="audio",
                                    duration=res["duration"])
            self._save()
            return {"media": medium["id"], "path": res["path"],
                    "backend": res["backend"], "voice": res["voice"],
                    "duration": res["duration"]}
        if name == "vibeedit_voice_lines":
            from .voice import synthesize as _synth
            proj = self._require()
            if not args.get("lines"):
                raise ValueError("voice_lines needs lines")
            import os as _os
            takes = []
            for i, line in enumerate(args["lines"]):
                out = _os.path.join(proj.folder, "media",
                                    f"voice_line_{i}.wav")
                res = _synth(line, out,
                             provider=args.get("provider"),
                             voice=args.get("voice"),
                             model=args.get("model"))
                medium = proj.add_media(res["path"], kind="audio",
                                        duration=res["duration"])
                takes.append({"media": medium["id"],
                              "path": res["path"],
                              "backend": res["backend"]})
            self._save()
            return {"takes": takes}
        if name == "vibeedit_voice_place":
            from .voice import place_on_voiceover as _place
            proj = self._require()
            if not args.get("media"):
                raise ValueError("voice_place needs media")
            item = _place(proj, args["media"],
                          args.get("at"))
            self._save()
            return {"item": item}
        if name == "vibeedit_voice_use":
            proj = self._require()
            proj.data["voice"] = {
                "provider": args.get("provider"),
                "voice": args.get("voice"),
                "model": args.get("model")}
            self._save()
            return {"voice": proj.data["voice"]}
        if name == "vibeedit_voice_fit":
            proj = self._require()
            if not args.get("item"):
                raise ValueError("voice_fit needs item")
            _track, item = proj.item(args["item"])
            target = int(args.get("frames") or args.get("to_frame") or 0)
            if target <= 0:
                raise ValueError("voice_fit needs a positive "
                                 "frames/to_frame target")
            ratio = float(args.get("min_ratio", 0)) or 0
            max_ratio = float(args.get("max_ratio", 0)) or 0
            needed = int(item["dur"]) / target
            if (ratio and needed < ratio) or \
                    (max_ratio and needed > max_ratio):
                raise ValueError(
                    f"voice_fit needs speed {needed:.3f}, outside "
                    f"[{ratio}, {max_ratio}]; nothing changed")
            proj.set_speed(args["item"], needed)
            self._save()
            return {"item": args["item"], "speed": needed,
                    "frames": target}
        # Phase B1 honest tools: every remaining Phase B1 name is a
        # check-and-error tool; _raise_honest performs the real check
        # (store-module / plugin-system / voice-module lookup where
        # applicable) and raises, never returning fake success.
        if name.startswith("vibeedit_") and any(
                t["name"] == name and t["description"].startswith(
                    "Not available") for t in TOOLS):
            self._raise_honest(name)
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
