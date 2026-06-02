"""Repository smoke tests + birthday helper."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.crm import repository
from app.crm.seeds import seed


@pytest.mark.asyncio
async def test_seed_idempotent(fresh_db):
    c1 = await seed()
    c2 = await seed()  # second run should be a no-op
    assert c1["parents"] >= 5
    assert c1["courses"] >= 5
    assert c1["competitors"] >= 5
    assert c2["parents"] == 0
    assert c2["courses"] == 0
    assert c2["competitors"] == 0


@pytest.mark.asyncio
async def test_parent_lookup_and_demo_join(fresh_db):
    await seed()
    parent = await repository.get_parent_by_phone("+919999900001")
    assert parent is not None
    assert parent["name"] == "Mr. Sharma"

    demo = await repository.get_latest_demo_for_parent(parent["id"])
    assert demo is not None
    assert demo["child_name"] == "Aarav"
    assert demo["subject"] == "Physics"
    assert demo["fee_spoken"]
    assert demo["course_id"]


@pytest.mark.asyncio
async def test_battlecard_has_all_competitors(fresh_db):
    await seed()
    rows = await repository.get_competitor_battlecard()
    names = {r["name"] for r in rows}
    assert "Physics Wallah (PW)" in names
    assert "Aakash" in names
    assert "BYJU'S" in names


@pytest.mark.asyncio
async def test_record_turn_and_finalise_objection(fresh_db):
    await seed()
    parent = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    aid = await repository.create_call_attempt(parent["id"], demo["id"], "CA-test")
    await repository.update_call_attempt_status(aid, "in-progress")

    turn = {
        "utterance": "Haan accha tha par sochna padega",
        "intent_classification": "ambiguous",
        "intent_confidence": 0.55,
        "sentiment": "neutral",
        "objection_primary": "stalling",
        "strategy_applied": "disambiguation_probe",
    }
    await repository.record_turn(aid, turn)

    final = {
        **turn,
        "intent_classification": "positive",
        "sentiment": "warm",
        "final": True,
        "next_step": "second_session_booked",
        "next_step_time": "2026-06-02T18:00:00+05:30",
        "objection_verbatim": "sochna padega",
        "counselor_notes": "Booked second session.",
        "sentiment_start": "neutral",
    }
    await repository.record_turn(aid, final)
    obj_id = await repository.finalise_objection(aid, parent["id"], final)
    assert obj_id > 0


@pytest.mark.asyncio
async def test_schedule_and_consume_callback(fresh_db):
    await seed()
    parent = await repository.get_parent_by_phone("+919999900002")
    when = datetime.now(timezone.utc) - timedelta(minutes=5)  # past = due
    cb_id = await repository.schedule_callback(parent["id"], None, when, "parent_requested")
    due = await repository.get_due_callbacks()
    assert any(c["id"] == cb_id for c in due)
    await repository.mark_callback(cb_id, "done")
    due_after = await repository.get_due_callbacks()
    assert not any(c["id"] == cb_id for c in due_after)


def test_days_until_birthday_in_seven_days():
    today = date(2026, 6, 1)
    dob = date(2010, 6, 8).isoformat()
    assert repository.days_until_birthday(dob, today) == 7


def test_days_until_birthday_today_is_zero():
    today = date(2026, 6, 1)
    dob = date(2010, 6, 1).isoformat()
    assert repository.days_until_birthday(dob, today) == 0


def test_days_until_birthday_already_passed_this_year():
    today = date(2026, 6, 1)
    dob = date(2010, 5, 20).isoformat()  # ~11 months out
    assert repository.days_until_birthday(dob, today) == 353


def test_days_until_birthday_none_for_missing_dob():
    assert repository.days_until_birthday(None) is None
    assert repository.days_until_birthday("") is None
    assert repository.days_until_birthday("garbage") is None
