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
                      write_backup, migrate_fps_units,
                      source_span_to_project_frames,
                      PROJECT_FILENAME)
from .filelock import ProjectFileLock

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
    {"name": "vibeedit_agent_terminals", "description": "Agent terminal tabs for this headless build: same shape as the original agent.terminals (terminal choices, unavailable plugin terminals, open tabs); this headless server has no agent dock, registers no terminal choices and no terminal sessions, and its plugin manifests carry no terminal field, so all three lists are always empty. Terminals run in an external terminal against this MCP server."},
    {"name": "vibeedit_agent_toggle_dock", "description": "Not available in this Windows build: no dock UI exists in this headless server; the web UI Agent dock is a separate browser view."},
    {"name": "vibeedit_agent_ask", "description": "Not available in this Windows build: in-app LLM chat is not present (parity-by-design: the original removed its model-API panel); use an external agent via MCP."},
    {"name": "vibeedit_agent_kit_check", "description": "Agent-kit status: kit folder, installed skills, installed kit version and releases channel (https://raw.githubusercontent.com/dongnguyenvie/bashcut-agent-kit/main/releases.json). Pass check_updates=true to compare against the channel (network); otherwise local only and newer is null."},
    {"name": "vibeedit_agent_kit_install", "description": "Install agent-kit skills from a folder of .md files, one .md file, a .zip bundle or a nested Claude-plugin folder (skills/<id>/SKILL.md) into the kit folder; unsafe ids and existing skills are refused. Folder skills install as their SKILL.md content under the flat <id>.md name."},
    {"name": "vibeedit_agent_kit_update", "description": "Update the agent kit from the signed releases channel: fetch releases.json, download the target archive, verify size, SHA-256 and the publisher Ed25519 signature, stage and validate its skills, then swap, keeping the old kit until the swap succeeds (restored on failure). Pass version for a specific release; already-current returns updated=false."},
    {"name": "vibeedit_agent_kit_later", "description": "Defer the agent-kit update offer: records later_until (7 days by default) in the kit state file, which agent_kit_check reports. No UI prompt exists in this headless server, so the record itself is the deferral."},
    {"name": "vibeedit_agent_status", "description": "Agent-kit status for this headless build: same data as agent_kit_check (kit folder, installed skills, installed version, releases channel); the original spec's per-tab/per-CLI setup state is not tracked here, and no terminal session exists."},
    {"name": "vibeedit_agent_setup", "description": "Not available in this Windows build: no agent terminal setup exists in this headless server."},
    {"name": "vibeedit_agent_setup_show", "description": "Not available in this Windows build: no agent setup view exists in this headless server."},
    {"name": "vibeedit_agent_restart_tab", "description": "Not available in this Windows build: no agent tab exists in this headless server."},
    {"name": "vibeedit_agent_quick_edit", "description": "Apply quick timeline edits (alias of timeline_apply; takes an ops list of add_clip/add_text/trim/split/move/delete/set_speed/set_fade/set_volume/set_text/set_keyframes/set_color/add_marker/remove_marker/add_transition/remove_transition; no quick-edit UI exists here)."},
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
    {"name": "vibeedit_chat_status", "description": "Chat agents in this headless build: the original lists chat agents in the agent dock (plugins with the agent.chat capability); this headless server has no dock, and its plugin manifests carry hooks, not an agent.chat capability field, while registry plugins are macOS-only and never executed, so the list is always empty."},
    {"name": "vibeedit_chat_transcript", "description": "Not available in this Windows build: no chat session exists in this headless server."},
    {"name": "vibeedit_show_about", "description": "About dialog content for this headless build: same data as app_version (MCP server, Python and project-schema versions); no dialog window exists here."},
    {"name": "vibeedit_show_commands", "description": "Commands dialog content for this headless build: same list as mcp_tools_list (tools + count); no dialog window exists here."},
    {"name": "vibeedit_show_shortcuts", "description": "Keyboard shortcuts derived at runtime by parsing static/app.js keydown listeners (not a hand-kept table): key combos with the code action each triggers; keys with no binding are absent, never listed as bound."},
    {"name": "vibeedit_show_settings", "description": "Not available in this Windows build: no settings dialog exists in this headless server."},
    {"name": "vibeedit_show_plugins", "description": "Plugins dialog content for this headless build: same list as plugins_list (discovered plugins + enable state); no dialog window exists here."},
    {"name": "vibeedit_show_review", "description": "Review dialog content for this headless build: same data as review_get (validation, stats, last export); no dialog window exists here."},
    {"name": "vibeedit_show_history", "description": "History dialog content for this headless build: same data as project_history (revision, .bak file, backups/ folder); no dialog window exists here."},
    {"name": "vibeedit_show_sections", "description": "Sections dialog content for this headless build: same list as markers_list (sections are markers in this port, shown by the timeline Sections button); no dialog window exists here."},
    {"name": "vibeedit_show_batch", "description": "Batch dialog content for this headless build: same data as batch_status (queued folders + last results); no dialog window exists here."},
    {"name": "vibeedit_show_export", "description": "Export dialog content for this headless build: same data as export_status (last export report or null); no dialog window exists here."},
    {"name": "vibeedit_show_export_progress", "description": "Export progress content for this headless build: same data as export_status; exports here are synchronous, so there is no in-progress state to report."},
    {"name": "vibeedit_show_updates", "description": "Updates dialog content for this headless build: same data as app_update_check (current version + channel status); no dialog window exists here."},
    {"name": "vibeedit_show_assets", "description": "Assets dialog content for this headless build: same list as media_list (project media); no dialog window exists here."},
    {"name": "vibeedit_show_agent_kit", "description": "Agent-kit dialog content for this headless build: same data as agent_kit_check (kit folder, installed skills, installed version, releases channel); no dialog window exists here."},
    {"name": "vibeedit_show_doctor", "description": "Doctor dialog content for this headless build: same data as doctor_run (Python/FFmpeg/FFprobe environment check); no dialog window exists here."},
    {"name": "vibeedit_ui_action", "description": "Not available in this Windows build: no live UI session exists for this headless server to act on."},
    {"name": "vibeedit_ui_dialog", "description": "Open dialogs in this headless build: the original reads open dialogs (alerts, file panels, sheets), topmost last; this headless server has no window and no dialog UI, so the list is always empty. Dialogs in the web UI live in the browser, not in this server."},
    {"name": "vibeedit_ui_view", "description": "Not available in this Windows build: no live UI session exists for this headless server."},
    {"name": "vibeedit_ui_select", "description": "Set the server session selection to the given timeline item ids (validated against the open project; unknown ids raise); with no items argument, returns the current selection. Selection is session state, reset on open; clip_backdrop defaults to it."},
    {"name": "vibeedit_ui_seek", "description": "Set the server session playhead to an absolute frame (frame int, clamped at 0); returns the new frame. Same session playhead the playhead_* step tools move."},
    {"name": "vibeedit_ui_frame", "description": "One timeline frame rendered with FFmpeg (draft preset) and extracted at the session playhead, or the given time_s: the actual composed frame, not a media first frame. Returns PNG base64 plus dimensions."},
    {"name": "vibeedit_ui_frames", "description": "Timeline frames rendered with FFmpeg (draft preset) and extracted at the given times_s, or evenly spaced when only count is given: actual composed frames, not media first frames. Returns PNG base64 plus dimensions per frame."},
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
    {"name": "vibeedit_voice_clone_list", "description": "Saved voice clones in this headless build: always empty — no cloning provider model is available here, so no clone can be created or stored. Voiceover takes are not clones; see voice_check for the generation backends."},
    {"name": "vibeedit_voice_clone_remove", "description": "Not available in this Windows build: no saved voice clones exist because no cloning provider model is available here."},
    {"name": "vibeedit_voice_synthesize", "description": "Synthesize text to a WAV with Edge TTS or Piper and add it as project media (clear error when the chosen backend is absent)."},
    {"name": "vibeedit_voice_speak", "description": "Synthesize a voice take (alias of voice_synthesize; measurement against the script is a separate transcribe step)."},
    {"name": "vibeedit_voice_lines", "description": "Synthesize every line of a script, one take per line, with Edge TTS or Piper."},
    {"name": "vibeedit_voice_check", "description": "Check which voice backends are available on this machine (piper binary, edge-tts module) and count voiceover takes in the open project."},
    {"name": "vibeedit_voice_use", "description": "Choose the project voice (provider/voice/model stored in project data and used as the default for synthesis)."},
    {"name": "vibeedit_voice_fit", "description": "Change a voiceover item speed (pitch kept by the renderer) so it lasts the given frames, within optional min/max ratios."},
    {"name": "vibeedit_voice_place", "description": "Place a generated audio media item on the Voiceover track (creating the track when the project has none)."},
    {"name": "vibeedit_image_generate", "description": "Not available in this Windows build: no image-generation provider/model is wired in this build."},
    {"name": "vibeedit_image_generate_list", "description": "List the project's generated pictures (media entries flagged generated)."},
    {"name": "vibeedit_image_style", "description": "Read or set the project's image style lock (style prompt, reference pictures, seed, disclosure label); clear removes it. The lock itself is state; generation still needs a provider."},
    {"name": "vibeedit_image_disclose", "description": "Put the disclosure label over generated pictures on the timeline (one small top-left text item per run); nothing is added when no label is configured anywhere."},
    {"name": "vibeedit_image_cutout", "description": "Cut out the foreground of an image with OpenCV grabCut (raises a clear error naming the missing backend when OpenCV is absent)."},
    {"name": "vibeedit_library_search", "description": "Search the project's saved library items by name, text or media id (local project data only; no provider)."},
    {"name": "vibeedit_library_generate", "description": "Not available in this Windows build: no library generation provider is wired in this build."},
    {"name": "vibeedit_library_brand_pose", "description": "Add a mascot pose to a brand kit from a photo (vision cutout sticker). The generate path needs an image.generate provider and is refused."},
    {"name": "vibeedit_library_export_pack", "description": "Write library items as a pack folder (pack.json and files); licence redistribute:false items are refused and named, licence-silent items are listed as unknownLicenses."},
    {"name": "vibeedit_library_import_pack", "description": "Add a pack (a folder with pack.json, or a .zip of one) to the project library; existing IDs are refused unless replace saves them as new versions."},
    {"name": "vibeedit_library_analyze", "description": "Measure an audio library item's file (duration, FFmpeg loudnorm/true peak, RMS landmarks, beat tempo, energy) and save as a new version; unmeasurable values stay null with a note."},
    {"name": "vibeedit_media_ocr", "description": "Recognise text in a project media entry or image file with Tesseract (alias of vision_text; clear error when Tesseract is absent)."},
    {"name": "vibeedit_media_subjects", "description": "Detect faces in a project media entry or image file with OpenCV Haar cascades (alias of vision_faces; clear error when OpenCV is absent)."},
    {"name": "vibeedit_media_describe", "description": "Store caller-supplied shot-by-shot facts for a source media (shots may not overlap; each needs at least one fact field)."},
    {"name": "vibeedit_media_description", "description": "Read media descriptions with coverage against measured shots (a measured shot counts as covered when half or more of it is described)."},
    {"name": "vibeedit_media_digest", "description": "Footage facts in one read: header (seconds, size, speech share, counts), described shots in time order, measured facts from the analysis record."},
    {"name": "vibeedit_media_cuts", "description": "Detect scene cuts in a project media with the FFmpeg scene filter (threshold, default 0.4) and correct the stored cut list: add cuts or remove candidates at source seconds, clear drops earlier corrections, remeasure measures again and drops corrections. Corrections live in the media record."},
    {"name": "vibeedit_media_sync", "description": "Find the time offset between two recordings of the same moment from their sound: mono 8 kHz envelopes cross-correlated (coarse 10/s, fine 100/s around the best lag), halves matched again for drift; time in 'to' = time in 'media' + offsetSeconds, correlation below 0.4 means no shared sound; with item, also the matching source frame of 'to' for that clip's in-point."},
    {"name": "vibeedit_media_speech_map", "description": "Map where an analysed media has sound that may be speech, and the gaps, with the calibration used: 0.1 s RMS level windows split into quiet/loud by Otsu unless thresholdDb is given; separation clear/weak/none/given, spans/gaps null with a reason when the classes do not separate; transcript section when a stored transcript exists. Spans are sound, not proof of speech."},
    {"name": "vibeedit_media_strip", "description": "Draw a filmstrip of a source range as one PNG: count frames (default 8) along the top with their time, a time ruler, the sound level (-60..0 dBFS per 0.1 s, from the media.analyze record or measured now), the speech-map gaps shaded (left out when speech and floor do not separate), and the stored transcript's words at their times. Returns {path, width, height, from, to, frames, levels, gaps, words}."},
    {"name": "vibeedit_media_proxy", "description": "Generate a low-resolution proxy file for a project video entry with FFmpeg (H.264, scaled to the given width, default 540px; the proxy is a derived file, not a new timeline media entry)."},
    {"name": "vibeedit_media_analysis", "description": "Read the media.analyze record of one media without measuring: tech, picture {cuts, shots, summary, histogram, cut curve}, sound {floor/median/loud, active spans, stereo correlation} and corrections; limits minScore/activityDb/bridgeSeconds are the reader's. Falls back to stored metadata enriched with a live ffprobe probe when no record exists."},
    {"name": "vibeedit_media_analyze", "description": "Measure source media once and keep the record on the media entry (keyed by file content): file facts, picture samples with exact-frame cut candidates, and sound levels (RMS per 0.1 s, peak, stereo correlation); transcript words only when faster-whisper is installed. A record that exists is reused unless force. Read it with media_analysis."},
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
    {"name": "vibeedit_plugins_install", "description": "Install a plugin from a local folder or .zip bundle (manifest validated before copying; URL sources must be downloaded first with plugins_download); or pass registry_plugin (+registry_version) to install a verified registry release (SHA-256 + publisher signature checked, staged, validated, installed disabled and never executed; registry provider plugins have no Windows-runnable entry). The caller's explicit install command is the approval in headless MCP."},
    {"name": "vibeedit_plugins_updates", "description": "Check a plugin for update metadata (local manifest metadata by default); pass check_registry=true to compare the installed version against the fetched plugin registry instead."},
    {"name": "vibeedit_plugins_search", "description": "Search plugins: local installed plugins by default (source=local); pass source=registry to search the fetched plugin registry (registry.json from the bashcut-plugins repo), or source=all for both. A registry fetch failure is reported, never silently replaced by local results."},
    {"name": "vibeedit_plugins_setup", "description": "Not available in this Windows build: pure .py plugins declare no dependency recipe for plugins.setup to run; manifest actions/views/overlays/proposals/replacement are real tools."},
    {"name": "vibeedit_plugins_set", "description": "Turn a plugin on or off (same switches as plugin_enable/plugin_disable). Per-hook switches are not supported in this build."},
    {"name": "vibeedit_plugins_set_overlays", "description": "Replace a plugin's overlays (empty list clears them); session-only, never saved with the project."},
    {"name": "vibeedit_plugins_overlays", "description": "List the overlays plugins draw on the timeline and viewer, by plugin (session-only, never saved with the project)."},
    {"name": "vibeedit_plugins_view", "description": "Render a plugin view from its manifest component model and return its components as JSON (text, lists, inputs with current values, buttons by id)."},
    {"name": "vibeedit_plugins_view_event", "description": "Do what a user does in a plugin view: click a button (runs its declared action hook when one exists), change an input, submit, select a row."},
    {"name": "vibeedit_plugins_proposal", "description": "Apply or discard an edit a plugin hook proposed (hooks return propose ops, stored pending until this decision)."},
    {"name": "vibeedit_plugins_replace", "description": "Replace an installed plugin with a new version from a folder, plugin.json or .zip; same plugin ID required, plugin must be disabled first."},
    {"name": "vibeedit_plugins_remove", "description": "Remove an installed plugin folder (refuses while the plugin is enabled; disable first)."},
    {"name": "vibeedit_plugins_run", "description": "Run one declared hook of an enabled plugin on a timeline item via apply_plugin (only declared hooks of enabled plugins run; disabled plugins are refused)."},
    {"name": "vibeedit_plugins_invoke", "description": "Run one declared hook of an enabled plugin on a timeline item via apply_plugin (only declared hooks of enabled plugins run; disabled plugins are refused)."},
    {"name": "vibeedit_plugins_actions", "description": "List actions plugins add to the editor, from manifest action declarations, with parameters, placements and availability."},
    {"name": "vibeedit_plugins_option", "description": "Set one plugin option (omit value to reset it to its default). Values are validated against the plugin's declared schema; project-scope values are a project edit, user-scope values are saved in plugins.json."},
    {"name": "vibeedit_plugins_options", "description": "Read a plugin's options: declared schema, scope (user/project) and current values (user-scope from plugins.json, project-scope from the open project; without an open project, project-scope options report their defaults)."},
    {"name": "vibeedit_plugins_show_view", "description": "Show a plugin view where it lives (panel/dock/sheet/window per its manifest placement) and record it as the project's currently-shown view; inspector views follow the selection and return shown=False. Needs an enabled plugin with that view; plugins_view stays the render path."},
    {"name": "vibeedit_clip_motion", "description": "Animate a clip with a MotionPreset (zoom-in/out, pan-left/right/up/down, fade-in-out, pop-in, slide-up, zoom-punch) or custom keyframes JSON; stored as keyframes and rendered by the zoompan/tilt/opacity paths. Focus framing is refused (needs a viewer band)."},
    {"name": "vibeedit_clip_backdrop", "description": "Fill a fitted picture's bars with a blur of itself or a colour (Inspector › Video › Backdrop). kind blur/color/none (none removes); blur is the radius as a share of the frame's short side (0-0.5, default 0.05), dim darkens it (0-1); main-track video/image items only; item(s) default to the server selection. Returns rev, items and backdrop."},
    {"name": "vibeedit_clip_change_framing", "description": "Cycle a video clip through Wide/Medium/Close-up/Left/Right framing presets (ReframePreset); zoom renders as fill scale and pan/tilt as crop offsets."},
    {"name": "vibeedit_clip_reframe", "description": "Set (or clear with null) a media clip's reframe window; rendered as a crop before scaling, never stretched."},
    {"name": "vibeedit_clip_send_to_agent", "description": "Not available in this Windows build: no agent session exists in this headless server to send a clip to."},
    {"name": "vibeedit_clip_unlink_audio", "description": "Unlink a clip's linked audio: clear linked_audio on the video item and linked_video on each audio partner (errors when the item has no linked audio)."},
    {"name": "vibeedit_music_replace", "description": "Swap the music bed for a new sound covering the old Music clips' span, keeping level/muted/fades; repeats unless loop=false."},
    {"name": "vibeedit_narration_windows", "description": "List timeline stretches with no spoken word and no voiceover item, with anchors (afterWord, firstCut, firstBeat, section), covered music/footage shares and a word budget when rate is given."},
    {"name": "vibeedit_outcomes_import", "description": "Import an export's retention curve and totals (JSON {curve, totals}, a point list, or CSV), stored per export in the project; re-import replaces."},
    {"name": "vibeedit_outcomes_map", "description": "Map an imported export's outcomes onto its sections (markers, else the whole video): retention, change, drop/lift points, replay peak, views at start, largest drops with nearby caption words."},
    {"name": "vibeedit_run_append", "description": "Append an entry to the run log stored in the project; stage gates enforced (done needs evidence or is unverified, skipped needs a reason, review-done with open required stages returns stage_pending)."},
    {"name": "vibeedit_run_checklist", "description": "The run's checklist derived from the plan and the run log: stage statuses, skill reads, audits, recipe, open items and the run panel's state (dismissed/shown/follow/visible)."},
    {"name": "vibeedit_run_dismiss", "description": "Close the run panel until it is shown again; the dismissed/shown state is stored in the project and reported by run_checklist."},
    {"name": "vibeedit_run_fix_issues", "description": "Draft the result card's Fix remaining issues request (exact original wording) from the current validation counts; needs a run result with issues left. Headless has no agent session to deliver to, so the request is returned for the calling agent to execute, never claimed delivered."},
    {"name": "vibeedit_run_follow", "description": "Toggle (or set with follow) the run panel's follow-agent state, stored in the project and reported by run_checklist; headless there is no viewer to scroll, so only the flag itself is real."},
    {"name": "vibeedit_run_toggle", "description": "Open or close the run panel (dismisses when visible, shows when hidden); state stored in the project and reported by run_checklist."},
    {"name": "vibeedit_run_another_recipe", "description": "Draft the result card's Try another recipe request (exact original wording) for a new version with a different recipe, keeping this one; needs a run result. Returned for the calling agent to execute, never claimed delivered."},
    {"name": "vibeedit_acme_voice_fast", "description": "Not available in this Windows build: acme.voice.fast is a provider capability string from the original's agent instructions and no acme provider is wired here; voice generation via Edge/Piper is the separate voice_synthesize tool."},
    {"name": "vibeedit_speech_rate", "description": "Measure speaking rate from transcript words (analysis-record words, or caption words for the timeline): syllables for Vietnamese, characters for CJK, else words; per-phrase p10/p50/p90, overall and articulation. Voice takes carry no text, so no voice rate is fabricated."},
    {"name": "vibeedit_app_vibeedit", "description": "Not available in this Windows build: no app-level automation client exists in this headless server."},
    {"name": "vibeedit_app_vibeedit_automation_clients", "description": "Automation clients for this headless build: the original lists clients connected to the app's Unix-socket automation server; this headless server has no Unix-socket automation server and no client registry, so the list is always empty. HTTP MCP callers are not automation clients."},
    {"name": "vibeedit_app_vibeedit_debug_log", "description": "MCP server debug log for this headless build: lines this server actually wrote to its debug-log file (ISO time + tool name per invocation, except debug-log reads themselves; arguments are never recorded), byte-capped like the original's rotation; empty with a note when no lines exist yet; the web server's HTTP log is not included."},
    {"name": "vibeedit_platforms_get", "description": "Not available in this Windows build: no platform-client registry exists in this headless server."},
    {"name": "vibeedit_context_get", "description": "Live editor context snapshot for this headless build: project name/rev, session playhead, selection, zoom, source marks/frame, track/item counts, duration and markers — all read from the open project and the server session, never invented."},
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
    {"name": "vibeedit_skills_import_plan", "description": "Preview a skill import from a .md file, a folder, a Claude-plugin folder (skills/<id>/SKILL.md) or a .zip of those, without writing anything: returns each skill's id, title, kind, file count, size and whether it already exists, plus safety warnings (zip-slip entries skipped, unsafe ids refused)."},
    {"name": "vibeedit_skills_import", "description": "Install skills from a .md file, a folder, a Claude-plugin folder or a .zip (copy-only, never executes anything, no provenance header added, never auto-enables; existing skills are skipped unless overwrite=true; pass only=[...] to install just some previewed ids). Records source path + SHA-256 per skill in skills/IMPORT_MANIFEST.json."},
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


