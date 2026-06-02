"""log_call_state + schedule_callback_request handlers."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.crm import repository
from app.crm.seeds import seed
from app.pipecat_bot.call_state import (
    CallContext,
    handle_log_call_state,
    handle_schedule_callback_request,
)


@pytest.mark.asyncio
async def test_log_call_state_records_turn(fresh_db):
    await seed()
    p = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(p["id"])
    aid = await repository.create_call_attempt(p["id"], demo["id"], "CA-1")
    ctx = CallContext(call_attempt_id=aid, parent_id=p["id"], demo_id=demo["id"])

    turn = {
        "utterance": "Sach kahun toh fees zyada lag rahi hai",
        "intent_classification": "soft_no",
        "intent_confidence": 0.82,
        "sentiment": "cold",
        "objection_primary": "price",
        "objection_verbatim": "fees zyada lag rahi hai",
        "strategy_applied": "value_roi_reframe",
    }
    out = await handle_log_call_state(ctx, turn)
    assert out["ok"]
    assert out["objection_cycles"] == 1
    assert ctx.sentiment_start == "cold"


@pytest.mark.asyncio
async def test_log_call_state_finalises_and_completes(fresh_db):
    await seed()
    p = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(p["id"])
    aid = await repository.create_call_attempt(p["id"], demo["id"], "CA-2")
    await repository.update_call_attempt_status(aid, "in-progress")
    ctx = CallContext(call_attempt_id=aid, parent_id=p["id"], demo_id=demo["id"])

    await handle_log_call_state(ctx, {
        "utterance": "Hmm",
        "intent_classification": "ambiguous",
        "intent_confidence": 0.5,
        "sentiment": "neutral",
        "objection_primary": "stalling",
        "strategy_applied": "disambiguation_probe",
    })
    await handle_log_call_state(ctx, {
        "utterance": "Theek hai book kar do",
        "intent_classification": "positive",
        "intent_confidence": 0.9,
        "sentiment": "warm",
        "objection_primary": "none",
        "objection_verbatim": "fees zyada lag rahi hai",
        "strategy_applied": "second_session_offer",
        "final": True,
        "next_step": "second_session_booked",
        "next_step_label": "Second session booked",
        "next_step_time": "2026-06-02T18:00:00+05:30",
        "counselor_notes": "Booked second session.",
    })

    attempt = await repository.get_call_attempt_by_sid("CA-2")
    assert attempt["status"] == "completed"


@pytest.mark.asyncio
async def test_schedule_callback_request_persists(fresh_db):
    await seed()
    p = await repository.get_parent_by_phone("+919999900002")
    demo = await repository.get_latest_demo_for_parent(p["id"])
    aid = await repository.create_call_attempt(p["id"], demo["id"], "CA-3")
    ctx = CallContext(call_attempt_id=aid, parent_id=p["id"], demo_id=demo["id"])

    # Parent wants a call at 19:00 IST tomorrow
    when_ist = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0).isoformat() + "+05:30"
    out = await handle_schedule_callback_request(
        ctx, {"when_iso": when_ist, "reason": "parent_requested"}
    )
    assert out["ok"]
    pending = await repository.get_pending_callbacks_for_parent(p["id"])
    assert len(pending) == 1
    assert pending[0]["reason"] == "parent_requested"


@pytest.mark.asyncio
async def test_schedule_callback_rejects_bad_iso(fresh_db):
    await seed()
    p = await repository.get_parent_by_phone("+919999900002")
    ctx = CallContext(call_attempt_id=1, parent_id=p["id"], demo_id=None)
    out = await handle_schedule_callback_request(ctx, {"when_iso": "not-a-date", "reason": "parent_requested"})
    assert not out["ok"]
