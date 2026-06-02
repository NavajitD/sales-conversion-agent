"""FastAPI routes for Vobiz outbound calling.

Flow:
  1. We POST to Vobiz REST → Vobiz dials the parent.
  2. When the parent answers, Vobiz POSTs to /vobiz/answer expecting XML.
     We return a <Response><Stream bidirectional=...>wss://.../vobiz/stream</Stream></Response>
     so Vobiz opens a bidirectional WebSocket to /vobiz/stream.
  3. /vobiz/stream — parse_vobiz_start() consumes Vobiz's initial frames,
     reads the call_uuid, stream_id, encoding, sample_rate; we then hand off
     to Pipecat. parent_phone (and parent_id) comes via the `body` query param
     we set in /vobiz/answer (base64-encoded JSON).
  4. /vobiz/recording-ready — Vobiz callback when the MP3 is available; we
     persist the URL for future analytics, no auto-download in alpha.
  5. /vobiz/recording-finished — recording stopped; logs metadata.

There's no separate "call status" callback equivalent to Twilio's. We infer
no-answer / failure from the Vobiz REST response and from whether the
WebSocket was ever opened. A short watchdog scheduled on `place_call` marks
attempts as `no-answer` if the WS never connects.
"""
from __future__ import annotations

import base64
import json
import urllib.parse
from typing import Any

from fastapi import APIRouter, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

from app.config import (
    VOBIZ_ENCODING,
    VOBIZ_SAMPLE_RATE,
    public_ws_url,
)
from app.crm import repository
from app.pipecat_bot.bot import run_bot

router = APIRouter()


@router.api_route("/vobiz/answer", methods=["GET", "POST"])
async def vobiz_answer(
    request: Request,
    CallUUID: str | None = Query(default=None),
    body_data: str | None = Query(default=None),
) -> HTMLResponse:
    """Return the <Stream> XML telling Vobiz to bridge audio to our WS."""
    logger.info(f"[vobiz] /answer CallUUID={CallUUID}")
    # The body_data query param carries the parent_phone / parent_id we attached
    # in place_call. We forward it to the WS so the bot can look up the CRM row.
    parent_payload: dict[str, Any] = {}
    if body_data:
        try:
            parent_payload = json.loads(body_data)
        except json.JSONDecodeError:
            logger.warning(f"[vobiz] bad body_data: {body_data[:120]}")

    # Encode for WS query param (base64 of JSON) — same convention the Vobiz
    # reference uses; our /vobiz/stream handler decodes it.
    body_b64 = base64.b64encode(
        json.dumps(parent_payload).encode("utf-8")
    ).decode("utf-8")

    ws_base = public_ws_url() + "/vobiz/stream"
    ws_url = f"{ws_base}?body={urllib.parse.quote(body_b64)}"
    content_type = f"{VOBIZ_ENCODING};rate={VOBIZ_SAMPLE_RATE}"

    # `keepCallAlive="true"` keeps the call up while we connect.
    # `audioTrack="inbound"` is the side Vobiz captures from the parent.
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f'    <Stream bidirectional="true" audioTrack="inbound" '
        f'contentType="{content_type}" keepCallAlive="true">\n'
        f"        {ws_url}\n"
        "    </Stream>\n"
        "</Response>"
    )
    return HTMLResponse(content=xml, media_type="application/xml")


