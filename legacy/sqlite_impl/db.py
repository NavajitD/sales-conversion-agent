"""SQLite schema + async connection helper.

Schema purpose:
  parents/children          → who we're calling and about whom
  demos                     → which demo class was attended (joins child + course + teacher)
  courses                   → Vedantu course catalog with pricing + offers
  competitors               → battle card rows used inline by the agent
  call_attempts             → every dial attempt, with status (no-answer, busy, completed, failed)
  call_turns                → log_call_state events from the live call
  callbacks                 → scheduled future call attempts (no-pickup cadence + parent-requested)
  objections                → finalised structured objection record per call
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS parents (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL,
  phone           TEXT NOT NULL UNIQUE,
  preferred_language TEXT DEFAULT 'hi-IN',
  city            TEXT,
  notes           TEXT,
  created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS children (
  id              INTEGER PRIMARY KEY,
  parent_id       INTEGER NOT NULL REFERENCES parents(id) ON DELETE CASCADE,
  name            TEXT NOT NULL,
  dob             TEXT,
  grade           TEXT,
  board           TEXT,
  exam_target     TEXT,
  exam_date       TEXT
);

CREATE TABLE IF NOT EXISTS courses (
  id              INTEGER PRIMARY KEY,
  code            TEXT UNIQUE NOT NULL,
  name            TEXT NOT NULL,
  grade           TEXT,
  board           TEXT,
  exam_target     TEXT,
  subjects        TEXT,
  duration        TEXT,
  fee_amount      INTEGER,
  fee_spoken      TEXT,
  payment_plan_available INTEGER DEFAULT 1,
  scholarship_available  INTEGER DEFAULT 0,
  batch_options   TEXT,
  current_offer   TEXT,
  offer_expires_at TEXT
);

CREATE TABLE IF NOT EXISTS demos (
  id              INTEGER PRIMARY KEY,
  child_id        INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
  course_id       INTEGER NOT NULL REFERENCES courses(id),
  subject         TEXT,
  teacher         TEXT,
  weak_topic      TEXT,
  attended_at     TEXT NOT NULL,
  notes           TEXT
);

CREATE TABLE IF NOT EXISTS competitors (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL,
  axis            TEXT NOT NULL,
  parent_concern  TEXT NOT NULL,
  vedantu_counter TEXT NOT NULL,
  proof_point     TEXT
);

CREATE TABLE IF NOT EXISTS call_attempts (
  id              INTEGER PRIMARY KEY,
  parent_id       INTEGER NOT NULL REFERENCES parents(id),
  demo_id         INTEGER REFERENCES demos(id),
  twilio_call_sid TEXT,
  status          TEXT,
  started_at      TEXT DEFAULT (datetime('now')),
  ended_at        TEXT,
  duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS call_turns (
  id              INTEGER PRIMARY KEY,
  call_attempt_id INTEGER NOT NULL REFERENCES call_attempts(id) ON DELETE CASCADE,
  ts              TEXT DEFAULT (datetime('now')),
  utterance       TEXT,
  intent_classification TEXT,
  intent_confidence REAL,
  objection_primary TEXT,
  objection_secondary TEXT,
  objection_verbatim TEXT,
  strategy_applied TEXT,
  sentiment       TEXT,
  is_final        INTEGER DEFAULT 0,
  next_step       TEXT,
  next_step_label TEXT,
  next_step_time  TEXT,
  counselor_notes TEXT
);

CREATE TABLE IF NOT EXISTS callbacks (
  id              INTEGER PRIMARY KEY,
  parent_id       INTEGER NOT NULL REFERENCES parents(id),
  demo_id         INTEGER REFERENCES demos(id),
  reason          TEXT,
  scheduled_at    TEXT NOT NULL,
  attempts_so_far INTEGER DEFAULT 0,
  status          TEXT DEFAULT 'pending',
  created_at      TEXT DEFAULT (datetime('now')),
  notes           TEXT
);

CREATE TABLE IF NOT EXISTS objections (
  id              INTEGER PRIMARY KEY,
  call_attempt_id INTEGER NOT NULL REFERENCES call_attempts(id) ON DELETE CASCADE,
  parent_id       INTEGER NOT NULL REFERENCES parents(id),
  objection_primary   TEXT,
  objection_secondary TEXT,
  objection_verbatim  TEXT,
  intent_final        TEXT,
  sentiment_start     TEXT,
  sentiment_end       TEXT,
  next_step       TEXT,
  next_step_time  TEXT,
  counselor_notes TEXT,
  recorded_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_callbacks_due ON callbacks(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_attempts_parent ON call_attempts(parent_id);
CREATE INDEX IF NOT EXISTS idx_turns_attempt ON call_turns(call_attempt_id);
"""


def _resolve_path(path: str | None) -> str:
    """Read DATABASE_PATH from env each call so tests can override at runtime."""
    if path:
        return path
    env = (os.environ.get("DATABASE_PATH") or "").strip()
    if env:
        return env
    # Fallback when run outside .env
    from app.config import DATABASE_PATH as default  # local import to avoid freezing
    return default


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


async def init_db(path: str | None = None) -> None:
    """Create tables if missing. Idempotent."""
    resolved = _resolve_path(path)
    _ensure_dir(resolved)
    async with aiosqlite.connect(resolved) as db:
        await db.executescript(SCHEMA)
        await db.commit()


@asynccontextmanager
async def connect(path: str | None = None) -> AsyncIterator[aiosqlite.Connection]:
    """`async with connect() as db:` — rows-as-dict, foreign keys on."""
    resolved = _resolve_path(path)
    _ensure_dir(resolved)
    async with aiosqlite.connect(resolved) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
