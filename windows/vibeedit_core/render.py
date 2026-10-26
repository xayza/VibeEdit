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

Phase 3 additions: full xfade transition kinds, main-track
position/scale/opacity keyframes (zoompan / stepwise alpha),
LUT strength via blended .cube files, overlay-item audio at its
timeline position, and single-pass loudnorm on export.

Phase 4 additions: adjustment layers (eq/LUT with enable windows on
the main picture), karaoke captions (one burned .ass track via the
subtitles filter), tilt keyframes (FFmpeg rotate, per-frame angle
expression), and music ducking (sidechaincompress with the main
audio as sidechain). Beat grids are detected and stored, not baked
into the picture (they drive markers and snap, and are drawn on the
web UI ruler).
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


def blended_cube_path(lut: str, strength: float, out_dir: str) -> str:
    """Write a .cube that blends the identity LUT with ``lut``.

    Each grid point becomes (1-strength)*identity + strength*lut, so
    strength 0 renders exactly the original picture and strength 1
    renders the full LUT. Grid order in a .cube file is R fastest,
    then G, then B; DOMAIN_MIN/MAX are honoured when present.
    Raises ValueError on unparseable LUT data.
    """
    import hashlib
    validate_cube(lut)
    domain_min = [0.0, 0.0, 0.0]
    domain_max = [1.0, 1.0, 1.0]
    size = None
    values: list[tuple[float, float, float]] = []
    with open(lut, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("LUT_3D_SIZE"):
                size = int(line.split()[1])
            elif line.startswith("DOMAIN_MIN"):
                domain_min = [float(v) for v in line.split()[1:4]]
            elif line.startswith("DOMAIN_MAX"):
                domain_max = [float(v) for v in line.split()[1:4]]
            elif line.startswith(("TITLE", "DOMAIN_")):
                continue
            else:
                parts = line.split()
                if len(parts) != 3:
                    raise ValueError(f"Invalid .cube data line: {line!r}")
                values.append(tuple(float(v) for v in parts))
    if size is None or len(values) != size ** 3:
        raise ValueError(
            f"LUT grid mismatch in {lut}: size {size}, "
            f"{len(values)} data lines")
    key = hashlib.sha256(
        f"{lut}|{strength:.4f}".encode()).hexdigest()[:12]
    out_path = os.path.join(out_dir, f"blended-{key}.cube")
    if not os.path.isfile(out_path):
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(f"# VibeEdit blended LUT (strength {strength:.4f})\n")
            fh.write(f"LUT_3D_SIZE {size}\n")
            fh.write("DOMAIN_MIN " + " ".join(f"{v:g}" for v in domain_min) + "\n")
            fh.write("DOMAIN_MAX " + " ".join(f"{v:g}" for v in domain_max) + "\n")
            idx = 0
            for b in range(size):
                for g in range(size):
                    for r in range(size):
                        ident = (
                            domain_min[0] + r / (size - 1) * (domain_max[0] - domain_min[0]),
                            domain_min[1] + g / (size - 1) * (domain_max[1] - domain_min[1]),
                            domain_min[2] + b / (size - 1) * (domain_max[2] - domain_min[2]),
                        )
                        vals = values[idx]
                        idx += 1
                        blended = tuple(
                            (1.0 - strength) * ident[c] + strength * vals[c]
                            for c in range(3))
                        fh.write(" ".join(f"{v:.6f}" for v in blended) + "\n")
    return out_path


def _color_filters(item: dict, lut_dir: str | None = None) -> list[str]:
    """lut3d + eq filters for a clip. Raises on a bad LUT.

    LUT strength (0..1, default 1.0) is rendered honestly by blending
    the LUT with the identity LUT into a temporary .cube file (see
    blended_cube_path); strength 0 skips the LUT entirely.
    """
    filters: list[str] = []
    color = item.get("color") or {}
    lut = color.get("lut")
    if lut:
        strength = float(color.get("strength", 1.0))
        if strength > 0.0:
            if strength < 1.0:
                if lut_dir is None:
                    raise ValueError(
                        "LUT strength blending needs a render temp dir")
                lut = blended_cube_path(lut, strength, lut_dir)
            else:
                validate_cube(lut)
            filters.append(f"lut3d=file='{lut}'")
    preset = color.get("preset")
    if preset and preset != "none":
        if preset not in COLOR_PRESETS:
            raise ValueError(f"Unknown colour preset: {preset!r}")
        filters.append(COLOR_PRESETS[preset])
    return filters


def render(project: dict, folder: str, output: str, preset: str = "full",
           normalize_audio: bool = False, ducking: bool | None = None) -> dict:
    """Render the project with FFmpeg. Returns a report dict.

    ``preset``: "full" (project resolution, fast preset) or "draft"
    (half resolution, veryfast preset, higher CRF).
    ``normalize_audio``: single-pass EBU R128 loudnorm (I=-16, TP=-1.5,
    LRA=11) applied to the final mixed audio.
    ``ducking``: None = use the project's audio.ducking setting;
    True/False forces music ducking on/off for this render only.
    """
    import tempfile
    lut_dir = tempfile.mkdtemp(prefix="vibeedit-lut-")
    try:
        return _render_inner(project, folder, output, preset,
                             normalize_audio, lut_dir, ducking)
    finally:
        import shutil
        shutil.rmtree(lut_dir, ignore_errors=True)


def _render_inner(project: dict, folder: str, output: str, preset: str,
                  normalize_audio: bool, lut_dir: str,
                  ducking_override: bool | None = None) -> dict:
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

    def _motion_filter(item: dict) -> str | None:
        """zoompan filter for main-track x/y/scale keyframes.

        zoompan's ``on`` variable is the output frame count, so
        keyframe times (seconds, clip-local) are converted to frames.
        Position fractions 0..1 become crop-window offsets.
        Returns None when the item has no motion keyframes.
        """
        fps_f = fps_value(fmt["fps"])
        x_pts = [(t * fps_f, v) for t, v in
                 keyframe_points(item, "x", fmt["fps"])]
        y_pts = [(t * fps_f, v) for t, v in
                 keyframe_points(item, "y", fmt["fps"])]
        s_pts = [(t * fps_f, v) for t, v in
                 keyframe_points(item, "scale", fmt["fps"])]
        if not (x_pts or y_pts or s_pts):
            return None
        z_expr = _piecewise_expr(s_pts, "on") if s_pts else "1"
        x_expr = (f"(iw-ow)*({_piecewise_expr(x_pts, 'on')})"
                  if x_pts else "(iw-ow)/2")
        y_expr = (f"(ih-oh)*({_piecewise_expr(y_pts, 'on')})"
                  if y_pts else "(ih-oh)/2")
        return (f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:"
                f"s={out_w}x{out_h}:fps={fps_str}")

    def _tilt_filter(item: dict, time_offset: float = 0.0) -> str | None:
        """FFmpeg rotate filter for tilt keyframes (degrees -> radians).

        The angle is a per-frame expression in clip-local time ``t``
        (verified: rotate's angle expression is evaluated per frame
        on FFmpeg 8.1). ``time_offset`` shifts the keyframe times for
        segments whose timestamps restart (opacity sub-segments).
        Output size is pinned to the input size so the frame size
        never changes mid-chain; rotated corners are filled black.
        Returns None when the item has no tilt keyframes.
        """
        import math
        pts = [(t - time_offset, math.radians(v)) for t, v in
               keyframe_points(item, "tilt", fmt["fps"])]
        if not pts:
            return None
        return (f"rotate=a='{_piecewise_expr(pts, 't')}':"
                f"ow='iw':oh='ih':c=black")

    def _main_range_segment(item: dict, local_start: float, local_dur: float,
                            alpha: float | None, fade_in: float,
                            fade_out: float) -> tuple[str, float]:
        """One main-track video segment (optionally a sub-range used
        for stepwise opacity). Returns (label, duration)."""
        dur_s = local_dur
        speed = float(item.get("speed", 1.0))
        medium = next((m for m in project["media"]
                       if m["id"] == item["media"]), None)
        if medium is None:
            raise KeyError(f"Media not found: {item['media']}")
        src = media_path(item["media"])
        idx = add_input(src)
        src_s = item.get("in", 0) / media_fps(medium) + local_start * speed
        src_dur_s = local_dur * speed
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
        vfilters.extend(_color_filters(item, lut_dir))
        motion = _motion_filter(item)
        if motion is not None:
            vfilters.append(motion)
            # Do NOT append an fps filter after zoompan: zoompan's
            # output timestamps use its own timebase, and a trailing
            # fps filter duplicates frames ~512x (verified: 90 input
            # frames became 46080). zoompan's own fps= option already
            # sets the output rate, and the segment is exact without it.
        else:
            vfilters.append(f"fps={fps_str}")
        tilt = _tilt_filter(item, local_start)
        if tilt is not None:
            vfilters.append(tilt)
        if alpha is not None:
            vfilters.append("format=yuva420p")
            vfilters.append(f"colorchannelmixer=aa={_num(alpha)}")
            vfilters.append("format=yuv420p")
        else:
            vfilters.append("format=yuv420p")
        if fade_in > 0:
            vfilters.append(f"fade=t=in:st=0:d={min(fade_in, dur_s):.3f}")
        if fade_out > 0:
            vfilters.append(
                f"fade=t=out:st={max(dur_s - fade_out, 0):.3f}:d={min(fade_out, dur_s):.3f}")
        filter_parts.append(f"[{idx}:v]{','.join(vfilters)}[{label}]")
        return label, dur_s

    def main_video_segment(item: dict, skip_fade_in: bool,
                           skip_fade_out: bool) -> tuple[str, float]:
        """Main-track video segment with Phase 3 keyframe rendering.

        x/y/scale keyframes render via zoompan; volume keyframes
        render in main_audio_segment (already in Phase 2). Opacity
        keyframes render stepwise (see overlay note): the clip is
        split at its opacity-keyframe times with a constant alpha per
        segment. The rare combination of opacity segments AND motion
        keyframes on one main clip skips the motion part (zoompan's
        frame counter restarts per segment, so its timing would be
        wrong); that case is reported in ``skipped``.
        """
        dur_s = frames_to_seconds(item["dur"], fmt["fps"])
        fade_in = 0.0 if skip_fade_in else float(item.get("fadeIn", 0) or 0)
        fade_out = 0.0 if skip_fade_out else float(item.get("fadeOut", 0) or 0)
        _medium = next((m for m in project["media"]
                        if m["id"] == item.get("media")), None)
        if _medium is not None and _medium.get("kind") == "image" \
                and item.get("keyframes"):
            skipped.append(f"main image clip {item['id']} keyframes "
                           "stored, not rendered")
        op_pts = keyframe_points(item, "opacity", fmt["fps"])
        has_motion = bool(keyframe_points(item, "x", fmt["fps"])
                          or keyframe_points(item, "y", fmt["fps"])
                          or keyframe_points(item, "scale", fmt["fps"]))
        if len(op_pts) >= 2:
            if has_motion:
                skipped.append(
                    f"main clip {item['id']} motion keyframes skipped "
                    "(combined with opacity segments)")
                # Temporarily drop motion for the segmented render.
                item = dict(item)
                item["keyframes"] = [kf for kf in item.get("keyframes") or []
                                     if not any(p in kf for p in ("x", "y", "scale"))]
            bounds = [0.0] + [t for t, _ in op_pts if 0.0 < t < dur_s] + [dur_s]
            bounds = sorted(set(bounds))
            seg_labels: list[str] = []
            for i, (b0, b1) in enumerate(zip(bounds, bounds[1:])):
                if b1 - b0 < 1e-6:
                    continue
                held = None
                for t_kf, v_kf in op_pts:
                    if t_kf <= b0 + 1e-9:
                        held = v_kf
                if held is None:
                    held = op_pts[0][1]
                label, _ = _main_range_segment(
                    item, b0, b1 - b0, held,
                    fade_in if i == 0 else 0.0,
                    fade_out if i == len(bounds) - 2 else 0.0)
                seg_labels.append(label)
            if len(seg_labels) == 1:
                return seg_labels[0], dur_s
            out_label = next_label("vop")
            inputs = "".join(f"[{lbl}]" for lbl in seg_labels)
            filter_parts.append(
                f"{inputs}concat=n={len(seg_labels)}:v=1:a=0[{out_label}]")
            return out_label, dur_s
        alpha = op_pts[0][1] if len(op_pts) == 1 else None
        return _main_range_segment(item, 0.0, dur_s, alpha,
                                   fade_in, fade_out)

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

    # ---- Phase 4: adjustment layers ----------------------------------
    # Each layer applies its colour preset and/or LUT to the main-track
    # picture only, for its own time range (eq/lut3d with an enable
    # expression). Overlays composited afterwards are not adjusted.
    adjustment_count = 0
    for track in project["tracks"]:
        if track.get("role") != "adjustment":
            continue
        for item in sorted(track["items"], key=lambda i: i["at"]):
            start_adj = adjust(frames_to_seconds(item["at"], fmt["fps"]))
            end_adj = adjust(frames_to_seconds(item["at"] + item["dur"],
                                               fmt["fps"]))
            filters = _color_filters(item, lut_dir)
            if not filters:
                skipped.append(f"adjustment {item['id']} (no colour set)")
                continue
            timed = [f"{f}:enable='between(t,{start_adj:.3f},"
                     f"{end_adj:.3f})'" for f in filters]
            out_label = next_label("vadj")
            filter_parts.append(f"[{current}]{','.join(timed)}[{out_label}]")
            current = out_label
            adjustment_count += 1

    # ---- overlay video tracks (position/scale/opacity keyframes) ------
    overlay_count = 0
    overlay_audio: list[str] = []
    for track in project["tracks"]:
        if track["kind"] != "video" or track.get("role") in ("main", "adjustment"):
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
                    ofilters.extend(_color_filters(item, lut_dir))
                    _tilt = _tilt_filter(item, b0)
                    if _tilt is not None:
                        ofilters.append(_tilt)
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
                ofilters.extend(_color_filters(item, lut_dir))
                _tilt = _tilt_filter(item)
                if _tilt is not None:
                    ofilters.append(_tilt)
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
                # Phase 3: overlay audio renders at its timeline
                # position, like main-track audio (delayed + padded).
                oa_filters = [
                    f"atrim=start={src_s:.3f}:end={src_s + dur_s * speed:.3f}",
                    "asetpts=PTS-STARTPTS"]
                if speed != 1.0:
                    oa_filters.append(_atempo_chain(speed))
                oa_filters.extend(volume_filters(item, dur_s))
                oa_filters.append(
                    f"adelay={int(adjust(start_s) * 1000)}:all=1")
                oa_filters.append(f"apad=whole_dur={total_s:.3f}")
                oa_filters.append("aresample=48000")
                oa_filters.append("aformat=channel_layouts=stereo")
                oa_label = next_label("aov")
                filter_parts.append(
                    f"[{idx}:a]{','.join(oa_filters)}[{oa_label}]")
                overlay_audio.append(f"[{oa_label}]")

    # ---- text overlays (position/opacity/scale keyframes) -------------
    font = find_font()
    text_count = 0
    karaoke_rendered = 0
    for track in project["tracks"]:
        if track["kind"] != "text":
            continue
        for item in sorted(track["items"], key=lambda i: i["at"]):
            if "karaoke" in item:
                # Rendered below as one burned .ass track, not drawtext.
                continue
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

    # ---- Phase 4: karaoke captions (one burned .ass track) -----------
    # All karaoke items become Dialogue lines with \k word tags in a
    # single .ass file, burned with the subtitles (libass) filter.
    # Dialogue times are absolute (transition-adjusted) timeline times.
    karaoke_items = []
    for track in project["tracks"]:
        if track["kind"] != "text":
            continue
        for item in sorted(track["items"], key=lambda i: i["at"]):
            karaoke = item.get("karaoke")
            if not karaoke:
                continue
            style = item.get("textStyle") or {}
            start_adj = adjust(frames_to_seconds(item["at"], fmt["fps"]))
            karaoke_items.append({
                "start_s": start_adj,
                "end_s": adjust(frames_to_seconds(item["at"] + item["dur"],
                                                  fmt["fps"])),
                "words": karaoke["words"],
                "size_frac": float(style.get("size", 0.062)),
                "position_y": float(style.get("positionY", 0.8))})
    if karaoke_items:
        from .karaoke import build_ass
        ass_path = os.path.join(lut_dir, "karaoke.ass")
        with open(ass_path, "w", encoding="utf-8") as fh:
            fh.write(build_ass(karaoke_items, out_w, out_h))
        out_label = next_label("vkar")
        filter_parts.append(
            f"[{current}]subtitles=filename='{ass_path}'[{out_label}]")
        current = out_label
        karaoke_rendered = len(karaoke_items)

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
            extra_audio.append((f"[{label}]", track.get("role")))
    # ---- Phase 4: music ducking (sidechaincompress) ------------------
    # When enabled, each music item is compressed with the main-track
    # audio as its sidechain, so music drops while dialogue/main
    # audio is present and returns when it stops. The main chain is
    # split (not consumed twice) so it can feed both the compressor
    # and the final mix.
    duck_cfg = (project.get("audio") or {}).get("ducking") or {}
    duck_enabled = duck_cfg.get("enabled", False) \
        if ducking_override is None else bool(ducking_override)
    ducking_applied = False
    music_labels = [lbl for lbl, role in extra_audio if role == "music"]
    extra_labels = [lbl for lbl, _ in extra_audio]
    if duck_enabled and achain and music_labels:
        sc_labels = [next_label("sc") for _ in music_labels]
        filter_parts.append(
            f"[{achain}]asplit={1 + len(music_labels)}[achain_main]"
            + "".join(f"[{lbl}]" for lbl in sc_labels))
        achain_main = "achain_main"
        ducked = {}
        for lbl, sc in zip(music_labels, sc_labels):
            dlabel = next_label("duck")
            filter_parts.append(
                f"{lbl}[{sc}]sidechaincompress="
                f"threshold={float(duck_cfg.get('threshold', 0.02))}:"
                f"ratio={float(duck_cfg.get('ratio', 2.0))}:"
                f"attack={float(duck_cfg.get('attack', 20.0))}:"
                f"release={float(duck_cfg.get('release', 250.0))}[{dlabel}]")
            ducked[lbl] = f"[{dlabel}]"
        extra_labels = [ducked.get(lbl, lbl) for lbl in extra_labels]
        ducking_applied = True
    else:
        achain_main = achain
    all_audio = ([f"[{achain_main}]"] if achain_main else []) + overlay_audio \
        + extra_labels
    audio_map = None
    if all_audio:
        if len(all_audio) == 1:
            audio_map = all_audio[0]
        else:
            filter_parts.append(
                f"{''.join(all_audio)}amix=inputs={len(all_audio)}:normalize=0[aout]")
            audio_map = "[aout]"
    if normalize_audio and audio_map is not None:
        # Single-pass EBU R128 loudnorm on the final mix.
        filter_parts.append(
            f"{audio_map}loudnorm=I=-16:TP=-1.5:LRA=11[aoutn]")
        audio_map = "[aoutn]"

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
        "overlay_audio_clips": len(overlay_audio),
        "karaoke_items": karaoke_rendered,
        "adjustment_layers": adjustment_count,
        "ducking_applied": ducking_applied,
        "loudness_normalized": bool(normalize_audio and audio_map),
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
