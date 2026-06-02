# Concurrency audit — sustained-load picture for Aria

Gitignored. Snapshot as of 2026-06-01 (Cloud Run revision aria-00012-cfh).

## TL;DR

**Realistic sustained ceiling today: ~25–30 concurrent calls** before the LLM key pool taps out.

The order of bottlenecks (smallest first) is:

1. **Groq RPM on the active key pool** (~30 calls in flight)
2. **Cloud Run instance count × per-instance ceiling** (~40–60 calls in flight if all instances scaled)
3. **Vobiz simultaneous-channel cap on the DID** (unknown — needs portal verification; assume ≤20)
4. **Cloud Run per-instance memory + CPU** (~4–6 concurrent sessions per 1Gi/1vCPU instance with cpu-boost)
5. **Sarvam Bulbul v3 TTS QPS** (>10 concurrent calls fit comfortably)
6. **Deepgram Nova-3 STT** (pay-as-you-go; not a wall)
7. **Firestore writes** (10k/s — not even close)

Anything past ~30 concurrent calls will:
- Get LLM 429s. The /llm proxy already handles this via key rotation (Groq scout → Groq 70b → Cerebras → Gemini if `GEMINI_IN_POOL=1`), so it degrades gracefully into ~340ms higher TTFB rather than failing — but bot-side turn latency creeps from ~250 ms to ~600+ ms.
- Eventually hit Cloud Run max-instances=10 and start queuing.
- Then either drop the Vobiz call (timeout while waiting for a worker) or sound noticeably laggy.

## Per-component capacity, with numbers

### 1. Cloud Run service `aria`
- Current config: `concurrency=8, max-instances=10, memory=1Gi, cpu=1, --cpu-boost`.
- Per-instance practical ceiling for **voice sessions** (not REST): 4–6.
  - **Memory**: each Pipecat session ≈ 80–120 MB (Silero VAD + audio jitter buffers + httpx connection pool + per-call CallMemory). At 1Gi we have ~7 sessions of headroom before OOM, but Python overhead, asyncio frames, and the FastAPI app itself burn ~250 MB baseline.
  - **CPU**: `cpu-boost` helps cold-start; steady-state, audio resampling + VAD pegs ~25–35% CPU per session. 4 concurrent = 100–140% (vCPU saturation point with `cpu=1`).
