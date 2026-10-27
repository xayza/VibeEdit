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

Phase B6 additions: motion-only transitions (spin, swing, arc,
arc-right, diamond, crash-out, infinite-out, screen-in, screen-out,
dip-black, color-shift, flicker, kaleidoscope) render with real
FFmpeg filter chains, not xfade substitutions — see
MOTION_TRANSITIONS, _motion_segment and list_transition_renderability().
The one original kind that still cannot render is halftone (see
UNRENDERABLE_TRANSITIONS); it raises a clear error, never a silent
dissolve/fade. Reframe (a per-clip crop window in source fractions)
is honoured in the main-track video/still/freeze paths via
reframe_crop_filter(). Wiring note: this file is the renderer only.
Project.add_transition() in project.py and the transitions list in
mcp.py were NOT edited in this batch (other agents own those files),
so motion kinds render through render() with a project dict that
lists them, but the Project/MCP API does not yet accept them — that
registry update is a separate, small follow-up once this batch is
verified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from .project import (frames_to_seconds, fps_value, COLOR_PRESETS,
                      validate_cube, keyframe_points, TRANSITION_XFADE,
                      eq_preset_filter)

# Fallback fonts on the Linux build/test machine. Windows fonts are
# resolved first from the SystemRoot environment variable in
# font_candidates() below — never from a hardcoded drive letter, so
# a Windows install on any drive works.
LINUX_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

# Backwards-compatible alias (Phase 1-4 name); the full candidate
# list, including the Windows SystemRoot entries, is font_candidates().
FONT_CANDIDATES = LINUX_FONT_CANDIDATES


def _filter_path(path: str) -> str:
    """Make a filesystem path safe inside a single-quoted FFmpeg
    filter argument (lut3d file, drawtext fontfile, subtitles
    filename, .ass/.cube paths).

    Phase 7 fix (real Windows export failure): FFmpeg's filter
    parser splits options on EVERY unescaped colon, even one inside
    single quotes — proven on FFmpeg 8.1.2, where
    a font path containing a colon fails with exactly the
    user's error (``No option name near 'C/font.ttf:text=...'``),
    while the same path with the colon escaped as ``\\:``
    renders fine. So a
    Windows drive-letter font path MUST have its colon escaped
    as ``\\:`` — converting backslashes to forward slashes
    alone (the Phase 5 fix) is not enough, and neither is
    single-quote wrapping. Every colon in the path is escaped,
    not just the drive colon, because a colon anywhere else in
    the path splits the same way. On Linux this is a no-op for
    ordinary colon-free paths.
    Plain ``-i`` input files are NOT passed through here — they are
    subprocess arguments and need no filter escaping.
    """
    return (str(path).replace("\\", "/").replace("'", "\\'")
            .replace(":", "\\:"))


def find_tool(name: str) -> str:
    """Locate an FFmpeg tool (``ffmpeg`` or ``ffprobe``).

    Search order: the VIBEEDIT_FFMPEG_DIR environment variable, then
    PATH (shutil.which), then a binary next to the running script /
    next to the frozen executable. Raises FileNotFoundError with a
    clear fix (install FFmpeg / set VIBEEDIT_FFMPEG_DIR / place the
    binary next to the app) instead of surfacing a bare traceback
    from subprocess.
    """
    exe_names = [name] if name.endswith(".exe") else [name, name + ".exe"]
    candidates: list[str] = []
    ffmpeg_dir = os.environ.get("VIBEEDIT_FFMPEG_DIR")
    if ffmpeg_dir:
        for exe in exe_names:
            candidates.append(os.path.join(ffmpeg_dir, exe))
    for exe in exe_names:
        found = shutil.which(exe)
        if found:
            candidates.append(found)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dirs = [os.path.dirname(sys.executable),
                 os.path.dirname(script_dir), script_dir]
    if getattr(sys, "frozen", False):
        base_dirs.insert(0, getattr(sys, "_MEIPASS",
                                    os.path.dirname(sys.executable)))
    for base in base_dirs:
        for exe in exe_names:
            candidates.append(os.path.join(base, exe))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise FileNotFoundError(
        f"FFmpeg tool {name!r} not found. Install FFmpeg and add it "
        f"to PATH, set the VIBEEDIT_FFMPEG_DIR environment variable "
        f"to the folder containing {name}, or place {name} next to "
        f"the VibeEdit script/executable.")


def app_fonts_dir() -> str:
    """App fonts folder (``windows/fonts/`` in a source checkout):
    where fonts_import stores imported fonts. It is searched by
    font_candidates() after the system fonts folder, so an imported
    font becomes usable by the renderer without touching system
    fonts."""
    return os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "fonts"))


def import_font(source_path: str, fonts_dir: str | None = None) -> dict:
    """Import a font file into the app fonts folder. Only .ttf and
    .otf files are accepted; the stored name is unique (never
    overwrites an existing font) and the source file is copied, not
    moved. Returns the stored entry (``fonts_list`` will include it
    because font_candidates() searches the app fonts folder)."""
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"Font file not found: {source_path}")
    ext = os.path.splitext(source_path)[1].lower()
    if ext not in (".ttf", ".otf"):
        raise ValueError(
            f"Only .ttf and .otf fonts can be imported, got {ext!r}")
    folder = fonts_dir or app_fonts_dir()
    os.makedirs(folder, exist_ok=True)
    from .project import unique_media_name
    stored = unique_media_name(folder, os.path.basename(source_path))
    import shutil
    shutil.copyfile(source_path, os.path.join(folder, stored))
    return {"name": stored, "path": os.path.join(folder, stored)}


def font_candidates() -> list[str]:
    """Font search order: VIBEEDIT_FONT is handled in find_font();
    otherwise the Windows fonts folder derived from SystemRoot (or
    SystemDrive) first, then the app fonts folder (imported fonts),
    then the Linux fallbacks. No drive letter
    is hardcoded here, so Windows on any drive is covered."""
    candidates: list[str] = []
    system_root = os.environ.get("SystemRoot")
    if system_root:
        candidates.append(os.path.join(system_root, "Fonts", "arial.ttf"))
        candidates.append(os.path.join(system_root, "Fonts", "segoeui.ttf"))
    else:
        drive = os.environ.get("SystemDrive")
        if drive:
            base = drive.rstrip("\\/")
            candidates.append(base + "\\Fonts\\arial.ttf")
            candidates.append(base + "\\Fonts\\segoeui.ttf")
    # Imported fonts (fonts_import): every font file in the app
    # fonts folder becomes a candidate, after system fonts.
    try:
        app_dir = app_fonts_dir()
        if os.path.isdir(app_dir):
            for name in sorted(os.listdir(app_dir)):
                if name.lower().endswith((".ttf", ".otf")):
                    candidates.append(os.path.join(app_dir, name))
    except Exception:
        pass
    candidates.extend(LINUX_FONT_CANDIDATES)
    return candidates


def find_font() -> str | None:
    """First existing font, or None when none is found.

    VIBEEDIT_FONT overrides the search: when it is set it must
    point at an existing font file, otherwise a clear error is
    raised instead of silently falling back to a different font.
    """
    override = os.environ.get("VIBEEDIT_FONT")
    if override:
        if os.path.isfile(override):
            return override
        raise FileNotFoundError(
            f"VIBEEDIT_FONT points at a missing font file: {override!r}. "
            f"Point it at an existing .ttf file or unset it to use "
            f"the automatic font search.")
    for path in font_candidates():
        if os.path.isfile(path):
            return path
    return None


