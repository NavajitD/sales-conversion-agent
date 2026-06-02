"""Callback cadence for outbound calling in urban/semi-urban India.

Heuristics, in priority order:
  1. Stay inside polite calling hours (10:00–20:30 IST). Anything earlier or
     later slides to the next 10:00.
  2. Avoid Sundays unless the parent themselves asked for a specific time.
  3. For no-answer retries, follow a frequency-decaying ladder that mirrors
     what high-performing edtech inside-sales teams typically run:
        Attempt 1 (the original call) — within the 2–4h post-demo golden window.
        Attempt 2 — +30 min after Attempt 1 (different ring rhythm catches many).
        Attempt 3 — +4 h.
        Attempt 4 — next day morning slot.
        Attempt 5 — next day evening slot.
        After 5 no-answers: drop to nurture_followup (handled elsewhere).
  4. Parent-requested callbacks honour the parent's time verbatim, only
     adjusted to fit polite hours.

This module is a pure-Python policy function. The scheduler that actually
places the call reads from the `callbacks` table at the policy-decided time.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Optional

# IST offset (no DST). Pipecat/Twilio scheduling stores UTC; policy reasons in IST.
IST = timezone(timedelta(hours=5, minutes=30))

POLITE_START = time(10, 0)   # 10:00 IST
POLITE_END = time(20, 30)    # 20:30 IST
MAX_NO_ANSWER_ATTEMPTS = 5

# Offsets from the previous attempt (or, for slot 0, from now).
NO_ANSWER_OFFSETS_MINUTES = [
    0,       # attempt 1 — handled by the initial call placement; cadence is for the *next* attempt
    30,      # attempt 2 — +30 min
    240,     # attempt 3 — +4 h
    None,    # attempt 4 — next-day morning slot
    None,    # attempt 5 — next-day evening slot
]


@dataclass
class CadenceDecision:
    next_attempt_at_utc: datetime
    is_terminal: bool          # True if we should not retry — caller should escalate to nurture
    attempt_number: int        # 1-indexed; what attempt this would be
    reason: str                # 'no_answer_retry' or 'nurture_followup'


def _to_ist(dt_utc: datetime) -> datetime:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(IST)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc)


def _slide_to_polite_hours(dt_ist: datetime, allow_sunday: bool = False) -> datetime:
    """Push dt forward to the nearest polite-hours slot in IST."""
    cur = dt_ist
    while True:
        if not allow_sunday and cur.weekday() == 6:  # Sunday
            cur = (cur + timedelta(days=1)).replace(
                hour=POLITE_START.hour, minute=POLITE_START.minute, second=0, microsecond=0
            )
            continue
        if cur.time() < POLITE_START:
            cur = cur.replace(hour=POLITE_START.hour, minute=POLITE_START.minute, second=0, microsecond=0)
            continue
        if cur.time() > POLITE_END:
            cur = (cur + timedelta(days=1)).replace(
                hour=POLITE_START.hour, minute=POLITE_START.minute, second=0, microsecond=0
            )
            continue
        return cur


def next_no_answer_retry(
    previous_attempt_utc: datetime,
    attempts_so_far: int,
    now_utc: datetime | None = None,
) -> CadenceDecision:
    """Decide when (if at all) to retry a no-answer.

    `attempts_so_far` = number of attempts already made (including the one that
    just no-answered). So after the initial call no-answers, this is 1.
    """
    now_utc = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    next_attempt_idx = attempts_so_far  # 0-indexed into NO_ANSWER_OFFSETS_MINUTES

    if next_attempt_idx >= MAX_NO_ANSWER_ATTEMPTS:
        # Place a nurture follow-up 3 days out at 11 AM IST.
        target_ist = _to_ist(now_utc) + timedelta(days=3)
        target_ist = target_ist.replace(hour=11, minute=0, second=0, microsecond=0)
        target_ist = _slide_to_polite_hours(target_ist)
        return CadenceDecision(
            next_attempt_at_utc=_to_utc(target_ist),
            is_terminal=True,
            attempt_number=next_attempt_idx + 1,
            reason="nurture_followup",
        )

    offset_min = NO_ANSWER_OFFSETS_MINUTES[next_attempt_idx]
    prev_ist = _to_ist(previous_attempt_utc)
    if offset_min is not None:
        candidate_ist = prev_ist + timedelta(minutes=offset_min)
    else:
        # Next-day morning (attempt 4) or evening (attempt 5)
        next_day = prev_ist + timedelta(days=1)
        if next_attempt_idx == 3:
            candidate_ist = next_day.replace(hour=11, minute=0, second=0, microsecond=0)
        else:  # attempt 5
            candidate_ist = next_day.replace(hour=19, minute=30, second=0, microsecond=0)

    candidate_ist = _slide_to_polite_hours(candidate_ist)
    return CadenceDecision(
        next_attempt_at_utc=_to_utc(candidate_ist),
        is_terminal=False,
        attempt_number=next_attempt_idx + 1,
        reason="no_answer_retry",
    )


def parent_requested_callback_at(
    when_utc: datetime, allow_sunday: bool = True
) -> datetime:
    """A parent-requested time honours the parent — only nudged to polite hours."""
    ist = _to_ist(when_utc)
    ist = _slide_to_polite_hours(ist, allow_sunday=allow_sunday)
    return _to_utc(ist)
