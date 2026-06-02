"""Firestore data-access layer.

Replaces the previous aiosqlite repository. Function names, signatures, and
returned-dict shapes match the old SQL implementation so call sites in
main.py, bot.py, vobiz_routes.py, callback_worker.py, and call_state.py
continue to work — except IDs are strings, not ints.

Collection design:
  parents/{phone}                            phone = doc ID (natural key)
    children/{child_id}                      subcollection
  courses/{code}                             code = doc ID
  demos/{id}                                 field: parent_phone (for queries)
  competitors/{id}
  call_attempts/{call_uuid}                  call_uuid = doc ID
    turns/{auto}                             subcollection
  callbacks/{id}                             indexed: status + scheduled_at
  objections/{id}                            indexed: call_attempt_id
  rate_limits/{phone}                        Phase 4 (visitor demo abuse limit)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from google.cloud import firestore as _fs

from app.crm.firestore_client import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _doc_with_id(snap, id_field: str = "id") -> dict[str, Any]:
    """Convert a DocumentSnapshot to a dict with its doc ID injected."""
    data = snap.to_dict() or {}
    data[id_field] = snap.id
    return data


# ── parents / children / demos ──────────────────────────────────────────────


async def get_parent_by_phone(phone: str) -> Optional[dict[str, Any]]:
    snap = await db().collection("parents").document(phone).get()
    if not snap.exists:
        return None
    return _doc_with_id(snap)


async def get_parent(parent_id: str) -> Optional[dict[str, Any]]:
    """parent_id IS the phone (we use phone as the doc ID)."""
    snap = await db().collection("parents").document(parent_id).get()
    if not snap.exists:
        return None
    return _doc_with_id(snap)


async def get_child(child_id: str) -> Optional[dict[str, Any]]:
    """Children live in subcollections, so we use a collection_group query
    on the unique `child_id` field stored on the doc."""
    q = db().collection_group("children").where(
        filter=_fs.FieldFilter("child_id", "==", child_id)
    ).limit(1)
    async for snap in q.stream():
        data = snap.to_dict() or {}
        data["id"] = snap.id
        # Reconstruct parent_id from the subcollection path: parents/{phone}/children/{id}
        parts = snap.reference.path.split("/")
        if len(parts) >= 2:
            data["parent_id"] = parts[1]
        return data
    return None


async def get_latest_demo_for_parent(parent_id: str) -> Optional[dict[str, Any]]:
    """Most-recent demo for this parent, joined with child+course fields.

    Returns dict with the SQL-join key shape that prompts.py expects:
      child_id, child_name, child_dob, grade, board, exam_target, exam_date,
      course_id, course_code, course_name, fee_amount, fee_spoken,
      batch_options, current_offer, offer_expires_at,
      payment_plan_available, scholarship_available,
      subject, teacher, weak_topic, attended_at, notes
    """
    fs = db()
    q = (
        fs.collection("demos")
        .where(filter=_fs.FieldFilter("parent_phone", "==", parent_id))
        .order_by("attended_at", direction=_fs.Query.DESCENDING)
        .limit(1)
    )
    demo_snap = None
    async for snap in q.stream():
        demo_snap = snap
        break
    if demo_snap is None:
        return None

    demo = demo_snap.to_dict() or {}
    demo["id"] = demo_snap.id

    # Hydrate child
    child_id = demo.get("child_id")
    if child_id:
        child = await get_child(child_id)
        if child:
            demo["child_id"] = child.get("child_id") or child_id
            demo["child_name"] = child.get("name")
            demo["child_dob"] = child.get("dob")
            demo["grade"] = child.get("grade")
            demo["board"] = child.get("board")
            demo["exam_target"] = child.get("exam_target")
            demo["exam_date"] = child.get("exam_date")

    # Hydrate course
    course_id = demo.get("course_id")
    if course_id:
        c_snap = await fs.collection("courses").document(course_id).get()
        if c_snap.exists:
            course = c_snap.to_dict() or {}
            demo["course_id"] = c_snap.id
            demo["course_code"] = c_snap.id  # we use code as doc id
            demo["course_name"] = course.get("name")
            demo["fee_amount"] = course.get("fee_amount")
            demo["fee_spoken"] = course.get("fee_spoken")
            demo["batch_options"] = course.get("batch_options")
            demo["current_offer"] = course.get("current_offer")
            demo["offer_expires_at"] = course.get("offer_expires_at")
            demo["payment_plan_available"] = course.get("payment_plan_available", 1)
            demo["scholarship_available"] = course.get("scholarship_available", 0)

    return demo


# ── battle card ─────────────────────────────────────────────────────────────


async def get_competitor_battlecard() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    async for snap in db().collection("competitors").order_by("name").stream():
        d = snap.to_dict() or {}
        d["id"] = snap.id
        out.append(d)
    return out


# ── call attempts + turns ───────────────────────────────────────────────────


async def create_call_attempt(
    parent_id: str, demo_id: str | None, twilio_call_sid: str | None
) -> str:
    """Returns the attempt_id. We use call_uuid (twilio_call_sid) as the doc ID
    when available so /vobiz/answer can find the attempt by its UUID."""
    attempt_id = twilio_call_sid or uuid.uuid4().hex
    doc = db().collection("call_attempts").document(attempt_id)
    await doc.set(
        {
            "parent_id": parent_id,
            "demo_id": demo_id,
            "twilio_call_sid": twilio_call_sid,
            "status": "queued",
            "started_at": _now_iso(),
            "ended_at": None,
            "duration_seconds": None,
        }
    )
    return attempt_id


async def update_call_attempt_status(
    attempt_id: str,
    status: str,
    duration_seconds: int | None = None,
    twilio_call_sid: str | None = None,
) -> None:
    update: dict[str, Any] = {"status": status}
    if duration_seconds is not None:
        update["duration_seconds"] = duration_seconds
    if twilio_call_sid is not None:
        update["twilio_call_sid"] = twilio_call_sid
    if status in {"completed", "no-answer", "busy", "failed", "canceled"}:
        update["ended_at"] = _now_iso()
    await db().collection("call_attempts").document(attempt_id).set(update, merge=True)


async def get_call_attempt_by_sid(sid: str) -> Optional[dict[str, Any]]:
    """We store call_attempts keyed by call_uuid (sid), so this is a direct get.
    Falls back to a field query if the doc isn't found by ID (for legacy rows)."""
    snap = await db().collection("call_attempts").document(sid).get()
    if snap.exists:
        return _doc_with_id(snap)
    q = (
        db()
        .collection("call_attempts")
        .where(filter=_fs.FieldFilter("twilio_call_sid", "==", sid))
        .limit(1)
    )
    async for s in q.stream():
        return _doc_with_id(s)
    return None