@router.websocket("/vobiz/stream")
async def vobiz_stream(
    websocket: WebSocket,
    body: str | None = Query(default=None),
):
    """Vobiz Media Streams: handshake via parse_vobiz_start, then run Pipecat."""
    await websocket.accept()

    parent_phone = ""
    parent_id: str | None = None
    if body:
        try:
            decoded = base64.b64decode(body).decode("utf-8")
            parsed = json.loads(decoded)
            parent_phone = parsed.get("parent_phone", "") or ""
            parent_id = parsed.get("parent_id")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[vobiz] failed to decode body query param: {e}")

    try:
        # Pipecat's helper consumes Vobiz's `start` event and returns IDs +
        # negotiated mediaFormat. It does NOT leave the socket "empty" the way
        # parse_telephony_websocket would for Pipecat's own transport, so the
        # FastAPIWebsocketTransport in run_bot will receive subsequent media
        # frames cleanly.
        from pipecat.serializers.vobiz import parse_vobiz_start

        parsed = await parse_vobiz_start(websocket)
        call_uuid = parsed.get("call_id") or websocket.query_params.get("call_uuid") or ""
        stream_id = parsed.get("stream_id") or ""
        encoding = parsed.get("encoding") or VOBIZ_ENCODING
        sample_rate = int(parsed.get("sample_rate") or VOBIZ_SAMPLE_RATE)
        logger.info(
            f"[vobiz] stream start call_uuid={call_uuid} stream_id={stream_id} "
            f"encoding={encoding} sample_rate={sample_rate} parent_phone={parent_phone!r}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"[vobiz] parse_vobiz_start failed: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    if not parent_phone and not parent_id:
        logger.error("[vobiz] no parent_phone/parent_id — cannot identify CRM row; closing WS")
        try:
            await websocket.close()
        except Exception:
            pass
        return

    try:
        await run_bot(
            websocket,
            call_uuid=call_uuid,
            stream_id=stream_id,
            encoding=encoding,
            sample_rate=sample_rate,
            parent_phone=parent_phone,
            parent_id=parent_id,
        )
    except Exception as e:
        logger.exception(f"[vobiz] bot crashed: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.api_route("/vobiz/recording-ready", methods=["GET", "POST"])
async def vobiz_recording_ready(request: Request) -> HTMLResponse:
    """Vobiz callback when the recording file is ready. We persist the URL."""
    data = await request.form()
    recording_url = data.get("RecordUrl")
    recording_id = data.get("RecordingID")
    call_uuid = data.get("CallUUID")
    duration = data.get("RecordingDuration")
    logger.info(
        f"[vobiz] recording-ready CallUUID={call_uuid} id={recording_id} "
        f"duration={duration} url={recording_url}"
    )
    if call_uuid:
        attempt = await repository.get_call_attempt_by_sid(call_uuid)
        if attempt:
            await repository.update_call_attempt_status(
                attempt["id"], attempt["status"] or "completed"
            )
            logger.info(f"[vobiz] attached recording metadata to attempt {attempt['id']}")
    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@router.api_route("/vobiz/recording-finished", methods=["GET", "POST"])
async def vobiz_recording_finished(request: Request) -> HTMLResponse:
    data = await request.form()
    logger.info(f"[vobiz] recording-finished: {dict(data)}")
    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@router.post("/vobiz/status")
async def vobiz_status(request: Request) -> JSONResponse:
    """Generic status callback endpoint (kept for parity with prior Twilio flow).

    Vobiz doesn't ship a Twilio-style multi-event status callback in the same
    shape; this is here so cadence retry logic can be exercised from outside
    (and our test suite). Expected body: CallUUID + CallStatus (form-encoded).
    """
    data = await request.form()
    call_uuid = data.get("CallUUID", "")
    status = data.get("CallStatus", "")
    duration_raw = data.get("CallDuration", "0") or "0"
    try:
        duration = int(duration_raw)
    except ValueError:
        duration = 0
    if not call_uuid:
        return JSONResponse({"ok": False, "error": "missing CallUUID"})
    attempt = await repository.get_call_attempt_by_sid(call_uuid)
    if not attempt:
        return JSONResponse({"ok": True, "matched": False})
    await repository.update_call_attempt_status(
        attempt["id"], status, duration_seconds=duration
    )
    if status in {"no-answer", "busy", "failed", "canceled"}:
        from app.telephony.cadence import next_no_answer_retry
        from datetime import datetime, timezone

        pending = await repository.get_pending_callbacks_for_parent(attempt["parent_id"])
        attempts_so_far = (
            len([c for c in pending if c["reason"] == "no_answer_retry"]) + 1
        )
        decision = next_no_answer_retry(
            previous_attempt_utc=datetime.now(timezone.utc),
            attempts_so_far=attempts_so_far,
        )
        await repository.schedule_callback(
            parent_id=attempt["parent_id"],
            demo_id=attempt.get("demo_id"),
            scheduled_at=decision.next_attempt_at_utc,
            reason=decision.reason,
            notes=f"auto-scheduled attempt #{decision.attempt_number}",
        )
    return JSONResponse({"ok": True, "matched": True})