def probe_media(path: str) -> dict:
    """ffprobe a file; returns width/height/fps/frames/duration/hasAudio."""
    cmd = [find_tool("ffprobe"), "-v", "quiet", "-print_format", "json",
           "-show_streams", "-show_format", path]
    # Phase 7: decode FFmpeg output as UTF-8 explicitly. The default
    # text encoding on Windows is the locale codepage (typically
    # windows-1252), which turns FFmpeg's UTF-8 output into mojibake
    # (e.g. Vietnamese "chào" displayed as "chÃ o") in error reports.
    out = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=True)
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
            filters.append(f"lut3d=file='{_filter_path(lut)}'")
    preset = color.get("preset")
    if preset and preset != "none":
        if preset not in COLOR_PRESETS:
            raise ValueError(f"Unknown colour preset: {preset!r}")
        # Phase 5: eq presets honour preset_strength (0..1, default
        # 1.0); strength 0 skips the eq filter entirely.
        eq_filter = eq_preset_filter(
            preset, float(color.get("preset_strength", 1.0)))
        if eq_filter:
            filters.append(eq_filter)
    # Code-gap batch: per-parameter eq sliders (original's individual
    # colour controls). Chained after any preset filter; only the
    # parameters actually stored are emitted, so a brightness-only
    # adjustment does not touch contrast/saturation.
    eq = color.get("eq") or {}
    if isinstance(eq, dict) and eq:
        parts = []
        for key in ("brightness", "contrast", "saturation", "gamma"):
            if key in eq:
                parts.append(f"{key}={float(eq[key]):g}")
        if parts:
            filters.append("eq=" + ":".join(parts))
    return filters


def reframe_crop_filter(item: dict) -> str | None:
    """Crop filter for a per-clip ``reframe`` window, or None.

    ``reframe`` is a dict of source-frame fractions with top-left
    origin: {"x": left, "y": top, "w": width, "h": height}, each
    0..1, x+w <= 1 and y+h <= 1. The window is cropped from the
    source (never stretched) and the existing fill scale/crop then
    sizes it to the project frame, so a 16:9 source reframed with
    {"x": 0.342, "y": 0, "w": 0.316, "h": 1} becomes a 9:16 window.
    A full-frame window returns None (no-op). A malformed window
    raises ValueError, never silently renders the full frame.
    Main-track clips only (video, still and freeze paths); overlay
    clips do not read ``reframe``.
    """
    ref = item.get("reframe")
    if ref is None:
        return None
    if not isinstance(ref, dict):
        raise ValueError(
            f"reframe must be a dict of x/y/w/h fractions, got {ref!r}")
    try:
        x, y, w, h = (float(ref["x"]), float(ref["y"]),
                      float(ref["w"]), float(ref["h"]))
    except (KeyError, TypeError, ValueError):
        raise ValueError(
            "reframe needs numeric x/y/w/h fractions, "
            f"got {ref!r}")
    if not (0 <= x and 0 <= y and 0 < w <= 1 and 0 < h <= 1
            and x + w <= 1 + 1e-9 and y + h <= 1 + 1e-9):
        raise ValueError(
            f"Invalid reframe window {ref!r}: need 0<=x, 0<=y, "
            "0<w<=1, 0<h<=1, x+w<=1, y+h<=1")
    if x == 0 and y == 0 and w == 1 and h == 1:
        return None
    return (f"crop=w='iw*{w:g}':h='ih*{h:g}':"
            f"x='iw*{x:g}':y='ih*{y:g}'")


# Code-gap batch 2: export presets from the original's
# ExportPreset.swift (sizes/bitrates verbatim; ProRes uses FFmpeg
# prores_ks in a .mov container). ``size`` None = project size
# (proRes) or the original's quickDraft rule (720p-ish). Unknown
# preset names are a hard error, never a silent H.264 fallback.
EXPORT_PRESETS = {
    "tiktok": {"width": 1080, "height": 1920, "bitrate": 8_000_000,
               "codec": "libx264", "ext": "mp4"},
    "reels": {"width": 1080, "height": 1920, "bitrate": 8_000_000,
              "codec": "libx264", "ext": "mp4"},
    "shorts": {"width": 1080, "height": 1920, "bitrate": 8_000_000,
               "codec": "libx264", "ext": "mp4"},
    "feed4x5": {"width": 1080, "height": 1350, "bitrate": 5_000_000,
                "codec": "libx264", "ext": "mp4"},
    "square": {"width": 1080, "height": 1080, "bitrate": 8_000_000,
               "codec": "libx264", "ext": "mp4"},
    "portrait3x4": {"width": 1080, "height": 1440, "bitrate": 8_000_000,
                    "codec": "libx264", "ext": "mp4"},
    "youtube1080": {"width": 1920, "height": 1080, "bitrate": 12_000_000,
                    "codec": "libx264", "ext": "mp4"},
    "youtube4k": {"width": 3840, "height": 2160, "bitrate": 45_000_000,
                  "codec": "libx264", "ext": "mp4"},
    "quickdraft": {"width": None, "height": None, "bitrate": 4_000_000,
                   "codec": "libx264", "ext": "mp4"},
    "prores": {"width": None, "height": None, "bitrate": None,
               "codec": "prores_ks", "ext": "mov"},
    "prores422hq": {"width": None, "height": None, "bitrate": None,
                    "codec": "prores_ks", "ext": "mov"},
}

# Phase B6: motion-only transitions from the original's
# TransitionMotion.builtIns that have no xfade name and were
# previously rejected. Each renders with a real filter chain in
# _motion_segment(); the "dissolve blend" in several entries is
# only the blend between two motion-transformed pictures, never a
# plain dissolve substitution — the motion (rotation, zoom, pan,
# mask, hue, strobe) is what makes the transition. Known honest
# approximations are called out in the method text and in
# _motion_segment: swing rotates about the centre (FFmpeg's rotate
# filter has no left-edge perspective pivot), zoom uses
# scale(eval=frame) centred on a black canvas (zoompan was tried:
# it renders, but its sub-1 zoom handling and per-frame zoom
# expression are less direct than the scale+overlay chain), and
# kaleidoscope is a 2x2 mirrored tile, not a hexagonal mirror.
MOTION_TRANSITIONS = {
    "spin": "rotate (outgoing 0 to -90 deg, incoming 90 to 0 deg) "
            "+ dissolve blend",
    "swing": "incoming damped sinusoidal rotate (70 deg settling, "
             "centre pivot — not a left-edge perspective swing) + "
             "outgoing slight zoom-out + dissolve blend",
    "arc": "pan + zoom (1 to 1.5) + small sinusoidal rotate "
           "(4 deg bump) + dissolve blend",
    "arc-right": "mirror of arc: pan + zoom + sinusoidal rotate "
                 "+ dissolve blend",
    "diamond": "geq-generated growing diamond mask + maskedmerge "
               "(no dissolve)",
    "crash-out": "zoom-out overlay (outgoing 1 to 0.45, incoming "
                 "2 to 1) + dissolve blend",
    "infinite-out": "zoom-out overlay (outgoing 1 to 0.3, incoming "
                    "3.3 to 1) + dissolve blend",
    "screen-in": "zoom overlay (outgoing 1 to 2.5, incoming card "
                "0.45 to 1) + dissolve blend",
    "screen-out": "zoom overlay (outgoing 1 to 0.45 card, incoming "
                 "1.15 to 1) + dissolve blend",
    "dip-black": "fade through black (outgoing fades out over the "
                 "first half, incoming fades in over the second "
                 "half; no dissolve)",
    "color-shift": "hue rotation (outgoing 0 to 180 deg, incoming "
                   "-180 to 0 deg) + saturation change + dissolve "
                   "blend",
    "flicker": "dissolve blend + incoming-picture strobe overlay "
               "(10 Hz, phased so the transition midpoint is a "
               "blend frame, not a plain clip frame)",
    "kaleidoscope": "2x2 mirrored-tile (hflip/vflip quadrants) + "
                    "full rotation + dissolve blend; APPROXIMATION, "
                    "not a true six-way hexagonal kaleidoscope "
                    "(no FFmpeg filter does that)",
}