# ---------------------------------------------------------------------------
# Round 20: keyboard-shortcut map derived from static/app.js at runtime.
#
# show_shortcuts keeps NO hand-copied table (that would drift the moment
# app.js changes). Instead it parses the live keydown listeners: JS
# comments are blanked with a string-aware scanner, document keydown
# listener bodies are extracted by balanced-brace matching, and each
# branch is read mechanically (modifier groups, key === "..." tests,
# action-call rules below). The deliberately-unbound shortcuts named
# in the round-18 comment block can never appear: comments are gone
# before parsing, so only code that actually binds a key is listed.
# Failure mode is loud, not silently wrong: if the parser cannot find
# the pinned shortcuts, the round-20 tests fail instead of returning
# a half-invented map. Known limitation: a ${...} interpolation
# containing braces or quotes would miscount braces (the listeners
# only use bare identifiers there); a regex literal containing a
# brace inside a listener body would do the same.
# ---------------------------------------------------------------------------

def _js_clean_with_mask(src):
    """Return (clean, is_code): JS source with comments blanked out.

    Strings stay verbatim but are marked non-code, so brace matching
    never counts a brace inside a string. Template literals stay
    verbatim too; ${...} interpolations are skipped as string
    content (bare identifiers only, as used in the listeners).
    """
    clean = []
    is_code = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            clean.append(" ")
            is_code.append(False)
            i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            clean.append(" ")
            is_code.append(False)
            i = j
        elif c in ("'", '"'):
            q = c
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == q:
                    j += 1
                    break
                j += 1
            clean.append(src[i:j])
            is_code.extend([False] * (j - i))
            i = j
        elif c == "`":
            j = i + 1
            depth = 0
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "`" and depth == 0:
                    j += 1
                    break
                if src[j] == "$" and j + 1 < n and src[j + 1] == "{":
                    depth += 1
                    j += 2
                    continue
                if src[j] == "}" and depth > 0:
                    depth -= 1
                    j += 1
                    continue
                j += 1
            clean.append(src[i:j])
            is_code.extend([False] * (j - i))
            i = j
        else:
            clean.append(c)
            is_code.append(True)
            i += 1
    return "".join(clean), is_code


def _js_match_brace(text, mask, open_pos):
    """Index of the code '}' matching the code '{' at open_pos."""
    depth = 0
    for p in range(open_pos, len(text)):
        if not mask[p]:
            continue
        if text[p] == "{":
            depth += 1
        elif text[p] == "}":
            depth -= 1
            if depth == 0:
                return p
    return None


def _js_match_paren(text, mask, open_pos):
    """Index of the code ')' matching the code '(' at open_pos."""
    depth = 0
    for p in range(open_pos, len(text)):
        if not mask[p]:
            continue
        if text[p] == "(":
            depth += 1
        elif text[p] == ")":
            depth -= 1
            if depth == 0:
                return p
    return None


def _js_next_code_brace(text, mask, start):
    for p in range(start, len(text)):
        if mask[p] and text[p] == "{":
            return p
    return None


def _js_keydown_regions(clean, mask):
    """(body_text, body_mask) for each document keydown listener."""
    regions = []
    needle = 'addEventListener("keydown"'
    start = 0
    while True:
        k = clean.find(needle, start)
        if k < 0:
            return regions
        # Only document-level listeners: zone.addEventListener (the
        # import dropzone's Enter/Space picker activation) is not a
        # global shortcut and must not be listed.
        if clean[max(0, k - 9):k] != "document.":
            start = k + 1
            continue
        b = _js_next_code_brace(clean, mask, k + len(needle))
        if b is None:
            return regions
        close = _js_match_brace(clean, mask, b)
        if close is None:
            return regions
        regions.append((clean[b + 1:close], mask[b + 1:close]))
        start = close + 1


def _js_defined_functions(clean):
    """Top-level `function name(` declarations (async allowed)."""
    import re
    return set(re.findall(r"(?m)^\s*(?:async\s+)?function\s+(\w+)\s*\(",
                          clean))


def _js_scan_branches(text, mask):
    """(condition, body) for each if/else-if in the region.

    Block bodies (``if (...) { ... }``) yield the block contents;
    single-statement branches (``if (...) markSource("in");``) yield
    the statement. Guard branches (``if (...) return;``) are yielded
    too, but carry no key test so callers skip them.
    """
    import re
    out = []
    pos = 0
    while True:
        m = re.search(r"(?:else\s+)?if\s*\(", text[pos:])
        if m is None:
            return out
        base = pos + m.start()
        if not mask[base]:
            pos = base + 1
            continue
        paren_open = pos + m.end() - 1
        paren_close = _js_match_paren(text, mask, paren_open)
        if paren_close is None:
            return out
        p = paren_close + 1
        while p < len(text) and (not mask[p] or text[p] in " \t\r\n"):
            p += 1
        if p >= len(text):
            return out
        if text[p] == "{":
            close = _js_match_brace(text, mask, p)
            if close is None:
                return out
            out.append((text[paren_open + 1:paren_close],
                        text[p + 1:close]))
            pos = close + 1
        else:
            s = None
            for q in range(p, len(text)):
                if mask[q] and text[q] == ";":
                    s = q
                    break
            if s is None:
                return out
            out.append((text[paren_open + 1:paren_close],
                        text[p:s + 1]))
            pos = s + 1


def _shortcut_branch_action(body, defined_fns):
    """The action a branch triggers, by mechanical rules in order.

    1. An api("PATH", ...) call -> POST PATH (save/undo/redo).
    2. A call to a function declared in app.js -> that function.
    3. click("ID") / railClick("TAB") / $("ID") + .click() -> the click.
    4. .pause() / .play() on the preview element.
    5. Otherwise the branch's first stripped line, verbatim.
    """
    import re
    m = re.search(r'api\("([^"]+)"', body)
    if m:
        return "POST " + m.group(1)
    for m in re.finditer(r"(\w+)\s*\(", body):
        if m.group(1) in defined_fns:
            return m.group(1) + "()"
    m = re.search(r'click\("([^"]+)"\)', body)
    if m:
        return "click " + m.group(1)
    m = re.search(r'railClick\("([^"]+)"\)', body)
    if m:
        return "open rail tab " + m.group(1)
    m = re.search(r'\$\("([^"]+)"\)', body)
    if m and ".click(" in body:
        return "click " + m.group(1)
    if ".pause()" in body:
        return "pause preview"
    if ".play()" in body:
        return "play preview"
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    return lines[0][:80] if lines else "(no action)"


_KEY_DISPLAY = {" ": "Space", "backspace": "Backspace",
                "delete": "Delete", "arrowleft": "ArrowLeft",
                "arrowright": "ArrowRight", "escape": "Escape"}


def _shortcut_display_key(key):
    if key in _KEY_DISPLAY:
        return _KEY_DISPLAY[key]
    if len(key) == 1:
        return key.upper()
    return key.capitalize()


def _shortcut_combo(ctrl, shift, alt, key):
    parts = []
    if ctrl:
        parts.append("Ctrl")
    if alt:
        parts.append("Alt")
    if shift:
        parts.append("Shift")
    parts.append(_shortcut_display_key(key))
    return "+".join(parts)


def _shortcut_keys_from_condition(cond):
    """(key, shift_override) per key === "..." alternative in cond.

    Alternatives are split on ||; shift_override is True/False when
    the alternative states it, else None (caller supplies the default).
    """
    import re
    out = []
    for alt in cond.split("||"):
        m = re.search(r"""(?:key|e\.key)\s*===\s*"([^"]+)""", alt)
        if not m:
            continue
        if re.search(r"!\s*(?:e\.shiftKey|shift)\b", alt):
            shift = False
        elif re.search(r"(?:e\.shiftKey|shift)\b", alt):
            shift = True
        else:
            shift = None
        out.append((m.group(1), shift))
    return out


def _shortcut_parse_listener(text, mask, defined_fns):
    """Shortcuts from one keydown listener body -> [(combo, action)]."""
    import re
    found = []
    seen = set()

    def add(ctrl, shift, alt, key, action):
        norm = key.lower()
        combo = _shortcut_combo(ctrl, shift, alt, norm)
        if combo in seen:
            return
        seen.add(combo)
        found.append((combo, action))

    # Escape-style negative key guard: if (e.key !== "X") return;
    m = re.search(r"""if\s*\(\s*e\.key\s*!==\s*"([^"]+)"\s*\)\s*return\s*;""",
                  text)
    if m and mask[m.start()]:
        add(False, False, False, m.group(1),
            _shortcut_branch_action(text, defined_fns))
        return found

    # Modifier-group form (round-18 handler): each group's branches
    # inherit the group's modifiers; a branch's own && shift / !shift
    # overrides the group's shift.
    groups = [
        (re.compile(r"if\s*\(\s*ctrl\s*&&\s*!alt\s*\)"), (True, None, False)),
        (re.compile(r"if\s*\(\s*alt\s*&&\s*!ctrl\s*\)"), (False, None, True)),
        (re.compile(r"if\s*\(\s*shift\s*&&\s*!ctrl\s*&&\s*!alt\s*\)"),
         (False, True, False)),
        (re.compile(r"if\s*\(\s*!ctrl\s*&&\s*!shift\s*&&\s*!alt\s*\)"),
         (False, False, False)),
    ]
    grouped = False
    for g_re, (g_ctrl, g_shift, g_alt) in groups:
        gm = g_re.search(text)
        if gm is None or not mask[gm.start()]:
            continue
        grouped = True
        b = _js_next_code_brace(text, mask, gm.end())
        if b is None:
            continue
        close = _js_match_brace(text, mask, b)
        if close is None:
            continue
        for cond, body in _js_scan_branches(text[b + 1:close],
                                             mask[b + 1:close]):
            for key, shift in _shortcut_keys_from_condition(cond):
                add(g_ctrl, g_shift if shift is None else shift, g_alt,
                    key, _shortcut_branch_action(body, defined_fns))
    if grouped:
        return found

    # Guard form: a leading return-guard fixes the base modifiers for
    # the whole listener (Ctrl required, or Ctrl forbidden).
    base_ctrl = False
    if re.search(r"if\s*\(\s*!\s*\(\s*e\.ctrlKey\s*\|\|\s*e\.metaKey\s*\)"
                 r"\s*\)\s*return\s*;", text):
        base_ctrl = True
    for cond, body in _js_scan_branches(text, mask):
        for key, shift in _shortcut_keys_from_condition(cond):
            add(base_ctrl, False if shift is None else shift, False,
                key, _shortcut_branch_action(body, defined_fns))
    return found


