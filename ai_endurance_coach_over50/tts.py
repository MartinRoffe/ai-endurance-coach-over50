"""ElevenLabs text-to-speech for coach chat replies.

Optional: set ELEVENLABS_API_KEY in .env. Uses Flash by default (fast + cheap).
Browser TTS is the fallback when the key is unset.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

# Daniel — calm British male; override with ELEVENLABS_VOICE_ID
_DEFAULT_VOICE = "onwK4e9ZLuTAKqWW03F9"
_DEFAULT_MODEL = "eleven_flash_v2_5"
_MAX_CHARS = 2500
_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def tts_configured() -> bool:
    return bool(os.getenv("ELEVENLABS_API_KEY", "").strip())


def synthesize(text: str, *, previous_text: str = "") -> bytes:
    """Return mp3 bytes for *text*. Raises on missing key or API failure."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    text = (text or "").strip()
    if not text:
        raise ValueError("empty text")
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS]

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", _DEFAULT_VOICE).strip() or _DEFAULT_VOICE
    model_id = os.getenv("ELEVENLABS_MODEL_ID", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL

    body: dict = {
        "text": text,
        "model_id": model_id,
        "apply_text_normalization": "auto",
    }
    prev = (previous_text or "").strip()
    if prev:
        body["previous_text"] = prev[:500]

    url = (
        _API_URL.format(voice_id=urllib.parse.quote(voice_id, safe=""))
        + "?output_format=mp3_44100_128"
        + "&optimize_streaming_latency=2"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        log.warning("ElevenLabs TTS HTTP %s: %s", e.code, detail)
        raise RuntimeError(f"ElevenLabs HTTP {e.code}") from e
    except urllib.error.URLError as e:
        log.warning("ElevenLabs TTS network error: %s", e)
        raise RuntimeError("ElevenLabs network error") from e
