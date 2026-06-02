"""Sarvam TTS smoke test (gated by SARVAM_API_KEY).

Synthesises a short Hinglish sentence over the batch HTTP endpoint and asserts
we get audio bytes back. Doesn't exercise the WS streaming path Pipecat uses
in production — keep that for the real Twilio call.
"""
from __future__ import annotations

import base64
import os

import httpx
import pytest


@pytest.mark.skipif(
    not os.environ.get("SARVAM_API_KEY", "").strip(),
    reason="SARVAM_API_KEY not set",
)
@pytest.mark.asyncio
async def test_sarvam_tts_returns_audio():
    key = os.environ["SARVAM_API_KEY"].strip()
    payload = {
        "text": "Namaste, main Aria bol rahi hoon Vedantu se.",
        "target_language_code": "hi-IN",
        "speaker": os.environ.get("SARVAM_TTS_SPEAKER", "anushka"),
        "model": os.environ.get("SARVAM_TTS_MODEL", "bulbul:v2"),
        "sample_rate": 16000,
        "enable_preprocessing": True,
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            "https://api.sarvam.ai/text-to-speech",
            json=payload,
            headers={"api-subscription-key": key, "Content-Type": "application/json"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    b64 = (body.get("audios") or [None])[0] or body.get("audio")
    assert b64, f"no audio in response: {body}"
    audio = base64.b64decode(b64)
    # WAV header (44 bytes) + at least some PCM data
    assert len(audio) > 200, f"audio too small ({len(audio)} bytes) — likely an error"
