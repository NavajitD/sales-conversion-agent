"""Per-phone rate limiting for the public demo.

Rolling-window limits applied to ALL phones (no whitelist exemption from
2026-06-01 — the build owner is also rate-limited now):
  HOUR_LIMIT = 5 calls per rolling 60-minute window
  DAY_LIMIT  = 25 calls per rolling 24-hour window

Storage: `rate_limits/{phone}` in Firestore — a list of ISO-8601 event
timestamps. `firestore_repo.append_rate_event` prunes events older than
24h on every write to keep the doc small.

Whitelisting now means *skipping* the limit, not *raising* it — and is
reserved for internal alpha-test numbers if we ever need it. Empty by
default per FUTURE.md hardening guidance.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

from app.crm import repository

# Default limits (everyone except the privileged numbers in PRIVILEGED).
# Per product requirement (2026-06-01): visitors get at most 5 calls per
# rolling 24h. The hourly cap is kept equal to the daily so the abuse story
# is the same: 5 then locked-out-for-24h. PRIVILEGED phones get a higher
# day-budget plus a smaller hour budget so the build owner can iterate.
HOUR_LIMIT: Final[int] = 5
DAY_LIMIT: Final[int] = 5

PRIVILEGED_HOUR_LIMIT: Final[int] = 5
PRIVILEGED_DAY_LIMIT: Final[int] = 25
PRIVILEGED: Final[set[str]] = {"+916009498752"}

# `WHITELIST` is kept for fully-unlimited numbers (still empty by default).
WHITELIST: Final[set[str]] = set()


def _limits_for(phone: str) -> tuple[int, int]:
    if phone in PRIVILEGED:
        return PRIVILEGED_HOUR_LIMIT, PRIVILEGED_DAY_LIMIT
    return HOUR_LIMIT, DAY_LIMIT


def normalise_e164(phone: str) -> str:
    """Strip whitespace, ensure leading '+'. Caller validates the digits."""
    p = (phone or "").strip().replace(" ", "").replace("-", "")
    if not p:
        return ""
    if not p.startswith("+"):
        p = "+" + p
    return p


def _count_within(events: list[str], window: timedelta) -> int:
    cutoff = datetime.now(timezone.utc) - window
    n = 0
    for ev in events:
        try:
            dt = datetime.fromisoformat(ev.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if dt >= cutoff:
            n += 1
    return n


def _status_dict(phone: str, events: list[str], whitelisted: bool = False) -> dict:
    hour_used = _count_within(events, timedelta(hours=1))
    day_used = _count_within(events, timedelta(hours=24))
    hour_limit, day_limit = _limits_for(phone)
    day_remaining = max(day_limit - day_used, 0)
    # You can never place more calls in the next hour than remain for the day,
    # so clamp hour_remaining to day_remaining. Without this the UI could show
    # contradictions like "3 more this hour · 2 more today" (e.g. when the
    # hourly and daily caps are equal).
    hour_remaining = min(max(hour_limit - hour_used, 0), day_remaining)
    return {
        "phone": phone,
        "hour_used": hour_used,
        "hour_limit": hour_limit,
        "hour_remaining": hour_remaining,
        "day_used": day_used,
        "day_limit": day_limit,
        "day_remaining": day_remaining,
        "whitelisted": whitelisted,
    }


async def status_for(phone: str) -> dict:
    """Read-only: how many calls used in the last 1h + 24h, how many remain."""
    phone = normalise_e164(phone)
    if not phone:
        return {
            "phone": "", "hour_used": 0, "hour_limit": HOUR_LIMIT,
            "hour_remaining": HOUR_LIMIT, "day_used": 0, "day_limit": DAY_LIMIT,
            "day_remaining": DAY_LIMIT, "whitelisted": False,
        }
    if phone in WHITELIST:
        return _status_dict(phone, [], whitelisted=True)
    data = await repository.get_rate_limit(phone)
    return _status_dict(phone, list(data.get("events") or []))


def _refuse(phone: str, events: list[str], reason: str) -> dict:
    status = _status_dict(phone, events)
    status["reason"] = reason
    return status


async def try_increment(phone: str) -> tuple[bool, dict]:
    """Atomically append an event if both windows have headroom.

    Returns (allowed, status_dict). On refusal, status_dict includes
    `reason` set to 'hour_limit_reached' or 'day_limit_reached'.
    """
    phone = normalise_e164(phone)
    if not phone:
        return False, {"error": "invalid phone"}
    if phone in WHITELIST:
        return True, _status_dict(phone, [], whitelisted=True)

    # Pre-check: read first so we can refuse without writing.
    current = await repository.get_rate_limit(phone)
    events = list(current.get("events") or [])
    hour_used = _count_within(events, timedelta(hours=1))
    day_used = _count_within(events, timedelta(hours=24))
    hour_limit, day_limit = _limits_for(phone)

    if hour_used >= hour_limit:
        return False, _refuse(phone, events, "hour_limit_reached")
    if day_used >= day_limit:
        return False, _refuse(phone, events, "day_limit_reached")

    now_iso = datetime.now(timezone.utc).isoformat()
    new_events = await repository.append_rate_event(phone, now_iso)
    return True, _status_dict(phone, list(new_events))
