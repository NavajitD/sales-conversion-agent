"""Voice A/B harness: side-by-side Hinglish TTS clips, ElevenLabs vs Sarvam.

For each test line, synthesises audio from both providers and writes to
disk. You play them back-to-back and pick the one that sounds more natural
on a phone call (which is what Pipecat resamples to: 8 kHz mu-law).

Usage:
  .venv/bin/python scripts/voice_ab.py [--out voice_ab_clips]

Output:
  voice_ab_clips/
    01_greeting_elevenlabs.mp3
    01_greeting_sarvam.mp3
    ...
    INDEX.md   ← play these in order; pick the one that sounds like a real
                 Indian counsellor, not a TTS engine

Notes:
  • We test the *natural* output of each provider; downstream Pipecat
    resampling to 8 kHz mu-law equalises some quality loss across both, so
    raw-quality differences here are an upper bound on the call-quality gap.
  • This is TTS only. STT comparison (ElevenLabs Realtime STT vs Deepgram
    Nova-3) needs a noisy Hinglish audio sample — wire that in once you have
    a sample recording, then run scripts/stt_ab.py (TODO Phase 2b.2).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVEN_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "cgSgspJ2msm6clMCkdW9").strip()
ELEVEN_MODEL = os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5").strip()

SARVAM_KEY = os.environ.get("SARVAM_API_KEY", "").strip()
SARVAM_SPEAKER = os.environ.get("SARVAM_TTS_SPEAKER", "simran").strip()
SARVAM_MODEL = os.environ.get("SARVAM_TTS_MODEL", "bulbul:v3").strip()

# Representative bot lines. Mix of Devanagari, Latin English brand names, and
# numbers — covers what Aria says daily.
LINES = [
    {
        "id": "01_greeting",
        "text": (
            "नमस्ते Sharma जी, मैं Priya बोल रही हूँ Vedantu से। "
            "आज Aarav ने Physics का demo attend किया था Ms. Kapoor के साथ। "
            "बस यह जानना था, कैसा लगा उन्हें?"
        ),
    },
    {
        "id": "02_price_split",
        "text": (
            "Amount खुद ज़्यादा लग रहा है, या अभी clear नहीं कि इतने का value मिलेगा?"
        ),
    },
    {
        "id": "03_competitor_pw",
        "text": (
            "PW ka price advantage real hai. Lekin Vedantu mein har bacche ka "
            "personal mentor hota hai jo weekly attendance aur test scores track "
            "karta hai। Yeh discipline layer कहीं और नहीं मिलता।"
        ),
    },
    {
        "id": "04_close_callback",
        "text": (
            "Kal evening seven baje main aapko दोबारा call करूँगी। "
            "Tab तक aap husband se discuss कर सकते हैं?"
        ),
    },
    {
        "id": "05_hard_no_exit",
        "text": (
            "बिल्कुल, आपका time और नहीं लूँगी। Aarav की पढ़ाई के लिए सबसे अच्छा। "
            "धन्यवाद, namaste।"
        ),
    },
]


async def synth_elevenlabs(client: httpx.AsyncClient, text: str) -> bytes | None:
    if not ELEVEN_KEY:
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}?output_format=mp3_22050_32"
    headers = {
        "xi-api-key": ELEVEN_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text,
        "model_id": ELEVEN_MODEL,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    r = await client.post(url, headers=headers, json=body, timeout=60.0)
    if r.status_code >= 400:
        print(f"  ! elevenlabs HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return None
    return r.content


async def synth_sarvam(client: httpx.AsyncClient, text: str) -> bytes | None:
    if not SARVAM_KEY:
        return None
    url = "https://api.sarvam.ai/text-to-speech"
    headers = {
        "API-Subscription-Key": SARVAM_KEY,
        "Content-Type": "application/json",
    }
    # Bulbul v3 rejects pitch + loudness; only pace is supported.
    body = {
        "inputs": [text],
        "target_language_code": "hi-IN",
        "speaker": SARVAM_SPEAKER,
        "model": SARVAM_MODEL,
        "pace": 1.0,
        "speech_sample_rate": 22050,
        "enable_preprocessing": True,
    }
    r = await client.post(url, headers=headers, json=body, timeout=60.0)
    if r.status_code >= 400:
        print(f"  ! sarvam HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        return None
    # Sarvam returns base64 in JSON.
    import base64

    data = r.json()
    audios = data.get("audios") or []
    if not audios:
        return None
    return base64.b64decode(audios[0])


async def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    index_lines: list[str] = []
    index_lines.append("# Voice A/B — ElevenLabs vs Sarvam Bulbul (Hinglish)")
    index_lines.append("")
    index_lines.append(
        f"- ElevenLabs voice: `{ELEVEN_VOICE}` model `{ELEVEN_MODEL}`"
    )
    index_lines.append(
        f"- Sarvam speaker: `{SARVAM_SPEAKER}` model `{SARVAM_MODEL}`"
    )
    index_lines.append("")
    index_lines.append(
        "Listen to each pair (EL → Sarvam) and judge: naturalness, Devanagari "
        "pronunciation, English brand names ('Vedantu', 'Ms. Kapoor', 'PW'), "
        "number reading ('seven baje', 'fourteen-five hundred'). Pick the one "
        "that sounds least like a TTS engine over a phone-quality channel."
    )
    index_lines.append("")

    async with httpx.AsyncClient() as client:
        for line in LINES:
            print(f"→ {line['id']}: {line['text'][:60]}…")
            el_audio = await synth_elevenlabs(client, line["text"])
            sa_audio = await synth_sarvam(client, line["text"])

            el_path = out_dir / f"{line['id']}_elevenlabs.mp3"
            sa_path = out_dir / f"{line['id']}_sarvam.wav"

            if el_audio:
                el_path.write_bytes(el_audio)
            if sa_audio:
                sa_path.write_bytes(sa_audio)

            index_lines.append(f"## {line['id']}")
            index_lines.append(f"> {line['text']}")
            index_lines.append("")
            if el_audio:
                index_lines.append(f"- ElevenLabs: [{el_path.name}]({el_path.name})")
            else:
                index_lines.append("- ElevenLabs: (failed — see stderr)")
            if sa_audio:
                index_lines.append(f"- Sarvam:     [{sa_path.name}]({sa_path.name})")
            else:
                index_lines.append("- Sarvam:     (failed — see stderr)")
            index_lines.append("")

    (out_dir / "INDEX.md").write_text("\n".join(index_lines))
    print(f"\nDone. Open {out_dir}/INDEX.md and play the clips.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=str, default="voice_ab_clips")
    args = ap.parse_args()
    if not ELEVEN_KEY and not SARVAM_KEY:
        print("ERROR: neither ELEVENLABS_API_KEY nor SARVAM_API_KEY is set", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(Path(args.out).resolve()))
