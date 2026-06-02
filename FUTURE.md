# Future scope

## Findings from 2026-05-31 LLM A/B benchmark

Source: `bench_results/llm_bench_20260531_234534.md` (7 prompts × 3 runs).

- **Groq llama-4-scout is the clear winner.** TTFB p50 = 103ms, total p50 = 244ms — fastest provider tested by a wide margin, clean output, zero errors over 21 calls. The key_rotator already places scout first; this benchmark confirms it should stay there. Consider also promoting `GROQ_FALLBACK_MODEL` to be the *default* `GROQ_MODEL` for both keys.
- **Sarvam-M emits visible `<think>...</think>` reasoning blocks.** Critical for voice — TTS would read them aloud. Disabled from the live pool (set `SARVAM_LLM_IN_POOL=1` to re-enable). To use Sarvam-M live we need a streaming-aware `<think>` stripper in `app/llm/proxy.py`: detect `<think>` at the start of the stream, buffer until `</think>`, then resume forwarding. Worth doing if we want Hinglish-native LLM coverage.
- **Gemini 2.0 Flash deprecated.** All 21 calls failed with HTTP 404 "model no longer available to new users". Updated `GEMINI_MODEL` to `gemini-flash-latest` (rotating alias). Re-run the bench after redeploy to get fresh Gemini numbers.
- **Cerebras gpt-oss-120b had 11/21 errors during the bench** (likely rate-limit). When it works: TTFB 528ms, total 585ms. Slower than Groq scout by ~2×.

## Findings from voice A/B (2026-05-31) — and the ElevenLabs decision (2026-06-01)

- **ElevenLabs is removed end-to-end.** The build owner's account ran out of credits. Critically, in production the ElevenLabs Realtime STT/TTS *initialization* succeeds (WebSocket connects), but the server closes the session within 0.5 s with `quota_exceeded`. Pipecat's reconnect loop hides the failure; the bot speaks into a closed pipe and the parent hears silence. The bot.py fallback path only catches *init* exceptions, so it never engaged. To re-enable later:
  1. Top up ElevenLabs credits
  2. Restore the imports + `_create_stt_tts` provider branches in `app/pipecat_bot/bot.py`
  3. Add `ELEVENLABS_API_KEY` back to `app/secrets.py` SECRET_NAMES
  4. Add the `elevenlabs` extra back to `requirements.txt` pipecat-ai install
  5. Add a runtime quota-failure detector that bails to fallback (the current code only catches init errors)
- **Sarvam Bulbul v3 rejects `pitch` and `loudness`** in the TTS body. Only `pace` is supported. Fixed in `scripts/voice_ab.py`.
- **Voice A/B is currently one-sided** (Sarvam only). Re-run after any future ElevenLabs re-enable.


Things deliberately deferred during the initial Cloud Run + Firestore migration.
Kept local; gitignored. Not roadmap commitments — a working list to consult
when picking the next move.

## Security & abuse

- **Rotate exposed keys before public launch.** The following keys were exposed
  in chat transcripts during the build and should be rotated before the demo
  goes public to non-trusted visitors:
  - `CEREBRAS_API_KEY_1`, `CEREBRAS_API_KEY_2`
  - `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`
  - `DEEPGRAM_API_KEY`, `SARVAM_API_KEY`
  - `VOBIZ_AUTH_TOKEN` (rotating this invalidates the active number binding;
    schedule a maintenance window)

  After rotation: update `.env` locally, run `./scripts/push_secrets.sh .env`,
  redeploy with `./scripts/deploy.sh`.

- **Stable Gemini API key.** The token currently in `.env` (`AQ.Ab8RN6...`)
  is an OAuth access token format and will expire. Replace with an AI Studio
  API key (starts with `AIzaSy`) from <https://aistudio.google.com/apikey>.

- ✅ **Rate limit upgraded to rolling windows (2026-06-01).** Now 5 calls/h +
  25 calls/24h per E.164, applied to ALL phones (whitelist set is empty
  by default). Implementation in `app/rate_limit.py` + `firestore_repo.
  append_rate_event`. Storage: `rate_limits/{phone}.events: [iso, ...]`,
  pruned on write.
- **Cloudflare Turnstile (still pending).** Even with rolling-window limits,
  a scripted attacker can rotate phone numbers to amortise abuse across
  many docs. Add invisible Turnstile widget on the demo page; verify with
  server-side `siteverify` before calling `append_rate_event`. Cost: one
  free Cloudflare app + ~20 LOC.

- **TRAI DND compliance.** No DND list lookup before placing calls. Must add
  before any real customer pilot in India.

- **Calling-hours window.** Hardcoded 10:00–20:30 IST in
  `app/telephony/cadence.py`. Could become a per-parent preference.

