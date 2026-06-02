"""Data-access layer (Firestore-backed).

Thin re-export of `firestore_repo`. Call sites in main.py, bot.py,
vobiz_routes.py, callback_worker.py, and call_state.py import from here
unchanged. The previous SQLite implementation is preserved at
`legacy/sqlite_impl/repository.py` for reference.

ID convention change: IDs are now strings (Firestore doc IDs), not ints.
  parent_id = E.164 phone (e.g. "+919999900001")
  child_id  = uuid hex
  course_id = course code (e.g. "VED-JEE-XI-2YR")
  call_attempt_id = Vobiz call_uuid (e.g. "f0e1d2c3-...")
  demo_id, callback_id, objection_id = uuid hex
"""
from __future__ import annotations

from app.crm.firestore_repo import (  # noqa: F401
    create_call_attempt,
    days_until_birthday,
    finalise_objection,
    get_call_attempt_by_sid,
    get_child,
    get_competitor_battlecard,
    get_due_callbacks,
    get_latest_demo_for_parent,
    get_parent,
    get_parent_by_phone,
    get_pending_callbacks_for_parent,
    get_rate_limit,
    increment_callback_attempts,
    append_rate_event,
    mark_callback,
    record_turn,
    schedule_callback,
    update_call_attempt_status,
)
