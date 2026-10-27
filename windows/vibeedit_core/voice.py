"""Voice generation for the Windows port (round 3).

The original macOS app speaks through plugin voice providers; on
Windows the two real providers wired here are:

- Edge TTS (online): the ``edge-tts`` Python module, when installed.
  Text is synthesized over the network; no voice audio is bundled.
- Piper (local): the ``piper`` binary, when on PATH, plus a caller-
  supplied ``.onnx`` voice model file (``model`` argument, or the
  ``VIBEEDIT_PIPER_MODEL`` environment variable). No model file is
  bundled or referenced by default — a Piper call without a model
  raises instead of inventing one.

Rules, enforced by the tests:

- Both backends are optional runtime-only dependencies. Importing
  this module never fails when they are absent, and neither backend
  is imported at module top level.
- Every function returns real results or raises — never fake audio.
  When no backend can run, :class:`VoiceUnavailable` names the
  missing binary/module and how to install it.
- Voice *cloning* is deliberately NOT implemented here: cloning a
  voice needs a cloning provider model (the original used an
  on-device provider), and none is available in this build. The
  clone tools therefore stay honest check-and-error tools; only
  generation (synthesize/speak/lines), placing a take, choosing a
  voice and fitting a take's speed are real here.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess


class VoiceUnavailable(Exception):
    """No usable voice backend on this machine (see the message)."""


def available_backends() -> dict:
    """Probe the two wired backends without importing them."""
    import importlib.util
    return {
        "piper": shutil.which("piper") is not None,
        "edge_tts": importlib.util.find_spec("edge_tts") is not None,
    }


def _ffprobe_duration_seconds(path: str) -> float | None:
    """Duration of an audio file via ffprobe, or None when ffprobe
    is absent or cannot read the file. Never raises."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration", "-of", "json", path],
            capture_output=True, text=True, timeout=30)
        if out.returncode != 0:
            return None
        return float(json.loads(out.stdout)["format"]["duration"])
    except Exception:
        return None


def _synthesize_edge(text: str, out_path: str,
                     voice: str | None) -> dict:
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceUnavailable(
            "Edge TTS is not installed. Install it with "
            "'pip install edge-tts' (it synthesizes over the "
            "network), or use the Piper backend instead.") from exc
    kwargs = {"voice": voice} if voice else {}
    communicate = edge_tts.Communicate(text, **kwargs)
    try:
        asyncio.run(communicate.save(out_path))
    except Exception as exc:
        raise VoiceUnavailable(
            f"Edge TTS synthesis failed: {exc}") from exc
    return {"backend": "edge_tts", "voice": voice}


def _synthesize_piper(text: str, out_path: str, model: str | None,
                      voice: str | None) -> dict:
    piper = shutil.which("piper")
    if piper is None:
        raise VoiceUnavailable(
            "The 'piper' binary was not found on PATH. Install "
            "Piper and put it on PATH, or use the Edge TTS backend "
            "instead.")
    model = model or os.environ.get("VIBEEDIT_PIPER_MODEL") or voice
    if not model or not model.endswith(".onnx"):
        raise VoiceUnavailable(
            "Piper needs a voice model file (.onnx): pass it as "
            "the 'model' argument (or set VIBEEDIT_PIPER_MODEL). "
            "No model is bundled with this build.")
    if not os.path.isfile(model):
        raise FileNotFoundError(f"Piper model file not found: {model}")
    proc = subprocess.run(
        [piper, "--model", model, "--output_file", out_path],
        input=text, text=True, capture_output=True, timeout=300)
    if proc.returncode != 0 or not os.path.isfile(out_path):
        raise VoiceUnavailable(
            "Piper synthesis failed: "
            f"{proc.stderr.strip() or proc.stdout.strip()}")
    return {"backend": "piper", "voice": model}


def synthesize(text: str, out_path: str, provider: str | None = None,
               voice: str | None = None,
               model: str | None = None) -> dict:
    """Synthesize ``text`` to ``out_path`` (WAV) with a real
    provider and return {"path", "backend", "voice", "duration"}.
    ``provider`` is "edge" or "piper"; when omitted, Piper is
    preferred when its binary exists, else Edge TTS when its module
    exists, else VoiceUnavailable naming both installs. ``voice``
    is the Edge voice name (e.g. "vi-VN-HoaiMyNeural") or, for
    Piper, a .onnx model path (same as ``model``)."""
    if not text or not text.strip():
        raise ValueError("Voice text must not be empty")
    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    backends = available_backends()
    if provider in (None, "auto"):
        if backends["piper"]:
            provider = "piper"
        elif backends["edge_tts"]:
            provider = "edge"
        else:
            raise VoiceUnavailable(
                "No voice backend is available: install Piper "
                "(binary on PATH plus a .onnx model) or Edge TTS "
                "('pip install edge-tts').")
    if provider == "piper":
        info = _synthesize_piper(text, out_path, model, voice)
    elif provider == "edge":
        info = _synthesize_edge(text, out_path, voice)
    else:
        raise ValueError(
            f"Unknown voice provider: {provider!r} (use 'edge' or "
            "'piper')")
    size = os.path.getsize(out_path) if os.path.isfile(out_path) else 0
    if size == 0:
        raise VoiceUnavailable(
            f"Voice provider {info['backend']} produced no audio")
    return {"path": out_path, "backend": info["backend"],
            "voice": info["voice"],
            "duration": _ffprobe_duration_seconds(out_path)}


def place_on_voiceover(project, media_id: str,
                       at: int | None = None) -> dict:
    """Place a media item on the Voiceover track (creating the
    track when the project has none) at ``at`` or at the track
    end, and return the new clip item. Only audio media may be
    placed on the Voiceover track."""
    medium = project.media(media_id)
    if medium.get("kind") != "audio":
        raise ValueError("Only audio media can go on the Voiceover "
                         "track")
    track = next((t for t in project.data["tracks"]
                  if t.get("role") == "voiceover"), None)
    if track is None:
        track = project.add_track("audio", "voiceover", "Voiceover")
    if at is None:
        at = max((int(i["at"]) + int(i["dur"])
                  for i in track["items"]), default=0)
    return project.add_clip(media_id, track["id"], int(at))