- **/admin operator dashboard auth.** The dashboard endpoints under
  `/api/dashboard/*` are currently public. If we ever expose an admin view
  beyond the visitor demo, gate it with Firebase Auth (Google sign-in
  restricted to `navjitdebnath5@gmail.com`).

## Concurrency hardening (surfaced 2026-06-01)

See `CONCURRENCY.md` for the full audit. Practical near-term moves, in order:

1. **Lower Cloud Run `concurrency` from 8 → 4** so a new instance is spun up
   sooner under voice load. Bump `max-instances` from 10 → 20 at the same
   time. ~5 min edit to `scripts/deploy.sh`.
2. **Pre-warm `min-instances=1`** to eliminate cold-start spike on the
   first call after idle. Cost: ~$5/mo.
3. **Add 1 paid Groq key** ($0.59/M tokens, Tier 1). Raises LLM RPM ~10×.
   Single env-var update post-purchase. The current sustained ceiling
   is ~30 concurrent calls and this is the cheapest way to push it.
4. **Audit Vobiz DID channel concurrency.** Unknown from this side; one
   portal lookup. If <10, raises the ceiling immediately.
5. **Retry-on-502 for Sarvam TTS.** Bulbul v3 occasionally 502s under
   sustained load; the bot currently produces a silent turn. ~1 h to add.
6. ✅ **Non-blocking panel broadcast (2026-06-01).** `PanelHub.broadcast`
   now spawns a per-viewer asyncio task with a 2 s send-timeout. Slow
   dashboards can never backpressure the bot. See `app/panel/ws.py`.

## LLM routing improvements (surfaced 2026-06-01)

- ✅ **Scout promoted to primary LLM (2026-06-01).** `GROQ_MODEL` now
  defaults to `meta-llama/llama-4-scout-17b-16e-instruct`. TTFB drops
  from ~580 ms (70b) to ~244 ms (scout) in the 2026-05-31 bench.
- ✅ **Hard-no / spouse-deferral escalation (2026-06-01).** The /llm proxy
  inspects the parent's last message for nuance markers and routes that
  single completion to `GROQ_NUANCE_MODEL` (70b) instead. See
  `app/llm/proxy.py::_needs_nuance` + `rotator.nuance_entry()`.
- **Stateful escalation (still pending).** The heuristic is keyword-based;
  a more robust path is to track previous-turn `intent_classification` and
  escalate on `hard_no` or `spouse_deferral`. Needs piping state into the
  proxy (header from bot, or a small Firestore lookup keyed by
  `call_attempt_id`).
- **Streaming `<think>` stripper.** Re-enables Sarvam-M in the LLM pool
  (Hinglish-native option). Buffer until `</think>`, then resume forwarding.
  Tracked in `app/llm/proxy.py` near `_sanitize_messages`.

## Self-improvement (beyond v1 objection-RAG)

- **Weekly prompt-tuning job.** After v1's soft-no/hard-no RAG ships, a
  scheduled (Cloud Scheduler → Cloud Run job) weekly task could rewrite
  the objection-handling section of the system prompt based on labeled
  outcomes. Risk: silent quality regressions. Mitigation: human approval
  step (Firestore-backed proposal queue) before any prompt change is
  promoted to production.

- **LoRA fine-tune.** Only feasible once volume > ~500 calls with high-
  confidence labels. Not before.

## Telephony / observability

- **Call-recording auto-download.** `/vobiz/recording-ready` receives the
  MP3 URL; we don't fetch yet. Wire to GCS bucket
  `aria-recordings-${PROJECT}` with a lifecycle rule (delete after 30 days
  unless flagged for training).

- **Trace each call's pipeline.** OpenTelemetry → Cloud Trace for
  STT/LLM/TTS spans; already have latency logs but not span-correlated.

## Architecture / ops

- **`/admin` operator dashboard.** Separate page with all calls, transcripts,
  outcome breakdown, soft-no→RAG examples in flight, abuse-limit usage.
  Gate behind Firebase Auth (Google sign-in restricted to my email).

- **Multi-region.** Cloud Run + Firestore both in `asia-south1` for now.
  If we ever need redundancy, dual-region Firestore is the lift.

- **README rewrite.** Current README still references the SQLite/Twilio era.
  Update once Phase 1 is verified live: Firestore, Cloud Run, Firebase
  Hosting, the deploy script, the public demo URL.

- **Pin pipecat-vobiz version.** Currently `>=0.0.3,<0.1`. When a release
  cuts >=0.1, audit the breakage surface.

## Demo / marketing

- **Persona richness.** Five seeded parents today. Could add 2–3 edge
  personas (very price-sensitive, English-only, very rushed) to stress-
  test the agent in the visitor demo.

- **Embedded call recording playback.** Once recordings auto-download to
  GCS, show the visitor a playable clip of their just-finished call.
