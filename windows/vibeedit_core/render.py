"""FFmpeg rendering for the VibeEdit Windows port (CapCut-style timeline).

Phase 1 rules kept:
- Clips play in timeline order on their tracks; gaps are black with
  silence. The main video track is the base picture. Overlay video
  items are composited over it at their timeline position. Text items
  are drawn over the whole picture with drawtext. Speed changes use
  setpts/atempo; fades are fade/afade at the clip edges.

Phase 2 additions:
- Transitions between consecutive main-track clips use xfade (video)
  and acrossfade (audio). The output timeline is shorter than the
  project timeline by the sum of transition durations: an overlay,
  text or music item positioned after a transition boundary is shifted
  earlier by the transitions at or before its start time (documented
  in VibeEdit/docs/windows-port.md). Edge fades on the two sides of a
  transition are skipped, because the transition replaces them.
- Keyframes (times in frames relative to the item start):
  position and opacity for overlay/text items, scale for overlay/text
  items, volume for audio items. Position and scale are rendered with
  FFmpeg expressions (overlay x/y use main-timeline time; scale and
  volume use clip-local time after setpts/atempo). Overlay opacity is
  rendered stepwise: the clip is split at its opacity-keyframe times
  and each segment gets a constant alpha (colorchannelmixer has no
  time variable, so a truly linear alpha ramp is not honestly
  available there); text opacity uses a linear drawtext alpha
  expression. Keyframes on main-track clips are stored but not
  rendered (reported in ``skipped``).
- Colour: a .cube LUT per clip via lut3d (missing/invalid LUT is a
  hard error, never a silent skip) and eq presets (vivid/warm/cool/
  faded/mono).
- SRT is handled in project.py (import/export), not here.

Out of scope (preserved in the project, reported as skipped, never
silently baked): adjustment layers, beat grids, overlay-item audio.
"""

from __future__ import annotations

import json
import os
import subprocess

from .project import (frames_to_seconds, fps_value, COLOR_PRESETS,
                      validate_cube, keyframe_points, TRANSITION_XFADE)

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


def _num(value: float) -> str:
    return f"{value:.6g}"


def _piecewise_expr(points: list[tuple[float, float]], var: str = "t") -> str:
    """Nested if() expression for linear interpolation between points.

    Points are (time, value), sorted. Outside the range the value is
    held at the nearest keyframe. Times/values are formatted plainly so
    the expression survives FFmpeg's filter parser.
    """
    if not points:
        raise ValueError("No keyframe points")
    if len(points) == 1:
        return _num(points[0][1])
    expr = _num(points[-1][1])
    for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
        span = t1 - t0
        seg = f"{_num(v0)}+({_num(v1)}-{_num(v0)})*({var}-{_num(t0)})/{_num(span)}" \
            if span else _num(v1)
        expr = f"if(lt({var},{_num(t1)}),{seg},{expr})"
    return f"if(lt({var},{_num(points[0][0])}),{_num(points[0][1])},{expr})"


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


