"""KeyRotator: pool composition, rotation order, quota detection."""
from __future__ import annotations

import pytest

from app.llm.key_rotator import KeyRotator


def _reset_env(monkeypatch):
    for i in range(1, 4):
        monkeypatch.delenv(f"CEREBRAS_API_KEY_{i}", raising=False)
        monkeypatch.delenv(f"GROQ_API_KEY_{i}", raising=False)


def test_pool_orders_cerebras_before_groq(monkeypatch):
    _reset_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY_1", "g1")
    monkeypatch.setenv("CEREBRAS_API_KEY_1", "c1")
    monkeypatch.setenv("CEREBRAS_API_KEY_2", "c2")
    r = KeyRotator()
    assert [e.label for e in r._pool] == ["cerebras-1", "cerebras-2", "groq-1"]
    assert r.current().provider == "cerebras"  # type: ignore[union-attr]
    assert r.current().key == "c1"  # type: ignore[union-attr]


def test_rotate_advances_through_pool(monkeypatch):
    _reset_env(monkeypatch)
    monkeypatch.setenv("CEREBRAS_API_KEY_1", "c1")
    monkeypatch.setenv("GROQ_API_KEY_1", "g1")
    r = KeyRotator()
    assert r.current().label == "cerebras-1"  # type: ignore[union-attr]
    r.rotate()
    assert r.current().label == "groq-1"  # type: ignore[union-attr]
    r.rotate()
    assert r.current() is None


def test_quota_error_status_codes():
    assert KeyRotator.is_quota_error(429, "")
    assert KeyRotator.is_quota_error(402, "")
    assert KeyRotator.is_quota_error(500, "rate_limit exceeded")
    assert KeyRotator.is_quota_error(403, "insufficient_quota")
    assert not KeyRotator.is_quota_error(200, "")
    assert not KeyRotator.is_quota_error(400, "bad request")


def test_pool_empty_when_no_keys(monkeypatch):
    _reset_env(monkeypatch)
    r = KeyRotator()
    assert r.pool_size() == 0
    assert r.current() is None


def test_base_url_and_model():
    assert KeyRotator.base_url("cerebras").endswith("cerebras.ai/v1")
    assert KeyRotator.base_url("groq").endswith("groq.com/openai/v1")
    # Model strings come from env overrides or defaults — accept any non-empty value.
    assert KeyRotator.model("cerebras").strip()
    assert KeyRotator.model("groq").strip()
