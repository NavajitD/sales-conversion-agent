"""Shared pytest fixtures."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Ensure repo root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Default tmp DB before any app module imports (so config defaults are sane).
_tmpdir = tempfile.mkdtemp(prefix="aria-tests-")
os.environ.setdefault("DATABASE_PATH", str(Path(_tmpdir) / "test.db"))
os.environ.setdefault("PUBLIC_URL", "https://test.invalid")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def fresh_db(tmp_path, monkeypatch):
    """Per-test DB pointed at a fresh tmp file."""
    db_path = tmp_path / "aria.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    from app.crm.db import init_db

    await init_db()  # picks up env via _resolve_path each call
    yield db_path