def _color_filters(item: dict) -> list[str]:
    """lut3d + eq filters for a clip. Raises on a bad LUT."""
    filters: list[str] = []
    color = item.get("color") or {}
    lut = color.get("lut")
    if lut:
        validate_cube(lut)
        filters.append(f"lut3d=file='{lut}'")
    preset = color.get("preset")
    if preset and preset != "none":
        if preset not in COLOR_PRESETS:
            raise ValueError(f"Unknown colour preset: {preset!r}")
        filters.append(COLOR_PRESETS[preset])
    return filters


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
    main_items = sorted(main["items"], key=lambda i: i["at"])

    # ---- transitions: validate once, build the time adjustment -------
    trans_by_pair: dict[tuple[str, str], dict] = {}
    for trans in project.get("transitions", []):
        kind = trans.get("kind")
        if kind not in TRANSITION_XFADE:
            raise ValueError(f"Unknown transition kind: {kind!r}")
        trans_by_pair[(trans["from"], trans["to"])] = trans
    boundaries: list[tuple[float, float]] = []  # (incoming start s, dur s)
    for idx in range(1, len(main_items)):
        prev_item, item = main_items[idx - 1], main_items[idx]
        if int(prev_item["at"]) + int(prev_item["dur"]) != int(item["at"]):
            continue
        trans = trans_by_pair.get((prev_item["id"], item["id"]))
        if trans is not None:
            dur_s = frames_to_seconds(trans["duration"], fmt["fps"])
            if dur_s > min(frames_to_seconds(prev_item["dur"], fmt["fps"]),
                           frames_to_seconds(item["dur"], fmt["fps"])):
                raise ValueError("Transition duration exceeds the shorter "
                                 "adjacent clip")
            boundaries.append((frames_to_seconds(item["at"], fmt["fps"]), dur_s))

    def adjust(time_s: float) -> float:
        """Original timeline time -> output timeline time."""
        shift = sum(d for start, d in boundaries if start <= time_s + 1e-9)
        return max(time_s - shift, 0.0)

    total_orig_s = 0.0
    for track in project["tracks"]:
        for item in track["items"]:
            total_orig_s = max(total_orig_s,
                               frames_to_seconds(item["at"] + item["dur"],
                                                 fmt["fps"]))
    total_s = adjust(total_orig_s)

    inputs: list[str] = []
    input_index: dict[str, int] = {}
    filter_parts: list[str] = []
    warnings: list[str] = []
    skipped: list[str] = []
    seg_counter = [0]

    def add_input(path: str) -> int:
        if path in input_index:
            return input_index[path]
        inputs.append(path)
        input_index[path] = len(inputs) - 1
        return len(inputs) - 1

    def next_label(prefix: str) -> str:
        seg_counter[0] += 1
        return f"{prefix}{seg_counter[0]}"

    def volume_filters(item: dict, dur_s: float) -> list[str]:
        """Static dB volume, or linear volume-keyframe expression."""
        vol_points = keyframe_points(item, "volume", fmt["fps"])
        if vol_points:
            db_points = [(t, 10 ** (db / 20.0)) for t, db in vol_points]
            return [f"volume='{_piecewise_expr(db_points, 't')}':eval=frame"]
        vol = float(item.get("volume", 0) or 0)
        return [f"volume={vol}dB"] if vol else []

    # ---- main track: video chain (concat, xfade at transitions) ------
    vchain: str | None = None
    vchain_dur = 0.0
    achain: str | None = None
    achain_dur = 0.0
    segment_count = 0
    cursor_s = 0.0
    prev_item: dict | None = None

    def chain_video(label: str, dur_s: float, trans: dict | None):
        nonlocal vchain, vchain_dur
        if vchain is None:
            vchain, vchain_dur = label, dur_s
            return
        if trans is not None:
            trans_s = frames_to_seconds(trans["duration"], fmt["fps"])
            out_label = next_label("vxf")
            filter_parts.append(
                f"[{vchain}][{label}]xfade=transition="
                f"{TRANSITION_XFADE[trans['kind']]}:duration={trans_s:.3f}:"
                f"offset={vchain_dur - trans_s:.3f}[{out_label}]")
            vchain, vchain_dur = out_label, vchain_dur + dur_s - trans_s
        else:
            out_label = next_label("vct")
            filter_parts.append(
                f"[{vchain}][{label}]concat=n=2:v=1:a=0[{out_label}]")
            vchain, vchain_dur = out_label, vchain_dur + dur_s

    def chain_audio(label: str, dur_s: float, trans: dict | None):
        nonlocal achain, achain_dur
        if achain is None:
            achain, achain_dur = label, dur_s
            return
        if trans is not None:
            trans_s = frames_to_seconds(trans["duration"], fmt["fps"])
            out_label = next_label("axf")
            filter_parts.append(
                f"[{achain}][{label}]acrossfade=d={trans_s:.3f}[{out_label}]")
            achain, achain_dur = out_label, achain_dur + dur_s - trans_s
        else:
            out_label = next_label("act")
            filter_parts.append(
                f"[{achain}][{label}]concat=n=2:v=0:a=1[{out_label}]")
            achain, achain_dur = out_label, achain_dur + dur_s

    def main_video_segment(item: dict, skip_fade_in: bool,
                           skip_fade_out: bool) -> tuple[str, float]:
        start_s = frames_to_seconds(item["at"], fmt["fps"])
        dur_s = frames_to_seconds(item["dur"], fmt["fps"])
        speed = float(item.get("speed", 1.0))
        medium = next((m for m in project["media"]
                       if m["id"] == item["media"]), None)
        if medium is None:
            raise KeyError(f"Media not found: {item['media']}")
        src = media_path(item["media"])
        idx = add_input(src)
        src_s = item.get("in", 0) / media_fps(medium)
        src_dur_s = dur_s * speed
        label = next_label("vseg")
        if medium.get("kind") == "image":
            filter_parts.append(
                f"[{idx}:v]loop=loop=-1:size=1:start=0,"
                f"trim=end_frame=1,scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                f"crop={out_w}:{out_h},setsar=1,fps={fps_str},"
                f"trim=end={dur_s:.3f},setpts=PTS-STARTPTS[{label}]")
            return label, dur_s
        zoom = 1.0
        transform = item.get("transform") or {}
        if isinstance(transform, dict) and transform.get("zoom"):
            zoom = float(transform["zoom"])
        if zoom != 1.0:
            zw, zh = int(out_w * zoom), int(out_h * zoom)
            scale = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
                     f"crop={out_w}:{out_h}")
        else:
            scale = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                     f"crop={out_w}:{out_h}")
        vfilters = [f"trim=start={src_s:.3f}:end={src_s + src_dur_s:.3f}",
                    "setpts=PTS-STARTPTS"]
        if speed != 1.0:
            vfilters.append(f"setpts=PTS/{speed:.4f}")
        vfilters.append(scale)
        vfilters.extend(_color_filters(item))
        vfilters.append(f"fps={fps_str}")
        vfilters.append("format=yuv420p")
        fade_in = 0.0 if skip_fade_in else float(item.get("fadeIn", 0) or 0)
        fade_out = 0.0 if skip_fade_out else float(item.get("fadeOut", 0) or 0)
        if fade_in > 0:
            vfilters.append(f"fade=t=in:st=0:d={min(fade_in, dur_s):.3f}")
        if fade_out > 0:
            vfilters.append(
                f"fade=t=out:st={max(dur_s - fade_out, 0):.3f}:d={min(fade_out, dur_s):.3f}")
        if item.get("keyframes"):
            skipped.append(f"main clip {item['id']} keyframes stored, "
                           "not rendered in Phase 2")
        filter_parts.append(f"[{idx}:v]{','.join(vfilters)}[{label}]")
        return label, dur_s

    def main_audio_segment(item: dict, skip_fade_in: bool,
                           skip_fade_out: bool) -> tuple[str, float]:
        start_s = frames_to_seconds(item["at"], fmt["fps"])
        dur_s = frames_to_seconds(item["dur"], fmt["fps"])
        speed = float(item.get("speed", 1.0))
        medium = next((m for m in project["media"]
                       if m["id"] == item["media"]), None)
        label = next_label("aseg")
        if medium is None or medium.get("kind") == "image" \
                or not medium.get("hasAudio", True):
            filter_parts.append(
                f"anullsrc=r=48000:cl=stereo:d={dur_s:.3f}[{label}]")
            return label, dur_s
        src = media_path(item["media"])
        idx = add_input(src)
        src_s = item.get("in", 0) / media_fps(medium)
        src_dur_s = dur_s * speed
        afilters = [f"atrim=start={src_s:.3f}:end={src_s + src_dur_s:.3f}",
                    "asetpts=PTS-STARTPTS"]
        if speed != 1.0:
            afilters.append(_atempo_chain(speed))
        fade_in = 0.0 if skip_fade_in else float(item.get("fadeIn", 0) or 0)
        fade_out = 0.0 if skip_fade_out else float(item.get("fadeOut", 0) or 0)
        _afade(afilters, dur_s, fade_in, fade_out)
        afilters.extend(volume_filters(item, dur_s))
        afilters.append("aresample=48000")
        afilters.append("aformat=channel_layouts=stereo")
        filter_parts.append(f"[{idx}:a]{','.join(afilters)}[{label}]")
        return label, dur_s

    for item in main_items:
        start_s = frames_to_seconds(item["at"], fmt["fps"])
        dur_s = frames_to_seconds(item["dur"], fmt["fps"])
        if start_s > cursor_s + 0.001:
            gap = start_s - cursor_s
            glabel = next_label("vgap")
            filter_parts.append(
                f"color=c=black:s={out_w}x{out_h}:r={fps_str}:d={gap:.3f},"
                f"format=yuv420p[{glabel}]")
            chain_video(glabel, gap, None)
            alabel = next_label("agap")
            filter_parts.append(
                f"anullsrc=r=48000:cl=stereo:d={gap:.3f}[{alabel}]")
            chain_audio(alabel, gap, None)
            segment_count += 1
            cursor_s = start_s
            prev_item = None
        trans = None
        if prev_item is not None and \
                int(prev_item["at"]) + int(prev_item["dur"]) == int(item["at"]):
            trans = trans_by_pair.get((prev_item["id"], item["id"]))
        # At a transition boundary the incoming clip's edge fade-in
        # is skipped (the blend is the edge treatment); a fade-out on
        # the outgoing clip still applies inside its own segment.
        vlabel, vdur = main_video_segment(
            item, skip_fade_in=trans is not None, skip_fade_out=False)
        chain_video(vlabel, vdur, trans)
        alabel, adur = main_audio_segment(
            item, skip_fade_in=trans is not None, skip_fade_out=False)
        chain_audio(alabel, adur, trans)
        segment_count += 1
        cursor_s = start_s + dur_s
        prev_item = item
    if total_orig_s > cursor_s + 0.001:
        gap = total_orig_s - cursor_s
        glabel = next_label("vgap")
        filter_parts.append(
            f"color=c=black:s={out_w}x{out_h}:r={fps_str}:d={gap:.3f},"
            f"format=yuv420p[{glabel}]")
        chain_video(glabel, gap, None)
        alabel = next_label("agap")
        filter_parts.append(
            f"anullsrc=r=48000:cl=stereo:d={gap:.3f}[{alabel}]")
        chain_audio(alabel, gap, None)
        segment_count += 1
    if vchain is None:
        filter_parts.append(
            f"color=c=black:s={out_w}x{out_h}:r={fps_str}:d=1,format=yuv420p[vseg0]")
        vchain = "vseg0"
        total_s = max(total_s, 1.0)
    else:
        total_s = vchain_dur
    current = vchain

    # ---- overlay video tracks (position/scale/opacity keyframes) ------
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
            x_pts = [(t, v) for t, v in keyframe_points(item, "x", fmt["fps"])]
            y_pts = [(t, v) for t, v in keyframe_points(item, "y", fmt["fps"])]
            scale_pts = keyframe_points(item, "scale", fmt["fps"])
            op_pts = keyframe_points(item, "opacity", fmt["fps"])

            def pos_expr(points, base_frac, shift):
                if not points:
                    return None
                shifted = [(t + shift, v) for t, v in points]
                return _piecewise_expr(shifted, "t")

            start_adj = adjust(start_s)
            x_expr = pos_expr(x_pts, 0.0, start_adj)
            y_expr = pos_expr(y_pts, 0.0, start_adj)
            # Opacity: split at keyframe times (stepwise-held values).
            if len(op_pts) >= 2:
                bounds = [0.0] + [t for t, _ in op_pts if 0.0 < t < dur_s] \
                    + [dur_s]
                bounds = sorted(set(bounds))
                for b0, b1 in zip(bounds, bounds[1:]):
                    if b1 - b0 < 1e-6:
                        continue
                    held = None
                    for t_kf, v_kf in op_pts:
                        if t_kf <= b0 + 1e-9:
                            held = v_kf
                    if held is None:
                        held = op_pts[0][1]
                    sub_src = src_s + b0 * speed
                    sub_src_dur = (b1 - b0) * speed
                    ofilters = [f"trim=start={sub_src:.3f}:end={sub_src + sub_src_dur:.3f}",
                                "setpts=PTS-STARTPTS"]
                    if speed != 1.0:
                        ofilters.append(f"setpts=PTS/{speed:.4f}")
                    if scale_pts:
                        sexpr = _piecewise_expr(
                            [(t - b0, v) for t, v in scale_pts
                             if b0 - 1e-9 <= t <= b1 + 1e-9] or
                            [(b0, _interp(scale_pts, b0))], "t")
                        ofilters.append(
                            f"scale=w='{out_w}*({sexpr})':h='{out_h}*({sexpr})':eval=frame")
                    else:
                        ofilters.append(
                            f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                            f"crop={out_w}:{out_h}")
                    ofilters.append(f"fps={fps_str}")
                    ofilters.extend(_color_filters(item))
                    ofilters.append("format=yuva420p")
                    ofilters.append(f"colorchannelmixer=aa={_num(held)}")
                    olabel = next_label("ov")
                    filter_parts.append(
                        f"[{idx}:v]{','.join(ofilters)}[{olabel}]")
                    out_label = next_label("vov")
                    x_arg = f"(main_w-overlay_w)*({x_expr})" if x_expr else "0"
                    y_arg = f"(main_h-overlay_h)*({y_expr})" if y_expr else "0"
                    filter_parts.append(
                        f"[{current}][{olabel}]overlay={x_arg}:{y_arg}:"
                        f"enable='between(t,{adjust(start_s + b0):.3f},"
                        f"{adjust(start_s + b1):.3f})'[{out_label}]")
                    current = out_label
                    overlay_count += 1
            else:
                ofilters = [f"trim=start={src_s:.3f}:end={src_s + dur_s * speed:.3f}",
                            "setpts=PTS-STARTPTS"]
                if speed != 1.0:
                    ofilters.append(f"setpts=PTS/{speed:.4f}")
                if scale_pts:
                    sexpr = _piecewise_expr(scale_pts, "t")
                    ofilters.append(
                        f"scale=w='{out_w}*({sexpr})':h='{out_h}*({sexpr})':eval=frame")
                else:
                    ofilters.append(
                        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                        f"crop={out_w}:{out_h}")
                ofilters.append(f"fps={fps_str}")
                ofilters.extend(_color_filters(item))
                ofilters.append("format=yuva420p")
                if len(op_pts) == 1:
                    ofilters.append(f"colorchannelmixer=aa={_num(op_pts[0][1])}")
                olabel = next_label("ov")
                filter_parts.append(f"[{idx}:v]{','.join(ofilters)}[{olabel}]")
                out_label = next_label("vov")
                x_arg = f"(main_w-overlay_w)*({x_expr})" if x_expr else "0"
                y_arg = f"(main_h-overlay_h)*({y_expr})" if y_expr else "0"
                filter_parts.append(
                    f"[{current}][{olabel}]overlay={x_arg}:{y_arg}:"
                    f"enable='between(t,{start_adj:.3f},{adjust(start_s + dur_s):.3f})'"
                    f"[{out_label}]")
                current = out_label
                overlay_count += 1
            if medium.get("hasAudio", True):
                skipped.append(f"overlay {item['id']} audio (renders "
                               "overlay picture only)")

    # ---- text overlays (position/opacity/scale keyframes) -------------
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
            dur_s = frames_to_seconds(item["dur"], fmt["fps"])
            start_adj = adjust(start_s)
            end_adj = adjust(start_s + dur_s)
            x_pts = keyframe_points(item, "x", fmt["fps"])
            y_pts = keyframe_points(item, "y", fmt["fps"])
            scale_pts = keyframe_points(item, "scale", fmt["fps"])
            op_pts = keyframe_points(item, "opacity", fmt["fps"])
            if x_pts:
                x_arg = f"(w-text_w)*({_piecewise_expr([(t + start_adj, v) for t, v in x_pts], 't')})"
            else:
                x_arg = f"(w-text_w)*{pos_x:.3f}"
            if y_pts:
                y_arg = f"(h-text_h)*({_piecewise_expr([(t + start_adj, v) for t, v in y_pts], 't')})"
            else:
                y_arg = f"(h-text_h)*{pos_y:.3f}"
            if scale_pts:
                fs_arg = f"({fontsize})*({_piecewise_expr([(t + start_adj, v) for t, v in scale_pts], 't')})"
            else:
                fs_arg = str(fontsize)
            alpha_arg = None
            if op_pts:
                alpha_arg = _piecewise_expr(
                    [(t + start_adj, v) for t, v in op_pts], "t")
            out_label = next_label("vtxt")
            parts = (f"[{current}]drawtext=fontfile='{font}':"
                     f"text='{_escape_drawtext(text)}':fontsize={fs_arg}:"
                     f"fontcolor=white:borderw=2:bordercolor=black:"
                     f"x={x_arg}:y={y_arg}:")
            if alpha_arg is not None:
                parts += f"alpha='{alpha_arg}':"
            parts += (f"enable='between(t,{start_adj:.3f},{end_adj:.3f})'"
                      f"[{out_label}]")
            filter_parts.append(parts)
            current = out_label
            text_count += 1

    # ---- audio mix -----------------------------------------------------
    extra_audio = []
    for track in project["tracks"]:
        if track["kind"] != "audio":
            continue
        for item in track["items"]:
            medium = next((m for m in project["media"]
                           if m["id"] == item.get("media")), None)
            if medium is None:
                continue
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
                        "asetpts=PTS-STARTPTS"]
            afilters.extend(volume_filters(item, dur_s))
            afilters.append(f"adelay={int(adjust(start_s) * 1000)}:all=1")
            afilters.append(f"apad=whole_dur={total_s:.3f}")
            label = next_label("aextra")
            filter_parts.append(f"[{idx}:a]{','.join(afilters)}[{label}]")
            extra_audio.append(f"[{label}]")
    all_audio = ([f"[{achain}]"] if achain else []) + extra_audio
    audio_map = None
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
        "segments": segment_count,
        "transitions": len(boundaries),
    }


def _interp(points: list[tuple[float, float]], t: float) -> float:
    """Local helper: interpolate (used for opacity-split scale fallback)."""
    if not points:
        return 1.0
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            return v0 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]
