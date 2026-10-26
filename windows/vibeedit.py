#!/usr/bin/env python3
"""VibeEdit Windows MVP command line.

Usage (run from the repo root, or from windows/ with adjusted paths):
    python windows/vibeedit.py new <name> [--dir DIR] [--width W] [--height H]
    python windows/vibeedit.py open <project-folder-or-file>
    python windows/vibeedit.py list <project>
    python windows/vibeedit.py timeline <project>
    python windows/vibeedit.py add <project> <media> <track> <at> [--in N] [--dur N] [--speed S]
    python windows/vibeedit.py text <project> <track> <at> <dur> "<text>"
    python windows/vibeedit.py trim <project> <item> <start|end> <toFrame>
    python windows/vibeedit.py split <project> <item> <atFrame>
    python windows/vibeedit.py move <project> <item> <track> <at>
    python windows/vibeedit.py delete <project> <item>
    python windows/vibeedit.py speed <project> <item> <speed>
    python windows/vibeedit.py undo <project>
    python windows/vibeedit.py export <project> [--preset draft|full] [--out FILE]
    python windows/vibeedit.py serve [--project DIR] [--port 8000]
    python windows/vibeedit.py mcp [project]
    python windows/vibeedit.py transition <project> <from> <to> <kind> <dur_s>
    python windows/vibeedit.py keyframe <project> <item> <at_s> <property> <value>
    python windows/vibeedit.py color <project> <item> [--lut FILE] [--preset NAME]
    python windows/vibeedit.py srt-import <project> <file> [--track t1]
    python windows/vibeedit.py srt-export <project> <file> [--track t1]

Times in CLI arguments are frames (the original's unit), except
export durations reported in seconds. Media paths in ``add`` are
stored relative to the project folder when possible; run
``probe``-style metadata is filled from ffprobe when the file exists.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vibeedit_core.project import (Project, load_project, save_project,
                                   new_project, find_project_file,
                                   PROJECT_FILENAME, fps_value)
from vibeedit_core.render import probe_media, render


def _open(path: str) -> tuple[Project, str]:
    if os.path.isdir(path):
        found = find_project_file(path)
        if not found:
            raise FileNotFoundError(f"No project file in folder: {path}")
        path = found
    data = load_project(path)
    return Project(data, os.path.dirname(os.path.abspath(path))), path


def _save_with_backup(proj: Project, path: str) -> None:
    if os.path.isfile(path):
        shutil.copyfile(path, path + ".bak")
    save_project(proj.data, path)


def cmd_new(args) -> int:
    folder = os.path.join(args.dir, args.name)
    os.makedirs(os.path.join(folder, "media"), exist_ok=True)
    os.makedirs(os.path.join(folder, "render"), exist_ok=True)
    data = new_project(args.name, width=args.width, height=args.height)
    path = os.path.join(folder, PROJECT_FILENAME)
    save_project(data, path)
    print(path)
    return 0


def cmd_open(args) -> int:
    proj, path = _open(args.path)
    print(f"{path}  rev={proj.rev}  {proj.width}x{proj.height}  "
          f"{proj.duration_seconds():.2f}s  tracks={len(proj.data['tracks'])}")
    return 0


def cmd_list(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps({"media": proj.data["media"],
                      "tracks": proj.data["tracks"]}, indent=2,
                     ensure_ascii=False))
    return 0


def cmd_timeline(args) -> int:
    proj, _ = _open(args.path)
    print(proj.timeline_text())
    return 0


def cmd_add(args) -> int:
    proj, path = _open(args.path)
    rel = args.media
    abs_media = rel if os.path.isabs(rel) else os.path.join(proj.folder, rel)
    if not os.path.isfile(abs_media):
        raise FileNotFoundError(f"Media file not found: {abs_media}")
    info = probe_media(abs_media)
    medium = proj.add_media(
        os.path.relpath(abs_media, proj.folder) if not os.path.isabs(rel) else rel,
        kind="video" if info.get("width") else "audio",
        **{k: v for k, v in info.items() if k in
           ("width", "height", "fps", "frames", "duration", "hasAudio")})
    item = proj.add_clip(medium["id"], args.track, args.at, args.in_frame,
                         args.dur, args.speed)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_text(args) -> int:
    proj, path = _open(args.path)
    item = proj.add_text(args.track, args.text, args.at, args.dur)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_trim(args) -> int:
    proj, path = _open(args.path)
    item = proj.trim(args.item, args.edge, args.to_frame)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_split(args) -> int:
    proj, path = _open(args.path)
    right = proj.split(args.item, args.at_frame)
    _save_with_backup(proj, path)
    print(json.dumps(right, ensure_ascii=False))
    return 0


def cmd_move(args) -> int:
    proj, path = _open(args.path)
    item = proj.move(args.item, args.track, args.at)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_delete(args) -> int:
    proj, path = _open(args.path)
    proj.delete(args.item)
    _save_with_backup(proj, path)
    print(f"deleted {args.item}")
    return 0


def cmd_speed(args) -> int:
    proj, path = _open(args.path)
    item = proj.set_speed(args.item, args.speed)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_undo(args) -> int:
    proj, path = _open(args.path)
    bak = path + ".bak"
    if not os.path.isfile(bak):
        raise RuntimeError("Nothing to undo (no backup file)")
    data = load_project(bak)
    proj.restore(data)
    save_project(proj.data, path)
    print(f"undone, rev={proj.rev}")
    return 0


def cmd_export(args) -> int:
    proj, path = _open(args.path)
    out = args.out or os.path.join(proj.folder, "render",
                                   f"export-{args.preset}.mp4")
    report = render(proj.data, proj.folder, out, preset=args.preset,
                    normalize_audio=args.normalize,
                    ducking=True if args.duck else None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_transition(args) -> int:
    proj, path = _open(args.path)
    trans = proj.add_transition(args.from_item, args.to_item, args.kind,
                                args.duration)
    _save_with_backup(proj, path)
    print(json.dumps(trans, ensure_ascii=False))
    return 0


def cmd_keyframe(args) -> int:
    proj, path = _open(args.path)
    item = proj.add_keyframe(args.item, args.at, args.property, args.value)
    _save_with_backup(proj, path)
    print(json.dumps(item.get("keyframes", []), ensure_ascii=False))
    return 0


def cmd_color(args) -> int:
    proj, path = _open(args.path)
    item = proj.set_color(args.item, args.lut, args.preset,
                          args.strength)
    _save_with_backup(proj, path)
    print(json.dumps(item.get("color", {}), ensure_ascii=False))
    return 0


def cmd_srt_import(args) -> int:
    proj, path = _open(args.path)
    with open(args.file, encoding="utf-8") as fh:
        items = proj.import_srt(args.track, fh.read())
    _save_with_backup(proj, path)
    print(f"imported {len(items)} cues onto {args.track}")
    return 0


def cmd_srt_export(args) -> int:
    proj, _ = _open(args.path)
    text = proj.export_srt(args.track)
    with open(args.file, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"exported {len(proj.data['tracks'])} tracks' captions to {args.file}")
    return 0



def cmd_marker_add(args) -> int:
    proj, path = _open(args.path)
    marker = proj.add_marker(args.text, args.at)
    _save_with_backup(proj, path)
    print(json.dumps(marker, ensure_ascii=False))
    return 0


def cmd_marker_list(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps(proj.data.get("markers", []), indent=2, ensure_ascii=False))
    return 0


def cmd_otio_export(args) -> int:
    from vibeedit_core.export_ops import export_otio
    proj, _ = _open(args.path)
    out = args.out or os.path.join(proj.folder, "render", "timeline.otio")
    report = export_otio(proj.data, proj.folder, out)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_batch(args) -> int:
    from vibeedit_core.export_ops import batch_export
    results = batch_export(args.projects, preset=args.preset,
                           normalize_audio=args.normalize)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if all(r.get("ok") for r in results) else 1


def cmd_duplicate(args) -> int:
    from vibeedit_core.export_ops import duplicate_project
    dest = duplicate_project(args.path, args.dest, args.name)
    print(dest)
    return 0


def cmd_media_metadata(args) -> int:
    from vibeedit_core.export_ops import media_metadata
    proj, _ = _open(args.path)
    print(json.dumps(media_metadata(proj.data, proj.folder, args.media),
                     indent=2, ensure_ascii=False))
    return 0


def cmd_plugin_list(args) -> int:
    from vibeedit_core.plugins import load_plugins
    plugins = load_plugins()
    print(json.dumps({k: v.get("description", "") for k, v in plugins.items()
                      if not k.startswith("_")}, indent=2, ensure_ascii=False))
    if plugins.get("_errors"):
        print(json.dumps({"errors": plugins["_errors"]}, indent=2))
    return 0


def cmd_plugin_run(args) -> int:
    from vibeedit_core.plugins import apply_plugin
    proj, path = _open(args.path)
    item = apply_plugin(proj, args.plugin, args.hook, args.item)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_transcribe(args) -> int:
    from vibeedit_core.transcribe import transcribe_media
    proj, path = _open(args.path)
    added = transcribe_media(proj, args.media, args.track, args.model)
    _save_with_backup(proj, path)
    print(f"transcribed {len(added)} segments onto {args.track}")
    return 0


# -- Phase 4 commands ---------------------------------------------------
def cmd_otio_import(args) -> int:
    from vibeedit_core.export_ops import import_otio
    report = import_otio(args.otio, args.dest, merge=args.merge)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_karaoke_add(args) -> int:
    proj, path = _open(args.path)
    item = proj.add_karaoke(args.item, json.loads(args.words))
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_karaoke_get(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps(proj.karaoke_get(args.item), indent=2, ensure_ascii=False))
    return 0


def cmd_karaoke_export(args) -> int:
    from vibeedit_core.export_ops import export_karaoke_ass
    proj, _ = _open(args.path)
    out = args.out or os.path.join(proj.folder, "render", "karaoke.ass")
    print(json.dumps(export_karaoke_ass(proj.data, out), indent=2,
                     ensure_ascii=False))
    return 0


def cmd_adjustment_add(args) -> int:
    proj, path = _open(args.path)
    item = proj.add_adjustment(args.at, args.dur, args.preset, args.lut,
                               args.strength)
    _save_with_backup(proj, path)
    print(json.dumps(item, ensure_ascii=False))
    return 0


def cmd_adjustment_list(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps(proj.list_adjustments(), indent=2, ensure_ascii=False))
    return 0


def cmd_adjustment_remove(args) -> int:
    proj, path = _open(args.path)
    proj.remove_adjustment(args.item)
    _save_with_backup(proj, path)
    print(json.dumps({"deleted": args.item}, ensure_ascii=False))
    return 0


def cmd_beat_detect(args) -> int:
    proj, path = _open(args.path)
    grid = proj.detect_beats(args.media, min_gap_s=args.min_gap)
    _save_with_backup(proj, path)
    print(json.dumps(grid, indent=2, ensure_ascii=False))
    return 0


def cmd_beat_list(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps(proj.beat_list(), indent=2, ensure_ascii=False))
    return 0


def cmd_beat_snap(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps({"frame": args.frame,
                      "snapped": proj.snap_frame(args.frame)},
                     ensure_ascii=False))
    return 0


def cmd_beats_to_markers(args) -> int:
    proj, path = _open(args.path)
    added = proj.beats_to_markers()
    _save_with_backup(proj, path)
    print(json.dumps(added, indent=2, ensure_ascii=False))
    return 0


def cmd_ducking(args) -> int:
    proj, path = _open(args.path)
    if args.off:
        config = proj.set_ducking(False)
    else:
        config = proj.set_ducking(True, amount_db=args.amount,
                                  threshold=args.threshold,
                                  ratio=args.ratio)
    _save_with_backup(proj, path)
    print(json.dumps(config, indent=2, ensure_ascii=False))
    return 0


def cmd_project_stats(args) -> int:
    proj, _ = _open(args.path)
    print(json.dumps(proj.project_stats(), indent=2, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vibeedit")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new")
    p.add_argument("name")
    p.add_argument("--dir", default="windows/projects")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.set_defaults(fn=cmd_new)

    p = sub.add_parser("open")
    p.add_argument("path")
    p.set_defaults(fn=cmd_open)

    p = sub.add_parser("list")
    p.add_argument("path")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("timeline")
    p.add_argument("path")
    p.set_defaults(fn=cmd_timeline)

    p = sub.add_parser("add")
    p.add_argument("path"); p.add_argument("media"); p.add_argument("track")
    p.add_argument("at", type=int)
    p.add_argument("--in", dest="in_frame", type=int, default=0)
    p.add_argument("--dur", type=int, default=None)
    p.add_argument("--speed", type=float, default=1.0)
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("text")
    p.add_argument("path"); p.add_argument("track")
    p.add_argument("at", type=int); p.add_argument("dur", type=int)
    p.add_argument("text")
    p.set_defaults(fn=cmd_text)

    p = sub.add_parser("trim")
    p.add_argument("path"); p.add_argument("item"); p.add_argument("edge")
    p.add_argument("to_frame", type=int)
    p.set_defaults(fn=cmd_trim)

    p = sub.add_parser("split")
    p.add_argument("path"); p.add_argument("item"); p.add_argument("at_frame", type=int)
    p.set_defaults(fn=cmd_split)

    p = sub.add_parser("move")
    p.add_argument("path"); p.add_argument("item"); p.add_argument("track")
    p.add_argument("at", type=int)
    p.set_defaults(fn=cmd_move)

    p = sub.add_parser("delete")
    p.add_argument("path"); p.add_argument("item")
    p.set_defaults(fn=cmd_delete)

    p = sub.add_parser("speed")
    p.add_argument("path"); p.add_argument("item"); p.add_argument("speed", type=float)
    p.set_defaults(fn=cmd_speed)

    p = sub.add_parser("undo")
    p.add_argument("path")
    p.set_defaults(fn=cmd_undo)

    p = sub.add_parser("export")
    p.add_argument("path")
    p.add_argument("--preset", default="full", choices=["full", "draft"])
    p.add_argument("--out", default=None)
    p.add_argument("--normalize", action="store_true")
    p.add_argument("--duck", action="store_true")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("transition")
    p.add_argument("path"); p.add_argument("from_item"); p.add_argument("to_item")
    p.add_argument("kind"); p.add_argument("duration", type=float)
    p.set_defaults(fn=cmd_transition)

    p = sub.add_parser("keyframe")
    p.add_argument("path"); p.add_argument("item"); p.add_argument("at", type=float)
    p.add_argument("property"); p.add_argument("value", type=float)
    p.set_defaults(fn=cmd_keyframe)

    p = sub.add_parser("color")
    p.add_argument("path"); p.add_argument("item")
    p.add_argument("--lut", default=None); p.add_argument("--preset", default=None)
    p.add_argument("--strength", type=float, default=None)
    p.set_defaults(fn=cmd_color)

    p = sub.add_parser("srt-import")
    p.add_argument("path"); p.add_argument("file")
    p.add_argument("--track", default="t1")
    p.set_defaults(fn=cmd_srt_import)

    p = sub.add_parser("srt-export")
    p.add_argument("path"); p.add_argument("file")
    p.add_argument("--track", default="t1")
    p.set_defaults(fn=cmd_srt_export)

    p = sub.add_parser("marker-add")
    p.add_argument("path"); p.add_argument("text"); p.add_argument("at", type=int)
    p.set_defaults(fn=cmd_marker_add)

    p = sub.add_parser("marker-list")
    p.add_argument("path")
    p.set_defaults(fn=cmd_marker_list)

    p = sub.add_parser("otio-export")
    p.add_argument("path"); p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_otio_export)

    p = sub.add_parser("batch")
    p.add_argument("projects", nargs="+")
    p.add_argument("--preset", default="full", choices=["full", "draft"])
    p.add_argument("--normalize", action="store_true")
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("duplicate")
    p.add_argument("path"); p.add_argument("dest"); p.add_argument("--name", default=None)
    p.set_defaults(fn=cmd_duplicate)

    p = sub.add_parser("media-metadata")
    p.add_argument("path"); p.add_argument("media")
    p.set_defaults(fn=cmd_media_metadata)

    p = sub.add_parser("plugin-list")
    p.set_defaults(fn=cmd_plugin_list)

    p = sub.add_parser("plugin-run")
    p.add_argument("path"); p.add_argument("plugin"); p.add_argument("hook"); p.add_argument("item")
    p.set_defaults(fn=cmd_plugin_run)

    p = sub.add_parser("transcribe")
    p.add_argument("path"); p.add_argument("media")
    p.add_argument("--model", default="small"); p.add_argument("--track", default="t1")
    p.set_defaults(fn=cmd_transcribe)

    p = sub.add_parser("otio-import")
    p.add_argument("otio"); p.add_argument("dest")
    p.add_argument("--merge", action="store_true")
    p.set_defaults(fn=cmd_otio_import)

    p = sub.add_parser("karaoke-add")
    p.add_argument("path"); p.add_argument("item"); p.add_argument("words")
    p.set_defaults(fn=cmd_karaoke_add)

    p = sub.add_parser("karaoke-get")
    p.add_argument("path"); p.add_argument("item")
    p.set_defaults(fn=cmd_karaoke_get)

    p = sub.add_parser("karaoke-export")
    p.add_argument("path"); p.add_argument("--out", default=None)
    p.set_defaults(fn=cmd_karaoke_export)

    p = sub.add_parser("adjustment-add")
    p.add_argument("path"); p.add_argument("at", type=int); p.add_argument("dur", type=int)
    p.add_argument("--preset", default=None); p.add_argument("--lut", default=None)
    p.add_argument("--strength", type=float, default=None)
    p.set_defaults(fn=cmd_adjustment_add)

    p = sub.add_parser("adjustment-list")
    p.add_argument("path")
    p.set_defaults(fn=cmd_adjustment_list)

    p = sub.add_parser("adjustment-remove")
    p.add_argument("path"); p.add_argument("item")
    p.set_defaults(fn=cmd_adjustment_remove)

    p = sub.add_parser("beat-detect")
    p.add_argument("path"); p.add_argument("media")
    p.add_argument("--min-gap", type=float, default=0.3)
    p.set_defaults(fn=cmd_beat_detect)

    p = sub.add_parser("beat-list")
    p.add_argument("path")
    p.set_defaults(fn=cmd_beat_list)

    p = sub.add_parser("beat-snap")
    p.add_argument("path"); p.add_argument("frame", type=int)
    p.set_defaults(fn=cmd_beat_snap)

    p = sub.add_parser("beats-to-markers")
    p.add_argument("path")
    p.set_defaults(fn=cmd_beats_to_markers)

    p = sub.add_parser("ducking")
    p.add_argument("path"); p.add_argument("--amount", type=float, default=6.0)
    p.add_argument("--threshold", type=float, default=0.02)
    p.add_argument("--ratio", type=float, default=None)
    p.add_argument("--off", action="store_true")
    p.set_defaults(fn=cmd_ducking)

    p = sub.add_parser("project-stats")
    p.add_argument("path")
    p.set_defaults(fn=cmd_project_stats)

    p = sub.add_parser("serve")
    p.add_argument("--project", default=None)
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(fn=lambda a: _serve(a))

    p = sub.add_parser("mcp")
    p.add_argument("project", nargs="?", default=None)
    p.set_defaults(fn=lambda a: _mcp(a))

    args = parser.parse_args(argv)
    try:
        return args.fn(args)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
        print(f"vibeedit: error: {exc}", file=sys.stderr)
        return 1


def _serve(args) -> int:
    from vibeedit_core.server import run_server
    run_server(args.project, args.port)
    return 0


def _mcp(args) -> int:
    from vibeedit_core.mcp import serve
    serve(args.project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
