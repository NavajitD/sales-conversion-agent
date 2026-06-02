"""Centralised env loading with sane defaults."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    """Read an env var. Returns default if missing OR set to blank/whitespace."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


def _int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


SERVER_HOST = _env("SERVER_HOST", "0.0.0.0")
SERVER_PORT = _int("SERVER_PORT", 3000)
PANEL_PORT = _int("PANEL_PORT", 5173)
PUBLIC_URL = _env("PUBLIC_URL").rstrip("/")

DATABASE_PATH = _env("DATABASE_PATH", str(ROOT / "data" / "aria.db"))

DEEPGRAM_API_KEY = _env("DEEPGRAM_API_KEY")
SARVAM_API_KEY = _env("SARVAM_API_KEY")
SARVAM_TTS_SPEAKER = _env("SARVAM_TTS_SPEAKER", "simran")
SARVAM_TTS_MODEL = _env("SARVAM_TTS_MODEL", "bulbul:v3")

VOBIZ_AUTH_ID = _env("VOBIZ_AUTH_ID")
VOBIZ_AUTH_TOKEN = _env("VOBIZ_AUTH_TOKEN")
VOBIZ_PHONE_NUMBER = _env("VOBIZ_PHONE_NUMBER")
VOBIZ_ENCODING = _env("VOBIZ_ENCODING", "audio/x-mulaw")
VOBIZ_SAMPLE_RATE = _int("VOBIZ_SAMPLE_RATE", 8000)
VOBIZ_L16_ENDIAN = _env("VOBIZ_L16_ENDIAN", "be")
DEMO_PHONE_NUMBER = _env("DEMO_PHONE_NUMBER")

CEREBRAS_MODEL = _env("CEREBRAS_MODEL", "gpt-oss-120b")  # Cerebras retired llama; gpt-oss-120b is current
GROQ_MODEL = _env("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
GROQ_FALLBACK_MODEL = _env("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
# Models routed for high-nuance edge cases (currently: hard_no escalation).
GROQ_NUANCE_MODEL = _env("GROQ_NUANCE_MODEL", "llama-3.3-70b-versatile")


def public_url() -> str:
    """Return the externally-reachable HTTPS URL (raises if missing)."""
    url = _env("PUBLIC_URL").rstrip("/")
    if not url:
        raise RuntimeError("PUBLIC_URL is not set — point at your ngrok HTTPS URL")
    return url


def public_ws_url() -> str:
    """Return a wss:// URL based on PUBLIC_URL (read fresh each call)."""
    url = public_url()
    if url.startswith("https://"):
        return "wss://" + url[len("https://") :]
    if url.startswith("http://"):
        return "ws://" + url[len("http://") :]
    return url
