"""Real media thumbnails for the Media Library grid.

Video: first frame extracted with FFmpeg, cached as a PNG under
<project>/render/thumbs/<safe-media-id>.png (runtime cache only —
never a repo file). Still images: the original file is served as-is.
Audio: no thumbnail exists, so generate_thumbnail raises ValueError
and the UI shows a music-note card instead of a fake frame.
"""

from __future__ import annotations

import os
import subprocess

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def thumbnail_path(project_dir: str, media_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in media_id)
    return os.path.join(project_dir, "render", "thumbs", safe + ".png")


def generate_thumbnail(src_path: str, dest_path: str, kind: str) -> str:
    """Return the path of a thumbnail image for src_path.

    For still images the source file itself is returned (no copy, no
    re-encode). For video an FFmpeg first-frame PNG is written to
    dest_path (reused if it already exists). Audio raises ValueError.
    """
    ext = os.path.splitext(src_path)[1].lower()
    if kind == "image" or ext in IMAGE_EXTS:
        return src_path
    if kind == "audio" or ext in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
        raise ValueError("Audio không có thumbnail")
    if os.path.isfile(dest_path):
        return dest_path
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    from .render import find_tool

    ffmpeg = find_tool("ffmpeg")
    for seek in ("0.5", "0"):
        cmd = [ffmpeg, "-y", "-v", "error", "-ss", seek, "-i", src_path,
               "-frames:v", "1", "-vf", "scale=320:-1", dest_path]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
        if proc.returncode == 0 and os.path.isfile(dest_path):
            return dest_path
    raise RuntimeError("FFmpeg không trích được khung hình thumbnail")