# Round 4: halftone renders two ways, and pixelize is still never
# substituted for it (pixelize is the glitch effect, not halftone).
#
# 1. Timeline render: an animated halftone dot mask built with the
#    FFmpeg geq filter (dot radius grows with transition progress)
#    driving maskedmerge between the outgoing tail and incoming
#    head. This keeps the real moving pictures on both sides,
#    which a still-frame segment cannot do.
# 2. Standalone pre-rendered segment: render_halftone_segment()
#    below extracts the boundary frames, composites the same dot
#    dissolve with Pillow frame by frame, and encodes a segment
#    file — the path the original plan suggested, kept for preview
#    and for use as a clip.
HALFTONE_TRANSITIONS = {
    "halftone": "animated halftone dot mask (geq) + alphamerge / "
                "overlay; dots grow until the incoming picture "
                "resolves out of dots (timeline), or the Pillow "
                "pre-rendered segment of the same dissolve "
                "(standalone)",
}

# Original kinds that still cannot render after a genuine attempt.
# They raise a clear error naming the kind and the reason (see
# _render_inner validation), never a silent dissolve/fade. Empty
# since round 4 (halftone was the only entry); kept so validation
# code that consults it keeps working and future kinds have a home.
UNRENDERABLE_TRANSITIONS: dict[str, str] = {}


def transition_renderability(kind: str) -> dict:
    """Honest renderability record for one transition kind.

    Returns {"kind", "renders", "method", "reason"}: "method" is
    the xfade name or the motion filter chain for kinds that
    render, None otherwise; "reason" is set only for kinds that
    do not render (unrenderable or unknown).
    """
    if kind in UNRENDERABLE_TRANSITIONS:
        return {"kind": kind, "renders": False, "method": None,
                "reason": UNRENDERABLE_TRANSITIONS[kind]}
    if kind in HALFTONE_TRANSITIONS:
        return {"kind": kind, "renders": True,
                "method": HALFTONE_TRANSITIONS[kind], "reason": None}
    if kind in MOTION_TRANSITIONS:
        return {"kind": kind, "renders": True,
                "method": MOTION_TRANSITIONS[kind], "reason": None}
    if kind in TRANSITION_XFADE:
        return {"kind": kind, "renders": True,
                "method": f"xfade:{TRANSITION_XFADE[kind]}",
                "reason": None}
    return {"kind": kind, "renders": False, "method": None,
            "reason": f"Unknown transition kind: {kind!r}"}


def list_transition_renderability() -> list[dict]:
    """All known transition kinds with an honest renders flag.

    Covers every xfade kind in project.TRANSITION_XFADE plus the
    Phase B6 motion kinds and the still-unrenderable kinds, sorted
    by kind name with no duplicates. The MCP transitions_list
    (mcp.py, owned by another agent in this batch) should merge
    this list so the new kinds appear there with the same flag.
    """
    kinds = sorted(set(TRANSITION_XFADE) | set(MOTION_TRANSITIONS)
                   | set(HALFTONE_TRANSITIONS)
                   | set(UNRENDERABLE_TRANSITIONS))
    return [transition_renderability(kind) for kind in kinds]


