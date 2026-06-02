"""Handles `log_call_state`, `schedule_callback_request`, and `end_call` tool calls.

Splits cleanly from the Pipecat pipeline file so it can be unit-tested without
a running pipeline. Pure async functions; side-effects are: SQLite writes +
panel broadcast.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger

from app.crm import repository
from app.panel.ws import hub
from app.telephony.cadence import parent_requested_callback_at


def _parse_bool(value: Any) -> bool:
    """Robustly coerce a value to bool. Handles string 'true'/'false' from LLM."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


@dataclass
class CallContext:
    """Per-call mutable state shared with the tool handlers.

    IDs are Firestore doc IDs (strings):
      call_attempt_id = Vobiz call_uuid
      parent_id       = E.164 phone
      demo_id         = uuid hex
    """
    call_attempt_id: str
    parent_id: str
    demo_id: str | None
    objection_cycles: int = 0
    sentiment_start: str | None = None


async def handle_log_call_state(ctx: CallContext, args: dict[str, Any]) -> dict[str, Any]:
    """Persist a per-turn event, broadcast it, and on `final` finalise the objection record."""
    # First non-trivial sentiment we see becomes the start.
    if ctx.sentiment_start is None and args.get("sentiment"):
        ctx.sentiment_start = args.get("sentiment")

    if args.get("objection_primary") not in (None, "none"):
        ctx.objection_cycles += 1

    is_final = _parse_bool(args.get("final"))
    # Only treat as final if next_step is also provided (prevents premature finalization)
    is_final = is_final and bool(args.get("next_step"))

    await repository.record_turn(ctx.call_attempt_id, args, is_final=is_final)
    await hub.broadcast(args)

    if is_final:
        finalised = {
            **args,
            "sentiment_start": ctx.sentiment_start,
            "sentiment_end": args.get("sentiment"),
        }
        await repository.finalise_objection(
            ctx.call_attempt_id, ctx.parent_id, finalised
        )
        # Mark the call attempt completed; final next_step is in objections row.
        await repository.update_call_attempt_status(
            ctx.call_attempt_id, "completed"
        )
        logger.info(f"[call_state] final: next_step={args.get('next_step')}")

    return {"ok": True, "objection_cycles": ctx.objection_cycles}


async def handle_schedule_callback_request(
    ctx: CallContext, args: dict[str, Any]
) -> dict[str, Any]:
    """Log a parent-asked callback at the requested time (nudged to polite hours)."""
    when_iso = args.get("when_iso")
    reason = args.get("reason", "parent_requested")
    notes = args.get("notes")
    if not when_iso:
        return {"ok": False, "error": "missing when_iso"}
    try:
        when = datetime.fromisoformat(when_iso.replace("Z", "+00:00"))
    except ValueError:
        return {"ok": False, "error": f"invalid when_iso: {when_iso}"}

    scheduled_utc = parent_requested_callback_at(when)
    cb_id = await repository.schedule_callback(
        ctx.parent_id, ctx.demo_id, scheduled_utc, reason, notes
    )
    logger.info(
        f"[callback] scheduled #{cb_id} for parent {ctx.parent_id} at {scheduled_utc.isoformat()} ({reason})"
    )
    return {"ok": True, "callback_id": cb_id, "scheduled_at": scheduled_utc.isoformat()}
