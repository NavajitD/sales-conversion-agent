"""DB init shim for Firestore.

The previous SQLite implementation created tables via DDL on startup. Firestore
is schemaless; init_db is a no-op here, kept only for call-site compatibility
with `main.py`'s startup hook. We do warm the Firestore client up-front so the
first call to a repository function doesn't pay the connection cost.

Composite indexes (for queries like `callbacks WHERE status='pending' ORDER BY
scheduled_at`) are declared in `firestore.indexes.json` and applied via
`firebase deploy --only firestore:indexes`.
"""
from __future__ import annotations

from app.crm.firestore_client import db


async def init_db(path: str | None = None) -> None:
    """No-op for Firestore. `path` arg preserved for signature compatibility."""
    _ = db()  # warm the singleton


async def connect(path: str | None = None):  # pragma: no cover
    """Legacy SQLite shim. Raises — call sites should not use this anymore."""
    raise RuntimeError(
        "app.crm.db.connect() is SQLite-only. The codebase now uses Firestore. "
        "Import from app.crm.firestore_client instead."
    )
