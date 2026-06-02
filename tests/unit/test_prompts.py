"""System prompt builder content checks."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.crm import repository
from app.crm.seeds import seed
from app.pipecat_bot.prompts import (
    ALL_TOOLS,
    LOG_CALL_STATE_TOOL,
    build_system_prompt,
)


@pytest.mark.asyncio
async def test_prompt_injects_parent_child_demo(fresh_db):
    await seed()
    parent = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    child = await repository.get_child(demo["child_id"])
    battlecard = await repository.get_competitor_battlecard()

    prompt = build_system_prompt(parent=parent, child=child, demo=demo, battlecard=battlecard)

    assert "Mr. Sharma" in prompt
    assert "Aarav" in prompt
    assert "Physics" in prompt
    assert "Ms. Kapoor" in prompt
    assert "Rotational Motion" in prompt
    assert "JEE" in prompt
    # Battlecard injection
    assert "Physics Wallah" in prompt or "PW" in prompt
    assert "Aakash" in prompt
    # Birthday angle should fire (Aarav's birthday is 12 days out by seed)
    assert "BIRTHDAY ANGLE" in prompt
    # Closing rule
    assert "next step" in prompt.lower()


@pytest.mark.asyncio
async def test_prompt_omits_birthday_when_far(fresh_db):
    await seed()
    # Mrs. Reddy's child Pranavi has birthday ~180 days out → suppressed.
    parent = await repository.get_parent_by_phone("+919999900002")
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    child = await repository.get_child(demo["child_id"])
    battlecard = await repository.get_competitor_battlecard()
    prompt = build_system_prompt(parent=parent, child=child, demo=demo, battlecard=battlecard)
    # Either "(none — do not mention birthdays)" or no birthday section at all
    assert "do not mention birthdays" in prompt


@pytest.mark.asyncio
async def test_prompt_language_register_per_parent(fresh_db):
    await seed()
    en_parent = await repository.get_parent_by_phone("+919999900003")
    demo = await repository.get_latest_demo_for_parent(en_parent["id"])
    child = await repository.get_child(demo["child_id"])
    bc = await repository.get_competitor_battlecard()
    prompt = build_system_prompt(parent=en_parent, child=child, demo=demo, battlecard=bc)
    # Mr. Iyer preferred en-IN — language rule should reflect that
    assert "Indian English" in prompt or "en-IN" in prompt or "English" in prompt


def test_tool_schema_required_fields_present():
    assert LOG_CALL_STATE_TOOL.name == "log_call_state"
    required = set(LOG_CALL_STATE_TOOL.required)
    assert {"utterance", "intent_classification", "intent_confidence", "sentiment"}.issubset(required)


def test_all_tools_count():
    assert len(ALL_TOOLS.standard_tools) == 3
    names = {t.name for t in ALL_TOOLS.standard_tools}
    assert names == {"log_call_state", "schedule_callback_request", "end_call"}
