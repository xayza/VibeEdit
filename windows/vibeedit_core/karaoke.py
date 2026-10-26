"""Karaoke .ass generation for the VibeEdit Windows port (Phase 4).

A karaoke item is a text item with ``karaoke: {words: [{text, start,
end}]}`` where word times are seconds relative to the cue start.
This module turns a project's karaoke items into one .ass file whose
Dialogue lines use libass ``\\k`` tags: the sung part renders in the
primary colour (yellow) and the not-yet-sung part in the secondary
colour (white). Burned with FFmpeg's subtitles filter (libass).
"""

from __future__ import annotations


def ass_timestamp(seconds: float) -> str:
    total_cs = int(round(seconds * 100))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def build_ass(karaoke_items: list[dict], width: int, height: int) -> str:
    """Build .ass text.

    Each item: {start_s, end_s, text, words: [{text, start, end}],
    size_frac, position_y}. Word times are relative to the cue start;
    the Dialogue line spans the cue, and \\k durations step through
    the words in order.
    """
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {int(width)}",
        f"PlayResY: {int(height)}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        # Primary = sung (yellow), Secondary = unsung (white).
        "Style: Default,Arial,48,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,"
        "0,0,0,0,100,100,0,0,1,2,0,2,10,10,20,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]
    for item in karaoke_items:
        fontsize = max(int(float(item.get("size_frac", 0.062)) * height), 12)
        margin_v = int((1.0 - float(item.get("position_y", 0.8))) * height)
        parts = []
        for word in item["words"]:
            cs = max(int(round((word["end"] - word["start"]) * 100)), 1)
            parts.append(f"{{\\k{cs}}}{_escape_ass(word['text'])} ")
        text = "".join(parts).rstrip()
        lines.append(
            f"Dialogue: 0,{ass_timestamp(item['start_s'])},"
            f"{ass_timestamp(item['end_s'])},Default,,0,0,{margin_v},,"
            f"{{\\fs{fontsize}}}{text}")
    return "\n".join(lines) + "\n"
