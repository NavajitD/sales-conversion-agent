"""Tiny in-process WebSocket fan-out for the React reasoning panel.

The panel just consumes log_call_state JSON. We retain the last call's events
in memory so a late-connecting panel can replay.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class PanelHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._events: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def attach(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            snapshot = list(self._events)
        for evt in snapshot:
            try:
                await ws.send_text(json.dumps(evt))
            except Exception:
                break
        try:
            while True:
                # Drain anything the panel sends (ignored).
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            async with self._lock:
                self._clients.discard(ws)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Fan-out to every viewer without blocking the caller.

        Voice call latency is sacrosanct — a slow viewer must not backpressure
        the bot's pipeline. We snapshot the viewer set under the lock, then
        spawn one bounded background task per viewer. Each task has its own
        per-send timeout so a half-broken connection drops out instead of
        wedging this fan-out.
        """
        async with self._lock:
            # Reset event store when a new call begins (a non-final event after a final one)
            if self._events and self._events[-1].get("final") and not event.get("final"):
                self._events = []
            self._events.append(event)
            payload = json.dumps(event)
            viewers = list(self._clients)

        for ws in viewers:
            asyncio.create_task(self._send_one(ws, payload))

    async def _send_one(self, ws: WebSocket, payload: str) -> None:
        try:
            await asyncio.wait_for(ws.send_text(payload), timeout=2.0)
        except Exception:
            # Discard the viewer on any error (timeout, disconnect, etc.).
            async with self._lock:
                self._clients.discard(ws)


hub = PanelHub()
