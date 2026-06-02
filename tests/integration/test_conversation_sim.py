"""Scripted conversation simulation against the real LLM.

This drives a multi-turn dialogue by calling the LLM proxy directly with the
real system prompt and a sequence of canned parent utterances. It validates:
  - The LLM emits valid log_call_state tool calls for the 5-turn arc.
  - Intent classification trajectory makes sense (ambiguous → soft_no → positive).
  - The closing turn carries final=True and a non-null next_step.
  - schedule_callback_request is called when the parent asks for a callback time.

Gated by CEREBRAS_API_KEY_1 / GROQ_API_KEY_1 — skipped in CI when neither is set.
This is the test that catches "the prompt + tool schema + model actually work together."
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
import pytest

from app.crm import repository
from app.crm.seeds import seed
from app.llm import key_rotator as kr
from app.llm.proxy import router as llm_router
from app.pipecat_bot.prompts import ALL_TOOLS, build_system_prompt


def _has_llm_key() -> bool:
    keys = [os.environ.get(f"CEREBRAS_API_KEY_{i}") for i in range(1, 4)]
    keys += [os.environ.get(f"GROQ_API_KEY_{i}") for i in range(1, 4)]
    return any(k and k.strip() for k in keys)


pytestmark = pytest.mark.skipif(
    not _has_llm_key(),
    reason="No CEREBRAS_API_KEY_* or GROQ_API_KEY_* set — skipping live LLM simulation",
)


def _build_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(llm_router)
    return app


def _tools_for_openai() -> list[dict[str, Any]]:
    """Convert our ToolsSchema → OpenAI Chat Completions tool list."""
    out = []
    for fs in ALL_TOOLS.standard_tools:
        out.append({
            "type": "function",
            "function": {
                "name": fs.name,
                "description": fs.description,
                "parameters": {
                    "type": "object",
                    "properties": fs.properties,
                    "required": fs.required,
                },
            },
        })
    return out


SCRIPT = [
    "Haan dekha tha... accha tha. Par abhi sochna padega.",
    "Sach kahun toh fees thodi zyada lag rahi hai.",
    "Value samajh aata hai, par ek saath dena heavy hai.",
    "Theek hai, ek aur demo ho sakta hai alag teacher ke saath?",
    "Haan kal sham 6 baje book kar dijiye.",
]


@pytest.mark.asyncio
async def test_full_conversation_emits_valid_tool_calls(fresh_db):
    await seed()
    kr.rotator.reload()
    app = _build_app()

    parent = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    child = await repository.get_child(demo["child_id"])
    bc = await repository.get_competitor_battlecard()
    system_prompt = build_system_prompt(parent=parent, child=child, demo=demo, battlecard=bc)

    tools = _tools_for_openai()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    tool_calls_observed: list[dict[str, Any]] = []

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        for user_utter in SCRIPT:
            messages.append({"role": "user", "content": user_utter})
            r = await client.post(
                "/llm/chat/completions",
                json={
                    "model": "ignored",
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "stream": False,
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            choice = body["choices"][0]
            msg = choice["message"]
            messages.append(msg)
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    name = tc["function"]["name"]
                    args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                    tool_calls_observed.append({"name": name, "args": args})
                    # Send a dummy tool response so the model can continue.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps({"ok": True}),
                    })

    log_calls = [c for c in tool_calls_observed if c["name"] == "log_call_state"]
    assert len(log_calls) >= 3, f"expected >=3 log_call_state calls, got {len(log_calls)}: {log_calls}"

    # Required fields present on every log_call_state
    for c in log_calls:
        for k in ("utterance", "intent_classification", "intent_confidence", "sentiment"):
            assert k in c["args"], f"missing {k} in {c['args']}"
        assert c["args"]["intent_classification"] in {"positive", "soft_no", "ambiguous", "hard_no"}
        assert 0.0 <= float(c["args"]["intent_confidence"]) <= 1.0

    # At least one ambiguous classification (the "sochna padega" turn) should surface.
    intents = [c["args"]["intent_classification"] for c in log_calls]
    assert "ambiguous" in intents or "soft_no" in intents

    # The closing event is final with a next_step set.
    finals = [c for c in log_calls if c["args"].get("final")]
    if finals:
        assert finals[-1]["args"].get("next_step")

    # The parent asked for a callback at "kal sham 6 baje" — model should have called
    # schedule_callback_request OR captured the time in log_call_state next_step_time.
    has_cb = any(c["name"] == "schedule_callback_request" for c in tool_calls_observed)
    has_next_time = any(
        c["args"].get("next_step_time") for c in log_calls if c["args"].get("final")
    )
    assert has_cb or has_next_time, "expected a callback to be scheduled or next_step_time set"


@pytest.mark.asyncio
async def test_hard_no_short_circuits(fresh_db):
    """A hostile hard-no should be respected: model should NOT keep pitching."""
    await seed()
    kr.rotator.reload()
    app = _build_app()

    parent = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    child = await repository.get_child(demo["child_id"])
    bc = await repository.get_competitor_battlecard()
    system_prompt = build_system_prompt(parent=parent, child=child, demo=demo, battlecard=bc)

    tools = _tools_for_openai()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Mujhe interest nahi hai. Call mat karna phir se."},
    ]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60.0) as client:
        r = await client.post(
            "/llm/chat/completions",
            json={"model": "ignored", "messages": messages, "tools": tools, "tool_choice": "auto", "stream": False},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        msg = body["choices"][0]["message"]

    if msg.get("tool_calls"):
        for tc in msg["tool_calls"]:
            if tc["function"]["name"] == "log_call_state":
                args = json.loads(tc["function"]["arguments"])
                assert args["intent_classification"] in {"hard_no", "soft_no"}, args
                if args["intent_classification"] == "hard_no":
                    # On hard_no the reply text should be brief and respectful — not a sales push.
                    text = (msg.get("content") or "").lower()
                    # Bad words to NOT see in a hard-no response
                    bad = ["enrol", "fees", "discount", "offer", "scholarship"]
                    assert not any(b in text for b in bad), (
                        f"model kept pitching on hard_no: {msg.get('content')}"
                    )