def shortcuts_from_app_js(app_js_path):
    """Parse static/app.js keydown listeners into a shortcut map.

    Returns {"source", "listeners", "typing_guard", "shortcuts"}.
    Raises ValueError when the file is missing (never an empty map
    presented as if shortcuts did not exist).
    """
    import os
    if not os.path.isfile(app_js_path):
        raise ValueError(
            "show_shortcuts: static/app.js not found at "
            f"{app_js_path}; cannot derive the shortcut map")
    with open(app_js_path, encoding="utf-8") as fh:
        src = fh.read()
    clean, mask = _js_clean_with_mask(src)
    defined_fns = _js_defined_functions(clean)
    regions = _js_keydown_regions(clean, mask)
    shortcuts = []
    seen = set()
    guarded = 0
    for text, m in regions:
        if "shortcutIsTypingTarget" in text or "tagName" in text:
            guarded += 1
        for combo, action in _shortcut_parse_listener(text, m,
                                                      defined_fns):
            if combo in seen:
                continue
            seen.add(combo)
            shortcuts.append({"keys": combo, "action": action})
    shortcuts.sort(key=lambda s: s["keys"])
    return {
        "source": "static/app.js keydown listeners, parsed at runtime "
                  "(not a hand-kept table)",
        "listeners": len(regions),
        "typing_guard": (f"{guarded} of {len(regions)} listeners skip "
                         "shortcuts while typing in an input/textarea/"
                         "select/contenteditable element; Escape is "
                         "unguarded"),
        "shortcuts": shortcuts,
    }


