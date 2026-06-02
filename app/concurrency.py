"""Concurrent-call cap.

Cost control: we only want N simultaneous live Aria calls running at any
moment. Above N, new visitors are queued — their UI polls a slot endpoint
and auto-retries the trigger so they don't have to refresh.

Source of truth: Firestore `call_attempts` collection. A call is "active" if
its `status == "in-progress"` and it started within the freshness window
(stuck-call safety net — a crashed pod could leave a stale in-progress doc).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Final

from google.cloud import firestore as _fs

from app.crm.firestore_client import db

MAX_CONCURRENT_CALLS: Final[int] = 5
# Calls older than this are treated as dead (failsafe against orphaned docs).
ACTIVE_FRESHNESS_SECONDS: Final[int] = 15 * 60


async def active_call_count() -> int:
    """Return how many calls are currently considered live.

    Single-field query on `status` (auto-indexed). The freshness filter is
    applied client-side to avoid needing a composite index for this hot path
    on the trigger-call latency budget.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ACTIVE_FRESHNESS_SECONDS)
    n = 0
    async for snap in (
        db()
        .collection("call_attempts")
        .where(filter=_fs.FieldFilter("status", "==", "in-progress"))
        .limit(50)
        .stream()
    ):
        data = snap.to_dict() or {}
        started_at = data.get("started_at")
        if not started_at:
            n += 1
            continue
        try:
            dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            n += 1
            continue
        if dt >= cutoff:
            n += 1
    return n


async def slot_status() -> dict:
    """Snapshot used by the UI's slot-poller."""
    active = await active_call_count()
    return {
        "active": active,
        "capacity": MAX_CONCURRENT_CALLS,
        "slot_available": active < MAX_CONCURRENT_CALLS,
    }