async def record_turn(
    call_attempt_id: str, event: dict[str, Any], *, is_final: bool = False
) -> str:
    turn = {
        "ts": _now_iso(),
        "call_attempt_id": call_attempt_id,
        "utterance": event.get("utterance"),
        "intent_classification": event.get("intent_classification"),
        "intent_confidence": event.get("intent_confidence"),
        "objection_primary": event.get("objection_primary"),
        "objection_secondary": event.get("objection_secondary"),
        "objection_verbatim": event.get("objection_verbatim"),
        "strategy_applied": event.get("strategy_applied"),
        "sentiment": event.get("sentiment"),
        "tone": event.get("tone"),
        "is_final": bool(is_final),
        "next_step": event.get("next_step"),
        "next_step_label": event.get("next_step_label"),
        "next_step_time": event.get("next_step_time"),
        "counselor_notes": event.get("counselor_notes"),
    }
    ref = db().collection("call_attempts").document(call_attempt_id).collection("turns")
    _, doc = await ref.add(turn)
    return doc.id


async def finalise_objection(
    call_attempt_id: str, parent_id: str, event: dict[str, Any]
) -> str:
    row = {
        "call_attempt_id": call_attempt_id,
        "parent_id": parent_id,
        "objection_primary": event.get("objection_primary"),
        "objection_secondary": event.get("objection_secondary"),
        "objection_verbatim": event.get("objection_verbatim"),
        "intent_final": event.get("intent_classification"),
        "sentiment_start": event.get("sentiment_start"),
        "sentiment_end": event.get("sentiment_end") or event.get("sentiment"),
        "next_step": event.get("next_step"),
        "next_step_time": event.get("next_step_time"),
        "counselor_notes": event.get("counselor_notes"),
        "recorded_at": _now_iso(),
    }
    _, doc = await db().collection("objections").add(row)
    return doc.id


