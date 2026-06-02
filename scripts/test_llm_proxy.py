"""Smoke test the /llm proxy without starting the full app.

Spawns the FastAPI app via httpx ASGI transport, sends a chat completion
request, prints the streamed reply.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.main import app  # noqa: E402


async def main():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/llm/chat/completions",
            json={
                "model": "ignored",
                "stream": True,
                "messages": [
                    {"role": "system", "content": "You are Aria. Reply in one short Hinglish sentence."},
                    {"role": "user", "content": "Namaste, kaisi ho?"},
                ],
            },
        ) as r:
            print("status:", r.status_code)
            async for chunk in r.aiter_text():
                sys.stdout.write(chunk)
                sys.stdout.flush()
            print()


if __name__ == "__main__":
    asyncio.run(main())
