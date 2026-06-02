"""OpenAI-compatible /llm proxy.

Pipecat's OpenAILLMService is pointed at this endpoint via `base_url`.
We forward the body unchanged (overriding `model`) to Cerebras (priority) or
Groq (fallback). On quota errors we rotate keys and retry; on a mid-stream
error we inject a Hinglish "hold" phrase so TTS doesn't go silent.

Performance: uses a persistent httpx.AsyncClient with connection pooling to
eliminate per-request TCP/TLS handshake overhead (~80ms saved per turn).
"""
from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from app.llm.key_rotator import rotator

router = APIRouter()

# Persistent connection pool — reused across all LLM calls (saves ~80ms/turn)
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _http_client


HOLD_PHRASES = [
    "Ek second, please hold.",
    "Ek moment, main check kar rahi hoon.",
    "Bas ek second rukiye.",
]
_hold_idx = 0


def _next_hold() -> str:
    global _hold_idx
    p = HOLD_PHRASES[_hold_idx % len(HOLD_PHRASES)]
    _hold_idx += 1
    return p


def _sse_chunk(content: str) -> bytes:
    payload = {
        "id": f"chatcmpl-hold-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "key-rotator",
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    return ("data: " + json.dumps(payload) + "\n\n").encode()


def _sse_done() -> bytes:
    return b"data: [DONE]\n\n"


# Hinglish + English markers that signal a nuance-heavy turn. When detected
# in the parent's last message, the proxy routes that single completion to
# GROQ_NUANCE_MODEL (70B) instead of the default scout. This catches the
# tail cases where scout misreads sarcasm or compound objections.
_NUANCE_MARKERS = (
    # hard refusal
    "nahi chahiye", "nahin chahiye", "bilkul nahi", "bilkul nahin",
    "kabhi nahi", "kabhi nahin", "don't call", "do not call", "stop calling",
    "remove my number", "no thanks", "no thank you", "no, thanks",
    "please don't", "please dont",
    # spouse deferral
    "husband", "wife", "spouse", "patni", "pati", "ghar mein pooch",
    "ghar mein discuss", "biwi se", "wife se", "husband se",
    # heavy hesitation / passive-aggressive
    "dekh lenge", "phir baat", "phir dekh", "baad mein dekh",
)


def _needs_nuance(body: dict) -> bool:
    msgs = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(msgs, list):
        return False
    last_user = ""
    for m in reversed(msgs):
        if isinstance(m, dict) and m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                last_user = content
            elif isinstance(content, list):
                # multimodal — concatenate any text parts
                last_user = " ".join(
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            break
    if not last_user:
        return False
    lower = last_user.lower()
    return any(m in lower for m in _NUANCE_MARKERS)


def _sanitize_messages(body: dict) -> dict:
    """Strip provider-specific fields that fail when we rotate to another provider."""
    msgs = body.get("messages")
    if not isinstance(msgs, list):
        return body
    cleaned = []
    for m in msgs:
        if isinstance(m, dict) and "reasoning" in m:
            m = {k: v for k, v in m.items() if k != "reasoning"}
        cleaned.append(m)
    return {**body, "messages": cleaned}


@router.post("/llm/chat/completions")
@router.post("/llm")
async def llm_proxy(req: Request) -> Any:
    """OpenAI-compatible chat/completions endpoint with key rotation."""
    body = _sanitize_messages(await req.json())
    use_stream = body.get("stream", True) is not False

    # Cap max_tokens for faster generation — voice responses should be short
    if "max_tokens" not in body and "max_completion_tokens" not in body:
        body["max_tokens"] = 300

    # Nuance escalation: if the parent's last turn carries hard-no /
    # spouse-deferral markers, route to the 70b nuance model for this single
    # completion. Median-cost-stays-low, tail-cost-improves.
    nuance = _needs_nuance(body)
    if nuance:
        logger.info("[llm] Nuance markers detected — escalating to 70b")

    max_attempts = max(rotator.pool_size(), 1) + 1
    client = _get_client()

    for attempt in range(max_attempts):
        if nuance and attempt == 0:
            entry = rotator.nuance_entry()
        else:
            entry = rotator.current()
        if entry is None:
            return JSONResponse(
                status_code=503, content={"error": "All LLM API keys exhausted"}
            )

        url = f"{rotator.base_url(entry.provider)}/chat/completions"
        model = rotator.model_for_entry(entry)
        forwarded = {**body, "model": model}
        headers = {
            "Authorization": f"Bearer {entry.key}",
            "Content-Type": "application/json",
        }

        try:
            if not use_stream:
                r = await client.post(url, headers=headers, json=forwarded)
                if r.status_code >= 400:
                    text = r.text
                    logger.error(f"[llm] {entry.label} HTTP {r.status_code}: {text[:300]}")
                    if rotator.is_quota_error(r.status_code, text):
                        rotator.mark_rate_limited(entry)
                        rotator.rotate()
                        continue
                    return JSONResponse(status_code=r.status_code, content=r.json() if "json" in r.headers.get("content-type", "") else {"error": text})
                if attempt > 0:
                    logger.info(f"[llm] Active key after {attempt} rotation(s): {entry.label}")
                return JSONResponse(content=r.json())

            # Streaming path
            req_ctx = client.stream("POST", url, headers=headers, json=forwarded)
            response = await req_ctx.__aenter__()

            if response.status_code >= 400:
                text = (await response.aread()).decode("utf-8", errors="replace")
                await req_ctx.__aexit__(None, None, None)
                logger.error(f"[llm] {entry.label} HTTP {response.status_code}: {text[:300]}")
                if rotator.is_quota_error(response.status_code, text):
                    rotator.mark_rate_limited(entry)
                    rotator.rotate()
                    continue
                return JSONResponse(status_code=response.status_code, content={"error": text})

            if attempt > 0:
                logger.info(f"[llm] Active key after {attempt} rotation(s): {entry.label}")

            async def gen():
                try:
                    if attempt > 0:
                        yield _sse_chunk(_next_hold() + " ")
                    async for chunk in response.aiter_raw():
                        if chunk:
                            yield chunk
                except Exception as e:  # noqa: BLE001
                    logger.error(f"[llm] mid-stream error from {entry.label}: {e}")
                    rotator.mark_rate_limited(entry)
                    rotator.rotate()
                    yield _sse_chunk(" " + _next_hold())
                    yield _sse_done()
                finally:
                    await req_ctx.__aexit__(None, None, None)

            return StreamingResponse(gen(), media_type="text/event-stream")

        except httpx.HTTPError as e:
            logger.error(f"[llm] {entry.label} transport error: {e}")
            rotator.mark_rate_limited(entry)
            rotator.rotate()
            continue

    return JSONResponse(
        status_code=503, content={"error": "LLM request failed after all retries"}
    )
