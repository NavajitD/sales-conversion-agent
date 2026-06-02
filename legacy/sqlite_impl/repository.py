"""Data-access layer on top of aiosqlite. All functions are async."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

import aiosqlite

from app.crm.db import connect


# ── parents / children / demos ──────────────────────────────────────────────


async def get_parent_by_phone(phone: str) -> Optional[dict[str, Any]]:
    async with connect() as db:
        cur = await db.execute("SELECT * FROM parents WHERE phone = ?", (phone,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_parent(parent_id: int) -> Optional[dict[str, Any]]:
    async with connect() as db:
        cur = await db.execute("SELECT * FROM parents WHERE id = ?", (parent_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_child(child_id: int) -> Optional[dict[str, Any]]:
    async with connect() as db:
        cur = await db.execute("SELECT * FROM children WHERE id = ?", (child_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_latest_demo_for_parent(parent_id: int) -> Optional[dict[str, Any]]:
    """Most-recent demo by any child of this parent (joined with child+course)."""
    sql = """
    SELECT d.*,
           c.id AS child_id, c.name AS child_name, c.dob AS child_dob,
           c.grade, c.board, c.exam_target, c.exam_date,
           co.id AS course_id, co.code AS course_code, co.name AS course_name,
           co.fee_amount, co.fee_spoken, co.batch_options, co.current_offer,
           co.offer_expires_at, co.payment_plan_available, co.scholarship_available
      FROM demos d
      JOIN children c ON d.child_id = c.id
      JOIN courses co ON d.course_id = co.id
     WHERE c.parent_id = ?
     ORDER BY d.attended_at DESC
     LIMIT 1
    """
    async with connect() as db:
        cur = await db.execute(sql, (parent_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


# ── battle card ─────────────────────────────────────────────────────────────


async def get_competitor_battlecard() -> list[dict[str, Any]]:
    async with connect() as db:
        cur = await db.execute("SELECT * FROM competitors ORDER BY name, axis")
        return [dict(r) for r in await cur.fetchall()]


# ── call attempts + turns ───────────────────────────────────────────────────


async def create_call_attempt(
    parent_id: int, demo_id: int | None, twilio_call_sid: str | None
) -> int:
    async with connect() as db:
        cur = await db.execute(
            "INSERT INTO call_attempts (parent_id, demo_id, twilio_call_sid, status) "
            "VALUES (?, ?, ?, 'queued')",
            (parent_id, demo_id, twilio_call_sid),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def update_call_attempt_status(
    attempt_id: int,
    status: str,
    duration_seconds: int | None = None,
    twilio_call_sid: str | None = None,
) -> None:
    fields = ["status = ?"]
    params: list[Any] = [status]
    if duration_seconds is not None:
        fields.append("duration_seconds = ?")
        params.append(duration_seconds)
    if twilio_call_sid is not None:
        fields.append("twilio_call_sid = ?")
        params.append(twilio_call_sid)
    if status in {"completed", "no-answer", "busy", "failed", "canceled"}:
        fields.append("ended_at = datetime('now')")
    params.append(attempt_id)
    async with connect() as db:
        await db.execute(
            f"UPDATE call_attempts SET {', '.join(fields)} WHERE id = ?", params
        )
        await db.commit()


async def get_call_attempt_by_sid(sid: str) -> Optional[dict[str, Any]]:
    async with connect() as db:
        cur = await db.execute(
            "SELECT * FROM call_attempts WHERE twilio_call_sid = ?", (sid,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def record_turn(call_attempt_id: int, event: dict[str, Any], *, is_final: bool = False) -> int:
    sql = """
    INSERT INTO call_turns (
      call_attempt_id, utterance, intent_classification, intent_confidence,
      objection_primary, objection_secondary, objection_verbatim,
      strategy_applied, sentiment, is_final,
      next_step, next_step_label, next_step_time, counselor_notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    async with connect() as db:
        cur = await db.execute(
            sql,
            (
                call_attempt_id,
                event.get("utterance"),
                event.get("intent_classification"),
                event.get("intent_confidence"),
                event.get("objection_primary"),
                event.get("objection_secondary"),
                event.get("objection_verbatim"),
                event.get("strategy_applied"),
                event.get("sentiment"),
                1 if is_final else 0,
                event.get("next_step"),
                event.get("next_step_label"),
                event.get("next_step_time"),
                event.get("counselor_notes"),
            ),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def finalise_objection(
    call_attempt_id: int, parent_id: int, event: dict[str, Any]
) -> int:
    sql = """
    INSERT INTO objections (
      call_attempt_id, parent_id, objection_primary, objection_secondary,
      objection_verbatim, intent_final, sentiment_start, sentiment_end,
      next_step, next_step_time, counselor_notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    async with connect() as db:
        cur = await db.execute(
            sql,
            (
                call_attempt_id,
                parent_id,
                event.get("objection_primary"),
                event.get("objection_secondary"),
                event.get("objection_verbatim"),
                event.get("intent_classification"),
                event.get("sentiment_start"),
                event.get("sentiment_end") or event.get("sentiment"),
                event.get("next_step"),
                event.get("next_step_time"),
                event.get("counselor_notes"),
            ),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


# ── callbacks ──────────────────────────────────────────────────────────────


async def schedule_callback(
    parent_id: int,
    demo_id: int | None,
    scheduled_at: datetime,
    reason: str,
    notes: str | None = None,
) -> int:
    async with connect() as db:
        cur = await db.execute(
            "INSERT INTO callbacks (parent_id, demo_id, scheduled_at, reason, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (parent_id, demo_id, scheduled_at.isoformat(), reason, notes),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_due_callbacks(now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.utcnow()
    async with connect() as db:
        cur = await db.execute(
            "SELECT * FROM callbacks WHERE status = 'pending' AND scheduled_at <= ? "
            "ORDER BY scheduled_at ASC",
            (now.isoformat(),),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_pending_callbacks_for_parent(parent_id: int) -> list[dict[str, Any]]:
    async with connect() as db:
        cur = await db.execute(
            "SELECT * FROM callbacks WHERE parent_id = ? AND status = 'pending' "
            "ORDER BY scheduled_at ASC",
            (parent_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def mark_callback(callback_id: int, status: str) -> None:
    async with connect() as db:
        await db.execute(
            "UPDATE callbacks SET status = ? WHERE id = ?", (status, callback_id)
        )
        await db.commit()


async def increment_callback_attempts(callback_id: int) -> None:
    async with connect() as db:
        await db.execute(
            "UPDATE callbacks SET attempts_so_far = attempts_so_far + 1 WHERE id = ?",
            (callback_id,),
        )
        await db.commit()


# ── helpers ────────────────────────────────────────────────────────────────


def days_until_birthday(dob_iso: str | None, today: date | None = None) -> int | None:
    """How many days until the child's next birthday. None if no DoB."""
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
