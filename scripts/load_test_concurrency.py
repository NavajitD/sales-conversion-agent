"""Load test for the Aria deployment.

Tests three independent paths in parallel; each is a separate subcommand
so you can run them individually and not flood Cloud Run all at once.

Usage:
  python scripts/load_test_concurrency.py llm   --concurrency 20 --duration 30
  python scripts/load_test_concurrency.py panel --viewers 50 --duration 30
  python scripts/load_test_concurrency.py rest  --concurrency 20 --duration 15
  python scripts/load_test_concurrency.py all   --duration 30

Does NOT place real phone calls — Vobiz media streams would need a synthetic
audio harness. This script measures the *control plane* (LLM proxy, panel
fanout, REST endpoints) which is where contention shows up first.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

try:
    import websockets  # noqa: E402
except ImportError:
    websockets = None  # type: ignore

BASE = "https://aria-446733252616.asia-south1.run.app"
WS_BASE = "wss://aria-446733252616.asia-south1.run.app"

PROMPT = (
    "Reply in 8 words or less: how are you today?"
)


async def llm_one(client: httpx.AsyncClient, idx: int, stats: dict) -> None:
    body = {
        "model": "ignored",
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "max_tokens": 30,
    }
    t0 = time.perf_counter()
    try:
        r = await client.post(BASE + "/llm/chat/completions", json=body, timeout=60.0)
        dt = (time.perf_counter() - t0) * 1000
        if r.status_code == 200:
            stats["latencies_ms"].append(dt)
            stats["ok"] += 1
        else:
            stats["errors"][r.status_code] = stats["errors"].get(r.status_code, 0) + 1
    except Exception as e:
        stats["transport"] = stats.get("transport", 0) + 1


async def llm_test(concurrency: int, duration: int) -> None:
    stats: dict[str, Any] = {"ok": 0, "errors": {}, "latencies_ms": []}
    end = time.monotonic() + duration
    async with httpx.AsyncClient() as client:
        async def worker(wid: int):
            while time.monotonic() < end:
                await llm_one(client, wid, stats)
        await asyncio.gather(*(worker(i) for i in range(concurrency)))
    n = stats["ok"]
    lats = stats["latencies_ms"]
    p50 = statistics.median(lats) if lats else 0
    p95 = (sorted(lats)[int(len(lats) * 0.95)] if len(lats) > 20 else max(lats, default=0))
    p99 = (sorted(lats)[int(len(lats) * 0.99)] if len(lats) > 100 else max(lats, default=0))
    print(f"[llm] concurrency={concurrency} duration={duration}s")
    print(f"  ok: {n}  ({n / max(duration, 1):.1f}/s)")
    print(f"  errors: {stats['errors']}")
    print(f"  p50: {p50:.0f}ms  p95: {p95:.0f}ms  p99: {p99:.0f}ms")


async def panel_one(idx: int, end: float, stats: dict) -> None:
    if websockets is None:
        raise RuntimeError("pip install websockets")
    try:
        async with websockets.connect(WS_BASE + "/panel", ping_interval=20) as ws:
            stats["connected"] += 1
            while time.monotonic() < end:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    stats["messages"] += 1
                    stats.setdefault("by_viewer", {}).setdefault(idx, 0)
                    stats["by_viewer"][idx] += 1
                except asyncio.TimeoutError:
                    continue
    except Exception as e:
        stats["errors"].append(str(e)[:120])


async def panel_test(viewers: int, duration: int) -> None:
    stats: dict[str, Any] = {"connected": 0, "messages": 0, "errors": []}
    end = time.monotonic() + duration
    await asyncio.gather(*(panel_one(i, end, stats) for i in range(viewers)))
    print(f"[panel] viewers={viewers} duration={duration}s")
    print(f"  connected: {stats['connected']}")
    print(f"  total messages: {stats['messages']}")
    if stats["errors"]:
        print(f"  errors: {stats['errors'][:5]}{'…' if len(stats['errors']) > 5 else ''}")


async def rest_one(client: httpx.AsyncClient, phone: str, stats: dict) -> None:
    t0 = time.perf_counter()
    try:
        # Use the rate-limit endpoint (read-only); avoid actually triggering
        # calls so we don't burn Vobiz credits.
        r = await client.get(BASE + "/api/dashboard/rate_limit/" + phone, timeout=15.0)
        dt = (time.perf_counter() - t0) * 1000
        stats["latencies_ms"].append(dt)
        stats["statuses"][r.status_code] = stats["statuses"].get(r.status_code, 0) + 1
    except Exception as e:
        stats["transport"] += 1


async def rest_test(concurrency: int, duration: int) -> None:
    stats: dict[str, Any] = {"statuses": {}, "latencies_ms": [], "transport": 0}
    end = time.monotonic() + duration
    async with httpx.AsyncClient() as client:
        async def worker(wid: int):
            phone = f"+91999990{wid:04d}"
            while time.monotonic() < end:
                await rest_one(client, phone, stats)
                await asyncio.sleep(0.05)
        await asyncio.gather(*(worker(i) for i in range(concurrency)))
    lats = stats["latencies_ms"]
    p50 = statistics.median(lats) if lats else 0
    print(f"[rest] concurrency={concurrency} duration={duration}s")
    print(f"  responses: {sum(stats['statuses'].values())}")
    print(f"  statuses: {stats['statuses']}")
    print(f"  p50: {p50:.0f}ms")


async def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_llm = sub.add_parser("llm")
    p_llm.add_argument("--concurrency", type=int, default=10)
    p_llm.add_argument("--duration", type=int, default=30)
    p_panel = sub.add_parser("panel")
    p_panel.add_argument("--viewers", type=int, default=20)
    p_panel.add_argument("--duration", type=int, default=30)
    p_rest = sub.add_parser("rest")
    p_rest.add_argument("--concurrency", type=int, default=20)
    p_rest.add_argument("--duration", type=int, default=15)
    p_all = sub.add_parser("all")
    p_all.add_argument("--duration", type=int, default=30)
    args = ap.parse_args()

    if args.cmd == "llm":
        await llm_test(args.concurrency, args.duration)
    elif args.cmd == "panel":
        await panel_test(args.viewers, args.duration)
    elif args.cmd == "rest":
        await rest_test(args.concurrency, args.duration)
    else:
        # Run all three in parallel
        await asyncio.gather(
            llm_test(10, args.duration),
            panel_test(20, args.duration),
            rest_test(15, args.duration),
        )


if __name__ == "__main__":
    asyncio.run(main())
