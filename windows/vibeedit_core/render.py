"""FFmpeg rendering for the VibeEdit Windows MVP (CapCut-style timeline).

CapCut-style rules implemented here:
- Clips play in timeline order on their tracks; gaps are black with
  silence (Phase 1 does not do crossfades — see windows-port.md).
- The main video track is the base picture. Overlay video items are
  composited over it at their timeline position (full frame, scaled to
  cover). Text items are drawn over the whole picture with drawtext.
- Speed changes use setpts/atempo; fades are fade/afade to/from black
  and silence at the clip edges (not crossfades between clips).
- Audio tracks are mixed: clip audio from the main track plus music
  items, each with volume and fades, delayed to its timeline position.

Out of scope for Phase 1 (preserved in the project, reported as
skipped, never silently baked): transitions, keyframes, LUTs,
adjustment layers, and overlay-item audio.
"""

from __future__ import annotations

import json
import os
import subprocess

from .project import frames_to_seconds, fps_value

FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    # Linux (dev/test machine)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_font() -> str | None:
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def probe_media(path: str) -> dict:
    """ffprobe a file; returns width/height/fps/frames/duration/hasAudio."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_streams", "-show_format", path]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(out.stdout)
    info: dict = {"duration": 0.0, "hasAudio": False}
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            info["width"] = int(stream.get("width", 0))
            info["height"] = int(stream.get("height", 0))
            rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
            if rate and "/" in str(rate):
                num, den = str(rate).split("/")
                if int(den):
                    info["fps"] = [int(num), int(den)]
            frames = stream.get("nb_frames")
            if frames:
                info["frames"] = int(frames)
        elif stream.get("codec_type") == "audio":
            info["hasAudio"] = True
    fmt = data.get("format", {})
    if fmt.get("duration"):
        info["duration"] = float(fmt["duration"])
    return info


def _escape_drawtext(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
            .replace("\n", " "))


def _atempo_chain(speed: float) -> str:
    """atempo only accepts 0.5-100; chain for anything outside."""
    if speed <= 0:
        raise ValueError("Speed must be positive")
    parts = []
    remaining = float(speed)
    while remaining > 100.0:
        parts.append("atempo=100.0")
        remaining /= 100.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.4f}")
    return ",".join(parts)


def _afade(filters: list[str], dur_s: float, fade_in: float, fade_out: float):
    if fade_in and fade_in > 0:
        filters.append(f"afade=t=in:st=0:d={min(fade_in, dur_s):.3f}")
    if fade_out and fade_out > 0:
        filters.append(
            f"afade=t=out:st={max(dur_s - fade_out, 0):.3f}:d={min(fade_out, dur_s):.3f}")


def render(project: dict, folder: str, output: str, preset: str = "full") -> dict:
    """Render the project with FFmpeg. Returns a report dict.

    ``preset``: "full" (project resolution, fast preset) or "draft"
    (half resolution, veryfast preset, higher CRF).
    """
    fmt = project["format"]
    width, height = int(fmt["width"]), int(fmt["height"])
    fps = fps_value(fmt["fps"])
    fps_str = f"{fps:.3f}".rstrip("0").rstrip(".")
    if preset == "draft":
        out_w, out_h = max(width // 2, 2), max(height // 2, 2)
        ff_preset, crf = "veryfast", "28"
    else:
        out_w, out_h, ff_preset, crf = width, height, "fast", "20"

    def media_path(item_media: str) -> str:
        for medium in project["media"]:
            if medium["id"] == item_media:
                path = medium["path"]
                return path if os.path.isabs(path) else os.path.join(folder, path)
        raise KeyError(f"Media not found in project: {item_media}")

    def media_fps(medium: dict) -> float:
        return fps_value(medium.get("fps", fmt["fps"]))

    tracks = {t["id"]: t for t in project["tracks"]}
    main = next((t for t in project["tracks"]
                 if t.get("role") == "main" and t["kind"] == "video"), None)
    if main is None:
        raise ValueError("Project has no main video track")

    total_frames = 0
    for track in project["tracks"]:
        for item in track["items"]:
            total_frames = max(total_frames, item["at"] + item["dur"])
    total_s = frames_to_seconds(total_frames, fmt["fps"]) if total_frames else 0.0

    inputs: list[str] = []
    input_index: dict[str, int] = {}
    filter_parts: list[str] = []
    video_segments: list[str] = []
    audio_segments: list[str] = []
    warnings: list[str] = []
    skipped: list[str] = []

    def add_input(path: str) -> int:
        if path in input_index:
            return input_index[path]
        inputs.append(path)
        input_index[path] = len(inputs) - 1
        return len(inputs) - 1

    # ---- main video track: sequential segments, gaps are black --------
    cursor_s = 0.0
    seg = 0
    for item in sorted(main["items"], key=lambda i: i["at"]):
        start_s = frames_to_seconds(item["at"], fmt["fps"])
        dur_s = frames_to_seconds(item["dur"], fmt["fps"])
        speed = float(item.get("speed", 1.0))
        if start_s > cursor_s + 0.001:
            gap = start_s - cursor_s
            filter_parts.append(
                f"color=c=black:s={out_w}x{out_h}:r={fps_str}:d={gap:.3f},"
                f"format=yuv420p[vseg{seg}]")
            video_segments.append(f"[vseg{seg}]")
            audio_segments.append(f"[aseg{seg}]")
            filter_parts.append(
                f"anullsrc=r=48000:cl=stereo:d={gap:.3f},"
                f"adelay={int(cursor_s * 1000)}:all=1,"
                f"apad=whole_dur={total_s:.3f}[aseg{seg}]")
            seg += 1
            cursor_s = start_s
        medium = next((m for m in project["media"]
                       if m["id"] == item["media"]), None)
        if medium is None:
            raise KeyError(f"Media not found: {item['media']}")
        src = media_path(item["media"])
        idx = add_input(src)
        src_s = item.get("in", 0) / media_fps(medium)
        src_dur_s = dur_s * speed
        kind = medium.get("kind", "video")
        if kind == "image":
            filter_parts.append(
                f"[{idx}:v]loop=loop=-1:size=1:start=0,"
                f"trim=end_frame=1,scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},setsar=1,fps={fps_str},"
                f"trim=end={dur_s:.3f},setpts=PTS-STARTPTS[vseg{seg}]")
        else:
            zoom = 1.0
            transform = item.get("transform") or {}
            if isinstance(transform, dict) and transform.get("zoom"):
                zoom = float(transform["zoom"])
            scale = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                     f"crop={out_w}:{out_h}")
            if zoom != 1.0:
                zw, zh = int(out_w * zoom), int(out_h * zoom)
                scale = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
                         f"crop={out_w}:{out_h}")
            vfilters = [f"trim=start={src_s:.3f}:end={src_s + src_dur_s:.3f}",
                        "setpts=PTS-STARTPTS",
                        f"setpts=PTS/{speed:.4f}" if speed != 1.0 else None,
                        scale, f"fps={fps_str}", "format=yuv420p"]
            vfilters = [f for f in vfilters if f]
            fade_in, fade_out = float(item.get("fadeIn", 0) or 0), float(item.get("fadeOut", 0) or 0)
            if fade_in > 0:
                vfilters.append(f"fade=t=in:st=0:d={min(fade_in, dur_s):.3f}")
            if fade_out > 0:
                vfilters.append(
                    f"fade=t=out:st={max(dur_s - fade_out, 0):.3f}:d={min(fade_out, dur_s):.3f}")
            filter_parts.append(f"[{idx}:v]{','.join(vfilters)}[vseg{seg}]")
        video_segments.append(f"[vseg{seg}]")
        # Audio for this clip (only if the source has audio).
        if kind != "image" and medium.get("hasAudio", True):
            afilters = [f"atrim=start={src_s:.3f}:end={src_s + src_dur_s:.3f}",
                        "asetpts=PTS-STARTPTS"]
            if speed != 1.0:
                afilters.append(_atempo_chain(speed))
            _afade(afilters, dur_s, float(item.get("fadeIn", 0) or 0),
                   float(item.get("fadeOut", 0) or 0))
            vol = float(item.get("volume", 0) or 0)
            if vol:
                afilters.append(f"volume={vol}dB")
            # Delay to the clip's timeline position and pad to the full
            # timeline length, so amix lines every clip up correctly.
            afilters.append(f"adelay={int(start_s * 1000)}:all=1")
            afilters.append(f"apad=whole_dur={total_s:.3f}")
            filter_parts.append(f"[{idx}:a]{','.join(afilters)}[aseg{seg}]")
            audio_segments.append(f"[aseg{seg}]")
        seg += 1
        cursor_s = start_s + dur_s
    if total_s > cursor_s + 0.001:
        gap = total_s - cursor_s
        filter_parts.append(
            f"color=c=black:s={out_w}x{out_h}:r={fps_str}:d={gap:.3f},"
            f"format=yuv420p[vseg{seg}]")
        video_segments.append(f"[vseg{seg}]")
        audio_segments.append(f"[aseg{seg}]")
        filter_parts.append(
            f"anullsrc=r=48000:cl=stereo:d={gap:.3f},"
            f"adelay={int(cursor_s * 1000)}:all=1,"
            f"apad=whole_dur={total_s:.3f}[aseg{seg}]")
        seg += 1
    if not video_segments:
        filter_parts.append(
            f"color=c=black:s={out_w}x{out_h}:r={fps_str}:d=1,format=yuv420p[vseg0]")
        video_segments.append("[vseg0]")
        total_s = max(total_s, 1.0)

    vlabel = "[vcat]"
    filter_parts.append(
        f"{''.join(video_segments)}concat=n={len(video_segments)}:v=1:a=0[vcat]")

    # ---- overlay video tracks (full-frame composite at their time) ----
    current = "vcat"
    overlay_count = 0
    for track in project["tracks"]:
        if track["kind"] != "video" or track.get("role") == "main":
            continue
        for item in sorted(track["items"], key=lambda i: i["at"]):
            medium = next((m for m in project["media"]
                           if m["id"] == item.get("media")), None)
            if medium is None or medium.get("kind") == "image":
                skipped.append(f"overlay {item['id']} (no video media)")
                continue
            start_s = frames_to_seconds(item["at"], fmt["fps"])
            dur_s = frames_to_seconds(item["dur"], fmt["fps"])
            speed = float(item.get("speed", 1.0))
            src = media_path(item["media"])
            idx = add_input(src)
            src_s = item.get("in", 0) / media_fps(medium)
            ofilters = [f"trim=start={src_s:.3f}:end={src_s + dur_s * speed:.3f}",
                        "setpts=PTS-STARTPTS"]
            if speed != 1.0:
                ofilters.append(f"setpts=PTS/{speed:.4f}")
            ofilters.append(
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},fps={fps_str},format=yuva420p")
            out_label = f"vov{overlay_count}"
            filter_parts.append(f"[{idx}:v]{','.join(ofilters)}[ov{overlay_count}]")
            filter_parts.append(
                f"[{current}][ov{overlay_count}]overlay=0:0:"
                f"enable='between(t,{start_s:.3f},{start_s + dur_s:.3f})'"
                f"[{out_label}]")
            current = out_label
            overlay_count += 1
            if medium.get("hasAudio", True):
                skipped.append(f"overlay {item['id']} audio (Phase 1 renders "
                               "overlay picture only)")

    # ---- text overlays -------------------------------------------------
    font = find_font()
    text_count = 0
    for track in project["tracks"]:
        if track["kind"] != "text":
            continue
        for item in sorted(track["items"], key=lambda i: i["at"]):
            text = item.get("text", "")
            if not text:
                continue
            if font is None:
                warnings.append("No drawtext font found; text overlays skipped")
                skipped.append(f"text {item['id']} (no font)")
                continue
            style = item.get("textStyle") or {}
            size_frac = float(style.get("size", 0.062))
            fontsize = max(int(size_frac * out_h), 12)
            pos_y = float(style.get("positionY", 0.8))
            pos_x = float(style.get("positionX", 0.5))
            start_s = frames_to_seconds(item["at"], fmt["fps"])
            end_s = frames_to_seconds(item["at"] + item["dur"], fmt["fps"])
            x_expr = f"(w-text_w)*{pos_x:.3f}"
            y_expr = f"(h-text_h)*{pos_y:.3f}"
            out_label = f"vtxt{text_count}"
            filter_parts.append(
                f"[{current}]drawtext=fontfile='{font}':"
                f"text='{_escape_drawtext(text)}':fontsize={fontsize}:"
                f"fontcolor=white:borderw=2:bordercolor=black:"
                f"x={x_expr}:y={y_expr}:"
                f"enable='between(t,{start_s:.3f},{end_s:.3f})'[{out_label}]")
            current = out_label
            text_count += 1

    # ---- audio mix -----------------------------------------------------
    audio_map = None
    # Music / extra audio tracks (items whose media is audio, or audio-only
    # clips placed on audio tracks) are mixed in at their timeline time.
    extra_audio = []
    for track in project["tracks"]:
        if track["kind"] != "audio":
            continue
        for item in track["items"]:
            medium = next((m for m in project["media"]
                           if m["id"] == item.get("media")), None)
            if medium is None:
                continue
            # Dialogue items linked to main clips are already rendered as
            # main-track audio; only standalone audio items are added here.
            if track.get("role") == "dialogue" and item.get("linkedVideo"):
                continue
            if medium.get("kind") == "video" and track.get("role") == "dialogue":
                continue
            start_s = frames_to_seconds(item["at"], fmt["fps"])
            dur_s = frames_to_seconds(item["dur"], fmt["fps"])
            src = media_path(item["media"])
            idx = add_input(src)
            src_s = item.get("in", 0) / media_fps(medium)
            afilters = [f"atrim=start={src_s:.3f}:end={src_s + dur_s:.3f}",
                        "asetpts=PTS-STARTPTS",
                        f"adelay={int(start_s * 1000)}:all=1",
                        f"apad=whole_dur={total_s:.3f}"]
            vol = float(item.get("volume", 0) or 0)
            if vol:
                afilters.append(f"volume={vol}dB")
            label = f"aextra{len(extra_audio)}"
            filter_parts.append(f"[{idx}:a]{','.join(afilters)}[{label}]")
            extra_audio.append(f"[{label}]")
    all_audio = audio_segments + extra_audio
    if all_audio:
        if len(all_audio) == 1:
            audio_map = all_audio[0]
        else:
            filter_parts.append(
                f"{''.join(all_audio)}amix=inputs={len(all_audio)}:normalize=0[aout]")
            audio_map = "[aout]"

    filter_complex = ";".join(filter_parts)
    cmd = ["ffmpeg", "-y"]
    for path in inputs:
        cmd += ["-i", path]
    cmd += ["-filter_complex", filter_complex,
            "-map", f"[{current}]", "-r", fps_str,
            "-c:v", "libx264", "-preset", ff_preset, "-crf", crf,
            "-pix_fmt", "yuv420p"]
    if audio_map:
        cmd += ["-map", audio_map, "-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += [output]
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed ({proc.returncode}): {proc.stderr[-2000:]}")
    return {
        "output": output, "preset": preset, "width": out_w, "height": out_h,
        "duration": round(total_s, 3), "fps": fps,
        "text_overlays": text_count, "overlay_clips": overlay_count,
        "warnings": warnings, "skipped": skipped,
        "segments": len(video_segments),
    }
