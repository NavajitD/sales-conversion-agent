"""Idempotent seeding (Firestore-backed).

Thin re-export of `firestore_seeds.seed`. The old SQLite version lives at
`legacy/sqlite_impl/seeds.py`.
"""
from __future__ import annotations

from app.crm.firestore_seeds import seed  # noqa: F401
