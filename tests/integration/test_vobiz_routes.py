"""Vobiz answer XML + status callback wiring (no real Vobiz needed)."""
from __future__ import annotations

import base64
import json
import urllib.parse

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.crm import repository
from app.crm.seeds import seed


def _build_app():
    app = FastAPI()
    from app.telephony.vobiz_routes import router

    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_answer_xml_returns_stream(monkeypatch, fresh_db):
    monkeypatch.setenv("PUBLIC_URL", "https://abc.ngrok-free.app")
    app = _build_app()

    parent_payload = {"parent_phone": "+919999900001", "parent_id": 1}
    body_data = urllib.parse.quote(json.dumps(parent_payload))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            f"/vobiz/answer?body_data={body_data}",
            data={"CallUUID": "VOB-1"},
        )
    assert r.status_code == 200
    body = r.text
    assert "<Stream " in body and 'bidirectional="true"' in body
    assert 'contentType="audio/x-mulaw;rate=8000"' in body
    assert "wss://abc.ngrok-free.app/vobiz/stream" in body
    # parent payload base64-encoded into `body` query param of the WS URL
    assert "body=" in body


@pytest.mark.asyncio
async def test_answer_xml_keepcallalive_set(monkeypatch, fresh_db):
    monkeypatch.setenv("PUBLIC_URL", "https://abc.ngrok-free.app")
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/vobiz/answer", data={"CallUUID": "VOB-2"})
    assert 'keepCallAlive="true"' in r.text


@pytest.mark.asyncio
async def test_status_no_answer_schedules_retry(monkeypatch, fresh_db):
    monkeypatch.setenv("PUBLIC_URL", "https://abc.ngrok-free.app")
    await seed()
    p = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(p["id"])
    await repository.create_call_attempt(p["id"], demo["id"], "VOB-NA")

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/vobiz/status",
            data={"CallUUID": "VOB-NA", "CallStatus": "no-answer", "CallDuration": "0"},
        )
    assert r.status_code == 200

    pending = await repository.get_pending_callbacks_for_parent(p["id"])
    assert len(pending) == 1
    assert pending[0]["reason"] in {"no_answer_retry", "nurture_followup"}


@pytest.mark.asyncio
async def test_status_completed_no_retry(monkeypatch, fresh_db):
    monkeypatch.setenv("PUBLIC_URL", "https://abc.ngrok-free.app")
    await seed()
    p = await repository.get_parent_by_phone("+919999900002")
    demo = await repository.get_latest_demo_for_parent(p["id"])
    await repository.create_call_attempt(p["id"], demo["id"], "VOB-OK")

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post(
            "/vobiz/status",
            data={"CallUUID": "VOB-OK", "CallStatus": "completed", "CallDuration": "180"},
        )

    pending = await repository.get_pending_callbacks_for_parent(p["id"])
    assert len(pending) == 0
    attempt = await repository.get_call_attempt_by_sid("VOB-OK")
    assert attempt["status"] == "completed"
    assert attempt["duration_seconds"] == 180


@pytest.mark.asyncio
async def test_status_unknown_call_uuid_returns_unmatched(fresh_db):
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/vobiz/status",
            data={"CallUUID": "VOB-DOESNOTEXIST", "CallStatus": "completed"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is False


@pytest.mark.asyncio
async def test_recording_ready_persists(monkeypatch, fresh_db):
    await seed()
    p = await repository.get_parent_by_phone("+919999900001")
    demo = await repository.get_latest_demo_for_parent(p["id"])
    aid = await repository.create_call_attempt(p["id"], demo["id"], "VOB-REC")
    await repository.update_call_attempt_status(aid, "completed")

    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/vobiz/recording-ready",
            data={
                "CallUUID": "VOB-REC",
                "RecordingID": "REC-1",
                "RecordUrl": "https://vobiz.example.com/r/REC-1.mp3",
                "RecordingDuration": "120",
            },
        )
    assert r.status_code == 200
    assert "<Response>" in r.text
