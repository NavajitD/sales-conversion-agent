"""Dashboard REST API — serves the CRM panel (Firestore-backed).

All endpoints are read-only (GET) except /trigger-call. The previous SQL
implementation lives at legacy/sqlite_impl/dashboard_api.py for reference.

Design notes:
  - Firestore can't JOIN, so we read parent docs and hydrate latest call /
    callback per parent in parallel. Fine for the demo (<200 parents).
  - Aggregations are computed client-side: pull recent docs, group in Python.
    If volume grows beyond a few thousand calls, precompute aggregate docs.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from google.cloud import firestore as _fs

from app import rate_limit
from app.crm.firestore_client import db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ── helpers ────────────────────────────────────────────────────────────────


async def _latest_attempt_for_parent(parent_id: str) -> dict[str, Any] | None:
    q = (
        db()
        .collection("call_attempts")
        .where(filter=_fs.FieldFilter("parent_id", "==", parent_id))
        .order_by("started_at", direction=_fs.Query.DESCENDING)
        .limit(1)
    )
    async for s in q.stream():
        d = s.to_dict() or {}
        d["id"] = s.id
        return d
    return None


async def _latest_objection_for_attempt(attempt_id: str) -> dict[str, Any] | None:
    q = (
        db()
        .collection("objections")
        .where(filter=_fs.FieldFilter("call_attempt_id", "==", attempt_id))
        .order_by("recorded_at", direction=_fs.Query.DESCENDING)
        .limit(1)
    )
    async for s in q.stream():
        d = s.to_dict() or {}
        d["id"] = s.id
        return d
    return None


async def _next_pending_callback(parent_id: str) -> dict[str, Any] | None:
    q = (
        db()
        .collection("callbacks")
        .where(filter=_fs.FieldFilter("parent_id", "==", parent_id))
        .where(filter=_fs.FieldFilter("status", "==", "pending"))
        .order_by("scheduled_at")
        .limit(1)
    )
    async for s in q.stream():
        d = s.to_dict() or {}
        d["id"] = s.id
        return d
    return None


async def _first_child_for_parent(parent_id: str) -> dict[str, Any] | None:
    q = (
        db()
        .collection("parents")
        .document(parent_id)
        .collection("children")
        .limit(1)
    )
    async for s in q.stream():
        d = s.to_dict() or {}
        d["id"] = s.id
        return d
    return None


# ── endpoints ──────────────────────────────────────────────────────────────


@router.get("/parents")
async def list_parents():
    """All parents with latest call outcome + first child + next pending callback."""
    parents: list[dict[str, Any]] = []
    async for snap in db().collection("parents").stream():
        p = snap.to_dict() or {}
        p["id"] = snap.id
        parents.append(p)

    async def hydrate(p: dict[str, Any]) -> dict[str, Any]:
        pid = p["id"]
        child, attempt, callback = await asyncio.gather(
            _first_child_for_parent(pid),
            _latest_attempt_for_parent(pid),
            _next_pending_callback(pid),
        )
        objection = (
            await _latest_objection_for_attempt(attempt["id"]) if attempt else None
        )
        return {
            **p,
            "child_name": child.get("name") if child else None,
            "grade": child.get("grade") if child else None,
            "exam_target": child.get("exam_target") if child else None,
            "last_call_status": attempt.get("status") if attempt else None,
            "last_call_at": attempt.get("started_at") if attempt else None,
            "last_call_duration": attempt.get("duration_seconds") if attempt else None,
            "next_step": objection.get("next_step") if objection else None,
            "sentiment_end": objection.get("sentiment_end") if objection else None,
            "next_callback_at": callback.get("scheduled_at") if callback else None,
            "callback_reason": callback.get("reason") if callback else None,
        }

    hydrated = await asyncio.gather(*(hydrate(p) for p in parents))
    return {"parents": hydrated}


@router.get("/personas")
async def list_personas():
    """Lightweight persona list for the public demo picker.

    The picker only needs name/city + the child's name/grade/exam_target, so we
    skip the expensive per-parent call/objection/callback hydration that
    `/parents` does (4 Firestore queries each, several of them composite-index
    `order_by` reads). This is just one `first_child` read per parent, which
    keeps the picker snappy even on a cold container.
    """
    parents: list[dict[str, Any]] = []
    async for snap in db().collection("parents").stream():
        p = snap.to_dict() or {}
        p["id"] = snap.id
        parents.append(p)

    async def slim(p: dict[str, Any]) -> dict[str, Any]:
        child = await _first_child_for_parent(p["id"])
        return {
            "id": p["id"],
            "name": p.get("name"),
            "city": p.get("city"),
            "child_name": child.get("name") if child else None,
            "grade": child.get("grade") if child else None,
            "exam_target": child.get("exam_target") if child else None,
        }

    personas = await asyncio.gather(*(slim(p) for p in parents))
    return {"parents": personas}


@router.get("/calls")
async def list_calls():
    """Last 100 call attempts with parent name + latest objection."""
    q = (
        db()
        .collection("call_attempts")
        .order_by("started_at", direction=_fs.Query.DESCENDING)
        .limit(100)
    )
    attempts: list[dict[str, Any]] = []
    async for s in q.stream():
        a = s.to_dict() or {}
        a["id"] = s.id
        attempts.append(a)

    async def hydrate(a: dict[str, Any]) -> dict[str, Any]:
        pid = a.get("parent_id")
        parent_task = (
            db().collection("parents").document(pid).get() if pid else None
        )
        obj = await _latest_objection_for_attempt(a["id"])
        parent_snap = await parent_task if parent_task else None
        parent = (parent_snap.to_dict() or {}) if parent_snap and parent_snap.exists else {}
        return {
            **a,
            "parent_name": parent.get("name"),
            "phone": parent.get("phone"),
            "objection_primary": obj.get("objection_primary") if obj else None,
            "next_step": obj.get("next_step") if obj else None,
            "sentiment_end": obj.get("sentiment_end") if obj else None,
            "intent_final": obj.get("intent_final") if obj else None,
        }

    hydrated = await asyncio.gather(*(hydrate(a) for a in attempts))
    return {"calls": hydrated}


@router.get("/calls/{attempt_id}/turns")
async def get_call_turns(attempt_id: str):
    """Turn-by-turn detail for a single call (ordered by ts)."""
    q = (
        db()
        .collection("call_attempts")
        .document(attempt_id)
        .collection("turns")
        .order_by("ts")
    )
    rows: list[dict[str, Any]] = []
    async for s in q.stream():
        d = s.to_dict() or {}
        d["id"] = s.id
        rows.append(d)
    return {"turns": rows}


@router.get("/callbacks")
async def list_callbacks():
    """Pending and recent callbacks, pending first."""
    pending: list[dict[str, Any]] = []
    async for s in (
        db()
        .collection("callbacks")
        .where(filter=_fs.FieldFilter("status", "==", "pending"))
        .order_by("scheduled_at")
        .limit(50)
        .stream()
    ):
        d = s.to_dict() or {}
        d["id"] = s.id
        pending.append(d)

    # Fetch a tail of non-pending callbacks by reading recent rows unfiltered
    # and filtering client-side. Firestore's `!=` filter requires a composite
    # index path that we don't want to maintain for this low-volume listing.
    other: list[dict[str, Any]] = []
    if len(pending) < 50:
        room = 50 - len(pending)
        async for s in (
            db()
            .collection("callbacks")
            .order_by("scheduled_at", direction=_fs.Query.DESCENDING)
            .limit(room * 3)
            .stream()
        ):
            d = s.to_dict() or {}
            if d.get("status") == "pending":
                continue
            d["id"] = s.id
            other.append(d)
            if len(other) >= room:
                break

    async def attach_parent(cb: dict[str, Any]) -> dict[str, Any]:
        pid = cb.get("parent_id")
        if not pid:
            return cb
        snap = await db().collection("parents").document(pid).get()
        if not snap.exists:
            return cb
        p = snap.to_dict() or {}
        return {**cb, "parent_name": p.get("name"), "phone": p.get("phone")}

    rows = await asyncio.gather(*(attach_parent(cb) for cb in pending + other))
    return {"callbacks": rows}


@router.get("/analytics")
async def analytics():
    """Aggregate stats. Client-side rollup over recent docs."""
    # Pull recent slices
    attempts: list[dict[str, Any]] = []
    async for s in (
        db()
        .collection("call_attempts")
        .order_by("started_at", direction=_fs.Query.DESCENDING)
        .limit(500)
        .stream()
    ):
        d = s.to_dict() or {}
        d["id"] = s.id
        attempts.append(d)

    objections: list[dict[str, Any]] = []
    async for s in (
        db()
        .collection("objections")
        .order_by("recorded_at", direction=_fs.Query.DESCENDING)
        .limit(500)
        .stream()
    ):
        objections.append(s.to_dict() or {})

    # Turns: collection_group across all attempts. We avoid order_by on the
    # collection_group query (which would require a global single-field index
    # exemption that may not have propagated yet). For low-volume demos the
    # unordered scan + client-side sort is fine; revisit if turns count > 10k.
    turns: list[dict[str, Any]] = []
    async for s in (
        db().collection_group("turns").limit(2000).stream()
    ):
        turns.append(s.to_dict() or {})
    turns.sort(key=lambda t: t.get("ts") or "", reverse=True)
    turns = turns[:1000]

    total_calls = len(attempts)
    completed_attempts = [a for a in attempts if a.get("status") == "completed"]
    completed = len(completed_attempts)

    outcomes_counter = Counter(o.get("next_step") for o in objections if o.get("next_step"))
    outcomes = [{"next_step": k, "n": v} for k, v in outcomes_counter.most_common()]

    top_objections_counter = Counter(
        t.get("objection_primary") for t in turns if t.get("objection_primary")
    )
    top_objections = [
        {"objection_primary": k, "n": v}
        for k, v in top_objections_counter.most_common(10)
    ]

    top_strategies_counter = Counter(
        t.get("strategy_applied")
        for t in turns
        if t.get("strategy_applied") and t.get("strategy_applied") != "none"
    )
    top_strategies = [
        {"strategy_applied": k, "n": v}
        for k, v in top_strategies_counter.most_common(10)
    ]

    durations = [
        a["duration_seconds"]
        for a in attempts
        if a.get("duration_seconds") and a["duration_seconds"] > 0
    ]
    avg_duration = sum(durations) / len(durations) if durations else 0

    sentiment_trend = [
        {
            "id": a["id"],
            "started_at": a.get("started_at"),
            "sentiment_end": next(
                (o.get("sentiment_end") for o in objections if o.get("call_attempt_id") == a["id"]),
                None,
            ),
        }
        for a in completed_attempts[:20]
    ]

    intent_counter = Counter(
        t.get("intent_classification") for t in turns if t.get("intent_classification")
    )
    intent_breakdown = [
        {"intent_classification": k, "n": v} for k, v in intent_counter.most_common()
    ]

    rejection_counter: Counter = Counter()
    for t in turns:
        intent = t.get("intent_classification")
        obj = t.get("objection_primary")
        if intent in ("hard_no", "soft_no") and obj:
            rejection_counter[(obj, intent)] += 1
    rejection_reasons = [
        {"objection_primary": obj, "intent_classification": intent, "n": n}
        for (obj, intent), n in rejection_counter.most_common(15)
    ]

    final_sentiments_counter = Counter(
        t.get("sentiment") for t in turns if t.get("is_final") and t.get("sentiment")
    )
    final_sentiments = [
        {"sentiment": k, "n": v} for k, v in final_sentiments_counter.most_common()
    ]

    # Agent confidence: mean intent_confidence across turns where the LLM
    # classified soft_no or hard_no (the high-stakes buckets) — this is the
    # "confidence rate of identifying between Soft and Hard No, and objection
    # reason" number surfaced in the demo + CRM page.
    classifying_confidences = [
        float(t.get("intent_confidence") or 0)
        for t in turns
        if t.get("intent_classification") in ("hard_no", "soft_no") and t.get("intent_confidence")
    ]
    avg_intent_confidence = (
        round(sum(classifying_confidences) / len(classifying_confidences), 3)
        if classifying_confidences else 0.0
    )

    # Yes / Soft No / Hard No bucket counts for the CRM pie chart.
    sentiment_buckets = {"yes": 0, "soft_no": 0, "hard_no": 0, "other": 0}
    for t in turns:
        intent = t.get("intent_classification") or ""
        if intent == "hard_no" or intent == "no_interest":
            sentiment_buckets["hard_no"] += 1
        elif intent == "soft_no" or intent.startswith("objection"):
            sentiment_buckets["soft_no"] += 1
        elif intent in ("positive", "enrolled", "second_session", "callback"):
            sentiment_buckets["yes"] += 1
        elif intent:
            sentiment_buckets["other"] += 1

    # Strategy → conversion-rate: % of calls where this strategy appeared
    # AND the call's final next_step is 'enrolled'. Approximate (we don't
    # have per-call strategy lineage in finalised objections), so we compute
    # share-of-strategy-among-enrolled vs total-strategy-applications.
    strategy_attempts: Counter = Counter()
    strategy_wins: Counter = Counter()
    enrolled_attempt_ids: set[str] = set()
    for o in objections:
        if o.get("next_step") == "enrolled" and o.get("call_attempt_id"):
            enrolled_attempt_ids.add(o["call_attempt_id"])
    for t in turns:
        s = t.get("strategy_applied")
        if not s or s == "none":
            continue
        strategy_attempts[s] += 1
        # turns are denormalised inside call_attempts/{id}/turns, so we don't
        # have the parent attempt id easily — but the Firestore doc path keeps
        # it. We stuffed `call_attempt_id` into the doc when recording. Read it
        # if present.
        att_id = t.get("call_attempt_id")
        if att_id and att_id in enrolled_attempt_ids:
            strategy_wins[s] += 1
    top_strategies_with_rate = [
        {
            "strategy_applied": s,
            "n": n,
            "conversion_rate": round(strategy_wins.get(s, 0) / n * 100, 1) if n else 0.0,
            "wins": strategy_wins.get(s, 0),
        }
        for s, n in strategy_attempts.most_common(10)
    ]

    conversion_rate = (
        round(
            len([o for o in outcomes if o["next_step"] == "enrolled"])
            / max(completed, 1)
            * 100,
            1,
        )
        if outcomes
        else 0.0
    )

    return {
        "total_calls": total_calls,
        "completed_calls": completed,
        "conversion_rate": conversion_rate,
        "avg_duration_seconds": round(avg_duration, 0),
        "outcomes": outcomes,
        "top_objections": top_objections,
        "top_strategies": top_strategies,
        "sentiment_trend": sentiment_trend,
        "intent_breakdown": intent_breakdown,
        "rejection_reasons": rejection_reasons,
        "final_sentiments": final_sentiments,
        "avg_intent_confidence": avg_intent_confidence,
        "sentiment_buckets": sentiment_buckets,
        "top_strategies_with_rate": top_strategies_with_rate,
    }


@router.get("/live")
async def live_status():
    """Currently active calls (status='in-progress', started within last 10 min)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    q = (
        db()
        .collection("call_attempts")
        .where(filter=_fs.FieldFilter("status", "==", "in-progress"))
        .where(filter=_fs.FieldFilter("started_at", ">", cutoff))
        .order_by("started_at", direction=_fs.Query.DESCENDING)
    )
    attempts: list[dict[str, Any]] = []
    async for s in q.stream():
        d = s.to_dict() or {}
        d["id"] = s.id
        attempts.append(d)

    async def attach_parent(a: dict[str, Any]) -> dict[str, Any]:
        pid = a.get("parent_id")
        if not pid:
            return a
        snap = await db().collection("parents").document(pid).get()
        if not snap.exists:
            return a
        p = snap.to_dict() or {}
        return {**a, "parent_name": p.get("name"), "phone": p.get("phone")}

    rows = await asyncio.gather(*(attach_parent(a) for a in attempts))
    return {"active_calls": rows}


