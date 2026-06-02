"""Deepgram STT smoke test (gated by DEEPGRAM_API_KEY).

Hits the prerecorded HTTP endpoint with a tiny synthetic audio so we can
confirm the key + model name are valid. The real path used at call-time is
the WebSocket / Nova-3 multilingual stream — we don't reproduce that here.
"""
from __future__ import annotations

import os
import struct
import wave
from io import BytesIO

import httpx
import pytest


def _silent_wav(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    buf = BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        n = int(duration_s * sample_rate)
        w.writeframes(struct.pack("<" + "h" * n, *([0] * n)))
    return buf.getvalue()


@pytest.mark.skipif(
    not os.environ.get("DEEPGRAM_API_KEY", "").strip(),
    reason="DEEPGRAM_API_KEY not set",
)
@pytest.mark.asyncio
async def test_deepgram_prerecorded_api_accepts_audio():
    key = os.environ["DEEPGRAM_API_KEY"].strip()
    wav = _silent_wav(1.0)
    params = {"model": "nova-3", "language": "multi", "smart_format": "true"}
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            "https://api.deepgram.com/v1/listen",
            params=params,
            content=wav,
            headers={
                "Authorization": f"Token {key}",
                "Content-Type": "audio/wav",
            },
        )
    # 200 means key + model + audio accepted; transcript is empty (silence) — that's fine.
    assert r.status_code == 200, f"Deepgram error {r.status_code}: {r.text[:300]}"
    body = r.json()
    assert "results" in body, f"unexpected body: {body}"
