"""Background loop that places due callbacks.

A simple polling worker. Every 30 s, it queries `callbacks WHERE due AND pending`
and calls `place_call` for each. We update the row to `done` after placement
(the actual call's eventual status drives further retries via cadence).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from loguru import logger

from app.crm import repository
from app.telephony.outbound import place_call

POLL_SECONDS = 30


async def _process_due() -> None:
    due = await repository.get_due_callbacks(datetime.now(timezone.utc))
    for cb in due:
        parent = await repository.get_parent(cb["parent_id"])
        if not parent:
            await repository.mark_callback(cb["id"], "cancelled")
            continue
        try:
            await place_call(parent["phone"], parent["id"], cb.get("demo_id"))
            await repository.increment_callback_attempts(cb["id"])
            await repository.mark_callback(cb["id"], "done")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[callback_worker] failed to place cb {cb['id']}: {e}")


async def run_forever() -> None:
    logger.info(f"[callback_worker] started; polling every {POLL_SECONDS}s")
    while True:
        try:
            await _process_due()
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[callback_worker] loop error: {e}")
        await asyncio.sleep(POLL_SECONDS)