@router.get("/rate_limit/{phone}")
async def get_rate_limit_status(phone: str):
    """Read-only counter for the public demo UI. Returns 'remaining' so the
    UI can show 'X of 3 demos left' and disable the call button at 0."""
    return await rate_limit.status_for(phone)


@router.get("/slot")
async def get_slot_status():
    """How many concurrent calls are running + whether a slot is free.

    The UI uses this to render a wait state when all 5 slots are taken and
    auto-retry the trigger-call as soon as `slot_available` flips to true.
    """
    from app.concurrency import slot_status
    return await slot_status()


@router.post("/trigger-call")
async def trigger_call_from_dashboard(body: dict | None = None):
    """Public-demo entry point.

    Body: {visitor_phone: "+91...", persona_id: "+919999900001"}
      visitor_phone — the phone Aria should call (where you hear the agent)
      persona_id    — the seeded parent context the agent uses (Sharma+Aarav etc.)

    Backwards-compat:
      {parent_id} or {phone} also accepted (legacy alpha-test path).

    Rate-limit: 3 lifetime calls per visitor_phone, except whitelisted numbers.
    Returns 429 with a structured error when the limit is exhausted.
    """
    from app.config import DEMO_PHONE_NUMBER
    from app.crm import repository
    from app.telephony.outbound import place_call

    body = body or {}
    visitor_phone = body.get("visitor_phone") or body.get("phone")
    persona_id = body.get("persona_id") or body.get("parent_id")

    # If nothing supplied, fall back to DEMO_PHONE_NUMBER (alpha path)
    if not visitor_phone and not persona_id:
        if not DEMO_PHONE_NUMBER:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": "no visitor_phone or persona_id supplied"},
            )
        visitor_phone = DEMO_PHONE_NUMBER

    # Resolve persona (the CRM context the agent acts on)
    if persona_id:
        persona = await repository.get_parent(persona_id)
    else:
        # Bare-phone case: caller is a known persona (legacy alpha path)
        persona = await repository.get_parent_by_phone(visitor_phone)
    if not persona:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": f"persona not found: {persona_id or visitor_phone}"},
        )

    # If no separate visitor_phone, the call goes to the persona's phone.
    target_phone = visitor_phone or persona.get("phone") or DEMO_PHONE_NUMBER
    if not target_phone:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "no target phone resolved"},
        )

    # Concurrent-call cap: bail BEFORE consuming a rate-limit slot so the
    # visitor doesn't lose a try when the issue is server capacity, not their
    # quota. The UI watches /api/dashboard/slot and auto-retries when a seat
    # opens.
    from app.concurrency import slot_status as _slot_status
    slot = await _slot_status()
    if not slot["slot_available"]:
        return JSONResponse(
            status_code=503,
            content={
                "ok": False,
                "error": "capacity_full",
                "message": (
                    f"All {slot['capacity']} demo seats are busy. We'll start "
                    "your call automatically as soon as one frees up."
                ),
                "slot": slot,
            },
        )

    # Rate-limit on the destination phone (the visitor's number).
    allowed, status = await rate_limit.try_increment(target_phone)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "error": "rate_limit_exceeded",
                "message": (
                    "You've hit the demo limit for this number "
                    "(5/hour or 25/day). Please try again later."
                ),
                "rate_limit": status,
            },
        )

    demo = await repository.get_latest_demo_for_parent(persona["id"])
    try:
        out = await place_call(target_phone, persona["id"], demo["id"] if demo else None)
    except Exception as e:
        # Increment already happened — accept the wasted slot rather than
        # trying to roll back (Firestore counters aren't trivially decrementable).
        return JSONResponse(
            status_code=502,
            content={
                "ok": False,
                "error": "place_call_failed",
                "detail": str(e)[:300],
                "rate_limit": status,
            },
        )
    return {"ok": True, "rate_limit": status, **out}
