"""LLM A/B benchmark: Gemini vs Cerebras vs Groq on Hinglish objection-handling.

Reads API keys from .env. Runs each provider against a frozen suite of
conversation states, measuring TTFB (time-to-first-token), total response
latency, and token usage. Writes a Markdown report under bench_results/.

Usage:
  .venv/bin/python scripts/bench_llm.py [--runs 3] [--out bench_results]

Decision rubric for picking a winner (subjective, you make the call):
  • TTFB < 600 ms is ideal for voice (parent perceives <1s as "snappy")
  • Total response < 2 s for short objection-handling turns
  • Output: Devanagari script enforced (system prompt), one idea per turn,
    no markdown/emojis, naturalistic Hinglish

The script does NOT auto-judge quality — it captures the raw outputs so
you can eyeball five providers on the same prompt and pick.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env so we don't need to export keys.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Frozen suite. Each row = a conversation state the bot is about to respond to.
# `messages` matches the OpenAI chat-completions wire format. System prompt is
# a compressed version of the full Priya prompt (full version is too long for
# fair latency comparison and equally penalises every provider).
SYSTEM_PROMPT_SHORT = (
    "You are Priya, a senior education counselor calling parents after their "
    "child's free Vedantu demo class. Reply in Hinglish (Devanagari for Hindi, "
    "Latin for English). One idea per turn, max two short sentences. Always end "
    "with a question or forward move. Never use markdown, bullets, emojis, "
    "numbered lists — your reply is read aloud."
)

SUITE = [
    {
        "id": "price_objection",
        "user": "Bahut mehnga lag raha hai, abhi affordable nahi hai humare liye.",
        "description": "Price/affordability objection; needs split-question and value/EMI framing",
    },
    {
        "id": "child_didnt_like",
        "user": "Bacche ko demo class mein boring laga, teacher engaging nahi thi.",
        "description": "Child-experience objection; needs validation + second-session offer",
    },
    {
        "id": "competitor_pw",
        "user": "Physics Wallah ka course bahut sasta hai, wahi le lete hain.",
        "description": "Competitor comparison; needs single-axis differentiation, no trash-talk",
    },
    {
        "id": "spouse_deferral",
        "user": "Mujhe husband se baat karni padegi, woh decide karte hain.",
        "description": "Authority deferral; equip parent to sell internally, pin deadline",
    },
    {
        "id": "soft_stall",
        "user": "Sochna padega, baad mein call karenge.",
        "description": "Stalling without a reason; needs exactly one probe",
    },
    {
        "id": "hard_no",
        "user": "Mujhe interest nahi hai, please call mat karna dobara.",
        "description": "Hard no; instant respect, exit warm, no push",
    },
    {
        "id": "positive_ready",
        "user": "Bacche ko bahut acha laga, hum enrol karna chahte hain. Process kya hai?",
        "description": "Positive intent; stop selling, drive to next step",
    },
]


@dataclass
class ProviderConfig:
    label: str
    base_url: str
    model: str
    api_key: str
    auth_header: str = "Bearer"  # most use Bearer; Gemini OpenAI-compat also uses Bearer

    def headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"{self.auth_header} {self.api_key}",
        }


def _config_from_env() -> list[ProviderConfig]:
    """Build provider configs from environment. Skips providers with no key."""
    out: list[ProviderConfig] = []

    # Groq: primary + scout fallback model (separate rate-limit bucket)
    for i in range(1, 4):
        k = (os.environ.get(f"GROQ_API_KEY_{i}") or "").strip()
        if not k:
            continue
        out.append(
            ProviderConfig(
                label=f"groq-{i}-llama-3.3-70b",
                base_url="https://api.groq.com/openai/v1",
                model="llama-3.3-70b-versatile",
                api_key=k,
            )
        )
        # Only bench scout on key #1 to limit noise
        if i == 1:
            out.append(
                ProviderConfig(
                    label="groq-1-llama-4-scout",
                    base_url="https://api.groq.com/openai/v1",
                    model="meta-llama/llama-4-scout-17b-16e-instruct",
                    api_key=k,
                )
            )
        break  # one Groq key is enough for the bench

    # Cerebras (gpt-oss-120b)
    for i in range(1, 4):
        k = (os.environ.get(f"CEREBRAS_API_KEY_{i}") or "").strip()
        if not k:
            continue
        out.append(
            ProviderConfig(
                label=f"cerebras-{i}-gpt-oss-120b",
                base_url="https://api.cerebras.ai/v1",
                model="gpt-oss-120b",
                api_key=k,
            )
        )
        break

    # Sarvam-M (Hinglish-native LLM)
    k = (os.environ.get("SARVAM_API_KEY") or "").strip()
    if k:
        out.append(
            ProviderConfig(
                label="sarvam-m",
                base_url="https://api.sarvam.ai/v1",
                model="sarvam-m",
                api_key=k,
            )
        )

    # Gemini (OpenAI-compatible)
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if k:
        out.append(
            ProviderConfig(
                label="gemini-2.0-flash",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                model="gemini-2.0-flash",
                api_key=k,
            )
        )

    return out


@dataclass
class TurnResult:
    suite_id: str
    provider: str
    run: int
    ttfb_ms: float | None
    total_ms: float
    completion_text: str
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


async def _one_request(
    client: httpx.AsyncClient,
    cfg: ProviderConfig,
    item: dict,
    run: int,
) -> TurnResult:
    """Streaming request; measures TTFB and total latency."""
    url = f"{cfg.base_url}/chat/completions"
    body = {
        "model": cfg.model,
        "stream": True,
        "temperature": 0.4,
        "max_tokens": 300,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT_SHORT},
            {"role": "user", "content": item["user"]},
        ],
    }

    start = time.monotonic()
    ttfb: float | None = None
    pieces: list[str] = []
    p_toks: int | None = None
    c_toks: int | None = None

    try:
        async with client.stream(
            "POST", url, headers=cfg.headers(), json=body, timeout=30.0
        ) as resp:
            if resp.status_code >= 400:
                text = (await resp.aread()).decode("utf-8", errors="replace")
                total_ms = (time.monotonic() - start) * 1000
                return TurnResult(
                    suite_id=item["id"],
                    provider=cfg.label,
                    run=run,
                    ttfb_ms=None,
                    total_ms=total_ms,
                    completion_text="",
                    error=f"HTTP {resp.status_code}: {text[:300]}",
                )
            async for raw in resp.aiter_lines():
                if not raw:
                    continue
                if not raw.startswith("data: "):
                    continue
                payload = raw[6:]
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                # First non-empty content token → TTFB
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        if ttfb is None:
                            ttfb = (time.monotonic() - start) * 1000
                        pieces.append(content)
                # Token usage may appear on the final chunk
                usage = chunk.get("usage")
                if usage:
                    p_toks = usage.get("prompt_tokens")
                    c_toks = usage.get("completion_tokens")
        total_ms = (time.monotonic() - start) * 1000
        return TurnResult(
            suite_id=item["id"],
            provider=cfg.label,
            run=run,
            ttfb_ms=ttfb,
            total_ms=total_ms,
            completion_text="".join(pieces).strip(),
            prompt_tokens=p_toks,
            completion_tokens=c_toks,
        )
    except Exception as e:  # noqa: BLE001
        total_ms = (time.monotonic() - start) * 1000
        return TurnResult(
            suite_id=item["id"],
            provider=cfg.label,
            run=run,
            ttfb_ms=None,
            total_ms=total_ms,
            completion_text="",
            error=str(e)[:300],
        )


async def run_bench(runs: int, out_dir: Path) -> Path:
    providers = _config_from_env()
    if not providers:
        print("ERROR: no providers configured (no API keys in env)", file=sys.stderr)
        sys.exit(1)

    print(f"Bench: {len(providers)} providers × {len(SUITE)} prompts × {runs} runs")
    for p in providers:
        print(f"  · {p.label}  (model={p.model})")

    results: list[TurnResult] = []
    async with httpx.AsyncClient() as client:
        for run_idx in range(runs):
            for item in SUITE:
                # Sequential within a (run, item) to make latency numbers
                # comparable (parallel would skew via shared network).
                for cfg in providers:
                    r = await _one_request(client, cfg, item, run_idx)
                    results.append(r)
                    err = f"  ERROR: {r.error[:80]}" if r.error else ""
                    ttfb = f"{r.ttfb_ms:6.0f}ms" if r.ttfb_ms else "    n/a"
                    print(
                        f"  [{run_idx+1}/{runs}] {item['id']:20s} {cfg.label:30s} "
                        f"ttfb={ttfb} total={r.total_ms:6.0f}ms{err}"
                    )

    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"llm_bench_{ts}.md"
    _write_report(out_file, providers, results, runs)
    return out_file


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    vs = sorted(values)
    k = (len(vs) - 1) * p
    f = int(k)
    c = min(f + 1, len(vs) - 1)
    return vs[f] + (vs[c] - vs[f]) * (k - f)


def _write_report(
    path: Path,
    providers: list[ProviderConfig],
    results: list[TurnResult],
    runs: int,
) -> None:
    by_provider: dict[str, list[TurnResult]] = {}
    for r in results:
        by_provider.setdefault(r.provider, []).append(r)

    lines: list[str] = []
    lines.append(f"# LLM bench report — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append(f"- Suite: {len(SUITE)} Hinglish prompts × {runs} runs")
    lines.append(f"- Providers: {', '.join(p.label for p in providers)}")
    lines.append("")
    lines.append("## Latency summary (TTFB / total, ms)")
    lines.append("")
    lines.append(
        "| Provider | TTFB p50 | TTFB p95 | Total p50 | Total p95 | Errors |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|")
    for cfg in providers:
        rs = by_provider.get(cfg.label, [])
        ttfbs = [r.ttfb_ms for r in rs if r.ttfb_ms is not None]
        totals = [r.total_ms for r in rs if r.error is None]
        err_count = sum(1 for r in rs if r.error)

        def fmt(x: float | None) -> str:
            return f"{x:.0f}" if x is not None else "n/a"

        lines.append(
            f"| {cfg.label} | {fmt(_percentile(ttfbs, 0.5))} | "
            f"{fmt(_percentile(ttfbs, 0.95))} | "
            f"{fmt(_percentile(totals, 0.5))} | "
            f"{fmt(_percentile(totals, 0.95))} | {err_count} |"
        )
    lines.append("")

    lines.append("## Sample responses (run 1)")
    lines.append("")
    for item in SUITE:
        lines.append(f"### {item['id']}")
        lines.append(f"_Description_: {item['description']}")
        lines.append("")
        lines.append(f"**Parent**: {item['user']}")
        lines.append("")
        for cfg in providers:
            r = next(
                (
                    x
                    for x in results
                    if x.suite_id == item["id"] and x.provider == cfg.label and x.run == 0
                ),
                None,
            )
            if not r:
                continue
            if r.error:
                lines.append(f"- **{cfg.label}** — error: `{r.error[:200]}`")
                continue
            ttfb = f"{r.ttfb_ms:.0f}ms" if r.ttfb_ms else "n/a"
            lines.append(
                f"- **{cfg.label}** (TTFB={ttfb}, total={r.total_ms:.0f}ms): "
                f"{r.completion_text}"
            )
        lines.append("")

    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "- TTFB matters most for voice: <600ms feels snappy, >1s feels laggy.\n"
        "- Eyeball the sample responses for Hinglish quality, brevity (≤2 short "
        "sentences), correct Devanagari script for Hindi words, and whether the "
        "response actually executes the objection-handling rule (split-question "
        "for price; validate-then-offer-second-session for child experience; etc.).\n"
        "- Errors usually mean a 429/quota — don't penalise the model, retry once.\n"
        "- Decide based on (TTFB p50, total p50, qualitative win-count)."
    )

    path.write_text("\n".join(lines))
    print(f"\nReport written to {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--out", type=str, default="bench_results")
    args = ap.parse_args()
    out_dir = Path(args.out).resolve()
    asyncio.run(run_bench(args.runs, out_dir))
