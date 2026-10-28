"""Round 7: the media.analyze pipeline for real.

Original semantics (read-only, from the Swift tree):
- ``media.analyze`` (CommandCatalog+Media.swift): "Measure source
  media once and keep the record (by file content): file facts
  (codec, size, rotation, frame timing for variable frame rate,
  colour transfer/primaries/bit depth, track lengths), picture
  samples (luma, spread, change, peak as in review.picture, plus
  sharpness and colourfulness) with every jump searched to its
  exact frame as a cut candidate, and sound levels (RMS per 0.1 s,
  peak, stereo correlation). Read it with media.analysis. A record
  that exists is reused unless force."
- ``media.analysis`` (MediaAnalysis+Reading.swift): derives cuts
  (candidates at/over minScore, minus removals matched within one
  sample interval, plus added cuts), shots with review.shots
  fields, shot-length histogram and cuts per 10 s, and sound
  summary (floor/median/loud percentiles, active spans over
  floor + activityDb, stereo correlation).
- ``media.speech-map`` / SpeechMap.swift: level windows split
  into quiet/loud by Otsu unless a threshold is given; when the
  classes are closer than minSeparationDb, separation is none
  and spans/gaps are null with a reason, never made-up silences.
- ``media.strip`` / MediaStills.swift: count frames (default 8)
  along the top with their time, a time ruler, the sound level
  (-60..0 dBFS per 0.1 s, from the record or measured now), the
  speech-map gaps shaded (left out when the classes do not
  separate), and the stored transcript's words at their times,
  as one PNG.
- ``media.sync`` / Plugins/audio-analysis Sync.swift: both
  loudness envelopes (100 per second, log RMS) cross-correlated
  -- a coarse search at 10 per second over every overlap of at
  least half the shorter file, then a fine one at 100 per second
  around the best lag; each half of the overlap matched again,
  two agreeing offsets mean a constant offset (no clock drift).
  Time in ``to`` = time in ``media`` + offsetSeconds; below 0.4
  correlation means no shared sound.

Windows implementation notes (honest deviations, all documented
here and in PARITY.md):
- Decoding is FFmpeg (subprocess) + pure Python stdlib; no numpy,
  no AVFoundation. Picture samples are 24x24 grey thumbnails
  (luma/spread/change/peak exactly as review.picture defines
  them on a 24x24 grid), sharpness is the mean absolute
  4-neighbour Laplacian of a 256-pixel grey frame, colourfulness
  is Hasler-Susstrunk on a 24x24 RGB thumbnail.
- Exact-frame narrowing of cut candidates assumes constant frame
  rate (the interval decode maps output frames to source frames
  by count); for variable frame rate the candidate falls back to
  the second sample's frame and the record says so.
- The record lives on the media entry as ``analysis_record`` so
  it rides save/backup/undo with the project. It is separate
  from the media_cuts record (``analysis`` key, FFmpeg scene
  filter detection from round 6); the two cut lists are different
  measurements and are never merged silently.
- The transcript slot is filled only when faster-whisper is
  installed; otherwise words are empty with a reason naming the
  install. Transcription never invents words.
- Sync envelopes are decoded to mono 8 kHz and correlated in
  pure Python with prefix sums (means/variances O(1) per lag);
  long files are therefore slower than the original's Accelerate
  path -- that is a performance note, not a correctness gap.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import struct
import subprocess
import sys
from datetime import datetime, timezone

SILENCE_DB = -120.0
CANDIDATE_FLOOR = 0.04
WINDOW = 0.1
LEVEL_RATE = 48000.0
ANALYSIS_VERSION = 1
MEASURED_BY = "vibeedit media.analyze v1"
GRID = 24
SAMPLES_DEFAULT_RATE = 4.0


def _round3(value: float) -> float:
    return round(float(value), 3)


def _round5(value: float) -> float:
    return round(float(value), 5)


def _median(values: list) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _percentile(ordered: list, share: float) -> float:
    if not ordered:
        return float("nan")
    return float(ordered[min(len(ordered) - 1, int(len(ordered) * share))])


def _dbfs(mean_square: float) -> float:
    if mean_square <= 0:
        return SILENCE_DB
    return max(SILENCE_DB, 10.0 * math.log10(mean_square))


def content_key(path: str) -> str:
    """Content key in the original's shape: SHA-256 of the size
    and the first and last mebibyte, namespaced with the
    measurement version. A moved or renamed file keeps its key;
    an edited one gets a new key. (The original hashes the same
    three parts; the exact byte layout is this build's own.)"""
    size = os.path.getsize(path)
    hasher = hashlib.sha256()
    hasher.update(f"media-analysis-v{ANALYSIS_VERSION}:{size}:".encode())
    with open(path, "rb") as handle:
        head = handle.read(1024 * 1024)
        hasher.update(head)
        if size > 1024 * 1024:
            handle.seek(max(0, size - 1024 * 1024))
            hasher.update(handle.read(1024 * 1024))
    return hasher.hexdigest()


def _ffprobe_json(path: str, extra_args: list) -> dict:
    from .render import find_tool

    cmd = [find_tool("ffprobe"), "-v", "quiet", "-print_format",
           "json"] + extra_args + [path]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe không đọc được {path}: "
                           f"{proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout or "{}")


def probe_tech(path: str) -> dict:
    """File facts in the original's Tech shape, from ffprobe."""
    data = _ffprobe_json(path, ["-show_streams", "-show_format"])
    fmt = data.get("format", {}) or {}
    try:
        seconds = float(fmt.get("duration", 0) or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    tech: dict = {"seconds": _round3(seconds),
                  "bytes": os.path.getsize(path) if os.path.isfile(path)
                  else None, "video": None, "audio": None}
    for stream in data.get("streams", []):
        ctype = stream.get("codec_type")
        if ctype == "video" and tech["video"] is None:
            rate = stream.get("avg_frame_rate") or \
                stream.get("r_frame_rate") or "0/0"
            try:
                num, den = str(rate).split("/")
                fps = float(num) / float(den) if int(den) else 0.0
            except (ValueError, ZeroDivisionError):
                fps = 0.0
            rotation = 0
            tags = stream.get("tags") or {}
            try:
                rotation = int(float(tags.get("rotate", 0)))
            except (TypeError, ValueError):
                rotation = 0
            for side in stream.get("side_data_list", []) or []:
                if side.get("side_data_type") == "Display Matrix" \
                        and side.get("rotation") is not None:
                    try:
                        rotation = int(side["rotation"])
                    except (TypeError, ValueError):
                        pass
            try:
                track_seconds = float(stream.get("duration", 0) or 0)
            except (TypeError, ValueError):
                track_seconds = 0.0
            video = {"codec": stream.get("codec_name"),
                     "width": int(stream.get("width", 0) or 0),
                     "height": int(stream.get("height", 0) or 0),
                     "rotation": rotation,
                     "nominalFPS": _round3(fps),
                     "seconds": _round3(track_seconds or seconds),
                     "frames": None, "minFrameSeconds": None,
                     "maxFrameSeconds": None, "meanFrameSeconds": None,
                     "transfer": stream.get("color_transfer"),
                     "primaries": stream.get("color_primaries"),
                     "matrix": stream.get("color_space"),
                     "bitDepth": stream.get("bits_per_raw_sample")
                     or stream.get("bits_per_sample")}
            nb = stream.get("nb_frames")
            if nb:
                try:
                    video["frames"] = int(nb)
                except (TypeError, ValueError):
                    pass
            tech["video"] = video
        elif ctype == "audio" and tech["audio"] is None:
            try:
                track_seconds = float(stream.get("duration", 0) or 0)
            except (TypeError, ValueError):
                track_seconds = 0.0
            try:
                rate = float(stream.get("sample_rate", 0) or 0)
            except (TypeError, ValueError):
                rate = 0.0
            tech["audio"] = {"codec": stream.get("codec_name"),
                             "channels": int(stream.get("channels", 0)
                                             or 0),
                             "sampleRate": rate,
                             "seconds": _round3(track_seconds or seconds)}
    return tech


def frame_timing(path: str, total_frames: int | None) -> dict | None:
    """Presentation-time steps of the video samples (min/max/
    mean, plus count). Skipped (None) when the frame count is
    unknown or above 30000, so a long file is not read twice
    just for timing statistics."""
    if not total_frames or total_frames > 30000:
        return None
    try:
        from .render import find_tool
        cmd = [find_tool("ffprobe"), "-v", "quiet",
               "-select_streams", "v:0", "-show_entries",
               "frame=best_effort_timestamp_time",
               "-of", "csv=p=0", path]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=300)
        if proc.returncode != 0:
            return None
        times = []
        for line in proc.stdout.splitlines():
            try:
                value = float(line.strip())
            except ValueError:
                continue
            if math.isfinite(value):
                times.append(value)
    except Exception:
        return None
    times.sort()
    steps = [b - a for a, b in zip(times, times[1:]) if b - a > 1e-6]
    if not steps:
        return None
    return {"frames": len(times), "min": min(steps),
            "max": max(steps), "mean": sum(steps) / len(steps)}

# ------------------------------------------------------------------
# Sound: RMS per 0.1 s window over all channels, peak, stereo
# correlation -- a faithful port of MediaAnalyzer+Sound's
# LevelMeter, with FFmpeg decoding to float PCM at 48 kHz.
# ------------------------------------------------------------------

class _LevelMeter:
    def __init__(self, channels: int):
        self.channels = max(1, channels)
        self.window_frames = int(LEVEL_RATE * WINDOW)
        self.levels: list = []
        self.power = 0.0
        self.count = 0
        self.peak = 0.0
        self.left_right = 0.0
        self.left_sq = 0.0
        self.right_sq = 0.0

    def add(self, samples):
        """Feed interleaved float samples (any chunk size)."""
        channels = self.channels
        i = 0
        total = len(samples)
        while i + channels <= total:
            frame_power = 0.0
            for channel in range(channels):
                value = samples[i + channel]
                if math.isfinite(value):
                    frame_power += value * value
                    if abs(value) > self.peak:
                        self.peak = abs(value)
            if channels > 1:
                left = samples[i]
                right = samples[i + 1]
                if math.isfinite(left) and math.isfinite(right):
                    self.left_right += left * right
                    self.left_sq += left * left
                    self.right_sq += right * right
            self.power += frame_power
            self.count += 1
            i += channels
            if self.count == self.window_frames:
                self._close()
        return i

    def _close(self):
        mean = self.power / (self.count * self.channels) \
            if self.count else 0.0
        self.levels.append(_dbfs(mean))
        self.power = 0.0
        self.count = 0

    def result(self) -> dict:
        if self.count > 0:
            self._close()
        correlation = None
        if self.channels > 1 and self.left_sq > 0 and self.right_sq > 0:
            correlation = self.left_right / math.sqrt(
                self.left_sq * self.right_sq)
        peak_db = max(SILENCE_DB, 20.0 * math.log10(self.peak)) \
            if self.peak > 0 else SILENCE_DB
        return {"window": WINDOW, "levels": [_round3(v) for v in self.levels],
                "peakDb": _round3(peak_db),
                "stereoCorrelation": (round(correlation, 5)
                                      if correlation is not None
                                      else None)}


def decode_sound_levels(path: str) -> dict | None:
    """Decode the audio track (at most 2 channels, 48 kHz float)
    and return the Sound record, or None when there is no audio
    track or the decode fails for lack of one."""
    tech = probe_tech(path)
    audio = tech.get("audio")
    if not audio or not audio.get("channels"):
        return None
    channels = max(1, min(2, int(audio["channels"])))
    from .render import find_tool
    cmd = [find_tool("ffmpeg"), "-v", "error", "-i", path, "-vn",
           "-ac", str(channels), "-ar", str(int(LEVEL_RATE)),
           "-f", "f32le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    meter = _LevelMeter(channels)
    fmt_size = 4
    try:
        leftover = b""
        while True:
            chunk = proc.stdout.read(1024 * 1024) if proc.stdout else b""
            if not chunk:
                break
            data = leftover + chunk
            usable = len(data) - (len(data) % (fmt_size * channels))
            if usable <= 0:
                leftover = data
                continue
            samples = struct.unpack(
                "<%df" % (usable // fmt_size),
                data[:usable])
            meter.add(samples)
            leftover = data[usable:]
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait(timeout=60)
    try:
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", "replace") \
                if proc.stderr else ""
            raise RuntimeError(f"FFmpeg không giải mã được âm thanh của "
                               f"{path}: {err.strip()[:300]}")
    finally:
        if proc.stderr:
            proc.stderr.close()
    return meter.result()


# ------------------------------------------------------------------
# Picture: 24x24 grey thumbnails (luma/spread/change/peak),
# sharpness (Laplacian on a 256-pixel grey frame) and
# colourfulness (Hasler-Susstrunk on a 24x24 RGB thumbnail).
# ------------------------------------------------------------------

def _grey_stats(pixels: bytes) -> tuple:
    n = len(pixels)
    if n == 0:
        return 0.0, 0.0
    mean = sum(pixels) / n / 255.0
    var = sum((p / 255.0 - mean) ** 2 for p in pixels) / n
    return round(mean, 5), round(math.sqrt(var), 5)


def _grey_difference(left: bytes, right: bytes) -> tuple:
    n = min(len(left), len(right))
    if n == 0:
        return 0.0, 0.0
    diffs = [abs(left[i] - right[i]) / 255.0 for i in range(n)]
    return round(sum(diffs) / n, 5), round(max(diffs), 5)


def _sharpness(grey: bytes, width: int, height: int) -> float:
    if width <= 2 or height <= 2 or len(grey) < width * height:
        return 0.0
    total = 0
    for row in range(1, height - 1):
        base = row * width
        for col in range(1, width - 1):
            index = base + col
            around = (grey[index - 1] + grey[index + 1]
                      + grey[index - width] + grey[index + width])
            total += abs(4 * grey[index] - around)
    return round(total / ((width - 2) * (height - 2)) / 255.0, 5)


def _colourfulness(rgb: bytes) -> float:
    n = len(rgb) // 3
    if n == 0:
        return 0.0
    rg = []
    yb = []
    for i in range(n):
        red = rgb[i * 3] / 255.0
        green = rgb[i * 3 + 1] / 255.0
        blue = rgb[i * 3 + 2] / 255.0
        rg.append(red - green)
        yb.append((red + green) / 2.0 - blue)
    def mean_dev(values):
        mean = sum(values) / len(values)
        dev = math.sqrt(sum((v - mean) ** 2 for v in values)
                        / len(values))
        return mean, dev
    mean_rg, dev_rg = mean_dev(rg)
    mean_yb, dev_yb = mean_dev(yb)
    return round(math.sqrt(dev_rg ** 2 + dev_yb ** 2)
                 + 0.3 * math.sqrt(mean_rg ** 2 + mean_yb ** 2), 5)


def _extract_frames(path: str, select: str, scale: str, fmt: str,
                    frame_bytes: int, max_frames: int | None = None):
    """Yield raw frames from one FFmpeg pass. ``select`` is an
    FFmpeg select expression; frames arrive in decode order."""
    from .render import find_tool
    cmd = [find_tool("ffmpeg"), "-v", "error", "-i", path, "-vf",
           f"select='{select}',{scale},format={fmt}",
           "-vsync", "0", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    buf = b""
    count = 0
    try:
        while True:
            if max_frames is not None and count >= max_frames:
                break
            chunk = proc.stdout.read(1024 * 1024) if proc.stdout else b""
            if not chunk:
                break
            buf += chunk
            while len(buf) >= frame_bytes:
                yield buf[:frame_bytes]
                buf = buf[frame_bytes:]
                count += 1
                if max_frames is not None and count >= max_frames:
                    break
    finally:
        if proc.stdout:
            proc.stdout.close()
        try:
            proc.wait(timeout=60)
        except Exception:
            proc.kill()
    if proc.returncode not in (0, None):
        err = proc.stderr.read().decode("utf-8", "replace") \
            if proc.stderr else ""
        if "No such file" in err or not err:
            pass
        elif count == 0:
            raise RuntimeError(f"FFmpeg không trích được khung hình từ {path}: {err.strip()[:300]}")


def measure_picture(path: str, fps: float, total_frames: int,
                    rate: float, width: int, height: int) -> dict | None:
    """Picture record at ``rate`` samples per second. Returns None
    when the file has no decodable video track."""
    if fps <= 0 or total_frames <= 0:
        return None
    interval = max(1, int(round(fps / rate)))
    sample_frames = list(range(0, total_frames, interval))
    if not sample_frames:
        return None
    # The -vf value is passed as one argv element (no shell), so
    # the select argument is single-quoted for the filtergraph
    # parser itself; the comma inside the quotes is not a filter
    # separator.
    select = f"not(mod(n,{interval}))"
    grey_frames = list(_extract_frames(
        path, select, "scale=24:24", "gray", GRID * GRID,
        max_frames=len(sample_frames)))
    if not grey_frames:
        return None
    rgb_frames = list(_extract_frames(
        path, select, "scale=24:24", "rgb24", GRID * GRID * 3,
        max_frames=len(sample_frames)))
    if width >= height:
        sharp_scale = "scale=256:-2"
        sharp_w = 256
        sharp_h = max(2, int(round(height * 256.0 / max(1, width))))
        if sharp_h % 2:
            sharp_h += 1
    else:
        sharp_scale = "scale=-2:256"
        sharp_h = 256
        sharp_w = max(2, int(round(width * 256.0 / max(1, height))))
        if sharp_w % 2:
            sharp_w += 1
    sharp_frames = list(_extract_frames(
        path, select, sharp_scale, "gray", sharp_w * sharp_h,
        max_frames=len(sample_frames)))
    samples = []
    previous = None
    for index, frame_no in enumerate(sample_frames):
        if index >= len(grey_frames):
            break
        grey = grey_frames[index]
        luma, spread = _grey_stats(grey)
        if previous is None:
            change, peak = 1.0, 1.0
        else:
            change, peak = _grey_difference(previous, grey)
        rgb = rgb_frames[index] if index < len(rgb_frames) else b""
        sharp = _sharpness(
            sharp_frames[index], sharp_w, sharp_h) \
            if index < len(sharp_frames) else 0.0
        samples.append({"frame": frame_no, "luma": luma,
                        "spread": spread, "change": change,
                        "peak": peak, "sharpness": sharp,
                        "colourfulness": _colourfulness(rgb)})
        previous = grey
    if not samples:
        return None
    # Narrow every sample-to-sample jump at/over the floor to its
    # exact frame pair by decoding the interval at full rate.
    candidates = []
    vfr_fallback = False
    for first, second in zip(samples, samples[1:]):
        if second["change"] < CANDIDATE_FLOOR:
            continue
        start_frame, end_frame = first["frame"], second["frame"]
        t0 = start_frame / fps
        t1 = end_frame / fps
        interval_frames = list(_extract_frames_range(
            path, t0, t1, GRID * GRID))
        best = None
        for offset in range(len(interval_frames) - 1):
            change, _peak = _grey_difference(
                interval_frames[offset], interval_frames[offset + 1])
            if best is None or change > best[1]:
                best = (offset, change)
        if best is not None and best[1] >= CANDIDATE_FLOOR \
                and len(interval_frames) >= 2:
            # CFR mapping: the k-th decoded frame of the interval
            # is source frame start_frame + k.
            candidates.append({"frame": start_frame + best[0] + 1,
                               "score": best[1]})
        else:
            candidates.append({"frame": end_frame,
                               "score": second["change"]})
            vfr_fallback = True
    return {"fps": _round3(fps), "interval": interval,
            "frames": total_frames, "source": "original",
            "samples": samples, "candidates": candidates,
            "candidateFloor": CANDIDATE_FLOOR,
            "narrowingNote": ("giải mã theo khoảng không cho cặp khung hình nào; "
                              "giữ candidate tại khung hình mẫu"
                              if vfr_fallback else None)}


def _extract_frames_range(path: str, t0: float, t1: float,
                          frame_bytes: int) -> list:
    """All 24x24 grey frames with presentation time in [t0, t1).
    Seek after -i for accuracy (intervals are short)."""
    from .render import find_tool
    cmd = [find_tool("ffmpeg"), "-v", "error", "-i", path,
           "-ss", f"{t0:.6f}", "-to", f"{t1:.6f}",
           "-vf", "scale=24:24,format=gray",
           "-vsync", "0", "-f", "rawvideo", "-"]
    proc = subprocess.run(cmd, capture_output=True, timeout=120)
    if proc.returncode != 0:
        return []
    raw = proc.stdout
    count = len(raw) // frame_bytes
    return [raw[i * frame_bytes:(i + 1) * frame_bytes]
            for i in range(count)]


def transcribe_words(path: str) -> tuple:
    """Timed words from faster-whisper when it is installed, else
    ([], reason). Word timestamps when the model provides them,
    otherwise one entry per segment (documented in the record)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return [], ("Chưa cài faster-whisper trên máy này nên không đo "
                    "transcript; hãy cài bằng 'pip install faster-whisper' "
                    "rồi đo lại. Các phép đo hình ảnh và âm thanh "
                    "không bị ảnh hưởng.")
    try:
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(
            path, word_timestamps=True)
        words = []
        for segment in segments:
            seg_words = getattr(segment, "words", None) or []
            if seg_words:
                for word in seg_words:
                    words.append({"text": word.word.strip(),
                                  "start": _round3(word.start),
                                  "end": _round3(word.end)})
            else:
                words.append({"text": segment.text.strip(),
                              "start": _round3(segment.start),
                              "end": _round3(segment.end)})
        return [w for w in words if w["text"]], None
    except Exception as exc:
        return [], f"Phiên âm thất bại nên để trống: {exc}"

# ------------------------------------------------------------------
# Whole-media measurement.
# ------------------------------------------------------------------

def measure_media(path: str, fps: float | None = None,
                  total_frames: int | None = None,
                  rate: float = SAMPLES_DEFAULT_RATE) -> dict:
    """Measure one file into the record shape. ``fps`` /
    ``total_frames`` come from the media entry when known, else
    from ffprobe. Raises FileNotFoundError / RuntimeError with a
    clear message instead of returning a partial record."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Không tìm thấy file media: {path}")
    if not (0.5 <= rate <= 30):
        raise ValueError("rate phải từ 0,5 đến 30 mẫu/giây")
    tech = probe_tech(path)
    video = tech.get("video") or {}
    audio = tech.get("audio")
    use_fps = fps or video.get("nominalFPS") or 0.0
    frames = total_frames or video.get("frames")
    if frames is None and use_fps and tech.get("seconds"):
        frames = int(round(use_fps * tech["seconds"]))
    if video and use_fps and frames:
        timing = frame_timing(path, frames)
        if timing and total_frames is None:
            video["frames"] = timing["frames"]
            video["minFrameSeconds"] = _round5(timing["min"])
            video["maxFrameSeconds"] = _round5(timing["max"])
            video["meanFrameSeconds"] = _round5(timing["mean"])
    tech["video"] = video if video else None
    tech["audio"] = audio
    picture = None
    if video and use_fps and frames:
        picture = measure_picture(path, use_fps, frames, rate,
                                  int(video.get("width", 0) or 0),
                                  int(video.get("height", 0) or 0))
    sound = None
    if audio:
        try:
            sound = decode_sound_levels(path)
        except Exception:
            sound = None
    words, reason = ([], "không có track audio nên không có gì để "
                     "phiên âm") if not audio else transcribe_words(path)
    record = {
        "version": ANALYSIS_VERSION,
        "key": content_key(path),
        "measuredBy": MEASURED_BY,
        "measuredAt": datetime.now(timezone.utc).isoformat(),
        "tech": tech,
        "picture": picture,
        "sound": sound,
        "corrections": {"add": [], "remove": []},
        "transcript": {"words": words,
                       "reason": reason} if reason is not None
        else {"words": words},
    }
    return record


# ------------------------------------------------------------------
# Reading a record: cuts, shots, sound (MediaAnalysis+Reading).
# ------------------------------------------------------------------

def listed_cuts(record: dict, min_score: float = 0.1) -> list:
    picture = record.get("picture") or {}
    interval = picture.get("interval", 1) or 1
    corrections = record.get("corrections") or {}
    removed = corrections.get("remove", []) or []
    kept = []
    for cand in picture.get("candidates", []) or []:
        if cand.get("score", 0) < min_score:
            continue
        if any(abs(frame - cand["frame"]) <= interval
               for frame in removed):
            continue
        kept.append({"frame": int(cand["frame"]),
                     "score": _round5(cand["score"])})
    frames = picture.get("frames", 0) or 0
    added_frames = corrections.get("add", []) or []
    for frame in added_frames:
        if 0 < frame < frames and not any(
                c["frame"] == frame for c in kept):
            kept.append({"frame": int(frame), "added": True})
    kept.sort(key=lambda c: c["frame"])
    return kept


def _shot_motion(samples: list, start: int, end: int) -> dict | None:
    inside = [s for s in samples if start < s["frame"] < end]
    if not inside:
        return None
    return {"mean": _round5(sum(s["change"] for s in inside)
                            / len(inside)),
            "peak": _round5(max(s["peak"] for s in inside)),
            "samples": len(inside)}


def derive_analysis(record: dict, min_score: float = 0.1,
                    activity_db: float = 10.0,
                    bridge_seconds: float = 0.3,
                    include_samples: bool = False,
                    include_curve: bool = False) -> dict:
    """The media.analysis reading of a record: tech, picture
    (cuts/shots/summary/histogram/cut curve), sound, corrections."""
    picture = record.get("picture")
    sound = record.get("sound")
    result: dict = {"key": record.get("key"),
                    "measuredBy": record.get("measuredBy"),
                    "measuredAt": record.get("measuredAt"),
                    "version": record.get("version"),
                    "tech": record.get("tech"),
                    "corrections": record.get("corrections")
                    or {"add": [], "remove": []}}
    transcript = record.get("transcript") or {}
    result["transcript"] = {
        "words": len(transcript.get("words", []) or []),
        "reason": transcript.get("reason")}
    if picture:
        fps = picture["fps"]
        cuts = listed_cuts(record, min_score)
        starts = [{"frame": 0}] + cuts
        ends = [c["frame"] for c in cuts] + [picture["frames"]]
        shots = []
        lengths = []
        for index, (start, end) in enumerate(zip(starts, ends)):
            if end <= start["frame"]:
                continue
            duration = end - start["frame"]
            lengths.append(duration / fps)
            row = {"index": index, "at": start["frame"],
                   "atSeconds": _round3(start["frame"] / fps),
                   "duration": duration,
                   "seconds": _round3(duration / fps),
                   "motion": _shot_motion(picture["samples"],
                                          start["frame"], end)}
            if index > 0:
                if start.get("added"):
                    row["cutAdded"] = True
                else:
                    row["cutDifference"] = start.get("score")
            inside = [s for s in picture["samples"]
                      if start["frame"] <= s["frame"] < end]
            if inside:
                mean = lambda key: _round5(sum(
                    s[key] for s in inside) / len(inside))
                row["picture"] = {"luma": mean("luma"),
                                  "spread": mean("spread"),
                                  "sharpness": mean("sharpness"),
                                  "colourfulness": mean(
                                      "colourfulness"),
                                  "samples": len(inside)}
            shots.append(row)
        edges = [0, 0.5, 1, 2, 4, 8, 16]
        histogram = []
        for i, low in enumerate(edges):
            high = edges[i + 1] if i + 1 < len(edges) else None
            count = sum(1 for length in lengths
                        if length >= low and (high is None
                                              or length < high))
            entry = {"from": low, "count": count}
            if high is not None:
                entry["to"] = high
            histogram.append(entry)
        seconds = record["tech"]["seconds"] if record.get("tech") \
            else 0
        windows = max(1, int(math.ceil(seconds / 10.0))) \
            if seconds else 1
        curve_counts = [0] * windows
        for cut in cuts:
            slot = min(windows - 1,
                       int(cut["frame"] / fps / 10.0)) if fps else 0
            curve_counts[slot] += 1
        cut_curve = [{"from": i * 10,
                      "to": min(int(math.ceil(seconds)),
                                (i + 1) * 10) if seconds else (i + 1) * 10,
                      "cuts": count}
                     for i, count in enumerate(curve_counts)]
        if lengths:
            ordered = sorted(lengths)
            summary = {"count": len(lengths),
                       "total": _round3(sum(lengths)),
                       "mean": _round3(sum(lengths) / len(lengths)),
                       "median": _round3(_median(lengths)),
                       "min": _round3(min(lengths)),
                       "max": _round3(max(lengths))}
        else:
            summary = {"count": 0}
        picture_out = {
            "units": "Khung hình nguồn tại fps. luma, spread, change, "
                     "peak theo review.picture (tỉ lệ trên thumbnail "
                     "xám 24x24); sharpness: Laplacian trị tuyệt đối "
                     "trung bình của khung hình xám 256 pixel; "
                     "colourfulness: Hasler-Susstrunk trên thumbnail "
                     "RGB nhỏ.",
            "fps": fps, "interval": picture["interval"],
            "frames": picture["frames"],
            "candidateFloor": picture["candidateFloor"],
            "minScore": min_score,
            "cuts": [{"frame": c["frame"],
                      "seconds": _round3(c["frame"] / fps),
                      **({"added": True} if c.get("added")
                         else {"score": c["score"]})}
                     for c in cuts],
            "candidatesBelow": sum(
                1 for c in picture["candidates"]
                if c.get("score", 0) < min_score),
            "shots": shots, "summary": summary,
            "histogram": histogram, "cutCurve": cut_curve,
            "narrowingNote": picture.get("narrowingNote")}
        if include_samples:
            picture_out["samples"] = [{
                "frame": s["frame"],
                "seconds": _round3(s["frame"] / fps),
                "luma": s["luma"], "spread": s["spread"],
                "change": s["change"], "peak": s["peak"],
                "sharpness": s["sharpness"],
                "colourfulness": s["colourfulness"]}
                for s in picture["samples"]]
        result["picture"] = picture_out
    else:
        result["picture"] = None
    if sound and sound.get("levels"):
        levels = sound["levels"]
        ordered = sorted(levels)
        floor = _percentile(ordered, 0.1)
        spans = active_spans(levels, sound["window"],
                             floor + activity_db, bridge_seconds)
        total = len(levels) * sound["window"]
        silent = sum(1 for v in levels if v <= SILENCE_DB)
        sound_out = {
            "units": "dBFS. Các mức là RMS trên cửa sổ 0,1 s của "
                     "mọi kênh (không phải LUFS). floorDb, medianDb "
                     "và loudDb là phân vị thứ 10, 50 và 95 của "
                     "mọi cửa sổ (lặng số đọc -120). Span đang hoạt "
                     "động là âm thanh trên floorDb + activityDb, "
                     "có phải lời nói hay không.",
            "window": sound["window"],
            "peakDb": _round3(sound["peakDb"]),
            "floorDb": _round3(floor),
            "medianDb": _round3(_percentile(ordered, 0.5)),
            "loudDb": _round3(_percentile(ordered, 0.95)),
            "silentShare": _round5(silent / len(levels)),
            "activityDb": activity_db,
            "bridgeSeconds": bridge_seconds,
            "active": [{"start": _round3(a), "end": _round3(b),
                        "seconds": _round3(b - a)}
                       for a, b in spans],
            "activeShare": _round5(
                sum(b - a for a, b in spans) / total) if total else 0,
            "stereoCorrelation": sound.get("stereoCorrelation")}
        if include_curve:
            per_second = max(1, int(round(1.0 / sound["window"])))
            curve = []
            for start in range(0, len(levels), per_second):
                chunk = levels[start:start + per_second]
                power = sum(0 if v <= SILENCE_DB else 10 ** (v / 10.0)
                            for v in chunk) / len(chunk)
                curve.append(_round3(
                    max(SILENCE_DB, 10.0 * math.log10(power))
                    if power > 0 else SILENCE_DB))
            sound_out["curve"] = curve
        result["sound"] = sound_out
    else:
        result["sound"] = None
    return result


# ------------------------------------------------------------------
# Spans + Otsu + speech map (SpeechMap.swift, faithful port).
# ------------------------------------------------------------------

def active_spans(levels: list, window: float, threshold: float,
                 bridge: float) -> list:
    """Windows at/over threshold, joined across quiet gaps up to
    ``bridge`` seconds, as (start, end) seconds."""
    raw = [(i * window, (i + 1) * window)
           for i, level in enumerate(levels) if level >= threshold]
    merged: list = []
    for start, end in sorted(raw):
        if merged and start - merged[-1][1] <= bridge + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _joined_spans(spans: list, bridge: float) -> list:
    merged: list = []
    for start, end in sorted(spans):
        if merged and start - merged[-1][1] <= bridge + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _gaps_between(spans: list, total: float) -> list:
    gaps = []
    reached = 0.0
    for start, end in spans:
        if start > reached:
            gaps.append((reached, start))
        reached = max(reached, end)
    if total > reached:
        gaps.append((reached, total))
    return gaps


def _overlap(first: list, second: list) -> float:
    return sum(max(0.0, min(a_end, b_end) - max(a_start, b_start))
               for a_start, a_end in first
               for b_start, b_end in second)


def _span_seconds(spans: list) -> float:
    return sum(end - start for start, end in spans)


def _spans_json(spans: list) -> list:
    return [{"start": _round3(a), "end": _round3(b),
             "seconds": _round3(b - a)} for a, b in spans]


def _gap_stats(gaps: list) -> dict:
    lengths = sorted(end - start for start, end in gaps)
    if not lengths:
        return {"count": 0}
    at = lambda share: lengths[min(
        len(lengths) - 1, int(len(lengths) * share))]
    return {"count": len(lengths),
            "medianSeconds": _round3(at(0.5)),
            "p90Seconds": _round3(at(0.9)),
            "maxSeconds": _round3(lengths[-1])}


def otsu_calibrate(levels: list) -> dict | None:
    """Otsu's split of dB levels in 0.5 dB bins. Digital silence
    is left out (it is always quiet). None with fewer than ten
    windows of sound or a level that hardly changes."""
    clamped = [v for v in levels if v > SILENCE_DB]
    if len(clamped) < 10:
        return None
    low, high = min(clamped), max(clamped)
    if high - low < 0.5:
        return None
    bin_width = 0.5
    count = int((high - low) / bin_width) + 1
    histogram = [0.0] * count
    for level in clamped:
        histogram[min(count - 1, int((level - low) / bin_width))] += 1
    total = float(len(clamped))
    centre = lambda index: low + (index + 0.5) * bin_width
    mean = sum(histogram[i] * centre(i) for i in range(count)) / total
    variance = sum((v - mean) ** 2 for v in clamped) / total
    best_score, best_split = -1.0, 0
    weight = 0.0
    partial = 0.0
    for index in range(count - 1):
        weight += histogram[index]
        partial += histogram[index] * centre(index)
        if weight <= 0 or weight >= total:
            continue
        low_mean = partial / weight
        high_mean = (mean * total - partial) / (total - weight)
        between = weight * (total - weight) * (low_mean - high_mean) ** 2 \
            / (total * total)
        if between > best_score:
            best_score, best_split = between, index
    if best_score < 0:
        return None
    threshold = low + (best_split + 1) * bin_width
    floor_vals = [v for v in clamped if v < threshold]
    speech_vals = [v for v in clamped if v >= threshold]
    return {"thresholdDb": _round3(threshold),
            "floorDb": _round3(_median(floor_vals))
            if floor_vals else float("nan"),
            "speechDb": _round3(_median(speech_vals))
            if speech_vals else float("nan"),
            "eta": _round5(best_score / variance) if variance > 0
            else 0.0}


def speech_map(sound: dict, words: list | None = None,
               threshold_db: float | None = None,
               bridge_seconds: float = 0.3,
               min_speech_seconds: float = 0.2,
               min_separation_db: float = 6.0) -> dict:
    """The media.speech-map JSON, following SpeechMap.json
    exactly: calibration, separation clear/weak/none/given,
    spans/gaps (or null with a reason), and the transcript
    section when words are given. Spans are sound, not proof
    of speech."""
    levels = sound["levels"]
    window = sound["window"]
    total = len(levels) * window
    calibration = otsu_calibrate(levels)
    cal_json: dict = {
        "method": "given" if threshold_db is not None else "otsu",
        "minSeparationDb": min_separation_db}
    if calibration:
        cal_json.update({
            "floorDb": calibration["floorDb"],
            "speechDb": calibration["speechDb"],
            "separationDb": _round3(calibration["speechDb"]
                                    - calibration["floorDb"]),
            "eta": calibration["eta"],
            "otsuThresholdDb": calibration["thresholdDb"]})
    if threshold_db is not None:
        separation = "given"
    elif calibration and calibration["speechDb"] - calibration["floorDb"] \
            >= min_separation_db:
        separation = "clear" if calibration["speechDb"] \
            - calibration["floorDb"] >= 2 * min_separation_db \
            else "weak"
    else:
        separation = "none"
    cal_json["separation"] = separation
    threshold = threshold_db
    if threshold is None and separation != "none" and calibration:
        threshold = calibration["thresholdDb"]
    cal_json["thresholdDb"] = threshold
    silent = sum(1 for v in levels if v <= SILENCE_DB) * window
    result: dict = {
        "measuredOn": f"RMS băng rộng trên mỗi cửa sổ {window} s từ "
                      "media.analyze (dBFS); lặng số được coi là lặng "
                      "và loại khỏi phép hiệu chuẩn",
        "seconds": _round3(total),
        "digitalSilenceSeconds": _round3(silent),
        "calibration": cal_json,
        "parameters": {"bridgeSeconds": bridge_seconds,
                       "minSpeechSeconds": min_speech_seconds}}
    level_spans = None
    if threshold is not None:
        level_spans = [span for span in active_spans(
            levels, window, threshold, bridge_seconds)
            if span[1] - span[0] >= min_speech_seconds]
    if level_spans is not None:
        result["spans"] = _spans_json(level_spans)
        result["speechSeconds"] = _round3(_span_seconds(level_spans))
        result["speechShare"] = _round5(
            _span_seconds(level_spans) / total) if total else 0
        gaps = _gaps_between(level_spans, total)
        result["gaps"] = _spans_json(gaps)
        result["gapStats"] = _gap_stats(gaps)
    else:
        result["spans"] = None
        result["gaps"] = None
        if calibration is None:
            result["reason"] = (
                "Quá ít âm thanh, hoặc mức âm gần như không đổi: "
                "không tách được lớp lặng và lớp ồn. Truyền "
                "thresholdDb để ép tách (chỉ trên -120 một chút "
                "sẽ tách âm thanh khỏi lặng số), hoặc đọc các "
                "span transcript.")
        else:
            result["reason"] = (
                "Các cửa sổ lặng và ồn gần nhau hơn "
                "minSeparationDb: nền và âm thanh trên nền không "
                "tách được nên không có span nào. Truyền "
                "thresholdDb để ép tách (chỉ trên -120 một chút "
                "sẽ tách âm thanh khỏi lặng số), hoặc đọc các "
                "span transcript.")
    if words is not None:
        heard = _joined_spans(
            [(w["start"], w["end"]) for w in words], bridge_seconds)
        transcript: dict = {
            "words": len(words),
            "spans": _spans_json(heard),
            "speechSeconds": _round3(_span_seconds(heard)),
            "gaps": _spans_json(_gaps_between(heard, total))}
        if level_spans is not None:
            shared = _overlap(level_spans, heard)
            level_total = _span_seconds(level_spans)
            heard_total = _span_seconds(heard)
            transcript["levelCoveredByWords"] = _round5(
                shared / level_total) if level_total else 0
            transcript["wordsCoveredByLevel"] = _round5(
                shared / heard_total) if heard_total else 0
        result["transcript"] = transcript
    else:
        result["transcript"] = None
    return result

# ------------------------------------------------------------------
# Sync: AudioSync.swift, faithful port (envelopes at 100/s, log
# RMS of 10 ms windows; coarse search at 10/s, fine at 100/s
# within +-0.3 s; halves must agree within 0.02 s to be steady).
# Pure Python with prefix sums, so each lag's mean/variance is
# O(1); only the dot product is a pass over the overlap.
# ------------------------------------------------------------------

SYNC_RATE = 8000.0
ENVELOPE_RATE = 100
FINE_RADIUS = 30


def _decode_mono_8k_envelope(path: str) -> list:
    """Log-RMS envelope at 100 values per second of the file's
    sound, decoded to mono 8 kHz. Streaming: the envelope list
    itself (100/s) is kept, never the raw samples."""
    from .render import find_tool
    cmd = [find_tool("ffmpeg"), "-v", "error", "-i", path, "-vn",
           "-ac", "1", "-ar", str(int(SYNC_RATE)), "-f", "f32le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    hop = int(SYNC_RATE) // ENVELOPE_RATE
    envelope = []
    acc = 0.0
    count = 0
    try:
        leftover = b""
        while True:
            chunk = proc.stdout.read(1024 * 1024) if proc.stdout else b""
            if not chunk:
                break
            data = leftover + chunk
            usable = len(data) - (len(data) % 4)
            if usable <= 0:
                leftover = data
                continue
            samples = struct.unpack("<%df" % (usable // 4),
                                    data[:usable])
            for value in samples:
                if math.isfinite(value):
                    acc += value * value
                count += 1
                if count == hop:
                    envelope.append(math.log(math.sqrt(acc / hop)
                                            * 32768.0 + 1.0))
                    acc = 0.0
                    count = 0
            leftover = data[usable:]
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.wait(timeout=120)
    try:
        if proc.returncode != 0:
            err = proc.stderr.read().decode("utf-8", "replace") \
                if proc.stderr else ""
            raise RuntimeError(f"FFmpeg không giải mã được {path} để đồng bộ: {err.strip()[:300]}")
    finally:
        if proc.stderr:
            proc.stderr.close()
    return envelope


class _Envelope:
    def __init__(self, values: list):
        self.values = values
        self.sums = [0.0]
        self.squares = [0.0]
        for value in values:
            self.sums.append(self.sums[-1] + value)
            self.squares.append(self.squares[-1] + value * value)

    def _sum(self, sums, lo, hi):
        return sums[hi] - sums[lo]


def _correlation(env_a: _Envelope, env_b: _Envelope, lag: int,
                 within: tuple | None = None) -> tuple:
    """Normalized correlation of a[t] with b[t+lag] over their
    overlap, restricted to a's ``within`` range. Returns
    (correlation, overlap_count); (-1, count) when too short."""
    limit = within if within is not None else (0, len(env_a.values))
    start = max(limit[0], -lag)
    end = min(limit[1], len(env_b.values) - lag)
    count = end - start
    if count < 20:
        return -1.0, max(0, count)
    sum_a = env_a._sum(env_a.sums, start, end)
    sum_b = env_b._sum(env_b.sums, start + lag, end + lag)
    sq_a = env_a._sum(env_a.squares, start, end)
    sq_b = env_b._sum(env_b.squares, start + lag, end + lag)
    mean_a = sum_a / count
    mean_b = sum_b / count
    var_a = sq_a / count - mean_a * mean_a
    var_b = sq_b / count - mean_b * mean_b
    if var_a <= 0 or var_b <= 0:
        return -1.0, count
    product = 0.0
    values_a = env_a.values
    values_b = env_b.values
    for index in range(start, end):
        product += (values_a[index] - mean_a) \
            * (values_b[index + lag] - mean_b)
    corr = product / (count * math.sqrt(var_a * var_b))
    return corr, count


def _best(env_a: _Envelope, env_b: _Envelope, lags,
          minimum_overlap: int, within: tuple | None = None):
    best = None
    for lag in lags:
        corr, count = _correlation(env_a, env_b, lag, within)
        if count < minimum_overlap:
            continue
        if best is None or corr > best[0]:
            best = (corr, lag)
    return best


def _decimate(values: list, factor: int) -> list:
    out = []
    for start in range(0, len(values) - factor + 1, factor):
        chunk = values[start:start + factor]
        out.append(sum(chunk) / len(chunk))
    return out


def align_sound(first_path: str, second_path: str) -> dict:
    """Time offset between two recordings of the same moment,
    from their sound. Result: offsetSeconds (time in the second
    file = time in the first + offset), correlation (below 0.4:
    no shared sound), the overlap in the first file's time, and
    each half of the overlap (steady when they agree within
    0.02 s). Raises a clear error when either file has less
    than 3 seconds of sound or the files do not overlap
    enough to compare."""
    a = _decode_mono_8k_envelope(first_path)
    b = _decode_mono_8k_envelope(second_path)
    if min(len(a), len(b)) < 3 * ENVELOPE_RATE:
        raise ValueError("Cả hai file cần ít nhất 3 giây âm thanh để đồng bộ")
    minimum_overlap = min(len(a), len(b)) // 2
    coarse_a = _Envelope(_decimate(a, 10))
    coarse_b = _Envelope(_decimate(b, 10))
    coarse = _best(coarse_a, coarse_b,
                   range(-(len(coarse_a.values) - 1),
                         len(coarse_b.values)),
                   minimum_overlap // 10)
    if coarse is None:
        raise ValueError("Các file không chồng lấn đủ để so sánh")
    fine_a = _Envelope(a)
    fine_b = _Envelope(b)
    centre = coarse[1] * 10
    fine = _best(fine_a, fine_b,
                 range(centre - FINE_RADIUS, centre + FINE_RADIUS + 1),
                 minimum_overlap)
    if fine is None:
        raise ValueError("Các file không chồng lấn đủ để so sánh")
    lag = fine[1]
    start = max(0, -lag)
    end = min(len(a), len(b) - lag)
    middle = (start + end) // 2
    halves = []
    for lo, hi in ((start, middle), (middle, end)):
        found = _best(fine_a, fine_b,
                      range(lag - FINE_RADIUS, lag + FINE_RADIUS + 1),
                      (middle - start) // 2, within=(lo, hi))
        if found is not None:
            halves.append({"offsetSeconds": round(
                found[1] / ENVELOPE_RATE, 3),
                "correlation": round(found[0], 3)})
    steady = len(halves) == 2 and abs(
        halves[0]["offsetSeconds"] - halves[1]["offsetSeconds"]) \
        <= 0.02 + 1e-9
    return {"offsetSeconds": round(lag / ENVELOPE_RATE, 3),
            "correlation": round(fine[0], 3),
            "sharedSound": fine[0] >= 0.4,
            "overlapStartSeconds": round(start / ENVELOPE_RATE, 3),
            "overlapEndSeconds": round(end / ENVELOPE_RATE, 3),
            "halves": halves,
            "steady": steady}


# ------------------------------------------------------------------
# Strip: frames + levels + gaps + words as one PNG (MediaStills).
# ------------------------------------------------------------------

def extract_frame_png(path: str, seconds: float, dest: str,
                      width: int) -> str:
    """One source frame at ``seconds`` as a PNG no wider than
    ``width`` (FFmpeg seek after -i for accuracy)."""
    from .render import find_tool
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    cmd = [find_tool("ffmpeg"), "-y", "-v", "error", "-i", path,
           "-ss", f"{max(0.0, seconds):.6f}", "-frames:v", "1",
           "-vf", f"scale={width}:-1", dest]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=120)
    if proc.returncode != 0 or not os.path.isfile(dest):
        raise RuntimeError(
            f"FFmpeg không trích được khung hình tại {seconds} giây từ "
            f"{path}: {proc.stderr.strip()[:300]}")
    return dest


def strip_frame_times(start: float, end: float, count: int) -> list:
    """Midpoints of ``count`` cells over [start, end) -- the
    original's strip frame placement."""
    return [start + (i + 0.5) * (end - start) / count
            for i in range(count)]


def _clock(seconds: float) -> str:
    tenths = int(round(max(0.0, seconds) * 10))
    return f"{tenths // 600}:{tenths // 10 % 60:02d}.{tenths % 10}"


def render_strip_png(frame_pngs: list, frame_times: list,
                     levels: list | None, window: float,
                     levels_from: float, gaps: list, words: list,
                     from_s: float, to_s: float,
                     width: int) -> tuple:
    """Draw the strip PNG with Pillow: frames row on top, time
    ruler, sound level (-60..0 dBFS) with gaps shaded, words at
    their times on two alternating lines. Returns (width,
    height). Raises RuntimeError naming Pillow when absent."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError(
            "Chưa cài Pillow nên không vẽ được PNG strip (bản thân dữ liệu strip vẫn được trả về); hãy cài bằng 'pip install pillow'.") from exc
    count = max(1, len(frame_pngs))
    cell_width = width / count
    images = []
    aspect = 16.0 / 9.0
    aspects = []
    for png in frame_pngs:
        try:
            image = Image.open(png).convert("RGB")
            images.append(image)
            aspects.append(image.width / max(1, image.height))
        except Exception:
            images.append(None)
    if aspects:
        aspects.sort()
        aspect = aspects[len(aspects) // 2]
    picture = 0 if not frame_pngs else max(24, round(cell_width / aspect))
    ruler, wave, text_h = 22, 110, 44
    height = int(picture + ruler + wave + text_h)
    canvas = Image.new("RGB", (width, height), (26, 26, 26))
    draw = ImageDraw.Draw(canvas)
    span = max(1e-9, to_s - from_s)
    x_of = lambda seconds: (seconds - from_s) / span * width
    for index, image in enumerate(images):
        x0 = int(index * cell_width)
        x1 = int((index + 1) * cell_width) - 2
        draw.rectangle([x0, 0, max(x0, x1), picture], fill=(0, 0, 0))
        if image is not None:
            scale = min((x1 - x0) / max(1, image.width),
                        picture / max(1, image.height))
            new_w = max(1, int(image.width * scale))
            new_h = max(1, int(image.height * scale))
            thumb = image.resize((new_w, new_h))
            canvas.paste(thumb, (x0 + (x1 - x0 - new_w) // 2,
                                 (picture - new_h) // 2))
        draw.text((x0 + 3, max(0, picture - 14)),
                  _clock(frame_times[index]), fill=(255, 255, 255))
    wave_top = picture + ruler
    for gap_start, gap_end in gaps:
        if gap_end > from_s and gap_start < to_s:
            gx0 = x_of(max(gap_start, from_s))
            gx1 = x_of(min(gap_end, to_s))
            draw.rectangle([gx0, wave_top, gx1, wave_top + wave + text_h],
                           fill=(64, 115, 255))
    step = next((s for s in
                 [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300]
                 if span / s <= 12), 600)
    tick = math.ceil(from_s / step) * step
    while tick <= to_s:
        tx = x_of(tick)
        draw.line([tx, picture, tx, picture + 6], fill=(153, 153, 153))
        draw.text((tx + 2, picture + 4), _clock(tick),
                  fill=(204, 204, 204))
        tick += step
    if levels is not None:
        for column in range(width):
            seconds = from_s + column / width * span
            index = int((seconds - levels_from) / window) \
                if window else -1
            if 0 <= index < len(levels):
                level = min(1.0, max(0.0, (levels[index] + 60.0) / 60.0))
                bar = level * wave
                draw.rectangle([column, wave_top + (wave - bar) / 2,
                                column, wave_top + (wave + bar) / 2],
                               fill=(89, 242, 140))
    for index, word in enumerate(words):
        if word["end"] > from_s and word["start"] < to_s:
            line = 0 if index % 2 == 0 else 1
            draw.text((x_of(max(word["start"], from_s)),
                       wave_top + wave + 4 + line * 20),
                      word["text"], fill=(255, 255, 255))
    return canvas, width, height


def prune_strips(directory: str, keep: int = 100) -> None:
    """Keep only the newest ``keep`` strip PNGs (the original
    prunes its stills directory to 300; strips are pruned
    separately so other stills are never deleted)."""
    try:
        entries = []
        for name in os.listdir(directory):
            if name.startswith("strip-") and name.endswith(".png"):
                full = os.path.join(directory, name)
                entries.append((os.path.getmtime(full), full))
        entries.sort(reverse=True)
        for _mtime, full in entries[keep:]:
            try:
                os.remove(full)
            except OSError:
                pass
    except OSError:
        pass
