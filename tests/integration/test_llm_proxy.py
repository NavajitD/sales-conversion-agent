"""LLM proxy: rotation behaviour with mocked Cerebras/Groq HTTP."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.llm import key_rotator as kr
from app.llm.proxy import router as llm_router


def _build_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(llm_router)
    return app


@pytest.mark.asyncio
async def test_proxy_streams_cerebras_response(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY_1", "c-test-1")
    monkeypatch.setenv("CEREBRAS_API_KEY_2", "")
    monkeypatch.setenv("GROQ_API_KEY_1", "")
    kr.rotator.reload()
    app = _build_app()

    sse_body = (
        b'data: {"id":"x","object":"chat.completion.chunk","choices":[{"delta":{"content":"hi"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.cerebras.ai/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, content=sse_body, headers={"content-type": "text/event-stream"}
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            async with c.stream(
                "POST",
                "/llm/chat/completions",
                json={"messages": [{"role": "user", "content": "yo"}], "stream": True},
            ) as r:
                body = b""
                async for chunk in r.aiter_raw():
                    body += chunk
        assert r.status_code == 200
        assert b"hi" in body
        assert b"[DONE]" in body


@pytest.mark.asyncio
async def test_proxy_rotates_on_quota_error(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY_1", "c-bad")
    monkeypatch.setenv("CEREBRAS_API_KEY_2", "")
    monkeypatch.setenv("CEREBRAS_API_KEY_3", "")
    monkeypatch.setenv("GROQ_API_KEY_1", "g-good")
    monkeypatch.setenv("GROQ_API_KEY_2", "")
    kr.rotator.reload()
    app = _build_app()

    good_sse = (
        b'data: {"id":"y","object":"chat.completion.chunk","choices":[{"delta":{"content":"ok"}}]}\n\n'
        b"data: [DONE]\n\n"
    )

    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.cerebras.ai/v1/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": "rate_limit"})
        )
        mock.post("https://api.groq.com/openai/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, content=good_sse, headers={"content-type": "text/event-stream"}
            )
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            async with c.stream(
                "POST",
                "/llm/chat/completions",
                json={"messages": [{"role": "user", "content": "x"}], "stream": True},
            ) as r:
                body = b""
                async for chunk in r.aiter_raw():
                    body += chunk
        assert r.status_code == 200
        assert b"ok" in body
        # Rotator advanced past Cerebras
        assert kr.rotator.current().provider == "groq"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_proxy_503_when_all_keys_exhausted(monkeypatch):
    monkeypatch.setenv("CEREBRAS_API_KEY_1", "c-bad")
    for v in ("CEREBRAS_API_KEY_2", "CEREBRAS_API_KEY_3", "GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3"):
        monkeypatch.setenv(v, "")
    kr.rotator.reload()
    app = _build_app()

    async with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.cerebras.ai/v1/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": "rate_limit"})
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post(
                "/llm/chat/completions",
                json={"messages": [{"role": "user", "content": "x"}], "stream": False},
            )
        assert r.status_code == 503
        assert "exhausted" in r.text.lower() or "failed" in r.text.lower()
