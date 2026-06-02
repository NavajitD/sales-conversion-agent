"""Panel WS broadcast hub — direct unit test with a stub WebSocket.

We don't go through Starlette's TestClient.websocket_connect here because
TestClient is sync and conflicts with our async test loop. The behaviour
under test is in PanelHub itself, so we stub the WebSocket interface.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.panel.ws import PanelHub


class StubWS:
    def __init__(self):
        self.accepted = False
        self.sent: list[str] = []
        self._closed = False
        self._recv_done = asyncio.Event()

    async def accept(self):
        self.accepted = True

    async def send_text(self, msg: str):
        if self._closed:
            raise RuntimeError("closed")
        self.sent.append(msg)

    async def receive_text(self):
        # Block until the test signals the connection should end.
        await self._recv_done.wait()
        # Raise WebSocketDisconnect-equivalent so attach() falls out.
        from fastapi import WebSocketDisconnect

        raise WebSocketDisconnect(1000)

    def close(self):
        self._closed = True
        self._recv_done.set()


@pytest.mark.asyncio
async def test_broadcast_reaches_live_client():
    hub = PanelHub()
    ws = StubWS()
    attach_task = asyncio.create_task(hub.attach(ws))
    # Wait for accept + registration
    for _ in range(20):
        await asyncio.sleep(0.005)
        if ws.accepted and len(hub._clients) == 1:
            break
    assert ws.accepted
    await hub.broadcast({"utterance": "test", "intent_classification": "ambiguous",
                         "intent_confidence": 0.5, "sentiment": "neutral"})
    await asyncio.sleep(0.01)
    assert ws.sent, "client received no broadcast"
    assert json.loads(ws.sent[0])["intent_classification"] == "ambiguous"
    ws.close()
    await attach_task


@pytest.mark.asyncio
async def test_late_client_replays_existing_events():
    hub = PanelHub()
    await hub.broadcast({"utterance": "t1", "intent_classification": "ambiguous",
                         "intent_confidence": 0.4, "sentiment": "neutral"})
    await hub.broadcast({"utterance": "t2", "intent_classification": "soft_no",
                         "intent_confidence": 0.7, "sentiment": "cold"})

    ws = StubWS()
    attach_task = asyncio.create_task(hub.attach(ws))
    for _ in range(20):
        await asyncio.sleep(0.005)
        if len(ws.sent) >= 2:
            break
    assert len(ws.sent) == 2
    assert json.loads(ws.sent[0])["utterance"] == "t1"
    assert json.loads(ws.sent[1])["utterance"] == "t2"
    ws.close()
    await attach_task


@pytest.mark.asyncio
async def test_event_store_resets_on_new_call():
    hub = PanelHub()
    await hub.broadcast({"utterance": "x1", "intent_classification": "positive",
                         "intent_confidence": 0.8, "sentiment": "warm", "final": True})
    await hub.broadcast({"utterance": "y1", "intent_classification": "ambiguous",
                         "intent_confidence": 0.5, "sentiment": "neutral"})
    assert len(hub._events) == 1
    assert hub._events[0]["utterance"] == "y1"
