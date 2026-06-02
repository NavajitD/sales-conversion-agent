"""Multi-provider LLM key pool: Groq → Sarvam → Cerebras.

Groq is preferred (non-reasoning, fastest TTFB). Each Groq key is tried with
the primary model first, then with a fallback model (separate rate-limit bucket).
Sarvam is next (good Hinglish). Cerebras is last resort (reasoning overhead).

Rate-limited keys are temporarily disabled for a cooldown period to avoid
wasting 200ms+ on known-failed requests.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

from app.config import (
    CEREBRAS_MODEL,
    GROQ_FALLBACK_MODEL,
    GROQ_MODEL,
    GROQ_NUANCE_MODEL,
)

CEREBRAS_BASE = "https://api.cerebras.ai/v1"
GROQ_BASE = "https://api.groq.com/openai/v1"
SARVAM_BASE = "https://api.sarvam.ai/v1"
# Gemini's OpenAI-compatibility shim. Accepts AIzaSy... API keys.
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"

# gemini-2.0-flash returned 404 "no longer available to new users" during the
# May 2026 bench. -latest auto-tracks the current stable Flash.
GEMINI_MODEL = "gemini-flash-latest"

# How long to skip a rate-limited key before retrying (seconds)
COOLDOWN_SECONDS = 60


@dataclass
class PoolEntry:
    provider: str  # "cerebras", "groq", or "sarvam"
    key: str
    label: str
    model_override: str = ""  # if set, overrides the default model for this provider
    _cooldown_until: float = field(default=0.0, repr=False)


class KeyRotator:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pool: list[PoolEntry] = []
        self._idx = 0
        self.reload()

    def reload(self) -> None:
        """Rebuild the pool from env.

        Order: Groq (primary GROQ_MODEL — scout) → Groq (GROQ_FALLBACK_MODEL —
        70b, separate rate-limit bucket) → Sarvam → Cerebras.
        """
        with self._lock:
            self._pool = []
            self._idx = 0
            groq_keys = []
            for i in range(1, 4):
                k = (os.environ.get(f"GROQ_API_KEY_{i}") or "").strip()
                if k:
                    groq_keys.append(k)
            # Primary model FIRST (scout — fast TTFB)
            for i, k in enumerate(groq_keys, 1):
                self._pool.append(PoolEntry("groq", k, f"groq-{i}-primary"))
            # Then fallback model (70b — slower but more nuanced; separate
            # rate-limit bucket so it survives when scout hits the daily cap).
            for i, k in enumerate(groq_keys, 1):
                self._pool.append(
                    PoolEntry(
                        "groq", k, f"groq-{i}-fallback",
                        model_override=GROQ_FALLBACK_MODEL,
                    )
                )
            # Sarvam LLM is DISABLED in the live pool: the May 2026 bench
            # showed it emits visible "<think>…</think>" reasoning blocks in
            # the response, which would be read aloud by TTS. Re-enable with
            # SARVAM_LLM_IN_POOL=1 once a streaming-aware <think> stripper is
            # added to the /llm proxy (tracked in FUTURE.md).
            sarvam_key = (os.environ.get("SARVAM_API_KEY") or "").strip()
            if sarvam_key and os.environ.get("SARVAM_LLM_IN_POOL") == "1":
                self._pool.append(PoolEntry("sarvam", sarvam_key, "sarvam-1"))
            # Gemini is OPT-IN to the live pool: bench it first (Phase 2a),
            # then set GEMINI_IN_POOL=1 to promote into call rotation.
            gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
            if gemini_key and os.environ.get("GEMINI_IN_POOL") == "1":
                self._pool.append(PoolEntry("gemini", gemini_key, "gemini-1"))
            # Cerebras (reasoning models — last resort due to TTFB overhead)
            for i in range(1, 4):
                k = (os.environ.get(f"CEREBRAS_API_KEY_{i}") or "").strip()
                if k:
                    self._pool.append(PoolEntry("cerebras", k, f"cerebras-{i}"))
            if not self._pool:
                logger.warning("[llm] No API keys configured")
            else:
                labels = ", ".join(e.label for e in self._pool)
                logger.info(f"[llm] Key pool ({len(self._pool)}): {labels}")

    def mark_rate_limited(self, entry: PoolEntry) -> None:
        """Mark an entry as rate-limited so it's skipped for COOLDOWN_SECONDS."""
        entry._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
        logger.info(f"[llm] {entry.label} rate-limited, cooldown {COOLDOWN_SECONDS}s")

    def current(self) -> Optional[PoolEntry]:
        """Return the next available (non-cooled-down) entry."""
        with self._lock:
            now = time.monotonic()
            # Find first available entry from current position
            for i in range(len(self._pool)):
                idx = (self._idx + i) % len(self._pool)
                entry = self._pool[idx]
                if entry._cooldown_until <= now:
                    self._idx = idx
                    return entry
            # All on cooldown — return the one with shortest remaining cooldown
            if self._pool:
                best = min(self._pool, key=lambda e: e._cooldown_until)
                self._idx = self._pool.index(best)
                return best
            return None

    def rotate(self) -> Optional[PoolEntry]:
        """Advance past current entry. Returns the new current entry."""
        with self._lock:
            now = time.monotonic()
            # Mark current as needing skip and find next available
            start = (self._idx + 1) % len(self._pool) if self._pool else 0
            for i in range(len(self._pool)):
                idx = (start + i) % len(self._pool)
                entry = self._pool[idx]
                if entry._cooldown_until <= now:
                    old_label = self._pool[self._idx].label if self._pool else "?"
                    self._idx = idx
                    logger.info(f"[llm] Key rotated: {old_label} → {entry.label}")
                    return entry
            # All on cooldown
            if self._pool:
                self._idx = start
                logger.warning(f"[llm] All keys on cooldown, using {self._pool[start].label}")
                return self._pool[start]
            return None

    def pool_size(self) -> int:
        with self._lock:
            return len(self._pool)

    def nuance_entry(self) -> Optional[PoolEntry]:
        """Return an entry that routes to GROQ_NUANCE_MODEL (70b by default).

        Used for high-nuance turns (hard_no signals, spouse_deferral keywords)
        where scout's small-model error rate matters more than its ~340ms TTFB
        advantage. Falls back to the regular pool's `current()` if no Groq key
        is available.
        """
        with self._lock:
            now = time.monotonic()
            for entry in self._pool:
                if entry.provider == "groq" and entry._cooldown_until <= now:
                    # Synthesize a one-off entry with the nuance model override.
                    return PoolEntry(
                        provider="groq",
                        key=entry.key,
                        label=f"{entry.label}-nuance",
                        model_override=GROQ_NUANCE_MODEL,
                    )
        return self.current()

    @staticmethod
    def base_url(provider: str) -> str:
        if provider == "cerebras":
            return CEREBRAS_BASE
        if provider == "sarvam":
            return SARVAM_BASE
        if provider == "gemini":
            return GEMINI_BASE
        return GROQ_BASE

    def model_for_entry(self, entry: PoolEntry) -> str:
        """Return the model to use for a given pool entry."""
        if entry.model_override:
            return entry.model_override
        if entry.provider == "cerebras":
            return CEREBRAS_MODEL
        if entry.provider == "sarvam":
            return "sarvam-m"
        if entry.provider == "gemini":
            return GEMINI_MODEL
        return GROQ_MODEL

    # Backward compat
    def model(self, provider: str) -> str:
        if provider == "cerebras":
            return CEREBRAS_MODEL
        if provider == "sarvam":
            return "sarvam-m"
        if provider == "gemini":
            return GEMINI_MODEL
        return GROQ_MODEL

    @staticmethod
    def is_quota_error(status: int, text: str) -> bool:
        if status in (402, 429):
            return True
        t = (text or "").lower()
        if status == 404 and "model_not_found" in t:
            return True
        return any(
            k in t
            for k in (
                "rate_limit",
                "ratelimit",
                "quota",
                "credits",
                "limit_exceeded",
                "insufficient_quota",
                "too many requests",
            )
        )


# Module-level singleton
rotator = KeyRotator()
