"""Outbound call placement via Vobiz REST.

POST https://api.vobiz.ai/api/v1/Account/{AUTH_ID}/Call/
Headers: X-Auth-ID, X-Auth-Token, Content-Type: application/json
Body:    {to, from, answer_url, answer_method}
"""
from __future__ import annotations

import json
import urllib.parse
from typing import Any

import httpx
from loguru import logger

from app.config import (
    VOBIZ_AUTH_ID,
    VOBIZ_AUTH_TOKEN,
    VOBIZ_PHONE_NUMBER,
    public_url,
)
from app.crm import repository

VOBIZ_API = "https://api.vobiz.ai/api/v1"


def _vobiz_call_url() -> str:
    if not VOBIZ_AUTH_ID:
        raise RuntimeError("VOBIZ_AUTH_ID not set")
    return f"{VOBIZ_API}/Account/{VOBIZ_AUTH_ID}/Call/"


async def place_call(parent_phone: str, parent_id: str, demo_id: str | None) -> dict[str, Any]:
    """Place an outbound call. Returns {call_uuid, attempt_id}."""
    if not VOBIZ_AUTH_TOKEN:
        raise RuntimeError("VOBIZ_AUTH_TOKEN not set")
    if not VOBIZ_PHONE_NUMBER:
        raise RuntimeError("VOBIZ_PHONE_NUMBER not set")

    base = public_url()
    # Encode parent_phone so the /answer handler can route to the right CRM row
    # even when Vobiz only echoes back its own CallUUID.
    body_payload = {"parent_phone": parent_phone, "parent_id": parent_id}
    body_encoded = urllib.parse.quote(json.dumps(body_payload))
    answer_url = f"{base}/vobiz/answer?body_data={body_encoded}"

    headers = {
        "Content-Type": "application/json",
        "X-Auth-ID": VOBIZ_AUTH_ID,
        "X-Auth-Token": VOBIZ_AUTH_TOKEN,
    }
    data = {
        "to": parent_phone,
        "from": VOBIZ_PHONE_NUMBER,
        "answer_url": answer_url,
        "answer_method": "POST",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(_vobiz_call_url(), headers=headers, json=data)
    if r.status_code != 201:
        logger.error(f"[vobiz] place_call HTTP {r.status_code}: {r.text[:400]}")
        raise RuntimeError(f"Vobiz API error ({r.status_code}): {r.text}")

    body = r.json()
    # Vobiz returns request_uuid or call_uuid depending on flow.
    call_uuid = body.get("request_uuid") or body.get("call_uuid") or "unknown"
    attempt_id = await repository.create_call_attempt(
        parent_id=parent_id, demo_id=demo_id, twilio_call_sid=call_uuid
    )
    logger.info(
        f"[vobiz] placed call call_uuid={call_uuid} to={parent_phone} attempt={attempt_id}"
    )
    return {"call_uuid": call_uuid, "attempt_id": attempt_id}