- **Total Cloud Run capacity: 4–6 × 10 = 40–60 sessions** (instances scale on CPU pressure, but `concurrency=8` lets queueing happen before new instances spawn — that's actually *bad* for voice).
- **Fix**: lower `concurrency` to `4` so Cloud Run spawns a new instance sooner under voice load. Worth doing before any pilot >5 calls.

### 2. Vobiz DID
- DID configured: `+917971442033` (in Secret Manager).
- Vobiz channel-concurrency cap **unknown** — needs verification in their portal. Typical Indian telephony resellers cap channels at 5/10/20 per DID by plan tier. Until verified, **assume ≤ 20**.
- **Action**: log into Vobiz portal and read "concurrent channel limit" off the account. If <10, that's our true wall.

### 3. Sarvam Bulbul v3 TTS
- Each turn ≈ 1 TTS request (streaming WS).
- With ~6 s turn cadence per call: 1 call = 0.17 TTS req/s.
- 30 concurrent calls = 5 TTS req/s. Bulbul's published soft ceiling is ~10 QPS on the public API. **Fits comfortably.**
- Note: Sarvam Bulbul v3 occasionally returns 502s under sustained load — the bot has no retry logic for those. Worth adding.

### 4. Deepgram Nova-3 STT
- Streaming WS per call. Deepgram's account-level concurrency is generous (10+ on standard pay-as-you-go).
- **Not a bottleneck below 50 concurrent.**

### 5. Groq LLM (current bottleneck)
- Per-key rate limit (free tier): ~30 RPM on `meta-llama/llama-4-scout-17b-16e-instruct`, separate ~30 RPM bucket on `llama-3.3-70b-versatile`.
- We have 3 Groq keys × 2 buckets = ~180 RPM theoretical, but practical is closer to ~90 RPM because keys share an org-level TPM ceiling.
- At ~1 LLM call per turn / 6 s = 10 calls/min per active conversation. **~9 concurrent calls before scout pool is exhausted.**
- The /llm proxy rotates to the 70B bucket, then Cerebras (~30 RPM), then Gemini if `GEMINI_IN_POOL=1`. **Combined ceiling: ~30 concurrent calls before all providers throttle.**
- Past ~30: latency degrades, but the rotator's mid-stream "hold" phrase keeps audio from going silent — the parent just hears Aria say "ek second" mid-conversation more often.

### 6. Firestore
- 10,000 writes/sec on Native mode. Each turn writes 1 doc.
- 30 concurrent calls × 10 turns/min = 300 writes/min = 5/sec. **Not a wall.**
- However: the dashboard analytics endpoint reads up to 500 attempts + 500 objections + 2000 turns per request, and the demo + CRM both poll every 15 s. With many viewers this becomes a real read load. Consider switching to a Firestore aggregate doc updated on each turn — but only if we ship more than a handful of dashboards.

### 7. Panel WebSocket broadcast
- `app/panel/ws.py` PanelHub holds a `set[WebSocket]`. Broadcast iterates the set, doing `await ws.send_text(json)` per viewer.
- Worth checking: **does a slow viewer backpressure the bot's tool-call handler?** The handler does `await hub.broadcast(args)` *after* persisting the turn — so if `send_text` blocks for one slow viewer, the bot's next prompt cycle waits.
- **User explicitly said**: "If analytics data gets queued and consequently dashboard latency increases, so be it." That implies decoupling the broadcast from the call path.
- **Fix to add (low risk)**: replace synchronous broadcast with a per-viewer `asyncio.Queue`. Bot pushes events; a per-viewer worker drains the queue. A slow viewer's queue grows; when it hits a cap, oldest events get dropped. The bot is never blocked.

## How to push the ceiling higher

In order of effort vs lift:

1. **Lower Cloud Run concurrency from 8 → 4 + bump max-instances to 20**. Spawns new instances sooner under load. ~5 min.
2. **Bump memory to 2Gi**. Reduces OOM risk under spiky call distribution. ~1 min, costs marginal.
3. **Decouple panel broadcast via asyncio.Queue**. Removes a real backpressure source on calls. ~30 min, in `app/panel/ws.py`. Tracked below.
4. **Add 1 more Groq paid key** (Tier 1 is ~$0.59/M tokens). Increases LLM RPM bucket ~10×. Single-line env-var change after key purchase.
5. **Pre-warm with min-instances=1**. Removes cold-start spike when call #1 arrives. Tiny cost (~$5/mo for 1 idle instance).
6. **Audit Vobiz DID channel cap**. Single portal lookup. If <10, escalate plan.
7. **Add retry-on-502 to Sarvam TTS**. The PipecatVobiz integration doesn't retry mid-stream; a single 502 = silent turn. ~1 hour to add.

If we ever need >50 sustained: switch from in-process Pipecat to a session-per-pod model (Cloud Run jobs, or a dedicated GKE deployment) so a single bad call can't drag a peer down.

## Useful diagnostic commands

```bash
# Current Cloud Run config
gcloud run services describe aria --region asia-south1 --project aria-crm-2e680

# Live concurrent calls from Firestore
# (call_attempts where status=='in-progress' and started_at > now - 10 min)

# LLM proxy throughput
ls bench_results/   # latest bench shows TTFB + total per provider

# Verify scout-first
curl -s https://aria-446733252616.asia-south1.run.app/llm/chat/completions \
  -X POST -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"hi"}],"stream":false}'
```

## Load-test script

See `scripts/load_test_concurrency.py`. It hammers:
- N parallel `/panel` WS subscriptions (tests broadcast fanout)
- N parallel `/llm` completions (measures real LLM rate-limit + rotation behaviour)
- Burst REST traffic against `/api/dashboard/trigger-call` (measures rate-limit responsiveness; doesn't actually place phone calls because the rate-limit fires first by design)

It does NOT simulate real Vobiz media streams — for that we'd need a synthetic-audio harness. That's a future job.