# Round 22: inputSchema for tools/list, derived from the actual
# MCPServer.call handler code (see
# ~/workspace/vibeedit-round22-tools/extract_args.py +
# build_schemas.py — regenerate, do not hand-edit). For every
# tool, `properties` holds exactly the arguments its handler
# reads (args["k"] -> required, args.get("k") -> optional,
# with types from int()/float()/bool() wrappers, .get defaults,
# and the verified MANUAL_FIXES in build_schemas.py). Aliases
# inherit their target's schema. Tools whose handler reads no
# arguments get empty properties: genuinely zero-argument tools
# (verified by the extraction) and honest check-and-error tools
# (the _raise_honest fallthrough reads nothing before raising).
# The shared round8-guard prelude reads `plugins_dir` for its
# whole family, but only plugin branches use the value, so the
# schema advertises it only there.
TOOL_SCHEMAS = {
    'vibeedit_acme_voice_fast': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_adjustment_add': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'dur': {'type': 'integer'}, 'lut': {'type': 'string'}, 'preset': {'type': 'string'}, 'strength': {'type': 'string'}}, 'required': ['at', 'dur']},
    'vibeedit_adjustment_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_adjustment_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_adjustment_remove': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_adjustments_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_ask': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_detach': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_dismiss_changes': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_dock_info': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_kit_check': {'type': 'object', 'properties': {'check_updates': {'type': 'boolean'}, 'kit_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_agent_kit_install': {'type': 'object', 'properties': {'kit_dir': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_agent_kit_later': {'type': 'object', 'properties': {'days': {'type': 'integer'}, 'kit_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_agent_kit_update': {'type': 'object', 'properties': {'kit_dir': {'type': 'string'}, 'version': {'type': 'string'}}, 'required': []},
    'vibeedit_agent_open': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_open_chat': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_open_claude': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_open_codex': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_open_shell': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_quick_edit': {'type': 'object', 'properties': {'ops': {'type': 'array'}}, 'required': []},
    'vibeedit_agent_restart_tab': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_setup': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_setup_show': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_show_changes': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_status': {'type': 'object', 'properties': {'check_updates': {'type': 'boolean'}, 'kit_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_agent_terminals': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_toggle_dock': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_tools_install': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_agent_undo_changes': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_app_update': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_app_update_check': {'type': 'object', 'properties': {'channel': {'type': 'string'}, 'check': {'type': 'string'}}, 'required': []},
    'vibeedit_app_update_download': {'type': 'object', 'properties': {'dest': {'type': 'string'}, 'sha256': {'type': 'string'}, 'url': {'type': 'string'}}, 'required': ['dest', 'url']},
    'vibeedit_app_update_later': {'type': 'object', 'properties': {'latest_version': {'type': 'string'}, 'remind_in_days': {'type': 'integer'}, 'version': {'type': 'string'}}, 'required': []},
    'vibeedit_app_update_prepare': {'type': 'object', 'properties': {'app_pid': {'type': 'string'}, 'dest': {'type': 'string'}, 'sha256': {'type': 'string'}, 'url': {'type': 'string'}}, 'required': ['dest', 'url']},
    'vibeedit_app_update_skip': {'type': 'object', 'properties': {'latest_version': {'type': 'string'}, 'version': {'type': 'string'}}, 'required': []},
    'vibeedit_app_version': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_app_vibeedit': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_app_vibeedit_automation_clients': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_app_vibeedit_debug_log': {'type': 'object', 'properties': {'lines': {'type': 'integer'}}, 'required': []},
    'vibeedit_audio_beats': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_audio_energy': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_audio_loudness': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_audio_measure': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_audio_mix_measure': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_batch_cancel': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_batch_presets': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_batch_queue': {'type': 'object', 'properties': {'folders': {'type': 'array'}}, 'required': []},
    'vibeedit_batch_retry': {'type': 'object', 'properties': {'normalize': {'type': 'boolean'}, 'preset': {'type': 'string'}}, 'required': []},
    'vibeedit_batch_run': {'type': 'object', 'properties': {'normalize': {'type': 'boolean'}, 'preset': {'type': 'string'}}, 'required': []},
    'vibeedit_batch_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_beat_count': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_beat_detect': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'min_gap': {'type': 'number'}}, 'required': ['media']},
    'vibeedit_beat_grid_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_beat_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_beat_nearest': {'type': 'object', 'properties': {'seconds': {'type': 'number'}}, 'required': ['seconds']},
    'vibeedit_beat_snap': {'type': 'object', 'properties': {'frame': {'type': 'integer'}}, 'required': ['frame']},
    'vibeedit_beats_detect': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'min_gap': {'type': 'number'}}, 'required': ['media']},
    'vibeedit_beats_grid': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_beats_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_beats_to_markers': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_brand_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_brand_set': {'type': 'object', 'properties': {'colours': {'type': 'string'}, 'logo_media': {'type': 'string'}}, 'required': []},
    'vibeedit_capabilities_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_captions_align': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'model': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_captions_export': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': []},
    'vibeedit_captions_find': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': []},
    'vibeedit_captions_generate': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'model': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_captions_group': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_captions_import': {'type': 'object', 'properties': {'srt': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['srt']},
    'vibeedit_captions_replace': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'replacement': {'type': 'string'}}, 'required': ['query', 'replacement']},
    'vibeedit_captions_style': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'position_x': {'type': 'number'}, 'position_y': {'type': 'number'}, 'preset': {'type': 'string'}, 'size': {'type': 'number'}}, 'required': ['item']},
    'vibeedit_captions_transcribe': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'model': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_captions_words': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_attach': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_command': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_commands': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_detach': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_reset': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_send': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_stop': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_chat_transcript': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_checkpoint_request': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_checkpoint_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_clip_at_time': {'type': 'object', 'properties': {'frame': {'type': 'integer'}}, 'required': ['frame']},
    'vibeedit_clip_backdrop': {'type': 'object', 'properties': {'blur': {'type': 'number'}, 'color': {'type': 'string'}, 'dim': {'type': 'number'}, 'item': {'type': 'string'}, 'items': {'type': ['array', 'string']}, 'kind': {'type': 'string'}}, 'required': ['kind']},
    'vibeedit_clip_change_framing': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_color': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'lut': {'type': 'string'}, 'preset': {'type': 'string'}, 'preset_strength': {'type': 'string'}, 'strength': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_color_eq': {'type': 'object', 'properties': {'eq': {'type': 'string'}, 'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_color_eq_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_color_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_color_preset_strength': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'preset': {'type': 'string'}, 'preset_strength': {'type': 'number'}}, 'required': ['item', 'preset_strength']},
    'vibeedit_clip_color_reset': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_copy': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'item': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'item', 'track']},
    'vibeedit_clip_cut': {'type': 'object', 'properties': {'atFrame': {'type': 'integer'}, 'item': {'type': 'string'}}, 'required': ['atFrame', 'item']},
    'vibeedit_clip_delete': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_duplicate': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'item': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'item', 'track']},
    'vibeedit_clip_fade': {'type': 'object', 'properties': {'fadeIn': {'type': 'string'}, 'fadeOut': {'type': 'string'}, 'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_fades_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_freeze': {'type': 'object', 'properties': {'frames': {'type': 'integer'}, 'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_keyframe': {'type': 'object', 'properties': {'at': {'type': 'number'}, 'item': {'type': 'string'}, 'property': {'type': 'string'}, 'value': {'type': 'number'}}, 'required': ['at', 'item', 'property', 'value']},
    'vibeedit_clip_keyframe_remove': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'property': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_keyframes': {'type': 'object', 'properties': {'at': {'type': 'number'}, 'item': {'type': 'string'}, 'keyframes': {'type': 'array'}, 'property': {'type': 'string'}, 'value': {'type': 'number'}}, 'required': []},
    'vibeedit_clip_keyframes_clear': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_link_audio': {'type': 'object', 'properties': {'audio': {'type': 'string'}, 'video': {'type': 'string'}}, 'required': ['audio', 'video']},
    'vibeedit_clip_list': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': []},
    'vibeedit_clip_motion': {'type': 'object', 'properties': {'focus': {'type': 'string'}, 'item': {'type': 'string'}, 'keyframes': {'type': ['object', 'string']}, 'preset': {'type': 'string'}, 'within': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_move': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'item': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'item', 'track']},
    'vibeedit_clip_mute': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_opacity_set': {'type': 'object', 'properties': {'at': {'type': 'number'}, 'item': {'type': 'string'}, 'opacity': {'type': 'number'}}, 'required': ['at', 'item', 'opacity']},
    'vibeedit_clip_overlap_check': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'dur': {'type': 'integer'}, 'track': {'type': 'string'}}, 'required': ['at', 'track']},
    'vibeedit_clip_paste': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'item': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'track']},
    'vibeedit_clip_paste_cross_project': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'dest': {'type': 'string'}, 'item': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'dest', 'item', 'track']},
    'vibeedit_clip_position_set': {'type': 'object', 'properties': {'at': {'type': 'number'}, 'item': {'type': 'string'}, 'x': {'type': 'number'}, 'y': {'type': 'number'}}, 'required': []},
    'vibeedit_clip_reframe': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'window': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_reverse': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'reverse': {'type': 'boolean'}}, 'required': ['item']},
    'vibeedit_clip_scale_set': {'type': 'object', 'properties': {'at': {'type': 'number'}, 'item': {'type': 'string'}, 'scale': {'type': 'number'}}, 'required': ['at', 'item', 'scale']},
    'vibeedit_clip_send_to_agent': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_clip_slow_down': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_speed': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'speed': {'type': 'number'}}, 'required': ['item', 'speed']},
    'vibeedit_clip_speed_curve': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'preset': {'type': 'string'}}, 'required': ['item', 'preset']},
    'vibeedit_clip_speed_down': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_speed_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_speed_reset': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_speed_up': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_split': {'type': 'object', 'properties': {'atFrame': {'type': 'integer'}, 'item': {'type': 'string'}}, 'required': ['atFrame', 'item']},
    'vibeedit_clip_text_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_tilt': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'keyframes': {'type': 'array'}}, 'required': ['item', 'keyframes']},
    'vibeedit_clip_transition': {'type': 'object', 'properties': {'duration': {'type': 'number'}, 'from': {'type': 'string'}, 'kind': {'type': 'string'}, 'to': {'type': 'string'}}, 'required': ['duration', 'from', 'kind', 'to']},
    'vibeedit_clip_trim': {'type': 'object', 'properties': {'edge': {'type': 'string'}, 'item': {'type': 'string'}, 'toFrame': {'type': 'integer'}}, 'required': ['edge', 'item', 'toFrame']},
    'vibeedit_clip_unlink_audio': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_clip_volume': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'volume': {'type': 'number'}}, 'required': ['item', 'volume']},
    'vibeedit_close_gaps': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': []},
    'vibeedit_color_measure': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_color_preset_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_context_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_doctor_run': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ducking_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ducking_set': {'type': 'object', 'properties': {'amount_db': {'type': 'number'}, 'attack': {'type': 'number'}, 'enabled': {'type': 'boolean'}, 'ratio': {'type': 'string'}, 'release': {'type': 'number'}, 'threshold': {'type': 'number'}}, 'required': []},
    'vibeedit_ducking_toggle': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_edl_import': {'type': 'object', 'properties': {'media_map': {'type': 'string'}, 'path': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_export_cancel': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_chapters': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_cover': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_dismiss_notice': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_ducked': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_history': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_link': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_normalized': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_open_output': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_otio': {'type': 'object', 'properties': {'out': {'type': 'string'}}, 'required': []},
    'vibeedit_export_preset': {'type': 'object', 'properties': {'preset': {'type': 'string'}}, 'required': ['preset']},
    'vibeedit_export_preset_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_preview': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_reveal_output': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_export_start': {'type': 'object', 'properties': {'preset': {'type': 'string'}}, 'required': []},
    'vibeedit_export_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_fonts_import': {'type': 'object', 'properties': {'fonts_dir': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_fonts_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_image_cutout': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'output': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': []},
    'vibeedit_image_disclose': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': []},
    'vibeedit_image_generate': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_image_generate_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_image_style': {'type': 'object', 'properties': {'clear': {'type': 'string'}, 'disclosure': {'type': 'string'}, 'references': {'type': 'string'}, 'seed': {'type': 'string'}, 'style': {'type': 'string'}}, 'required': []},
    'vibeedit_jobs_cancel': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_jobs_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_jobs_wait': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_karaoke_add': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'words': {'type': 'string'}}, 'required': ['item', 'words']},
    'vibeedit_karaoke_export_ass': {'type': 'object', 'properties': {'out': {'type': 'string'}}, 'required': []},
    'vibeedit_karaoke_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_karaoke_remove': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_karaoke_syllable_add': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'words': {'type': 'string'}}, 'required': ['item', 'words']},
    'vibeedit_keyframes_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_knowledge_add_lesson': {'type': 'object', 'properties': {'text': {'type': 'string'}, 'title': {'type': 'string'}}, 'required': ['text']},
    'vibeedit_knowledge_approve': {'type': 'object', 'properties': {'lesson': {'type': 'string'}, 'proposal': {'type': 'string'}}, 'required': []},
    'vibeedit_knowledge_claims': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_facts': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_get': {'type': 'object', 'properties': {'lesson': {'type': 'string'}}, 'required': ['lesson']},
    'vibeedit_knowledge_history': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_lessons': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_memo': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': []},
    'vibeedit_knowledge_migrate': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_prefs': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_proposals': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_reject': {'type': 'object', 'properties': {'lesson': {'type': 'string'}, 'proposal': {'type': 'string'}}, 'required': []},
    'vibeedit_knowledge_remove_lesson': {'type': 'object', 'properties': {'lesson': {'type': 'string'}}, 'required': ['lesson']},
    'vibeedit_knowledge_revert': {'type': 'object', 'properties': {'steps': {'type': 'integer'}}, 'required': []},
    'vibeedit_knowledge_set_claim': {'type': 'object', 'properties': {'key': {'type': 'string'}, 'statement': {'type': 'string'}}, 'required': ['key', 'statement']},
    'vibeedit_knowledge_set_fact': {'type': 'object', 'properties': {'key': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['key', 'value']},
    'vibeedit_knowledge_set_pref': {'type': 'object', 'properties': {'key': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['key', 'value']},
    'vibeedit_knowledge_skill': {'type': 'object', 'properties': {'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['skill']},
    'vibeedit_knowledge_split_memo': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_knowledge_update_lesson': {'type': 'object', 'properties': {'lesson': {'type': 'string'}, 'text': {'type': 'string'}}, 'required': ['lesson', 'text']},
    'vibeedit_knowledge_verdicts': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_layer_add_adjustment': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'dur': {'type': 'integer'}, 'lut': {'type': 'string'}, 'preset': {'type': 'string'}, 'strength': {'type': 'string'}}, 'required': []},
    'vibeedit_layer_add_audio': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'role': {'type': 'string'}}, 'required': []},
    'vibeedit_layer_add_text': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'role': {'type': 'string'}}, 'required': []},
    'vibeedit_layer_add_video': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'role': {'type': 'string'}}, 'required': []},
    'vibeedit_layer_delete': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': ['track']},
    'vibeedit_layer_down': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': ['track']},
    'vibeedit_layer_up': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': ['track']},
    'vibeedit_layers_add': {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'name': {'type': 'string'}, 'role': {'type': 'string'}}, 'required': []},
    'vibeedit_layers_set': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['name', 'track']},
    'vibeedit_library_add': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_library_analyze': {'type': 'object', 'properties': {'entry': {'type': 'string'}, 'item': {'type': 'string'}, 'media_path': {'type': 'string'}}, 'required': []},
    'vibeedit_library_apply': {'type': 'object', 'properties': {'at': {'type': 'string'}, 'entry': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['entry']},
    'vibeedit_library_brand_pose': {'type': 'object', 'properties': {'brand': {'type': 'string'}, 'generate': {'type': 'string'}, 'image': {'type': 'string'}, 'media': {'type': 'string'}, 'pose': {'type': 'string'}}, 'required': ['brand', 'pose']},
    'vibeedit_library_export_pack': {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'output': {'type': 'string'}, 'pack': {'type': 'string'}}, 'required': ['output']},
    'vibeedit_library_favorite': {'type': 'object', 'properties': {'entry': {'type': 'string'}}, 'required': ['entry']},
    'vibeedit_library_generate': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_library_get': {'type': 'object', 'properties': {'entry': {'type': 'string'}}, 'required': ['entry']},
    'vibeedit_library_import_pack': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'replace': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_library_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_library_move': {'type': 'object', 'properties': {'entry': {'type': 'string'}, 'to': {'type': 'integer'}}, 'required': ['entry', 'to']},
    'vibeedit_library_place': {'type': 'object', 'properties': {'at': {'type': 'string'}, 'entry': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['entry']},
    'vibeedit_library_preview': {'type': 'object', 'properties': {'entry': {'type': 'string'}}, 'required': ['entry']},
    'vibeedit_library_remove': {'type': 'object', 'properties': {'entry': {'type': 'string'}}, 'required': ['entry']},
    'vibeedit_library_save_selection': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_library_search': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': []},
    'vibeedit_library_stats': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_library_update': {'type': 'object', 'properties': {'entry': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['entry', 'name']},
    'vibeedit_luts_import': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_marker_at_time': {'type': 'object', 'properties': {'frame': {'type': 'integer'}}, 'required': ['frame']},
    'vibeedit_marker_move': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'marker': {'type': 'string'}}, 'required': ['at', 'marker']},
    'vibeedit_markers_add': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'text': {'type': 'string'}}, 'required': ['at', 'text']},
    'vibeedit_markers_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_markers_remove': {'type': 'object', 'properties': {'marker': {'type': 'string'}}, 'required': ['marker']},
    'vibeedit_mcp_tools_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_media_add': {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_media_analysis': {'type': 'object', 'properties': {'activityDb': {'type': 'number'}, 'bridgeSeconds': {'type': 'number'}, 'curve': {'type': 'string'}, 'media': {'type': 'string'}, 'minScore': {'type': 'number'}, 'samples': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_analyze': {'type': 'object', 'properties': {'force': {'type': ['boolean', 'string']}, 'media': {'type': 'string'}, 'rate': {'type': 'number'}}, 'required': []},
    'vibeedit_media_cuts': {'type': 'object', 'properties': {'add': {'type': 'string'}, 'clear': {'type': 'boolean'}, 'media': {'type': 'string'}, 'remeasure': {'type': 'boolean'}, 'remove': {'type': 'string'}, 'threshold': {'type': 'number'}}, 'required': ['media']},
    'vibeedit_media_describe': {'type': 'object', 'properties': {'append': {'type': 'string'}, 'media': {'type': 'string'}, 'shots': {'type': 'string'}}, 'required': ['media', 'shots']},
    'vibeedit_media_description': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': []},
    'vibeedit_media_digest': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_duration': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_frame': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_frames': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_get': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_import': {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_media_inventory': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_media_kind_list': {'type': 'object', 'properties': {'kind': {'type': 'string'}}, 'required': []},
    'vibeedit_media_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_media_metadata': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_ocr': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'output': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': []},
    'vibeedit_media_place': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'dur': {'type': 'string'}, 'in': {'type': 'integer'}, 'media': {'type': 'string'}, 'speed': {'type': 'number'}, 'track': {'type': 'string'}}, 'required': ['at', 'media', 'track']},
    'vibeedit_media_proxy': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'out': {'type': 'string'}, 'width': {'type': 'integer'}}, 'required': ['media']},
    'vibeedit_media_remove': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_resolve_range': {'type': 'object', 'properties': {'dur': {'type': 'string'}, 'in': {'type': 'integer'}, 'item': {'type': 'string'}, 'media': {'type': 'string'}}, 'required': []},
    'vibeedit_media_speech_map': {'type': 'object', 'properties': {'bridgeSeconds': {'type': 'number'}, 'media': {'type': 'string'}, 'minSeparationDb': {'type': 'number'}, 'minSpeechSeconds': {'type': 'number'}, 'thresholdDb': {'type': 'number'}}, 'required': ['media']},
    'vibeedit_media_strip': {'type': 'object', 'properties': {'count': {'type': 'integer'}, 'from': {'type': 'number'}, 'media': {'type': 'string'}, 'to': {'type': 'number'}, 'width': {'type': 'integer'}}, 'required': ['media']},
    'vibeedit_media_subjects': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'output': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': []},
    'vibeedit_media_sync': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'media': {'type': 'string'}, 'to': {'type': 'string'}}, 'required': ['media', 'to']},
    'vibeedit_media_transcribe': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'model': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_media_transcript': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_media_usage': {'type': 'object', 'properties': {'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_music_replace': {'type': 'object', 'properties': {'library': {'type': 'string'}, 'loop': {'type': 'string'}, 'media': {'type': 'string'}}, 'required': []},
    'vibeedit_narration_windows': {'type': 'object', 'properties': {'minSeconds': {'type': 'number'}, 'min_seconds': {'type': 'number'}, 'rate': {'type': 'string'}}, 'required': []},
    'vibeedit_otio_export': {'type': 'object', 'properties': {'out': {'type': 'string'}}, 'required': []},
    'vibeedit_otio_import': {'type': 'object', 'properties': {'dest': {'type': 'string'}, 'merge': {'type': 'boolean'}, 'otio': {'type': 'string'}}, 'required': ['dest', 'otio']},
    'vibeedit_outcomes_import': {'type': 'object', 'properties': {'data': {'type': 'string'}, 'export': {'type': 'string'}, 'path': {'type': 'string'}, 'payload': {'type': 'string'}}, 'required': ['export']},
    'vibeedit_outcomes_map': {'type': 'object', 'properties': {'export': {'type': 'string'}, 'window': {'type': 'number'}}, 'required': ['export']},
    'vibeedit_overlay_items': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plan_apply': {'type': 'object', 'properties': {'ops': {'type': 'string'}}, 'required': []},
    'vibeedit_plan_check': {'type': 'object', 'properties': {'ops': {'type': 'array'}}, 'required': []},
    'vibeedit_platforms_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playback_shuttle_back': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playback_shuttle_forward': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playback_stop': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playback_toggle': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playhead_back_second': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playhead_forward_second': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playhead_next_frame': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_playhead_previous_frame': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugin_disable': {'type': 'object', 'properties': {'plugin': {'type': 'string'}}, 'required': ['plugin']},
    'vibeedit_plugin_enable': {'type': 'object', 'properties': {'plugin': {'type': 'string'}}, 'required': ['plugin']},
    'vibeedit_plugin_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_actions': {'type': 'object', 'properties': {'plugin': {'type': 'string'}, 'plugins_dir': {'type': 'string'}, 'query': {'type': 'string'}}, 'required': []},
    'vibeedit_plugins_bundles': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_download': {'type': 'object', 'properties': {'dest': {'type': 'string'}, 'url': {'type': 'string'}}, 'required': ['url']},
    'vibeedit_plugins_hooks': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_install': {'type': 'object', 'properties': {'overwrite': {'type': 'boolean'}, 'registry_plugin': {'type': 'string'}, 'registry_version': {'type': 'string'}, 'source': {'type': 'string'}, 'source_label': {'type': 'string'}}, 'required': []},
    'vibeedit_plugins_invoke': {'type': 'object', 'properties': {'hook': {'type': 'string'}, 'item': {'type': 'string'}, 'item_id': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugin_id': {'type': 'string'}}, 'required': ['hook']},
    'vibeedit_plugins_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_option': {'type': 'object', 'properties': {'option': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugin_id': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': []},
    'vibeedit_plugins_options': {'type': 'object', 'properties': {'plugin': {'type': 'string'}, 'plugin_id': {'type': 'string'}}, 'required': []},
    'vibeedit_plugins_overlays': {'type': 'object', 'properties': {'plugin': {'type': 'string'}, 'plugins_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_plugins_proposal': {'type': 'object', 'properties': {'decision': {'type': 'string'}, 'id': {'type': 'string'}}, 'required': ['decision', 'id']},
    'vibeedit_plugins_reload': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_remove': {'type': 'object', 'properties': {'plugin': {'type': 'string'}}, 'required': ['plugin']},
    'vibeedit_plugins_replace': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugins_dir': {'type': 'string'}}, 'required': ['path', 'plugin']},
    'vibeedit_plugins_run': {'type': 'object', 'properties': {'hook': {'type': 'string'}, 'item': {'type': 'string'}, 'item_id': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugin_id': {'type': 'string'}}, 'required': ['hook']},
    'vibeedit_plugins_search': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'source': {'type': 'string'}}, 'required': []},
    'vibeedit_plugins_set': {'type': 'object', 'properties': {'enabled': {'type': 'string'}, 'hooks': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugin_id': {'type': 'string'}}, 'required': ['enabled']},
    'vibeedit_plugins_set_overlays': {'type': 'object', 'properties': {'overlays': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugins_dir': {'type': 'string'}}, 'required': ['overlays', 'plugin']},
    'vibeedit_plugins_setup': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_show_view': {'type': 'object', 'properties': {'plugin': {'type': 'string'}, 'view': {'type': 'string'}}, 'required': ['plugin', 'view']},
    'vibeedit_plugins_updates': {'type': 'object', 'properties': {'check_registry': {'type': 'string'}, 'plugin': {'type': 'string'}}, 'required': ['plugin']},
    'vibeedit_plugins_validate': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_plugins_view': {'type': 'object', 'properties': {'plugin': {'type': 'string'}, 'plugins_dir': {'type': 'string'}, 'view': {'type': 'string'}}, 'required': ['plugin', 'view']},
    'vibeedit_plugins_view_event': {'type': 'object', 'properties': {'node': {'type': 'string'}, 'plugin': {'type': 'string'}, 'plugins_dir': {'type': 'string'}, 'type': {'type': 'string'}, 'value': {'type': 'string'}, 'view': {'type': 'string'}}, 'required': ['node', 'plugin', 'view']},
    'vibeedit_project_backup': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_clear_recents': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_close': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_create': {'type': 'object', 'properties': {'directory': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_project_credits': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_data': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_derive': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_project_duplicate': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_project_duration_frames': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_folder': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_format': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_format_set': {'type': 'object', 'properties': {'fps': {'type': ['number', 'array']}, 'height': {'type': 'string'}, 'width': {'type': 'string'}}, 'required': []},
    'vibeedit_project_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_history': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_import_media': {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_project_info': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_magnetic_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_magnetic_set': {'type': 'object', 'properties': {'enabled': {'type': 'boolean'}}, 'required': ['enabled']},
    'vibeedit_project_new': {'type': 'object', 'properties': {'directory': {'type': 'string'}, 'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_project_open': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_project_recents': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_rename': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_project_rev': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_save': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_search_text': {'type': 'object', 'properties': {'query': {'type': 'string'}}, 'required': []},
    'vibeedit_project_set_data': {'type': 'object', 'properties': {'key': {'type': 'string'}, 'value': {'type': 'string'}}, 'required': ['key', 'value']},
    'vibeedit_project_show_recents': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_stats': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_project_validate': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_accept': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_compare': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_coverage': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_layout': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_measure': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_packet': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_picture': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_run': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_shots': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_sync': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_verify': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_review_window': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_another_recipe': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_append': {'type': 'object', 'properties': {'by': {'type': 'string'}, 'data': {'type': 'string'}, 'eta': {'type': 'string'}, 'evidence': {'type': 'string'}, 'findings': {'type': 'string'}, 'fixed': {'type': 'string'}, 'kind': {'type': 'string'}, 'left': {'type': 'string'}, 'measured': {'type': 'string'}, 'name': {'type': 'string'}, 'notMeasured': {'type': 'string'}, 'origin': {'type': 'string'}, 'point': {'type': 'string'}, 'progress': {'type': 'string'}, 'reason': {'type': 'string'}, 'round': {'type': 'string'}, 'stage': {'type': 'string'}, 'status': {'type': 'string'}, 'text': {'type': 'string'}, 'verdict': {'type': 'string'}, 'verifiedBy': {'type': 'string'}}, 'required': ['kind']},
    'vibeedit_run_checklist': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_dismiss': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_fix_issues': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_follow': {'type': 'object', 'properties': {'follow': {'type': 'string'}}, 'required': []},
    'vibeedit_run_log': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_show': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_stop': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_run_toggle': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_schema_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_script_check': {'type': 'object', 'properties': {'text': {'type': 'string'}}, 'required': ['text']},
    'vibeedit_selects_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_selects_place': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'select': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['select']},
    'vibeedit_selects_set': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'in': {'type': 'integer'}, 'media': {'type': 'string'}, 'name': {'type': 'string'}, 'out': {'type': 'string'}}, 'required': ['media', 'name']},
    'vibeedit_show_about': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_agent_kit': {'type': 'object', 'properties': {'check_updates': {'type': 'boolean'}, 'kit_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_show_assets': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_batch': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_commands': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_doctor': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_export': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_export_progress': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_history': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_plugins': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_review': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_sections': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_settings': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_shortcuts': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_show_updates': {'type': 'object', 'properties': {'channel': {'type': 'string'}, 'check': {'type': 'string'}}, 'required': []},
    'vibeedit_skills_disable': {'type': 'object', 'properties': {'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['skill']},
    'vibeedit_skills_enable': {'type': 'object', 'properties': {'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['skill']},
    'vibeedit_skills_export': {'type': 'object', 'properties': {'dest': {'type': 'string'}, 'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['skill']},
    'vibeedit_skills_get': {'type': 'object', 'properties': {'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['skill']},
    'vibeedit_skills_import': {'type': 'object', 'properties': {'only': {'type': 'array'}, 'overwrite': {'type': 'boolean'}, 'path': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_skills_import_plan': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['path']},
    'vibeedit_skills_list': {'type': 'object', 'properties': {'skills_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_skills_propose': {'type': 'object', 'properties': {'body': {'type': 'string'}, 'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}, 'title': {'type': 'string'}}, 'required': ['body', 'skill']},
    'vibeedit_skills_remove': {'type': 'object', 'properties': {'confirm': {'type': 'boolean'}, 'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': ['skill']},
    'vibeedit_skills_save': {'type': 'object', 'properties': {'body': {'type': 'string'}, 'overwrite': {'type': 'boolean'}, 'skill': {'type': 'string'}, 'skills_dir': {'type': 'string'}, 'title': {'type': 'string'}}, 'required': ['body', 'skill']},
    'vibeedit_skills_search': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'skills_dir': {'type': 'string'}}, 'required': []},
    'vibeedit_source_close': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_source_insert': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'in': {'type': 'integer'}, 'media': {'type': 'string'}, 'out': {'type': 'integer'}, 'speed': {'type': 'number'}, 'track': {'type': 'string'}}, 'required': ['media', 'out']},
    'vibeedit_source_mark_in': {'type': 'object', 'properties': {'frame': {'type': 'integer'}, 'media': {'type': 'string'}}, 'required': ['frame']},
    'vibeedit_source_mark_out': {'type': 'object', 'properties': {'frame': {'type': 'integer'}, 'media': {'type': 'string'}}, 'required': ['frame']},
    'vibeedit_source_next_frame': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_source_overwrite': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'in': {'type': 'integer'}, 'media': {'type': 'string'}, 'out': {'type': 'integer'}, 'track': {'type': 'string'}}, 'required': ['media', 'out']},
    'vibeedit_source_previous_frame': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_source_show': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_source_toggle_playback': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_speech_rate': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'unit': {'type': 'string'}}, 'required': []},
    'vibeedit_speed_curve_apply': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'preset': {'type': 'string'}}, 'required': ['item', 'preset']},
    'vibeedit_srt_export': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': []},
    'vibeedit_srt_import': {'type': 'object', 'properties': {'srt': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['srt']},
    'vibeedit_storage_clear': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_storage_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_text_add': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'dur': {'type': 'integer'}, 'text': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'dur', 'text', 'track']},
    'vibeedit_text_line_style': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'line_style': {'type': 'string'}}, 'required': ['item', 'line_style']},
    'vibeedit_text_list': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': []},
    'vibeedit_text_preset_apply': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'position_x': {'type': 'number'}, 'position_y': {'type': 'number'}, 'preset': {'type': 'string'}, 'size': {'type': 'number'}}, 'required': ['item']},
    'vibeedit_text_preset_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_text_set': {'type': 'object', 'properties': {'item': {'type': 'string'}, 'text': {'type': 'string'}}, 'required': ['item', 'text']},
    'vibeedit_text_style_get': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_timeline_apply': {'type': 'object', 'properties': {'ops': {'type': 'array'}}, 'required': []},
    'vibeedit_timeline_changes': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_clip_count': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_close_gap': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': []},
    'vibeedit_timeline_cut_range': {'type': 'object', 'properties': {'end': {'type': 'integer'}, 'start': {'type': 'integer'}}, 'required': ['end', 'start']},
    'vibeedit_timeline_delete': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_timeline_deselect': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_duration': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_gaps': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_get': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_header_compact': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_lift': {'type': 'object', 'properties': {'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_timeline_move': {'type': 'object', 'properties': {'at': {'type': 'integer'}, 'item': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['at', 'item', 'track']},
    'vibeedit_timeline_move_items': {'type': 'object', 'properties': {'items': {'type': 'array'}}, 'required': ['items']},
    'vibeedit_timeline_redo': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_refresh_waveforms': {'type': 'object', 'properties': {'buckets': {'type': 'integer'}}, 'required': []},
    'vibeedit_timeline_reorder': {'type': 'object', 'properties': {'before': {'type': 'string'}, 'item': {'type': 'string'}}, 'required': ['item']},
    'vibeedit_timeline_select_all': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_sheet': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_snap': {'type': 'object', 'properties': {'frame': {'type': 'integer'}}, 'required': ['frame']},
    'vibeedit_timeline_split': {'type': 'object', 'properties': {'atFrame': {'type': 'string'}, 'item': {'type': 'string'}}, 'required': []},
    'vibeedit_timeline_undo': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_zoom_fit': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_zoom_in': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_timeline_zoom_out': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_tool_status': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_track_add': {'type': 'object', 'properties': {'kind': {'type': 'string'}, 'name': {'type': 'string'}, 'role': {'type': 'string'}}, 'required': []},
    'vibeedit_track_duration': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': ['track']},
    'vibeedit_track_get': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': ['track']},
    'vibeedit_track_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_track_remove': {'type': 'object', 'properties': {'track': {'type': 'string'}}, 'required': ['track']},
    'vibeedit_track_rename': {'type': 'object', 'properties': {'name': {'type': 'string'}, 'track': {'type': 'string'}}, 'required': ['name', 'track']},
    'vibeedit_transcript_words': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_transition_preview': {'type': 'object', 'properties': {'transition': {'type': 'string'}}, 'required': ['transition']},
    'vibeedit_transition_remove': {'type': 'object', 'properties': {'transition': {'type': 'string'}}, 'required': ['transition']},
    'vibeedit_transition_set': {'type': 'object', 'properties': {'duration': {'type': 'number'}, 'from': {'type': 'string'}, 'kind': {'type': 'string'}, 'to': {'type': 'string'}}, 'required': ['duration', 'from', 'kind', 'to']},
    'vibeedit_transitions_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_transitions_renderability': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ui_action': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ui_actions': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ui_dialog': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ui_frame': {'type': 'object', 'properties': {'time': {'type': 'number'}, 'time_s': {'type': 'number'}}, 'required': []},
    'vibeedit_ui_frames': {'type': 'object', 'properties': {'count': {'type': 'integer'}, 'times': {'type': 'array'}, 'times_s': {'type': 'array'}}, 'required': []},
    'vibeedit_ui_respond': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_ui_seek': {'type': 'object', 'properties': {'frame': {'type': 'integer'}}, 'required': ['frame']},
    # Round 24: items is OPTIONAL here (no items -> current selection,
    # see the handler); the round-22 AST extraction marked it required
    # from the later args["items"] indexing and was wrong. Required
    # lists describe what the handler demands, not what it indexes.
    'vibeedit_ui_select': {'type': 'object', 'properties': {'items': {'type': 'string'}}, 'required': []},
    'vibeedit_ui_view': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_variants_create': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_variants_diff': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']},
    'vibeedit_variants_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_view_compare': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_view_fullscreen': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_view_inspector_pane': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_view_library_pane': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_view_safe_area': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_vision_cutout': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'output': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': []},
    'vibeedit_vision_cutout_model': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'model': {'type': 'string'}, 'output': {'type': 'string'}}, 'required': ['media', 'model']},
    'vibeedit_vision_faces': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'output': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': []},
    'vibeedit_vision_text': {'type': 'object', 'properties': {'media': {'type': 'string'}, 'output': {'type': 'string'}, 'path': {'type': 'string'}}, 'required': []},
    'vibeedit_voice_check': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_voice_clone_add': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_voice_clone_list': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_voice_clone_remove': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_voice_fit': {'type': 'object', 'properties': {'frames': {'type': 'integer'}, 'item': {'type': 'string'}, 'max_ratio': {'type': 'number'}, 'min_ratio': {'type': 'number'}, 'to_frame': {'type': 'integer'}}, 'required': ['item']},
    'vibeedit_voice_lines': {'type': 'object', 'properties': {'lines': {'type': 'array'}, 'model': {'type': 'string'}, 'provider': {'type': 'string'}, 'voice': {'type': 'string'}}, 'required': ['lines']},
    'vibeedit_voice_place': {'type': 'object', 'properties': {'at': {'type': 'string'}, 'media': {'type': 'string'}}, 'required': ['media']},
    'vibeedit_voice_speak': {'type': 'object', 'properties': {'file': {'type': 'string'}, 'model': {'type': 'string'}, 'provider': {'type': 'string'}, 'text': {'type': 'string'}, 'voice': {'type': 'string'}}, 'required': ['text']},
    'vibeedit_voice_synthesize': {'type': 'object', 'properties': {'file': {'type': 'string'}, 'model': {'type': 'string'}, 'provider': {'type': 'string'}, 'text': {'type': 'string'}, 'voice': {'type': 'string'}}, 'required': ['text']},
    'vibeedit_voice_use': {'type': 'object', 'properties': {'model': {'type': 'string'}, 'provider': {'type': 'string'}, 'voice': {'type': 'string'}}, 'required': []},
    'vibeedit_windows_check': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_workflow_gates': {'type': 'object', 'properties': {}, 'required': []},
    'vibeedit_workflow_set_gates': {'type': 'object', 'properties': {'gates': {'type': 'string'}}, 'required': ['gates']},
}

# Attach: tools/list (and /api/mcp-tools) return TOOLS directly,
# so every entry carries its schema from import time on.
for _tool in TOOLS:
    _schema = TOOL_SCHEMAS.get(_tool["name"])
    if _schema is not None:
        _tool["inputSchema"] = _schema
del _tool, _schema

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
        # Round 19: one-time fps-unit migration (backs up the
        # pre-migration file via the first-save rule, then saves).
        if migrate_fps_units(data)["converted"]:
            self._save()
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

    def _refresh_if_newer(self) -> bool:
        """Reload the cached project when the disk file is NEWER.

        Round 22 P0, mirror of web State.refresh_from_disk: the
        stdio MCP server caches the project between calls in one
        process while the web app writes the same file. Without
        this, an MCP write after a web edit overwrote the web edit
        (and vice versa — the web side refresh covers the other
        direction). Reload only when disk rev > cached rev; a
        failed read never touches the cache. MCP keeps no undo
        stack (undo restores the on-disk .bak), so nothing else
        needs clearing. True simultaneous writes can still race;
        the sequential interleave is fully covered.
        """
        if self.path is None or self.project is None:
            return False
        try:
            disk = load_project(self.path)
            disk_rev = int(disk.get("rev", 0) or 0)
        except Exception:
            return False
        if disk_rev <= self.project.rev:
            return False
        self.project.restore(disk)
        return True

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
            raise self._na(name, "plugin setup and show-view "
                           "are not supported in this headless build "
                           "(no dependency recipe to run, no viewer "
                           "to show a view in); the local plugin "
                           f"system holds: {available or 'none'}. "
                           "Plugin install, search, hook execution, "
                           "option read/set, overlays, actions, views, "
                           "proposals and replacement are real "
                           "(plugins_install/plugins_search/"
                           "plugins_run/plugins_options/plugins_option/"
                           "plugins_set/plugins_overlays/"
                           "plugins_set_overlays/plugins_actions/"
                           "plugins_view/plugins_view_event/"
                           "plugins_proposal/plugins_replace); no "
                           "untrusted code is copied or executed "
                           "outside those paths")
        if name.startswith("vibeedit_voice_") or name in (
                "vibeedit_acme_voice_fast",):
            found = importlib.util.find_spec("vibeedit_core.voice")
            raise self._na(name, "no voice cloning provider is "
                           "wired in this build (generation via Edge/Piper "
                           "is wired separately); nothing is cloned")
        if name.startswith("vibeedit_agent_kit"):
            raise self._na(name, "unknown agent-kit tool; kit_check, "
                           "kit_install, kit_update and kit_later are "
                           "real in this build")
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
        "vibeedit_layer_delete", "vibeedit_captions_replace",
        "vibeedit_music_replace", "vibeedit_outcomes_import",
        "vibeedit_library_import_pack", "vibeedit_image_disclose"})

    # Round 25: tools that must NOT hold the project file lock.
    # Renders and frame extraction run for seconds to minutes and
    # never write the project file (they only set in-memory
    # last_export or render to a temp dir); transcription writes the
    # project but only after a minutes-long model run; network tools
    # (kit/plugin/update downloads) likewise never write the project
    # file. Holding the lock across any of them would wedge web
    # writes for the whole operation, so they keep the round-22
    # behaviour (refresh first, unlocked) and only a truly
    # overlapping locked write could still win over their save.
    # project_open is excluded separately in call(): it loads a new
    # path (and only ever migration-saves a file being opened).
    LONG_RUNNING_TOOLS = frozenset({
        "vibeedit_export_start", "vibeedit_export_preset",
        "vibeedit_export_normalized", "vibeedit_export_ducked",
        "vibeedit_export_preview", "vibeedit_ui_frame",
        "vibeedit_ui_frames",
        "vibeedit_captions_transcribe", "vibeedit_media_transcribe",
        "vibeedit_captions_generate",
        "vibeedit_agent_kit_update", "vibeedit_plugins_install",
        "vibeedit_plugins_download", "vibeedit_app_update_check",
        "vibeedit_app_update_download", "vibeedit_app_update_prepare"})

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
        # Round 19 aliases: show_* dialog content is the underlying
        # data tool's output (no dialog window exists in this headless
        # server); agent_quick_edit applies edits through timeline_apply.
        "vibeedit_show_about": "vibeedit_app_version",
        "vibeedit_show_commands": "vibeedit_mcp_tools_list",
        "vibeedit_show_plugins": "vibeedit_plugins_list",
        "vibeedit_show_history": "vibeedit_project_history",
        "vibeedit_show_assets": "vibeedit_media_list",
        "vibeedit_show_batch": "vibeedit_batch_status",
        "vibeedit_show_export": "vibeedit_export_status",
        "vibeedit_show_export_progress": "vibeedit_export_status",
        "vibeedit_show_review": "vibeedit_review_get",
        "vibeedit_show_doctor": "vibeedit_doctor_run",
        "vibeedit_show_agent_kit": "vibeedit_agent_kit_check",
        "vibeedit_show_updates": "vibeedit_app_update_check",
        "vibeedit_show_sections": "vibeedit_markers_list",
        "vibeedit_agent_quick_edit": "vibeedit_timeline_apply",
        # Round 21 alias: the original agent.status spec is the agent
        # kit's folder/version/skills (+ per-tab/per-CLI setup state,
        # not tracked here) — not a terminal session — so its headless
        # content is exactly agent_kit_check's data.
        "vibeedit_agent_status": "vibeedit_agent_kit_check",
    }

    def _touch_agent_status(self) -> None:
        # Round 14: one-line agent-connection status for the web dock.
        # The MCP process is separate from the web server, so it leaves
        # a last-activity stamp (timestamp only, no content) in the temp
        # dir; the web server reads it via /api/agent-status. Best
        # effort only: it must never break a tool call.
        if not self.path:
            return
        try:
            import hashlib
            import json as _json
            import os as _os
            import tempfile
            import time as _time
            folder = _os.path.dirname(_os.path.abspath(self.path))
            key = hashlib.sha1(_os.path.normcase(folder).encode()).hexdigest()[:12]
            stamp = _os.path.join(tempfile.gettempdir(), f"vibeedit-mcp-{key}.json")
            with open(stamp, "w", encoding="utf-8") as fh:
                _json.dump({"last_seen": _time.time()}, fh)
        except Exception:
            pass

    # -- Round 21: file-backed MCP debug log -----------------------
    # Mirrors the original's DebugLog design (one shared plain-text
    # file, byte-capped rotation, VIBEEDIT_DEBUG_LOG_PATH override)
    # for this headless build: one line per MCP tool invocation
    # (ISO time + resolved tool name). Arguments are NEVER recorded
    # (they may carry user content); the web server's HTTP log is a
    # separate process and is not included. Best effort only: logging
    # must never break a tool call.
    _DEBUG_LOG_MAX_BYTES = 256 * 1024
    _DEBUG_LOG_KEEP_BYTES = 128 * 1024

    def _debug_log_path(self) -> str:
        import os as _os
        import tempfile
        override = _os.environ.get("VIBEEDIT_DEBUG_LOG_PATH")
        if override:
            return override
        return _os.path.join(tempfile.gettempdir(), "vibeedit-debug.log")

    def _trim_debug_log(self, path: str) -> None:
        import os as _os
        try:
            if _os.path.getsize(path) <= self._DEBUG_LOG_MAX_BYTES:
                return
            with open(path, "rb") as fh:
                data = fh.read()
            tail = data[-self._DEBUG_LOG_KEEP_BYTES:]
            cut = tail.find(b"\n")
            if cut >= 0:
                tail = tail[cut + 1:]
            with open(path, "wb") as fh:
                fh.write(tail)
        except Exception:
            pass

    def _log_call(self, resolved_name: str) -> None:
        # Debug-log reads themselves are not logged: a read tool must
        # not pollute the log it reads, and this keeps the "no lines
        # yet" case reachable on a fresh path.
        if resolved_name == "vibeedit_app_vibeedit_debug_log":
            return
        try:
            import datetime as _dt
            stamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
            path = self._debug_log_path()
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp} {resolved_name}\n")
            self._trim_debug_log(path)
        except Exception:
            pass

    def call(self, name: str, args: dict) -> dict:
        name = self.ALIASES.get(name, name)
        # Round 24: missing required arguments fail fast as
        # ValueError naming the missing keys, before any state is
        # touched (no disk reload, no backup, no log line for a call
        # that never ran). Previously handlers indexed args directly
        # and the caller got a bare KeyError ("'at'"). TOOL_SCHEMAS
        # required lists are derived from exactly those direct
        # indexings (args["k"] -> required, args.get("k") ->
        # optional), so this check cannot reject a call the handler
        # would have accepted; honest tools have empty schemas, so
        # they still reach their NOT_AVAILABLE error unchanged.
        if not isinstance(args, dict):
            raise ValueError(
                f"{name}: arguments must be an object, got "
                f"{type(args).__name__}")
        schema = TOOL_SCHEMAS.get(name)
        if schema is not None:
            missing = [k for k in schema.get("required", [])
                       if k not in args]
            if missing:
                raise ValueError(
                    f"{name}: missing required argument(s): "
                    f"{', '.join(missing)}")
        self._touch_agent_status()
        self._log_call(name)
        # Round 25: serialize the read-modify-write critical section
        # across processes (see filelock.py). _call_inner refreshes
        # first and saves right after mutating, and the lock makes
        # that sequence atomic against the web server's locked
        # writes — the true-simultaneous race round 22 left open.
        # Long-running tools and project_open run unlocked (see
        # LONG_RUNNING_TOOLS); a call with no project open has no
        # lock file to take and fails in _call_inner as before.
        if (self.path is None or name in self.LONG_RUNNING_TOOLS
                or name == "vibeedit_project_open"):
            return self._call_inner(name, args)
        with ProjectFileLock(self.path):
            return self._call_inner(name, args)

    def _call_inner(self, name: str, args: dict) -> dict:
        # Round 22 P0: reload-before-write. Every MCP call first
        # picks up a newer disk file (web app edits) so a later
        # save cannot silently discard them. Handlers save
        # immediately after mutating, so no unsaved MCP state
        # exists at refresh time. project_open manages its own
        # path and loads from disk itself, so it skips this.
        if name != "vibeedit_project_open":
            self._refresh_if_newer()
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
        if name == "vibeedit_media_analyze":
            # Round 7: real measurement (see vibeedit_core/
            # analysis.py for the original semantics). One record
            # per media entry, keyed by file content, reused
            # unless force (force drops the record's corrections
            # with the record itself).
            from .analysis import content_key, measure_media
            from .project import fps_value as _fps_value
            proj = self._require()
            raw_media = args.get("media")
            if raw_media:
                ids = [part.strip() for part in str(raw_media)
                       .split(",") if part.strip()]
            else:
                ids = [m["id"] for m in proj.data["media"]
                       if m.get("kind") in ("video", "audio")]
            if not ids:
                raise ValueError("media_analyze needs media: no "
                                 "video or audio media in this "
                                 "project")
            force = str(args.get("force", "")).lower() in (
                "true", "1", "yes") if not isinstance(
                args.get("force"), bool) else bool(args.get("force"))
            try:
                rate = float(args.get("rate", 4.0))
            except (TypeError, ValueError):
                raise ValueError("rate must be a number between "
                                 "0.5 and 30")
            if not 0.5 <= rate <= 30:
                raise ValueError("rate must be between 0.5 and 30")
            results = []
            for media_id in ids:
                medium = proj.media(media_id)
                src = self._media_abs(proj, medium)
                key = content_key(src)
                existing = medium.get("analysis_record")
                if isinstance(existing, dict) \
                        and existing.get("key") == key and not force:
                    results.append({"media": media_id, "key": key,
                                    "reused": True, "measured": False,
                                    "hasPicture": existing.get(
                                        "picture") is not None,
                                    "hasSound": existing.get(
                                        "sound") is not None})
                    continue
                try:
                    fps = _fps_value(medium["fps"]) \
                        if medium.get("fps") else None
                except Exception:
                    fps = None
                frames = medium.get("frames")
                try:
                    frames = int(frames) if frames else None
                except (TypeError, ValueError):
                    frames = None
                record = measure_media(src, fps=fps,
                                       total_frames=frames, rate=rate)
                medium["analysis_record"] = record
                transcript = record.get("transcript") or {}
                results.append({"media": media_id,
                                "key": record["key"],
                                "reused": False, "measured": True,
                                "hasPicture": record.get("picture")
                                is not None,
                                "hasSound": record.get("sound")
                                is not None,
                                "transcriptWords": len(
                                    transcript.get("words", []) or []),
                                "transcriptReason": transcript.get(
                                    "reason")})
            self._save()
            return {"results": results}
        if name == "vibeedit_media_analysis":
            # Round 7: read the stored record when one exists
            # (derived cuts/shots/sound per MediaAnalysis+Reading);
            # otherwise the round 5 ffprobe behaviour, unchanged
            # so existing callers keep working.
            from .analysis import derive_analysis
            from .export_ops import media_metadata
            if not args.get("media"):
                raise ValueError("media_analysis needs media")
            proj = self._require()
            result = media_metadata(proj.data, proj.folder,
                                    args["media"])
            try:
                medium = proj.media(args["media"])
                record = medium.get("analysis")
                if isinstance(record, dict):
                    result["analysis_cuts"] = record.get("cuts")
                    result["analysis_cuts_detected"] = \
                        record.get("cuts_detected")
                    result["analysis_cuts_threshold"] = \
                        record.get("threshold")
                stored = medium.get("analysis_record")
                if isinstance(stored, dict):
                    def _num(key, default):
                        try:
                            return float(args.get(key, default))
                        except (TypeError, ValueError):
                            raise ValueError(f"{key} must be a "
                                             "number")
                    min_score = _num("minScore", 0.1)
                    activity_db = _num("activityDb", 10.0)
                    bridge = _num("bridgeSeconds", 0.3)
                    if not 0 <= min_score <= 1:
                        raise ValueError("minScore must be "
                                         "between 0 and 1")
                    if not 0 <= activity_db <= 80:
                        raise ValueError("activityDb must be "
                                         "between 0 and 80")
                    if not 0 <= bridge <= 10:
                        raise ValueError("bridgeSeconds must be "
                                         "between 0 and 10")
                    samples = str(args.get("samples", "")).lower() \
                        in ("true", "1", "yes") if not isinstance(
                        args.get("samples"), bool) else bool(
                        args.get("samples"))
                    curve = str(args.get("curve", "")).lower() \
                        in ("true", "1", "yes") if not isinstance(
                        args.get("curve"), bool) else bool(
                        args.get("curve"))
                    result["analysis_record"] = derive_analysis(
                        stored, min_score=min_score,
                        activity_db=activity_db,
                        bridge_seconds=bridge,
                        include_samples=samples,
                        include_curve=curve)
                    # The derived reading above overwrites the raw
                    # record that media_metadata echoed from the
                    # entry, so the large raw levels/samples are
                    # never returned; only the derived reading is.
            except ValueError:
                raise
            except Exception as exc:
                # A failed derivation must not leak the raw record
                # through the metadata echo.
                result.pop("analysis_record", None)
                result["analysis_error"] = str(exc)
            return result
        if name == "vibeedit_media_cuts":
            # Round 6: original media.cuts semantics — correct the
            # cut list of an analysed media (see vibeedit_core/
            # cuts.py for the full mapping). Detection runs on
            # first use; remeasure measures again and drops
            # earlier corrections.
            from .cuts import apply_cut_corrections, detect_cuts
            from .project import fps_value
            if not args.get("media"):
                raise ValueError("media_cuts needs media")
            proj = self._require()
            medium = proj.media(args["media"])
            src = self._media_abs(proj, medium)
            record = medium.get("analysis")
            if not isinstance(record, dict):
                record = {}
            remeasure = bool(args.get("remeasure"))
            if record.get("cuts_detected") and not remeasure:
                detected = list(record["cuts_detected"])
                threshold = record.get("threshold", 0.4)
                measured_now = False
            else:
                det = detect_cuts(
                    src, threshold=float(args.get("threshold", 0.4)))
                detected = det["cuts"]
                threshold = det["threshold"]
                measured_now = True
                record = {"cuts_detected": detected,
                          "threshold": threshold}
            try:
                raw_fps = medium.get("fps") or \
                    proj.data.get("format", {}).get("fps")
                fps = fps_value(raw_fps) if raw_fps else None
            except Exception:
                fps = None
            tolerance = (1.0 / fps) if fps else 0.04
            try:
                duration = float(medium["duration"]) \
                    if medium.get("duration") is not None else None
            except (TypeError, ValueError):
                duration = None
            current = list(record.get("cuts", detected))
            corrected = apply_cut_corrections(
                detected, current, add=args.get("add"),
                remove=args.get("remove"),
                clear=bool(args.get("clear")),
                tolerance=tolerance, duration=duration)
            record["cuts"] = corrected["cuts"]
            record["cuts_corrections"] = {
                "added": corrected["added"],
                "removed": corrected["removed"]}
            medium["analysis"] = record
            self._save()
            return {"media": medium["id"], "cuts": corrected["cuts"],
                    "detected": detected, "added": corrected["added"],
                    "removed": corrected["removed"],
                    "removed_unmatched": corrected["removed_unmatched"],
                    "threshold": threshold, "remeasured": measured_now,
                    "tolerance": round(tolerance, 4)}
        if name == "vibeedit_media_speech_map":
            # Round 7: SpeechMap.json, faithful port (see
            # analysis.py). Sound from the stored record when
            # one exists, else measured now; transcript words
            # from the record when faster-whisper measured any.
            from .analysis import (decode_sound_levels, speech_map)
            if not args.get("media"):
                raise ValueError("media_speech_map needs media")
            proj = self._require()
            medium = proj.media(args["media"])
            src = self._media_abs(proj, medium)
            stored = medium.get("analysis_record")
            sound = None
            level_source = None
            if isinstance(stored, dict) and stored.get("sound"):
                sound = stored["sound"]
                level_source = "analysis"
            if sound is None:
                sound = decode_sound_levels(src)
                level_source = "measured"
            if sound is None or not sound.get("levels"):
                raise ValueError(
                    f"Media {medium['id']} has no audio levels to "
                    "map: it has no audio track")
            def _opt(key, default, low, high):
                try:
                    value = float(args.get(key, default))
                except (TypeError, ValueError):
                    raise ValueError(f"{key} must be a number")
                if not low <= value <= high:
                    raise ValueError(f"{key} must be between {low} "
                                     f"and {high}")
                return value
            threshold = args.get("thresholdDb")
            if threshold is not None:
                try:
                    threshold = float(threshold)
                except (TypeError, ValueError):
                    raise ValueError("thresholdDb must be a number")
                if not -120 <= threshold <= 0:
                    raise ValueError("thresholdDb must be between "
                                     "-120 and 0")
            bridge = _opt("bridgeSeconds", 0.3, 0, 10)
            min_speech = _opt("minSpeechSeconds", 0.2, 0, 10)
            min_sep = _opt("minSeparationDb", 6.0, 0, 60)
            words = None
            if isinstance(stored, dict):
                transcript = stored.get("transcript") or {}
                if transcript.get("words"):
                    words = transcript["words"]
            result = speech_map(sound, words=words,
                                threshold_db=threshold,
                                bridge_seconds=bridge,
                                min_speech_seconds=min_speech,
                                min_separation_db=min_sep)
            result["media"] = medium["id"]
            result["levels"] = level_source
            return result
        if name == "vibeedit_media_strip":
            import os
            # Round 7: MediaStills.strip, faithful shape. Frames
            # at cell midpoints over from..to; levels from the
            # record or measured now; gaps from the speech map;
            # words from the stored transcript. The PNG needs
            # Pillow; without it the strip data is still returned
            # with path null and the reason stated.
            from .analysis import (decode_sound_levels,
                                   extract_frame_png, prune_strips,
                                   render_strip_png, speech_map,
                                   strip_frame_times)
            if not args.get("media"):
                raise ValueError("media_strip needs media")
            proj = self._require()
            medium = proj.media(args["media"])
            if medium.get("kind") == "image":
                raise ValueError("media_strip needs a video or "
                                 "audio media, not a still image")
            src = self._media_abs(proj, medium)
            stored = medium.get("analysis_record")
            duration = None
            for candidate in (medium.get("duration"),
                              (stored or {}).get("tech", {}).get(
                                  "seconds")):
                try:
                    if candidate is not None and float(candidate) > 0:
                        duration = float(candidate)
                        break
                except (TypeError, ValueError):
                    continue
            if duration is None:
                raise ValueError("media_strip needs a known media "
                                 "duration")
            def _range_num(key, default, low, high):
                try:
                    value = float(args.get(key, default))
                except (TypeError, ValueError):
                    raise ValueError(f"{key} must be a number")
                if not low <= value <= high:
                    raise ValueError(f"{key} must be between {low} "
                                     f"and {high}")
                return value
            from_s = _range_num("from", 0.0, 0, 86400)
            to_s = _range_num("to", duration, 0, 86400)
            if not to_s > from_s:
                raise ValueError("from must be before to, inside "
                                 "a video or audio media")
            to_s = min(to_s, duration)
            try:
                count = int(args.get("count", 8))
            except (TypeError, ValueError):
                raise ValueError("count must be an integer")
            if not 1 <= count <= 24:
                raise ValueError("count must be between 1 and 24")
            try:
                width = int(args.get("width", 1600))
            except (TypeError, ValueError):
                raise ValueError("width must be an integer")
            if not 400 <= width <= 8192:
                raise ValueError("width must be between 400 and "
                                 "8192")
            times = strip_frame_times(from_s, to_s, count)
            fps = None
            try:
                from .project import fps_value as _fps_value
                if medium.get("fps"):
                    fps = _fps_value(medium["fps"])
            except Exception:
                fps = None
            if fps is None and isinstance(stored, dict):
                pic = stored.get("picture") or {}
                fps = pic.get("fps")
            frames = []
            frame_pngs = []
            cell_width = max(160, int(width / count) * 2)
            stills_dir = os.path.join(proj.folder, "render",
                                      "stills")
            safe_id = "".join(c if c.isalnum() or c in "-_" else "_"
                              for c in medium["id"])
            for index, seconds in enumerate(times):
                if medium.get("kind") == "audio":
                    # The original's strip has no frame row for
                    # sound alone, and its returned frames list
                    # is empty for audio.
                    continue
                frame_no = int(seconds * fps) if fps else None
                frames.append({"frame": frame_no,
                               "seconds": round(seconds, 3)})
                dest = os.path.join(
                    stills_dir,
                    f"strip-{safe_id}-{index}-{int(seconds * 10)}"
                    ".png")
                try:
                    extract_frame_png(src, seconds, dest, cell_width)
                    frame_pngs.append(dest)
                except Exception:
                    frame_pngs.append(None)
            sound = None
            level_source = None
            if isinstance(stored, dict) and stored.get("sound"):
                sound = stored["sound"]
                level_source = "analysis"
            if sound is None:
                try:
                    sound = decode_sound_levels(src)
                    level_source = "measured"
                except Exception:
                    sound = None
            gaps = []
            gaps_json: dict = {"shown": False, "reason": None}
            if sound is not None and sound.get("levels"):
                mapped = speech_map(sound)
                if mapped.get("gaps") is not None:
                    shown = [g for g in mapped["gaps"]
                             if g["end"] > from_s
                             and g["start"] < to_s]
                    gaps = [(g["start"], g["end"]) for g in shown]
                    gaps_json = {"shown": True, "count": len(shown)}
                else:
                    gaps_json = {"shown": False,
                                 "reason": mapped.get("reason")}
            words = []
            if isinstance(stored, dict):
                transcript = stored.get("transcript") or {}
                words = [w for w in transcript.get("words", []) or []
                         if w["end"] > from_s and w["start"] < to_s]
            path = None
            png_reason = None
            height = None
            if medium.get("kind") != "audio":
                try:
                    canvas, width, height = render_strip_png(
                        [p for p in frame_pngs],
                        times,
                        sound["levels"] if sound else None,
                        sound["window"] if sound else 0.1, 0.0,
                        gaps, words, from_s, to_s, width)
                    import os as _os
                    _os.makedirs(stills_dir, exist_ok=True)
                    path = _os.path.join(
                        stills_dir,
                        f"strip-{safe_id}-{int(from_s * 10)}-"
                        f"{int(to_s * 10)}-{width}.png")
                    canvas.save(path)
                    prune_strips(stills_dir)
                except RuntimeError as exc:
                    png_reason = str(exc)
            else:
                png_reason = ("Audio has no picture row; the "
                               "strip data (levels, gaps, words) "
                               "is returned without a PNG")
            return {"path": path, "pngReason": png_reason,
                    "media": medium["id"], "width": width,
                    "height": height, "from": round(from_s, 3),
                    "to": round(to_s, 3), "frames": frames,
                    "levels": level_source, "gaps": gaps_json,
                    "words": len(words)}
        if name == "vibeedit_media_sync":
            # Round 7: AudioSync, faithful port (see analysis.py).
            # Offset: time in 'to' = time in 'media' + offset.
            # Correlation below 0.4 means no shared sound, even
            # when the halves happen to agree.
            from .analysis import align_sound
            if not args.get("media") or not args.get("to"):
                raise ValueError("media_sync needs media and to")
            proj = self._require()
            first = proj.media(args["media"])
            second = proj.media(args["to"])
            result = align_sound(self._media_abs(proj, first),
                                 self._media_abs(proj, second))
            result["media"] = first["id"]
            result["to"] = second["id"]
            item_id = args.get("item")
            if item_id:
                found = None
                for track in proj.data["tracks"]:
                    for item in track["items"]:
                        if item["id"] == item_id:
                            found = item
                            break
                    if found is not None:
                        break
                if found is None:
                    raise ValueError(f"Unknown timeline item: "
                                     f"{item_id}")
                if found.get("media") != first["id"]:
                    raise ValueError("item is not a clip of the "
                                     "media given")
                from .project import fps_value as _fps_value
                try:
                    fps_first = _fps_value(first["fps"]) \
                        if first.get("fps") else None
                except Exception:
                    fps_first = None
                try:
                    fps_second = _fps_value(second["fps"]) \
                        if second.get("fps") else None
                except Exception:
                    fps_second = None
                fps_first = fps_first or _fps_value(proj.fps)
                fps_second = fps_second or _fps_value(proj.fps)
                in_seconds = int(found.get("in", 0)) / fps_first
                to_seconds = in_seconds + result["offsetSeconds"]
                result["item"] = {
                    "item": item_id,
                    "mediaInFrame": int(found.get("in", 0)),
                    "mediaInSeconds": round(in_seconds, 3),
                    "toSeconds": round(to_seconds, 3),
                    "toFrame": int(round(to_seconds * fps_second))}
            return result
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
            # Round 19: in/out are SOURCE frames, dur is PROJECT
            # frames — convert the span (see project.py).
            medium = proj.media(args["media"])
            result = proj.add_clip(
                args["media"], track_id, int(args.get("at", 0)), in_frame,
                source_span_to_project_frames(
                    out_frame - in_frame, medium.get("fps"),
                    proj.data["format"]["fps"]),
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
        if name == "vibeedit_ui_select":
            # Round 19: targeted session selection (timeline_select_all
            # selects everything; this sets exactly the given items).
            if args.get("items") is None:
                return {"selection": list(self.selection)}
            proj = self._require()
            known = {i["id"] for t in proj.data["tracks"]
                     for i in t["items"]}
            wanted = [str(i) for i in args["items"]]
            unknown = [i for i in wanted if i not in known]
            if unknown:
                raise ValueError(
                    f"ui_select: unknown timeline items: {unknown}")
            self.selection = wanted
            return {"selection": list(self.selection)}
        if name == "vibeedit_ui_seek":
            # Round 19: absolute set for the same session playhead the
            # playhead_* step tools move (they only step relatively).
            if "frame" not in args:
                raise ValueError("ui_seek: pass frame (int, >= 0)")
            try:
                frame = int(args["frame"])
            except (TypeError, ValueError):
                raise ValueError("ui_seek: frame must be an int")
            self.playhead_frame = max(0, frame)
            return {"frame": self.playhead_frame}
        if name == "vibeedit_show_shortcuts":
            # Round 20: derived from the live app.js, never hand-kept.
            import os
            app_js = os.path.join(
                os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))),
                "static", "app.js")
            return shortcuts_from_app_js(app_js)
        if name in ("vibeedit_ui_frame", "vibeedit_ui_frames"):
            # Round 20: render the timeline (draft preset) with FFmpeg
            # and extract real composed frames at the requested times.
            # No live player exists headless, so the render IS the
            # player-frame source; a media first frame would be wrong
            # here (it shows the source, not the timeline at that time).
            import base64
            import os
            import shutil
            import subprocess
            import tempfile
            from .project import fps_value
            from .render import find_tool, render
            proj = self._require()
            fps = fps_value(proj.fps)
            duration = proj.duration_seconds()
            if duration <= 0 or not fps:
                raise ValueError(
                    "ui_frame: timeline is empty, nothing to render")
            if name == "vibeedit_ui_frame":
                if args.get("time") is None and args.get("time_s") is None:
                    times = [self.playhead_frame / fps]
                else:
                    raw = (args["time"] if args.get("time") is not None
                           else args.get("time_s"))
                    try:
                        times = [float(raw)]
                    except (TypeError, ValueError):
                        raise ValueError(
                            "ui_frame: time must be a number of seconds")
            else:
                if args.get("times") is not None or \
                        args.get("times_s") is not None:
                    raw_list = (args["times"]
                                if args.get("times") is not None
                                else args.get("times_s"))
                    try:
                        times = [float(t) for t in raw_list]
                    except (TypeError, ValueError):
                        raise ValueError(
                            "ui_frames: times must be numbers of seconds")
                else:
                    try:
                        count = int(args.get("count", 5))
                    except (TypeError, ValueError):
                        raise ValueError("ui_frames: count must be an int")
                    if count < 1:
                        raise ValueError("ui_frames: count must be >= 1")
                    times = [duration * (i + 0.5) / count
                             for i in range(count)]
            for t in times:
                if not 0 <= t < duration:
                    raise ValueError(
                        f"ui_frame: time {t} outside timeline "
                        f"[0, {duration})")
            tmp = tempfile.mkdtemp(prefix="vibeedit-frame-")
            try:
                out = os.path.join(tmp, "timeline.mp4")
                render(proj.data, proj.folder, out, preset="draft")
                ffmpeg = find_tool("ffmpeg")
                frames = []
                for t in times:
                    png = os.path.join(tmp, f"frame-{len(frames)}.png")
                    proc = subprocess.run(
                        [ffmpeg, "-v", "error", "-i", out,
                         "-ss", repr(t), "-frames:v", "1", "-y", png],
                        capture_output=True, text=True)
                    if proc.returncode != 0 or not os.path.isfile(png):
                        raise ValueError(
                            f"ui_frame: could not extract frame at {t}s: "
                            f"{proc.stderr.strip()}")
                    with open(png, "rb") as fh:
                        raw = fh.read()
                    if raw[:8] != b"\x89PNG\r\n\x1a\n" or len(raw) < 24:
                        raise ValueError(
                            "ui_frame: FFmpeg did not produce a PNG frame")
                    frames.append({
                        "time": t,
                        "width": int.from_bytes(raw[16:20], "big"),
                        "height": int.from_bytes(raw[20:24], "big"),
                        "png_base64": base64.b64encode(raw).decode(),
                    })
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if name == "vibeedit_ui_frame":
                return {"frame": frames[0], "preset": "draft",
                        "duration": duration,
                        "playhead_frame": self.playhead_frame}
            return {"frames": frames, "preset": "draft",
                    "duration": duration}
        if name == "vibeedit_context_get":
            # Round 19: headless equivalent of live editor context — a
            # snapshot assembled from the open project + session state.
            proj = self._require()
            tracks = proj.data["tracks"]
            items = [i for t in tracks for i in t["items"]]
            return {
                "name": proj.data.get("name"),
                "rev": proj.rev,
                "playhead_frame": self.playhead_frame,
                "selection": list(self.selection),
                "zoom_px_per_s": self.zoom_px_per_s,
                "source_frame": self.source_frame,
                "source_marks": dict(self.source_marks),
                "tracks": len(tracks),
                "items": len(items),
                "duration_seconds": round(proj.duration_seconds(), 3),
                "markers": proj.data.get("markers", []),
            }
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
            source = str(args.get("source", "local") or "local").strip().lower()
            if source not in ("local", "registry", "all"):
                raise ValueError(
                    "plugins_search: source must be local, registry or all")
            plugins = []
            registry_error = None
            if source in ("local", "all"):
                plugins = [p for p in list_plugins(args.get("plugins_dir"))
                           if p["name"] != "_errors"]
                if query:
                    plugins = [p for p in plugins
                               if query in p["name"].lower()
                               or query in p.get("description", "").lower()
                               or any(query in h.lower()
                                      for h in p.get("hooks", []))]
            registry_results = []
            if source in ("registry", "all"):
                # Round 15: registry fetch failure is reported, never
                # silently replaced by local results.
                from . import round15 as _r15
                try:
                    registry, meta = _r15.fetch_registry(
                        cache_path=_r15.registry_cache_path(
                            args.get("plugins_dir")))
                    registry_results = _r15.search_registry(
                        registry, args.get("query", ""))
                except Exception as exc:
                    if source == "registry":
                        raise ValueError(
                            f"plugins_search: registry fetch failed: "
                            f"{exc}") from exc
                    registry_error = str(exc)
            return {"query": args.get("query", ""), "source": source,
                    "plugins": plugins, "count": len(plugins),
                    "registry": registry_results,
                    "registry_count": len(registry_results),
                    "registry_error": registry_error}
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
        if name == "vibeedit_plugins_options":
            # Round 6: original plugins.options semantics — schema,
            # scope and current values (see vibeedit_core/
            # plugins.py). Reading needs no open project; without
            # one, project-scope options report their defaults and
            # the reply says so.
            from .plugins import (get_plugin_options,
                                  get_plugin_option_values)
            plugin = args.get("plugin") or args.get("plugin_id")
            if not plugin:
                raise ValueError("plugins_options needs plugin")
            try:
                proj = self._require()
                project_data = proj.data
                project_open = True
            except RuntimeError:
                project_data = None
                project_open = False
            schema = get_plugin_options(
                plugin, plugins_dir=args.get("plugins_dir"))
            values = get_plugin_option_values(
                plugin, plugins_dir=args.get("plugins_dir"),
                project_data=project_data)
            return {"plugin": plugin, "project_open": project_open,
                    "options": [{**opt, "value": values[opt["id"]]}
                                for opt in schema]}
        if name == "vibeedit_plugins_option":
            # Round 6: original plugins.option semantics — set one
            # option, omit value to reset to default. Project-scope
            # values are saved with the project; user-scope values
            # go to plugins.json. Values are validated against the
            # declared schema before anything is written.
            from .plugins import set_plugin_option
            plugin = args.get("plugin") or args.get("plugin_id")
            option = args.get("option")
            if not plugin or not option:
                raise ValueError("plugins_option needs plugin and option")
            from .plugins import get_plugin_options
            schema = get_plugin_options(
                plugin, plugins_dir=args.get("plugins_dir"))
            entry = next((o for o in schema if o["id"] == option), None)
            if entry is None:
                raise ValueError(
                    f"Unknown option {option!r} for plugin {plugin!r}")
            if entry["scope"] == "project":
                proj = self._require()
                result = set_plugin_option(
                    plugin, option, args.get("value"),
                    plugins_dir=args.get("plugins_dir"),
                    project_data=proj.data)
                self._save()
            else:
                result = set_plugin_option(
                    plugin, option, args.get("value"),
                    plugins_dir=args.get("plugins_dir"))
            return result
        if name == "vibeedit_plugins_set":
            # Round 6: original plugins.set turns a plugin (or its
            # hooks) off; agents can only turn them off, turning on
            # stays with the user in the Plugins sheet. This port
            # already has plugin_enable/plugin_disable, so set
            # mirrors those switches for the enabled flag.
            # Per-hook switches do not exist in this build and are
            # refused plainly instead of pretended.
            from .plugins import set_plugin_enabled
            plugin = args.get("plugin") or args.get("plugin_id")
            if not plugin:
                raise ValueError("plugins_set needs plugin")
            if args.get("hooks") is not None:
                raise ValueError(
                    "Per-hook switches are not supported in this "
                    "build; use plugins_set with enabled only")
            if args.get("enabled") is None:
                raise ValueError("plugins_set needs enabled (true/false)")
            enabled = args["enabled"]
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() in (
                    "true", "on", "1", "yes")
            return set_plugin_enabled(plugin, bool(enabled),
                                      plugins_dir=args.get("plugins_dir"))
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
        if name == "vibeedit_skills_import_plan":
            from .skill_import import plan_import
            return plan_import(args["path"], args.get("skills_dir"))
        if name == "vibeedit_skills_import":
            from .skill_import import apply_import
            return apply_import(args["path"],
                                overwrite=bool(args.get("overwrite",
                                                        False)),
                                only=args.get("only"),
                                skills_dir=args.get("skills_dir"))
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
            # Round 24: source is required ONLY on the local path;
            # the registry path takes registry_plugin instead, so the
            # schema cannot list source as required. Neither given
            # still fails as ValueError, never a bare KeyError.
            if not args.get("registry_plugin") and not args.get("source"):
                raise ValueError(
                    "plugins_install needs source (local folder/.zip) "
                    "or registry_plugin (verified registry release)")
            if args.get("registry_plugin"):
                # Round 15: verified registry install. The caller's
                # explicit install command is the approval in
                # headless MCP; nothing runs before validation.
                from . import round15 as _r15
                registry, _meta = _r15.fetch_registry(
                    cache_path=_r15.registry_cache_path(
                        args.get("plugins_dir")))
                return _r15.install_registry_plugin(
                    registry, args["registry_plugin"],
                    version=args.get("registry_version"),
                    plugins_dir=args.get("plugins_dir"),
                    overwrite=bool(args.get("overwrite", False)))
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
            if str(args.get("check_registry", "")).lower() in (
                    "true", "1", "yes") or args.get("check_registry") is True:
                from . import round15 as _r15
                registry, _meta = _r15.fetch_registry(
                    cache_path=_r15.registry_cache_path(
                        args.get("plugins_dir")))
                return _r15.check_registry_updates(
                    args["plugin"], registry,
                    plugins_dir=args.get("plugins_dir"))
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
        if name == "vibeedit_clip_backdrop":
            # Round 9: original clip.backdrop (see project.py
            # validate_backdrop / set_backdrop). Items come from
            # "items" (comma separated), a single "item", or the
            # server selection — the original's default. All items
            # are validated before any is changed, so a bad id
            # cannot leave a half-applied multi-item edit.
            from .project import validate_backdrop
            proj = self._require()
            raw = args.get("items", "")
            if isinstance(raw, str):
                ids = [s.strip() for s in raw.split(",") if s.strip()]
            elif isinstance(raw, list):
                ids = [str(s) for s in raw]
            else:
                ids = []
            if not ids and args.get("item"):
                ids = [args["item"]]
            if not ids:
                ids = list(self.selection)
            if not ids:
                raise ValueError(
                    "clip_backdrop needs item or items, or a server "
                    "selection (timeline_select_all)")
            kind = args.get("kind")
            if kind is None:
                raise ValueError(
                    "clip_backdrop needs kind: blur, color or none")
            backdrop = None
            if kind != "none":
                backdrop = {"kind": kind}
                if args.get("color") is not None:
                    backdrop["color"] = args["color"]
                if args.get("blur") is not None:
                    backdrop["blur"] = args["blur"]
                if args.get("dim") is not None:
                    backdrop["dim"] = args["dim"]
                backdrop = validate_backdrop(backdrop)
                for item_id in ids:
                    track, item = proj.item(item_id)
                    if "media" not in item \
                            or track.get("kind") != "video":
                        raise ValueError(
                            "Backdrop applies to video clips or "
                            "images only")
                    if track.get("role") != "main":
                        raise ValueError(
                            "Backdrop renders on the main track "
                            "only in this build")
            for item_id in ids:
                proj.set_backdrop(item_id, backdrop)
            self._save()
            return {"rev": proj.rev, "items": ids,
                    "backdrop": backdrop}
        if name in ("vibeedit_run_dismiss", "vibeedit_run_toggle",
                    "vibeedit_run_follow", "vibeedit_run_fix_issues",
                    "vibeedit_run_another_recipe"):
            # Round 9: run-panel actions (see round9.py). The
            # state actions save; the follow-up drafters do not
            # mutate the project, so they do not save.
            from . import round9 as _r9
            proj = self._require()
            if name == "vibeedit_run_dismiss":
                result = _r9.run_panel_dismiss(proj)
                self._save()
            elif name == "vibeedit_run_toggle":
                result = _r9.run_panel_toggle(proj)
                self._save()
            elif name == "vibeedit_run_follow":
                on = args.get("follow")
                if on is None:
                    flag = None
                elif isinstance(on, bool):
                    flag = on
                else:
                    flag = str(on).lower() in ("true", "1", "yes")
                result = _r9.run_panel_follow(proj, flag)
                self._save()
            elif name == "vibeedit_run_fix_issues":
                output = None
                if self.last_export and self.last_export.get("output"):
                    output = self.last_export["output"]
                result = _r9.run_fix_issues(proj, output)
            else:
                result = _r9.run_another_recipe(proj)
            return result
        if name == "vibeedit_plugins_show_view":
            # Round 9: original plugins.show-view (see round9.py).
            # Only a shown (non-inspector) view mutates state, so
            # only then is the project saved. Missing parameters
            # are a controlled ValueError, never a KeyError (the
            # round 3 handler rule).
            from . import round9 as _r9
            proj = self._require()
            if not args.get("plugin") or not args.get("view"):
                raise ValueError(
                    "plugins_show_view needs plugin and view")
            result = _r9.show_plugin_view(
                proj, args["plugin"], args["view"],
                args.get("plugins_dir"))
            if result.get("shown"):
                self._save()
            return result
        # Round 8: state/workflow + local-data tools (see
        # vibeedit_core/round8.py and plugins.py for the logic).
        if name in ("vibeedit_clip_motion",
                    "vibeedit_clip_change_framing",
                    "vibeedit_music_replace", "vibeedit_narration_windows",
                    "vibeedit_outcomes_import", "vibeedit_outcomes_map",
                    "vibeedit_run_append", "vibeedit_run_checklist",
                    "vibeedit_media_describe", "vibeedit_media_description",
                    "vibeedit_media_digest", "vibeedit_speech_rate",
                    "vibeedit_image_style", "vibeedit_image_disclose",
                    "vibeedit_image_generate_list",
                    "vibeedit_library_export_pack",
                    "vibeedit_library_import_pack",
                    "vibeedit_library_analyze",
                    "vibeedit_library_brand_pose",
                    "vibeedit_agent_kit_check",
                    "vibeedit_agent_kit_install",
                    "vibeedit_agent_kit_update",
                    "vibeedit_agent_kit_later",
                    "vibeedit_agent_terminals",
                    "vibeedit_app_vibeedit_automation_clients",
                    "vibeedit_app_vibeedit_debug_log",
                    "vibeedit_voice_clone_list",
                    "vibeedit_ui_dialog",
                    "vibeedit_chat_status",
                    "vibeedit_plugins_overlays",
                    "vibeedit_plugins_set_overlays",
                    "vibeedit_plugins_actions", "vibeedit_plugins_view",
                    "vibeedit_plugins_view_event",
                    "vibeedit_plugins_proposal",
                    "vibeedit_plugins_replace"):
            from . import round8 as _r8
            from .plugins import (
                apply_plugin_proposal, get_plugin_view,
                list_plugin_actions, list_plugin_overlays,
                plugin_view_event, replace_plugin,
                set_plugin_overlays)
            pdir = args.get("plugins_dir")

            def _bool(value, default=False):
                if isinstance(value, bool):
                    return value
                if value is None:
                    return default
                return str(value).lower() in ("true", "1", "yes")

            def _json_arg(value):
                if isinstance(value, str):
                    return json.loads(value)
                return value
            if name == "vibeedit_clip_motion":
                proj = self._require()
                result = _r8.apply_motion(
                    proj, args["item"], preset=args.get("preset"),
                    keyframes=args.get("keyframes"),
                    focus=args.get("focus"), within=args.get("within"))
                self._save()
                return result
            if name == "vibeedit_clip_change_framing":
                proj = self._require()
                result = _r8.change_framing(proj, args["item"])
                self._save()
                return result
            if name == "vibeedit_music_replace":
                proj = self._require()
                result = _r8.music_replace(
                    proj, media_id=args.get("media"),
                    library_id=args.get("library"),
                    loop=_bool(args.get("loop"), True))
                self._save()
                return result
            if name == "vibeedit_narration_windows":
                proj = self._require()
                return _r8.narration_windows(
                    proj,
                    min_seconds=float(args.get("minSeconds",
                                             args.get("min_seconds", 1.0))),
                    rate=(float(args["rate"])
                          if args.get("rate") is not None else None))
            if name == "vibeedit_outcomes_import":
                proj = self._require()
                payload = args.get("payload", args.get("data"))
                if payload is None and args.get("path"):
                    with open(args["path"], encoding="utf-8") as fh:
                        payload = fh.read()
                    if args["path"].lower().endswith(".json"):
                        payload = json.loads(payload)
                result = _r8.import_outcomes(
                    proj, args["export"], payload)
                self._save()
                return result
            if name == "vibeedit_outcomes_map":
                proj = self._require()
                return _r8.map_outcomes(
                    proj, args["export"],
                    window_seconds=float(args.get("window", 5.0)))
            if name == "vibeedit_run_append":
                proj = self._require()
                fields = {}
                for key in ("stage", "status", "evidence", "reason",
                            "name", "origin", "verifiedBy", "point",
                            "verdict", "findings", "by", "text",
                            "progress", "eta", "round", "fixed", "left",
                            "measured", "notMeasured"):
                    if args.get(key) is not None:
                        fields[key] = args[key]
                if args.get("data") is not None:
                    data = _json_arg(args["data"])
                    if isinstance(data, dict):
                        fields.update(data)
                result = _r8.append_run_entry(proj, args["kind"],
                                              fields)
                self._save()
                return result
            if name == "vibeedit_run_checklist":
                return _r8.run_checklist(self._require())
            if name == "vibeedit_media_describe":
                proj = self._require()
                result = _r8.describe_media(
                    proj, args["media"], _json_arg(args["shots"]),
                    append=_bool(args.get("append")))
                self._save()
                return result
            if name == "vibeedit_media_description":
                return _r8.media_description(
                    self._require(), args.get("media"))
            if name == "vibeedit_media_digest":
                return _r8.media_digest(self._require(),
                                        args["media"])
            if name == "vibeedit_speech_rate":
                return _r8.speech_rate(self._require(),
                                       args.get("media"),
                                       args.get("unit"))
            if name == "vibeedit_image_style":
                proj = self._require()
                result = _r8.image_style(
                    proj, style=args.get("style"),
                    references=args.get("references"),
                    seed=args.get("seed"),
                    disclosure=args.get("disclosure"),
                    clear=_bool(args.get("clear")))
                self._save()
                return result
            if name == "vibeedit_image_disclose":
                proj = self._require()
                result = _r8.image_disclose(proj, args.get("text"))
                self._save()
                return result
            if name == "vibeedit_image_generate_list":
                return _r8.image_generate_list(self._require())
            if name == "vibeedit_library_export_pack":
                proj = self._require()
                return _r8.export_pack(
                    proj, args["output"], pack=args.get("pack"),
                    kind=args.get("kind"))
            if name == "vibeedit_library_import_pack":
                proj = self._require()
                result = _r8.import_pack(
                    proj, args["path"],
                    replace=_bool(args.get("replace")))
                self._save()
                return result
            if name == "vibeedit_library_analyze":
                proj = self._require()
                result = _r8.analyze_library_item(
                    proj, args.get("item", args.get("entry")),
                    media_path=args.get("media_path"))
                self._save()
                return result
            if name == "vibeedit_library_brand_pose":
                proj = self._require()
                if args.get("generate") is not None:
                    raise ValueError(
                        "library.brand-pose generate needs an "
                        "image.generate provider, which is not "
                        "wired in this build; pass image or media "
                        "for the cutout path")
                result = _r8.brand_pose_image(
                    proj, args["brand"], args["pose"],
                    image=args.get("image"),
                    media_id=args.get("media"))
                self._save()
                return result
            if name == "vibeedit_agent_kit_check":
                from . import round15 as _r15
                return _r15.kit_status(
                    args.get("kit_dir"),
                    check_updates=_bool(args.get("check_updates", False)))
            if name == "vibeedit_agent_kit_install":
                return _r8.kit_install_skills(args["path"],
                                              args.get("kit_dir"))
            if name == "vibeedit_agent_kit_update":
                from . import round15 as _r15
                return _r15.kit_update(args.get("kit_dir"),
                                       version=args.get("version"))
            if name == "vibeedit_agent_kit_later":
                from . import round15 as _r15
                days = args.get("days", 7)
                try:
                    days = int(days)
                except (TypeError, ValueError):
                    raise ValueError(
                        "agent_kit_later: days must be an integer") from None
                return _r15.kit_later(args.get("kit_dir"), days=days)
            if name == "vibeedit_agent_terminals":
                # Round 22: same shape as the original's
                # agent.terminals (ProjectDocument+Terminals.swift):
                # choices, unavailable plugin terminals, open tabs.
                # All three are empty by design here: no dock, no
                # agent sessions, and no terminal field in plugin
                # manifests (see plugins._validate_manifest), so no
                # plugin can register a terminal either.
                return {"terminals": [], "unavailable": [], "tabs": []}
            if name == "vibeedit_app_vibeedit_automation_clients":
                # Round 22: the original lists clients of its
                # Unix-socket automation server (UnixSocket.swift);
                # this headless server has no such socket and no
                # client registry, so the list is always empty.
                return {"clients": []}
            if name == "vibeedit_voice_clone_list":
                # Round 24: empty by design, same precedent as
                # agent_terminals (round 22): no cloning provider
                # model exists in this build, so no clone can be
                # created or stored (voice.py deliberately
                # implements no cloning). Voiceover takes are not
                # clones and are listed elsewhere.
                return {"clones": []}
            if name == "vibeedit_ui_dialog":
                # Round 24: empty by design: the headless server
                # has no window, so it never has an open dialog;
                # the web UI's dialogs live in the browser.
                return {"dialogs": []}
            if name == "vibeedit_chat_status":
                # Round 24: empty by design: chat agents are plugins
                # with the agent.chat capability; the port's plugin
                # manifests carry hooks, not capabilities, and
                # registry plugins are macOS-only and never
                # executed, so no chat agent can exist here.
                return {"agents": []}
            if name == "vibeedit_app_vibeedit_debug_log":
                # Round 21: read back exactly the lines this server
                # wrote (see _log_call); never invent lines.
                import os as _os
                try:
                    wanted = int(args.get("lines", 100))
                except (TypeError, ValueError):
                    raise ValueError(
                        "debug_log: lines must be an int") from None
                if wanted < 1 or wanted > 1000:
                    raise ValueError(
                        "debug_log: lines must be between 1 and 1000")
                path = self._debug_log_path()
                if not _os.path.isfile(path):
                    return {"path": path, "lines": [], "total": 0,
                            "note": "no log lines yet"}
                with open(path, encoding="utf-8",
                          errors="replace") as fh:
                    all_lines = fh.read().splitlines()
                return {"path": path,
                        "lines": all_lines[-wanted:],
                        "total": len(all_lines)}
            if name == "vibeedit_plugins_overlays":
                return list_plugin_overlays(args.get("plugin"), pdir)
            if name == "vibeedit_plugins_set_overlays":
                return set_plugin_overlays(
                    args["plugin"], _json_arg(args["overlays"]), pdir)
            if name == "vibeedit_plugins_actions":
                return list_plugin_actions(args.get("query"),
                                           args.get("plugin"), pdir)
            if name == "vibeedit_plugins_view":
                return get_plugin_view(args["plugin"], args["view"],
                                       pdir)
            if name == "vibeedit_plugins_view_event":
                view = get_plugin_view(args["plugin"], args["view"],
                                       pdir)
                comp = next((c for c in view["components"]
                             if c["id"] == args["node"]), None)
                project = None
                if comp is not None and comp.get("action") \
                        and args.get("type", "click") in (
                            "click", "row-button"):
                    project = self._require()
                result = plugin_view_event(
                    args["plugin"], args["view"], args["node"],
                    args.get("type", "click"), args.get("value"),
                    project=project, plugins_dir=pdir)
                if project is not None:
                    self._save()
                return result
            if name == "vibeedit_plugins_proposal":
                proj = self._require()
                result = apply_plugin_proposal(
                    proj, args["id"], args["decision"])
                self._save()
                return result
            if name == "vibeedit_plugins_replace":
                return replace_plugin(args["plugin"], args["path"],
                                      pdir)
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


def handle(server: MCPServer, request: dict) -> dict | None:
    method = request.get("method")
    req_id = request.get("id")
    # Round 22: JSON-RPC notifications never get a response.
    # Previously every notification (e.g. notifications/initialized,
    # which carries no "id") fell through to the unknown-method
    # error branch and the server answered -32603 "Unknown method",
    # which can disconnect spec-strict clients. A request without
    # an "id" field, and any notifications/* method by name, is a
    # notification: return None and serve() writes nothing.
    # Unknown methods WITH an id still get the -32603 error.
    if "id" not in request or str(method or "").startswith("notifications/"):
        return None
    try:
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "capabilities": {"tools": {}, "resources": {}},
                      "serverInfo": {"name": "vibeedit-mcp", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "resources/list":
            # Round 23 (optional): let MCP clients discover skills
            # without a tools/call. URIs are vibeedit-skill://<id>;
            # this path never touches tools/*.
            from .skills import list_skills
            result = {"resources": [
                {"uri": "vibeedit-skill://%s" % (entry["id"],),
                 "name": entry["id"],
                 "mimeType": "text/markdown"}
                for entry in list_skills()]}
        elif method == "resources/read":
            params = request.get("params", {})
            uri = params.get("uri", "")
            if not uri.startswith("vibeedit-skill://"):
                raise ValueError(
                    "Unknown resource uri: %r" % (uri,))
            from .skills import get_skill
            skill_id = uri[len("vibeedit-skill://"):]
            result = {"contents": [
                {"uri": uri, "mimeType": "text/markdown",
                 "text": get_skill(None, skill_id)}]}
        elif method == "tools/call":
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("tools/call requires params to be an object")
            tool_name = params.get("name")
            if not isinstance(tool_name, str) or not tool_name:
                raise ValueError(
                    "tools/call requires params.name to be a tool name")
            result = server.call(tool_name, params.get("arguments", {}))
        else:
            raise ValueError(f"Unknown method: {method}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:  # noqa: BLE001 - surfaced to the MCP client
        return {"jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32603, "message": str(exc)}}


def serve(folder: str | None = None) -> None:
    server = MCPServer(folder)
    server._touch_agent_status()
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
        # Round 22: handle() returns None for notifications; write
        # nothing for them (writing "null" would still be a
        # protocol-violating response).
        response = handle(server, request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    serve(sys.argv[1] if len(sys.argv) > 1 else None)