# ── callbacks ──────────────────────────────────────────────────────────────


async def schedule_callback(
    parent_id: str,
    demo_id: str | None,
    scheduled_at: datetime,
    reason: str,
    notes: str | None = None,
) -> str:
    row = {
        "parent_id": parent_id,
        "demo_id": demo_id,
        "scheduled_at": scheduled_at.isoformat(),
        "reason": reason,
        "notes": notes,
        "attempts_so_far": 0,
        "status": "pending",
        "created_at": _now_iso(),
    }
    _, doc = await db().collection("callbacks").add(row)
    return doc.id


async def get_due_callbacks(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    q = (
        db()
        .collection("callbacks")
        .where(filter=_fs.FieldFilter("status", "==", "pending"))
        .where(filter=_fs.FieldFilter("scheduled_at", "<=", now.isoformat()))
        .order_by("scheduled_at")
    )
    out: list[dict[str, Any]] = []
    async for snap in q.stream():
        out.append(_doc_with_id(snap))
    return out


async def get_pending_callbacks_for_parent(parent_id: str) -> list[dict[str, Any]]:
    q = (
        db()
        .collection("callbacks")
        .where(filter=_fs.FieldFilter("parent_id", "==", parent_id))
        .where(filter=_fs.FieldFilter("status", "==", "pending"))
        .order_by("scheduled_at")
    )
    out: list[dict[str, Any]] = []
    async for snap in q.stream():
        out.append(_doc_with_id(snap))
    return out


async def mark_callback(callback_id: str, status: str) -> None:
    await db().collection("callbacks").document(callback_id).set(
        {"status": status}, merge=True
    )


async def increment_callback_attempts(callback_id: str) -> None:
    await db().collection("callbacks").document(callback_id).update(
        {"attempts_so_far": _fs.Increment(1)}
    )


# ── helpers ────────────────────────────────────────────────────────────────


def days_until_birthday(dob_iso: str | None, today: date | None = None) -> int | None:
    """Days until the child's next birthday. None if no DoB. Pure function."""
    if not dob_iso:
        return None
    today = today or date.today()
    try:
        dob = date.fromisoformat(dob_iso)
    except ValueError:
        return None
    this_year = dob.replace(year=today.year)
    if this_year < today:
        this_year = dob.replace(year=today.year + 1)
    return (this_year - today).days


# ── rate limiting (Phase 4) ─────────────────────────────────────────────────


async def get_rate_limit(phone: str) -> dict[str, Any]:
    """Return the per-phone event log. {events: [iso, ...], first_at, last_at, count}."""
    snap = await db().collection("rate_limits").document(phone).get()
    if not snap.exists:
        return {"events": [], "count": 0, "first_at": None, "last_at": None}
    data = snap.to_dict() or {}
    events = data.get("events") or []
    return {
        "events": events,
        "count": len(events),
        "first_at": data.get("first_at"),
        "last_at": data.get("last_at"),
    }


async def append_rate_event(phone: str, now_iso: str) -> list[str]:
    """Atomically append a new event, pruning entries older than 24h.

    Returns the pruned-and-appended event list (ISO timestamps).
    """
    ref = db().collection("rate_limits").document(phone)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    @_fs.async_transactional
    async def _tx(tx, ref):
        snap = await ref.get(transaction=tx)
        data = snap.to_dict() if snap.exists else {}
        events = list(data.get("events") or [])
        kept: list[str] = []
        for ev in events:
            try:
                dt = datetime.fromisoformat(ev.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue
            if dt >= cutoff:
                kept.append(ev)
        kept.append(now_iso)
        first_at = data.get("first_at") or now_iso
        tx.set(
            ref,
            {"events": kept, "first_at": first_at, "last_at": now_iso},
            merge=True,
        )
        return kept

    return await _tx(db().transaction(), ref)