def halftone_frame(a_image, b_image, progress: float, cell: int = 24):
    """One frame of a halftone dissolve: dots of ``b_image`` grow
    over ``a_image`` as ``progress`` goes 0 -> 1.

    The mask is a grid of circles whose radius grows with progress;
    at progress 1 the radius (0.72 * cell) exceeds the cell-corner
    distance (0.707 * cell), so the frame is fully ``b_image``.
    Pillow is imported here (lazy) so importing render.py never
    fails when Pillow is absent.
    """
    from PIL import Image, ImageDraw
    a = a_image.convert("RGB")
    b = b_image.convert("RGB").resize(a.size)
    p = max(0.0, min(1.0, float(progress)))
    mask = Image.new("L", a.size, 0)
    radius = p * cell * 0.72
    if radius > 0:
        draw = ImageDraw.Draw(mask)
        step = max(2, int(cell))
        for cy in range(step // 2, a.size[1] + step // 2, step):
            for cx in range(step // 2, a.size[0] + step // 2, step):
                draw.ellipse([cx - radius, cy - radius,
                              cx + radius, cy + radius], fill=255)
    return Image.composite(b, a, mask)


def _extract_boundary_frame(src: str, out: str, last: bool) -> None:
    """Extract the first (or near-last) frame of ``src`` to ``out``.

    The last frame uses ``-sseof`` because the exact frame count
    is not always known; 0.05s before the end is the boundary
    frame for any transition-length purpose and is documented as
    such. Raises on FFmpeg failure.
    """
    cmd = [find_tool("ffmpeg"), "-y", "-v", "error"]
    if last:
        cmd += ["-sseof", "-0.05"]
    cmd += ["-i", src, "-frames:v", "1", out]
    subprocess.run(cmd, capture_output=True, text=True, check=True)


def render_halftone_segment(a_path: str, b_path: str, out_path: str,
                            duration_s: float, fps: float,
                            width: int, height: int,
                            cell: int = 24) -> dict:
    """Pre-render a halftone dissolve segment file (round 4).

    Extracts the last frame of ``a_path`` and the first frame of
    ``b_path``, composites ``n`` Pillow dot-dissolve frames, and
    encodes them to ``out_path`` (H.264, yuv420p). Returns
    {"path", "frames", "width", "height", "duration"}. This is the
    standalone segment path: the timeline render itself uses the
    geq maskedmerge variant (same dissolve, motion-preserving),
    because a still-frame segment would freeze motion during the
    transition window. Raises when Pillow or FFmpeg is absent, or
    when either boundary frame cannot be extracted.
    """
    from PIL import Image
    import tempfile
    if duration_s <= 0 or fps <= 0 or width <= 0 or height <= 0:
        raise ValueError(
            "render_halftone_segment needs positive duration, fps, "
            "width and height")
    n_frames = max(1, int(round(float(fps) * float(duration_s))))
    tmpdir = tempfile.mkdtemp(prefix="vibeedit-halftone-")
    try:
        a_png = os.path.join(tmpdir, "a.png")
        b_png = os.path.join(tmpdir, "b.png")
        _extract_boundary_frame(a_path, a_png, last=True)
        _extract_boundary_frame(b_path, b_png, last=False)
        a = Image.open(a_png).convert("RGB").resize((width, height))
        b = Image.open(b_png).convert("RGB").resize((width, height))
        for i in range(n_frames):
            frame = halftone_frame(a, b, (i + 1) / n_frames, cell)
            frame.save(os.path.join(tmpdir, f"f_{i:04d}.png"))
        cmd = [find_tool("ffmpeg"), "-y", "-v", "error",
               "-framerate", str(fps), "-i",
               os.path.join(tmpdir, "f_%04d.png"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p",
               "-r", str(fps), out_path]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return {"path": out_path, "frames": n_frames, "width": width,
            "height": height, "duration": float(duration_s)}


def generate_proxy(src: str, out_path: str, width: int = 540) -> dict:
    """Transcode ``src`` to a low-resolution proxy file (round 5).

    H.264 / yuv420p video scaled to ``width`` (default 540px,
    aspect preserved, height auto and even) plus AAC audio, veryfast
    preset. The proxy is a derived file for fast preview/editing —
    it is NOT registered as a new timeline media entry. Raises
    ValueError when the source has no video stream (an audio-only
    file needs no video proxy) and propagates FFmpeg failures.
    """
    info = probe_media(src)
    if not info.get("width"):
        raise ValueError(
            "generate_proxy needs a video source; %s has no video "
            "stream" % (src,))
    try:
        width = int(width)
    except (TypeError, ValueError) as exc:
        raise ValueError("proxy width must be an integer") from exc
    if width < 2:
        raise ValueError("proxy width must be >= 2")
    if width % 2:
        width -= 1
    os.makedirs(os.path.dirname(os.path.abspath(out_path)),
                exist_ok=True)
    cmd = [find_tool("ffmpeg"), "-y", "-v", "error",
           "-i", src, "-vf", "scale=%d:-2" % (width,),
           "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-movflags", "+faststart", out_path]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    out_info = probe_media(out_path)
    return {"path": out_path, "width": out_info.get("width"),
            "height": out_info.get("height"),
            "duration": out_info.get("duration"), "source": src}


def export_preset_info(name: str, project_width: int,
                       project_height: int) -> dict:
    """Resolve an export preset name to concrete parameters. Aliases
    follow the original's ExportPreset.aliases (e.g. youtube-1080,
    youtube-4k, prores-422-hq, draft)."""
    key = (name or "").lower().replace("_", "-")
    aliases = {"tiktok-9x16": "tiktok", "instagram-reels": "reels",
               "youtube-shorts": "shorts", "feed-4x5": "feed4x5",
               "4x5": "feed4x5", "instagram-feed": "feed4x5",
               "1x1": "square", "feed-1x1": "square",
               "portrait-3x4": "portrait3x4", "3x4": "portrait3x4",
               "xiaohongshu": "portrait3x4", "youtube-1080": "youtube1080",
               "youtube-1080p": "youtube1080", "youtube-4k": "youtube4k",
               "quick-draft": "quickdraft", "draft": "quickdraft",
               "720p": "quickdraft", "prores-422-hq": "prores",
               "prores": "prores"}
    key = aliases.get(key, key)
    if key not in EXPORT_PRESETS:
        raise ValueError(
            f"Unknown export preset: {name!r} "
            f"(choose one of {', '.join(sorted(EXPORT_PRESETS))})")
    info = dict(EXPORT_PRESETS[key])
    if info["width"] is None:
        if key == "quickdraft":
            if project_width == project_height:
                info["width"], info["height"] = 720, 720
            elif project_width >= project_height:
                info["width"] = 1280
                info["height"] = max(2, 1280 * project_height
                                     // project_width // 2 * 2)
            else:
                info["width"] = max(2, 1280 * project_width
                                    // project_height // 2 * 2)
                info["height"] = 1280
        else:
            info["width"], info["height"] = project_width, project_height
    return info


def render(project: dict, folder: str, output: str, preset: str = "full",
           normalize_audio: bool = False, ducking: bool | None = None,
           export_preset: str | None = None) -> dict:
    """Render the project with FFmpeg. Returns a report dict.

    ``preset``: "full" (project resolution, fast preset) or "draft"
    (half resolution, veryfast preset, higher CRF).
    ``export_preset``: an original ExportPreset name (see
    EXPORT_PRESETS) overriding resolution/codec/bitrate/container;
    unknown names raise, never fall back silently.
    ``normalize_audio``: single-pass EBU R128 loudnorm (I=-16, TP=-1.5,
    LRA=11) applied to the final mixed audio.
    ``ducking``: None = use the project's audio.ducking setting;
    True/False forces music ducking on/off for this render only.
    """
    import tempfile
    lut_dir = tempfile.mkdtemp(prefix="vibeedit-lut-")
    try:
        return _render_inner(project, folder, output, preset,
                             normalize_audio, lut_dir, ducking,
                             export_preset)
    finally:
        import shutil
        shutil.rmtree(lut_dir, ignore_errors=True)


def _render_inner(project: dict, folder: str, output: str, preset: str,
                  normalize_audio: bool, lut_dir: str,
                  ducking_override: bool | None = None,
                  export_preset: str | None = None) -> dict:
    fmt = project["format"]
    width, height = int(fmt["width"]), int(fmt["height"])
    fps = fps_value(fmt["fps"])
    fps_str = f"{fps:.3f}".rstrip("0").rstrip(".")
    if preset == "draft":
        out_w, out_h = max(width // 2, 2), max(height // 2, 2)
        ff_preset, crf = "veryfast", "28"
    else:
        out_w, out_h, ff_preset, crf = width, height, "fast", "20"
    # Code-gap batch 2: export presets override resolution/codec.
    preset_info = None
    video_codec, video_bitrate = "libx264", None
    if export_preset:
        preset_info = export_preset_info(export_preset, width, height)
        out_w, out_h = preset_info["width"], preset_info["height"]
        video_codec = preset_info["codec"]
        video_bitrate = preset_info["bitrate"]
        if video_codec == "prores_ks":
            ff_preset, crf = None, None

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
        if kind in UNRENDERABLE_TRANSITIONS:
            raise ValueError(
                f"Transition kind {kind!r} cannot be rendered: "
                f"{UNRENDERABLE_TRANSITIONS[kind]}")
        if kind not in TRANSITION_XFADE \
                and kind not in MOTION_TRANSITIONS \
                and kind not in HALFTONE_TRANSITIONS:
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
            if trans["kind"] in MOTION_TRANSITIONS or trans["kind"] in HALFTONE_TRANSITIONS:
                chain_motion_video(label, dur_s, trans)
                return
            if trans["kind"] in UNRENDERABLE_TRANSITIONS:
                raise ValueError(
                    f"Transition kind {trans['kind']!r} cannot be "
                    f"rendered: {UNRENDERABLE_TRANSITIONS[trans['kind']]}")
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

    def _motion_segment(vtail: str, vhead: str, kind: str,
                        trans_s: float) -> str:
        """Build one motion-transition segment (Phase B6).

        ``vtail`` is the last ``trans_s`` of the outgoing picture
        and ``vhead`` the first ``trans_s`` of the incoming picture,
        both with timestamps from 0. Returns a label exactly
        ``trans_s`` long at project size/fps in yuv420p. Each input
        label is consumed exactly once at this level (branches that
        need an input twice split it themselves, e.g. flicker).
        Time ``t`` inside every expression is transition-local
        (0..trans_s) because both inputs were reset with
        setpts=PTS-STARTPTS before arriving here. ``p`` below is
        transition progress (0..1) as an expression.
        """
        d = f"{trans_s:.3f}"
        w, h = out_w, out_h

        def _apply(src: str, filters: list[str], prefix: str) -> str:
            out = next_label(prefix)
            filter_parts.append(f"[{src}]{','.join(filters)}[{out}]")
            return out

        def _finish(src: str, prefix: str = "mfin") -> str:
            out = next_label(prefix)
            filter_parts.append(
                f"[{src}]fps={fps_str},setpts=PTS-STARTPTS,"
                f"format=yuv420p[{out}]")
            return out

        def _dissolve(a: str, b: str) -> str:
            """Blend two motion-transformed pictures (xfade offset 0
            over the whole segment). The dissolve is the blend, not
            the transition: both pictures already carry the motion.
            """
            out = next_label("mxf")
            filter_parts.append(
                f"[{a}][{b}]xfade=transition=dissolve:duration={d}:"
                f"offset=0[{out}]")
            return _finish(out, "mfin")

        def _rotated(src: str, angle: str) -> str:
            return _apply(src, [
                f"rotate=a='{angle}':ow='iw':oh='ih':c=black",
                "format=yuv420p"], "mrot")

        def _zoomed(src: str, zoom: str, x: str | None = None,
                    y: str | None = None) -> str:
            """Scale by a per-frame zoom expression, centred (or
            panned) on a black canvas. scale(eval=frame) evaluates
            its w/h per frame (verified, unlike eq brightness,
            whose expression is evaluated once and so is never used
            for animation here); overlay x/y are per-frame too. A
            zoom below 1 shows black around the shrunken picture;
            above 1 crops the enlarged picture — both are honest
            zoom behaviour and keep the size at project size.
            """
            scaled = _apply(src, [
                f"scale=w='{w}*({zoom})':h='{h}*({zoom})':eval=frame"],
                "mzsc")
            canvas = next_label("mzcv")
            filter_parts.append(
                f"color=c=black:s={w}x{h}:r={fps_str}:d={d}[{canvas}]")
            out = next_label("mzov")
            x_arg = x or "(main_w-overlay_w)/2"
            y_arg = y or "(main_h-overlay_h)/2"
            filter_parts.append(
                f"[{canvas}][{scaled}]overlay='{x_arg}':'{y_arg}',"
                f"format=yuv420p[{out}]")
            return out

        def _tiled_rotated(src: str, angle: str) -> str:
            """2x2 mirrored tile + rotation (kaleidoscope
            approximation, see MOTION_TRANSITIONS). Quadrants are
            scaled to integer halves, then the stack is scaled back
            to project size so odd project sizes still concat
            cleanly."""
            hw, hh = w // 2, h // 2
            s1, s2, s3, s4 = (next_label("msp") for _ in range(4))
            filter_parts.append(
                f"[{src}]split=4[{s1}][{s2}][{s3}][{s4}]")
            q1 = _apply(s1, [f"scale={hw}:{hh}"], "mtil")
            q2 = _apply(s2, [f"scale={hw}:{hh}", "hflip"], "mtil")
            q3 = _apply(s3, [f"scale={hw}:{hh}", "vflip"], "mtil")
            q4 = _apply(s4, [f"scale={hw}:{hh}", "hflip,vflip"], "mtil")
            top = next_label("mtil")
            filter_parts.append(f"[{q1}][{q2}]hstack[{top}]")
            bot = next_label("mtil")
            filter_parts.append(f"[{q3}][{q4}]hstack[{bot}]")
            stacked = next_label("mtil")
            filter_parts.append(f"[{top}][{bot}]vstack[{stacked}]")
            sized = _apply(stacked, [f"scale={w}:{h}"], "mtil")
            return _rotated(sized, angle)

        p = f"t/{d}"
        if kind == "spin":
            a = _rotated(vtail, f"-1.570796*{p}")
            b = _rotated(vhead, f"1.570796*(1-{p})")
            return _dissolve(a, b)
        if kind == "swing":
            # Damped sinusoidal settle: 70 deg at t=0, oscillating
            # with shrinking amplitude, exactly 0 at t=D. Centre
            # pivot only — FFmpeg rotate has no left-edge
            # perspective pivot, so this is not a true left-edge
            # swing; the method text in MOTION_TRANSITIONS says so.
            a = _zoomed(vtail, f"1-0.08*{p}")
            b = _rotated(vhead,
                         f"1.221730*(1-{p})*cos(6.283185*{p})")
            return _dissolve(a, b)
        if kind in ("arc", "arc-right"):
            s = 1.0 if kind == "arc" else -1.0
            a_rot = _rotated(vtail,
                             f"{0.069813 * s:.6f}*sin(3.141593*{p})")
            a = _zoomed(a_rot, f"1+0.5*{p}",
                        x=f"(main_w-overlay_w)/2{-0.25 * s:+g}"
                          f"*main_w*{p}")
            b_rot = _rotated(vhead,
                             f"{-0.069813 * s:.6f}*sin(3.141593*{p})")
            b = _zoomed(b_rot, f"1.5-0.5*{p}",
                        x=f"(main_w-overlay_w)/2{0.25 * s:+g}"
                          f"*main_w*(1-{p})")
            return _dissolve(a, b)
        if kind == "diamond":
            # Diamond mask: Manhattan distance from the centre,
            # normalised so 0 = centre point and 1 = the corners;
            # the mask opens as t/D grows. geq is per-pixel and
            # therefore slow at large frame sizes — noted in the
            # report, not hidden: long/high-resolution diamond
            # transitions render noticeably slower than xfade.
            cx, cy = w / 2, h / 2
            mask = next_label("mmask")
            # geq's time variable is uppercase T (lowercase t is
            # undefined there and fails filter init — verified).
            p_geq = f"T/{d}"
            filter_parts.append(
                f"nullsrc=s={w}x{h}:r={fps_str}:d={d},"
                f"geq=lum='255*lte((abs(X-{cx:g})/{cx:g}"
                f"+abs(Y-{cy:g})/{cy:g})/2,{p_geq})':"
                f"cb=128:cr=128,format=gray[{mask}]")
            out = next_label("mdia")
            filter_parts.append(
                f"[{vtail}][{vhead}][{mask}]maskedmerge[{out}]")
            return _finish(out, "mfin")
        if kind == "crash-out":
            a = _zoomed(vtail, f"1-0.55*{p}")
            b = _zoomed(vhead, f"2-{p}")
            return _dissolve(a, b)
        if kind == "infinite-out":
            a = _zoomed(vtail, f"1-0.7*{p}")
            b = _zoomed(vhead, f"3.3-2.3*{p}")
            return _dissolve(a, b)
        if kind == "screen-in":
            a = _zoomed(vtail, f"1+1.5*{p}")
            b = _zoomed(vhead, f"0.45+0.55*{p}")
            return _dissolve(a, b)
        if kind == "screen-out":
            a = _zoomed(vtail, f"1-0.55*{p}")
            b = _zoomed(vhead, f"1.15-0.15*{p}")
            return _dissolve(a, b)
        if kind == "dip-black":
            half = trans_s / 2
            a = _apply(vtail, [
                f"trim=start=0:end={half:.3f}",
                "setpts=PTS-STARTPTS",
                f"fade=t=out:st=0:d={half:.3f}",
                "format=yuv420p"], "mdip")
            b = _apply(vhead, [
                f"trim=start={half:.3f}:end={trans_s:.3f}",
                "setpts=PTS-STARTPTS",
                f"fade=t=in:st=0:d={half:.3f}",
                "format=yuv420p"], "mdip")
            out = next_label("mdip")
            filter_parts.append(
                f"[{a}][{b}]concat=n=2:v=1:a=0[{out}]")
            return _finish(out, "mfin")
        if kind == "color-shift":
            # hue's h/s expressions ARE evaluated per frame
            # (verified: hue output diverges from the input
            # increasingly over time, unlike eq brightness).
            a = _apply(vtail, [
                f"hue=h='180*{p}':s='1+1.2*{p}'",
                "format=yuv420p"], "mhue")
            b = _apply(vhead, [
                f"hue=h='-180*(1-{p})':s='2.2-1.2*{p}'",
                "format=yuv420p"], "mhue")
            return _dissolve(a, b)
        if kind == "flicker":
            # The head is used twice (dissolve + strobe overlay),
            # so it is split first. The strobe overlays the
            # incoming picture at 10 Hz, phased so the transition
            # midpoint is a blend frame; it settles on the incoming
            # picture at the end (dissolve is ~100% incoming there).
            hs1, hs2 = next_label("msp"), next_label("msp")
            filter_parts.append(
                f"[{vhead}]split=2[{hs1}][{hs2}]")
            dis = _dissolve(vtail, hs1)
            out = next_label("mflk")
            filter_parts.append(
                f"[{dis}][{hs2}]overlay=0:0:"
                f"enable='lt(mod(t*10+0.5,1),0.5)',"
                f"format=yuv420p[{out}]")
            return _finish(out, "mfin")
        if kind == "kaleidoscope":
            a = _tiled_rotated(vtail, f"-6.283185*{p}")
            b = _tiled_rotated(vhead, f"6.283185*(1-{p})")
            return _dissolve(a, b)
        if kind == "halftone":
            # Round 4: animated halftone dot mask. A nullsrc stream
            # is turned into a binary mask by geq: within each 24px
            # cell a disc grows with frame progress (N+1)/total,
            # reaching the cell-corner distance (0.707 * 24 = 17px)
            # at the last frame, so the output ends fully on the
            # incoming picture. The incoming head gets the mask as
            # its alpha channel (alphamerge) and is composited over
            # the outgoing tail (overlay): a hard dot pick, not a
            # blend. Both real moving pictures are preserved
            # (unlike a still-frame Pillow segment, which would
            # freeze motion during the transition window). This is
            # not pixelize: pixelize averages blocks; halftone
            # resolves the picture out of dots.
            # maskedmerge was tried first and rejected: even in
            # RGB with a binary mask it produced blended magenta
            # frames on FFmpeg 8.1.2 instead of a hard pick
            # (verified with solid red/blue clips and solid
            # white/black masks).
            total = max(1, int(round(float(fps) * trans_s)))
            cell = 24
            mask_src = next_label("hmask")
            filter_parts.append(
                f"nullsrc=s={w}x{h}:r={fps_str}:d={trans_s:.3f}"
                f"[{mask_src}]")
            mask = next_label("hmask")
            filter_parts.append(
                f"[{mask_src}]geq=lum='if(lt(hypot(mod(X,{cell})-"
                f"{cell // 2},mod(Y,{cell})-{cell // 2}),"
                f"18*(N+1)/{total}),255,0)',format=gray[{mask}]")
            over_a = next_label("hov")
            filter_parts.append(f"[{vhead}][{mask}]alphamerge[{over_a}]")
            out = next_label("hov")
            filter_parts.append(
                f"[{vtail}][{over_a}]overlay=0:0:format=yuv420[{out}]")
            return _finish(out, "mfin")
        raise ValueError(
            f"Motion transition {kind!r} has no filter builder in "
            "render.py (registry/render mismatch)")

    def chain_motion_video(label: str, dur_s: float, trans: dict):
        """Chain a motion transition (Phase B6).

        The accumulated chain is split into its pre-transition part
        and its last ``trans_s`` (the outgoing tail); the incoming
        clip is split into its first ``trans_s`` (the incoming
        head) and the remainder. The motion segment replaces the
        overlap, then pre + segment + remainder are concatenated,
        so the output duration is vchain_dur + dur_s - trans_s,
        exactly as with xfade. Empty pre/post parts (transition as
        long as a clip) are skipped, never concatenated as empty
        segments. Audio still uses acrossfade (chain_audio).
        """
        nonlocal vchain, vchain_dur
        trans_s = frames_to_seconds(trans["duration"], fmt["fps"])
        if trans_s > vchain_dur + 1e-6:
            raise ValueError(
                "Transition duration exceeds the rendered output "
                "so far for motion transition "
                f"{trans['kind']!r}")
        pre_dur = vchain_dur - trans_s
        post_dur = dur_s - trans_s
        pieces: list[str] = []
        if pre_dur > 1e-6:
            vs_a, vs_b = next_label("msp"), next_label("msp")
            filter_parts.append(
                f"[{vchain}]split=2[{vs_a}][{vs_b}]")
            vpre = next_label("mpre")
            filter_parts.append(
                f"[{vs_a}]trim=start=0:end={pre_dur:.3f},"
                f"setpts=PTS-STARTPTS,format=yuv420p[{vpre}]")
            pieces.append(vpre)
            vtail = next_label("mtail")
            filter_parts.append(
                f"[{vs_b}]trim=start={pre_dur:.3f}:"
                f"end={vchain_dur:.3f},setpts=PTS-STARTPTS,"
                f"format=yuv420p[{vtail}]")
        else:
            vtail = vchain
        if post_dur > 1e-6:
            is_a, is_b = next_label("msp"), next_label("msp")
            filter_parts.append(
                f"[{label}]split=2[{is_a}][{is_b}]")
            vhead = next_label("mhead")
            filter_parts.append(
                f"[{is_a}]trim=start=0:end={trans_s:.3f},"
                f"setpts=PTS-STARTPTS,format=yuv420p[{vhead}]")
            vpost = next_label("mpost")
            filter_parts.append(
                f"[{is_b}]trim=start={trans_s:.3f}:end={dur_s:.3f},"
                f"setpts=PTS-STARTPTS,format=yuv420p[{vpost}]")
        else:
            vhead = label
            vpost = None
        vtrans = _motion_segment(vtail, vhead, trans["kind"], trans_s)
        pieces.append(vtrans)
        if vpost is not None:
            pieces.append(vpost)
        if len(pieces) == 1:
            out_label = pieces[0]
        else:
            out_label = next_label("mct")
            joined = "".join(f"[{p}]" for p in pieces)
            filter_parts.append(
                f"{joined}concat=n={len(pieces)}:v=1:a=0,"
                f"format=yuv420p[{out_label}]")
        vchain, vchain_dur = out_label, vchain_dur + dur_s - trans_s

    def _crop_offset_expr(transform: dict) -> str:
        """FFmpeg crop x/y expressions for a clip transform. The
        original's ReframePreset pan/tilt are canvas pixels from
        centre; the centred crop is the neutral position, so the
        expressions are centre plus pan/tilt, clamped to the scaled
        frame. Expressions (not static numbers) are used because the
        scaled frame's true size depends on the source aspect, which
        is only known at filter time. Empty when the transform
        carries no pan/tilt, so clips without a framing preset keep
        the exact centred crop they always had."""
        if not isinstance(transform, dict):
            return ""
        try:
            pan = float(transform.get("pan") or 0)
        except (TypeError, ValueError):
            pan = 0.0
        try:
            tilt = float(transform.get("tilt") or 0)
        except (TypeError, ValueError):
            tilt = 0.0
        if pan == 0 and tilt == 0:
            return ""
        return (f":x='min(max((iw-ow)/2+{pan:g},0),iw-ow)'"
                f":y='min(max((ih-oh)/2+{tilt:g},0),ih-oh)'")


    def _motion_filter(item: dict, frame_offset: float = 0.0) -> str | None:
        """zoompan filter for main-track x/y/scale keyframes.

        zoompan's ``on`` variable is the output frame count, so
        keyframe times (seconds, clip-local) are converted to frames.
        Position fractions 0..1 become crop-window offsets.
        ``frame_offset`` shifts the keyframe times for segments
        whose frame counter restarts (Phase 5: opacity sub-segments
        pass their start frame here, which is what makes motion +
        opacity on one main clip render together — the piecewise
        expression is time-shift invariant, so shifting every point
        by the segment start keeps the motion exact).
        Returns None when the item has no motion keyframes.
        """
        fps_f = fps_value(fmt["fps"])
        x_pts = [(t * fps_f - frame_offset, v) for t, v in
                 keyframe_points(item, "x", fmt["fps"])]
        y_pts = [(t * fps_f - frame_offset, v) for t, v in
                 keyframe_points(item, "y", fmt["fps"])]
        s_pts = [(t * fps_f - frame_offset, v) for t, v in
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
            # Phase 7: still-image clips now render their keyframes
            # too (previously stored, not rendered). The looped still
            # feeds zoompan exactly like a video clip: zoompan's
            # ``on`` counter advances once per looped frame, so
            # x/y/scale keyframes animate over the still, tilt
            # rotates it per frame, colour filters apply, and
            # opacity/fades are honoured via the alpha/format steps
            # below. Without motion keyframes the old static chain
            # (with its explicit fps filter) is kept.
            img_filters = [
                "loop=loop=-1:size=1:start=0",
            ]
            # Phase B6 reframe: crop the source window before the
            # fill scale (see reframe_crop_filter).
            _reframe = reframe_crop_filter(item)
            if _reframe is not None:
                img_filters.append(_reframe)
            img_filters.extend([
                f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase",
                f"crop={out_w}:{out_h}"
                f"{_crop_offset_expr(item.get('transform') or {})}",
                "setsar=1",
            ])
            motion = _motion_filter(item, local_start * fps_value(fmt["fps"]))
            if motion is not None:
                # zoompan carries its own fps= option; a trailing
                # fps filter would duplicate frames (Phase 3 lesson).
                img_filters.append(motion)
            else:
                img_filters.append(f"fps={fps_str}")
            tilt = _tilt_filter(item, local_start)
            if tilt is not None:
                img_filters.append(tilt)
            img_filters.extend(_color_filters(item, lut_dir))
            if alpha is not None:
                img_filters.append("format=yuva420p")
                img_filters.append(f"colorchannelmixer=aa={_num(alpha)}")
                img_filters.append("format=yuv420p")
            else:
                img_filters.append("format=yuv420p")
            if fade_in > 0:
                img_filters.append(
                    f"fade=t=in:st=0:d={min(fade_in, dur_s):.3f}")
            if fade_out > 0:
                img_filters.append(
                    f"fade=t=out:st={max(dur_s - fade_out, 0):.3f}:"
                    f"d={min(fade_out, dur_s):.3f}")
            img_filters.append(f"trim=end={dur_s:.3f}")
            img_filters.append("setpts=PTS-STARTPTS")
            filter_parts.append(
                f"[{idx}:v]{','.join(img_filters)}[{label}]")
            return label, dur_s
        if item.get("freeze"):
            # Code-gap batch 2: hold the clip's first source frame
            # (freeze_clip points ``in`` at the source clip's last
            # frame) for the whole segment. Motion/tilt are not
            # applied to a held frame; colour and fades still are.
            frame_dur = 1.0 / media_fps(medium)
            fscale = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                      f"crop={out_w}:{out_h}"
                      f"{_crop_offset_expr(item.get('transform') or {})}")
            ffilters = [f"trim=start={src_s:.3f}:end={src_s + frame_dur:.3f}",
                        "setpts=PTS-STARTPTS",
                        "loop=loop=-1:size=1:start=0",
                        f"trim=end={dur_s:.3f}",
                        "setpts=PTS-STARTPTS"]
            # Phase B6 reframe (see reframe_crop_filter).
            _reframe = reframe_crop_filter(item)
            if _reframe is not None:
                ffilters.append(_reframe)
            ffilters.append(fscale)
            ffilters.extend(_color_filters(item, lut_dir))
            ffilters.append(f"fps={fps_str}")
            ffilters.append("format=yuv420p")
            if fade_in > 0:
                ffilters.append(
                    f"fade=t=in:st=0:d={min(fade_in, dur_s):.3f}")
            if fade_out > 0:
                ffilters.append(
                    f"fade=t=out:st={max(dur_s - fade_out, 0):.3f}:d={min(fade_out, dur_s):.3f}")
            filter_parts.append(f"[{idx}:v]{','.join(ffilters)}[{label}]")
            return label, dur_s
        zoom = 1.0
        transform = item.get("transform") or {}
        if isinstance(transform, dict) and transform.get("zoom"):
            zoom = float(transform["zoom"])
        if zoom != 1.0:
            zw, zh = int(out_w * zoom), int(out_h * zoom)
            scale = (f"scale={zw}:{zh}:force_original_aspect_ratio=increase,"
                     f"crop={out_w}:{out_h}"
                     f"{_crop_offset_expr(transform)}")
        else:
            scale = (f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                     f"crop={out_w}:{out_h}"
                     f"{_crop_offset_expr(transform)}")
        vfilters = [f"trim=start={src_s:.3f}:end={src_s + src_dur_s:.3f}",
                    "setpts=PTS-STARTPTS"]
        if speed != 1.0:
            vfilters.append(f"setpts=PTS/{speed:.4f}")
        if item.get("reverse"):
            # Code-gap batch 2: play the trimmed range backwards.
            vfilters.append("reverse")
            vfilters.append("setpts=PTS-STARTPTS")
        # Phase B6 reframe: crop the source window before the fill
        # scale (see reframe_crop_filter).
        _reframe = reframe_crop_filter(item)
        if _reframe is not None:
            vfilters.append(_reframe)
        vfilters.append(scale)
        vfilters.extend(_color_filters(item, lut_dir))
        motion = _motion_filter(item, local_start * fps_value(fmt["fps"]))
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
        segment. Phase 5: motion keyframes are NOT dropped for
        opacity-segmented clips any more — each segment's zoompan
        expression is shifted by the segment start frame (see
        _motion_filter), so motion + opacity render together.
        """
        dur_s = frames_to_seconds(item["dur"], fmt["fps"])
        fade_in = 0.0 if skip_fade_in else float(item.get("fadeIn", 0) or 0)
        fade_out = 0.0 if skip_fade_out else float(item.get("fadeOut", 0) or 0)
        # Phase 7: main-track still-image keyframes now render in
        # _main_range_segment (zoompan/tilt/colour/opacity), so the
        # old "stored, not rendered" skipped entry is gone.
        op_pts = keyframe_points(item, "opacity", fmt["fps"])
        if len(op_pts) >= 2:
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
        if item.get("freeze"):
            # A held frame has no source audio; silence for the segment.
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
        if item.get("reverse"):
            afilters.append("areverse")
            afilters.append("asetpts=PTS-STARTPTS")
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
            if medium is None:
                skipped.append(f"overlay {item['id']} (no media)")
                continue
            if medium.get("kind") == "image":
                # Phase 8: overlay still images now render (previously
                # skipped entirely). The single frame is looped for
                # the item duration, scaled to the project frame,
                # with scale keyframes via zoompan, tilt, colour and
                # stepwise opacity exactly like the main-track still
                # path; position keyframes drive the overlay x/y.
                # Images carry no audio, so no audio branch follows.
                start_s = frames_to_seconds(item["at"], fmt["fps"])
                dur_s = frames_to_seconds(item["dur"], fmt["fps"])
                src = media_path(item["media"])
                idx = add_input(src)
                x_pts = [(t, v) for t, v in
                         keyframe_points(item, "x", fmt["fps"])]
                y_pts = [(t, v) for t, v in
                         keyframe_points(item, "y", fmt["fps"])]
                scale_pts = keyframe_points(item, "scale", fmt["fps"])
                op_pts = keyframe_points(item, "opacity", fmt["fps"])
                start_adj = adjust(start_s)

                def _pos(points):
                    if not points:
                        return None
                    return _piecewise_expr(
                        [(t + start_adj, v) for t, v in points], "t")

                x_expr = _pos(x_pts)
                y_expr = _pos(y_pts)
                if len(op_pts) >= 2:
                    bounds = [0.0] + [t for t, _ in op_pts
                                      if 0.0 < t < dur_s] + [dur_s]
                    bounds = sorted(set(bounds))
                else:
                    bounds = [0.0, dur_s]
                for b0, b1 in zip(bounds, bounds[1:]):
                    if b1 - b0 < 1e-6:
                        continue
                    held = None
                    for t_kf, v_kf in op_pts:
                        if t_kf <= b0 + 1e-9:
                            held = v_kf
                    if held is None:
                        held = op_pts[0][1] if op_pts else 1.0
                    ofilters = [
                        "loop=loop=-1:size=1:start=0",
                        f"scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
                        f"crop={out_w}:{out_h}",
                        "setsar=1",
                    ]
                    if scale_pts:
                        fps_f = fps_value(fmt["fps"])
                        s_pts = [(t * fps_f - b0 * fps_f, v)
                                 for t, v in scale_pts]
                        ofilters.append(
                            f"zoompan=z='{_piecewise_expr(s_pts, 'on')}':"
                            f"x='(iw-ow)/2':y='(ih-oh)/2':d=1:"
                            f"s={out_w}x{out_h}:fps={fps_str}")
                    else:
                        ofilters.append(f"fps={fps_str}")
                    _tilt = _tilt_filter(item, b0)
                    if _tilt is not None:
                        ofilters.append(_tilt)
                    ofilters.extend(_color_filters(item, lut_dir))
                    ofilters.append("format=yuva420p")
                    ofilters.append(f"colorchannelmixer=aa={_num(held)}")
                    ofilters.append(f"trim=end={b1 - b0:.3f}")
                    ofilters.append("setpts=PTS-STARTPTS")
                    olabel = next_label("ovimg")
                    filter_parts.append(
                        f"[{idx}:v]{','.join(ofilters)}[{olabel}]")
                    out_label = next_label("vov")
                    x_arg = (f"(main_w-overlay_w)*({x_expr})"
                             if x_expr else "0")
                    y_arg = (f"(main_h-overlay_h)*({y_expr})"
                             if y_expr else "0")
                    filter_parts.append(
                        f"[{current}][{olabel}]overlay={x_arg}:{y_arg}:"
                        f"enable='between(t,{adjust(start_s + b0):.3f},"
                        f"{adjust(start_s + b1):.3f})'[{out_label}]")
                    current = out_label
                    overlay_count += 1
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
                    if item.get("reverse"):
                        ofilters.append("reverse")
                        ofilters.append("setpts=PTS-STARTPTS")
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
                if item.get("reverse"):
                    ofilters.append("reverse")
                    ofilters.append("setpts=PTS-STARTPTS")
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
    # A missing font used to leave text overlays silently skipped
    # (or, worse, a broken drawtext filter). Fail loudly instead,
    # naming the fix, but only when the project actually has text
    # to draw — a text-free project renders fine without any font.
    _has_text = any(
        (item.get("text") and "karaoke" not in item)
        for track in project["tracks"] if track["kind"] == "text"
        for item in track["items"])
    if _has_text and font is None:
        raise RuntimeError(
            "No font found for text overlays. Install a font (on "
            "Windows: any .ttf in the system Fonts folder) or set "
            "the VIBEEDIT_FONT environment variable to a .ttf file, "
            "then export again.")
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
                # Unreachable after the upfront check above; kept as
                # a defensive guard so a missing font can never
                # silently produce a broken drawtext filter.
                raise RuntimeError(
                    "No font found for text overlays. Install a font "
                    "or set VIBEEDIT_FONT to a .ttf file.")
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
            parts = (f"[{current}]drawtext=fontfile='{_filter_path(font)}':"
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
            f"[{current}]subtitles=filename='{_filter_path(ass_path)}'"
            f"[{out_label}]")
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
    cmd = [find_tool("ffmpeg"), "-y"]
    for path in inputs:
        cmd += ["-i", path]
    cmd += ["-filter_complex", filter_complex,
            "-map", f"[{current}]", "-r", fps_str,
            "-c:v", video_codec]
    if video_codec == "prores_ks":
        cmd += ["-pix_fmt", "yuv422p10le"]
    else:
        if ff_preset is not None:
            cmd += ["-preset", ff_preset]
        if video_bitrate is not None:
            cmd += ["-b:v", str(video_bitrate)]
        else:
            cmd += ["-crf", crf]
        cmd += ["-pix_fmt", "yuv420p"]
    if audio_map:
        cmd += ["-map", audio_map, "-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += [output]
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    # Phase 7: explicit UTF-8 decoding (see probe_media above) — the
    # Windows locale codepage would otherwise mojibake any
    # non-ASCII text (e.g. Vietnamese) in FFmpeg's error output.
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed ({proc.returncode}): {proc.stderr[-2000:]}")
    return {
        "output": output, "preset": preset,
        "export_preset": export_preset,
        "video_codec": video_codec, "video_bitrate": video_bitrate,
        "width": out_w, "height": out_h,
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
