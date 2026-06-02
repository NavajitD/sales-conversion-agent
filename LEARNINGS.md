# Aria — Engineering Learnings & Neat Tricks

A running log of the bugs, root causes, and tricks from building Aria (the
post-demo voice agent). Written to be raided for blog posts and LinkedIn —
each entry is a self-contained story: **symptom → root cause → fix**, with a
quotable line where there's one.

---

## Telephony & the call lifecycle

### The call dropped the instant the parent picked up
**Symptom:** Outbound call connects, parent answers, and the line dies within a
second. Silence, then dial tone.
**Root cause:** When a visitor enters *their own* phone number to be called, the
bot was looking up the CRM persona by that visitor phone — which is never in the
CRM (the seeded personas have their own numbers). The lookup returned nothing,
the bot raised, and the WebSocket closed the moment Vobiz bridged the audio.
**Fix:** Identify the persona by `parent_id` (the seeded CRM doc), which is
round-tripped through the call body, and only fall back to phone for the legacy
"call the seeded number directly" path.
> The visitor's phone is *who we dial*, not *who the agent thinks it's calling*.
> Those are two different identities and conflating them killed every call.

### The regional Cloud Run URL is not optional for WebSockets
**Symptom:** Vobiz could fetch the `/answer` webhook fine, but the media
WebSocket to `/vobiz/stream` never opened — bot never started, parent heard
silence.
**Root cause:** `gcloud run ... status.url` returns the legacy `*.a.run.app`
alias. It serves HTTP but does **not** accept WSS upstream.
**Fix:** Derive the regional URL explicitly
(`aria-<projectNumber>.<region>.run.app`) and pin it as `PUBLIC_URL` for the
webhooks. The deploy script computes it from the project number.

### Loopback to your own LLM proxy: bind to `$PORT`, not your dev port
**Symptom:** The pre-baked greeting played, then the bot went silent from turn 2.
**Root cause:** On Cloud Run, uvicorn binds to `$PORT` (8080), but the bot's
loopback call to the in-container `/llm` proxy used the local-dev default (3000).
Every real LLM call hit a dead port and failed with `Connection error`.
**Fix:** Prefer `$PORT` when building the loopback URL.
> A "works on my machine" port default that only bites *after* the first turn is
> the nastiest kind — the call looks healthy right up until it isn't.

---

## Latency (P0 for voice)

### Greet on pickup — don't wait for the human to say "hello"
**Symptom:** ~5-second dead air before the agent spoke.
**Root cause:** The greeting was gated behind a 3-second "wait for the parent to
say hello first" timeout, *then* TTS synthesis on top.
**Insight:** This is an **outbound** call — the agent initiated it, so the agent
speaks first. There's nothing to wait for.
**Fix:** Greet immediately on connect (a 0.3s media-stream warmup only). Dropped
~5s → ~1–2s (just TTS time-to-first-byte).

### Pre-warm the cold path while the greeting plays
**Insight:** The greeting is pre-baked TTS, so the *first* time the LLM proxy
actually dials its upstream (Groq) is the parent's first reply — paying a cold
TLS handshake on the one turn the human is waiting on.
**Trick:** Fire a tiny throwaway completion (`max_tokens=1`) the instant the call
starts. The ~2s greeting hides the handshake, so turn 1 is as fast as turn 3.
Pure background task — never awaited on the voice path.

### A warm WebSocket is most of the "instant short reply" win
**Insight:** The Sarvam TTS websocket keeps itself alive with a keepalive, so
the connection is already hot. The only remaining cost on a one-word "अच्छा" is
the synthesis round-trip itself.
**Trick (opt-in):** Pre-render a curated set of short fillers once per process —
same voice, model, and sample rate as the live socket, so the timbre is
identical — and replay the cached PCM when the agent's whole turn is exactly one
of them. Exact-match only; any miss or error falls straight through to live TTS,
so it can never change how a real sentence sounds or make a turn fail. Shipped
behind a flag (`TTS_FILLER_CACHE`) because it touches the audio path and deserves
a live-call validation before going on.

**What actually happened (the punchline):** On the validation call the cache
pre-rendered all 8 clips perfectly, fell back cleanly, added zero latency — and
hit **zero** times. The agent's *own system prompt* says *"No robotic
acknowledgements. Vary, and be specific"* and *"end most turns with a question,"*
so she never utters a bare "जी" or "अच्छा" to match against. The optimization was
defeated by the personality we deliberately gave her.
> The best caches exploit repetition. We'd spent the prompt *engineering away*
> the exact repetition the cache needed. Measure the hit rate before you trust
> the idea — a clever optimization for behaviour your system doesn't exhibit is
> just dead code with a nice comment.

### Where the ~1s turn latency actually goes
From the logs: end-to-end (speech-end → first audio) ≈ 0.95–1.35s, of which
Deepgram STT TTFB ≈ 450ms and Groq llama-4-scout TTFB ≈ 100ms. **TTS
time-to-first-byte dominates the rest.** Lowering STT `endpointing` (200ms) trims
a little but risks clipping slow speakers — usually not worth it.

---

## LLM routing

### A key-rotating, OpenAI-compatible proxy buys you resilience for free
The bot talks plain OpenAI Chat Completions to a local `/llm` proxy that rotates
across a pool (Groq → Cerebras → Gemini) and fails over on quota errors
mid-stream. Swapping providers is a config change, not a code change.

### Benchmark before you pick a primary
A 21-call A/B put **Groq llama-4-scout** first by a wide margin (TTFB p50 103ms,
total p50 244ms, zero errors). Cerebras gpt-oss-120b was ~2× slower with frequent
rate-limit errors; Gemini 2.0 Flash was silently *deprecated* (every call 404'd).
Numbers, not vibes, decide the order.

### Reasoning models will read their `<think>` tags out loud
Sarvam-M emits visible `<think>…</think>` blocks. On a voice agent the TTS will
literally speak the model's inner monologue. Either strip it (a streaming-aware
`<think>` buffer in the proxy) or keep the model out of the live pool.
> "Use a reasoning model for voice" and "don't let it narrate its own reasoning"
> are the same task.

### Spend nuance budget only on the hard turns
Median cost stays low by running the fast small model by default, and escalating
to a bigger 70B model **only** for the single completion where hard-no /
spouse-deferral markers show up. Tail quality improves without paying for it
every turn.

---

## Voice & TTS quality

### Force Devanagari or the phone call is unintelligible
**Root cause:** Romanized Hindi ("Namaste, kaise hain") makes the TTS mispronounce
everything. The model must emit Devanagari ("नमस्ते, कैसे हैं"); English brand/
subject words stay Latin. This is a hard, per-turn prompt rule — not a suggestion.

### Treat stray non-Hindi scripts as STT glitches, not intent
A single Odia/Tamil/Telugu word from the transcriber that contradicts the flow is
a codemix artifact, not the parent switching languages or refusing. The prompt
explicitly tells the model to ignore it rather than classify a `hard_no`.

### Don't let backchannels cut the agent off
"अच्छा", "हाँ", "हम्म" while the agent is mid-sentence are *encouragement*, not
interruptions. A min-words turn strategy (need 3+ words to interrupt while the bot
speaks; 1 word when it's silent) keeps the agent from flinching at every nod.

### The greeting child name must come from the persona, never a constant
**Symptom:** Every call greeted the child as "Aarav" regardless of persona.
**Root cause:** The "instant" pre-baked greeting was a hardcoded string. The
system prompt had the right name; the greeting didn't.
**Fix:** Build the greeting per-call from the persona (child name + demo subject).
> Anything pre-baked for latency is also pre-baked for *staleness*. Template it.

### Aria the product vs. Priya the counsellor
The site/brand is "Aria"; the in-call agent introduces herself as "Priya". Keep
them straight — the transcript and live panel label the speaker **Priya** (who
the parent actually talks to), while the product chrome stays **Aria**.

---

## Live transcript & analytics

### Don't reconstruct the transcript from the LLM's memory — stream the real STT
**Symptom:** The live transcript dropped many of the parent's turns.
**Root cause:** Parent turns were only shown if the LLM happened to echo them back
verbatim through its `log_call_state` tool call. Whatever the model paraphrased or
skipped simply never appeared.
**Fix:** Broadcast the actual Deepgram transcript straight to the panel as the
parent speaks. The tool call still drives the *analytics* (intent, tone,
objection) — but the transcript now comes from the source of truth.
> If you find yourself rebuilding a transcript from the model's tool calls, stop —
> the STT already has it.

### Your logging tool was speaking to the customer (every tool result re-runs the LLM)
**Symptom:** Priya sounded confused and repetitive — re-explaining herself,
double-texting, sometimes in romanized Hindi, once even narrating a tool name.
**Root cause:** The agent logs structured state every turn via a `log_call_state`
tool. By default, when a tool returns, the framework runs the LLM *again* with the
result — so every turn produced a **second** generation on top of the real reply.
That second pass, with nothing new to say, drifted: it paraphrased, repeated the
last question, dropped out of Devanagari, even said "मैं log_call_state call करूंगी"
out loud. The analytics tool had become a second, worse voice.
**Fix:** Return the tool result with `run_llm=False`. A pure side-effect tool
(logging, analytics) should *record and stop*, not provoke another turn. One
parent turn → one spoken reply.
> Not every tool result deserves a follow-up turn. A logging call that "talks
> back" is the model filling silence you accidentally asked it to fill — and
> models fill silence worse than they answer questions.

### Voice latency is sacrosanct: every side-channel is fire-and-forget
The panel fan-out (transcript, sentiment, reasoning) never blocks the voice
pipeline. Each broadcast is an `asyncio.create_task` with a per-viewer send
timeout, so a slow or half-dead browser tab drops itself instead of
back-pressuring the call.

---

## Reliability & ops

### ElevenLabs taught us that "connected" ≠ "working"
The Realtime STT/TTS WebSocket connected fine, then the server closed it within
0.5s with `quota_exceeded`. Pipecat's reconnect loop *hid* the failure — the bot
spoke into a closed pipe and the parent heard silence. The fallback only caught
*init* exceptions, so it never engaged.
**Lesson:** A health check that only verifies "the socket opened" is a lie. Watch
for early server-side closes, and make fallbacks trigger on *runtime* failure, not
just construction failure.

### Your STT will transcribe hold music, and your agent will earnestly reply to it
**Symptom:** A test call where the parent put the line on hold turned into the
agent calmly answering the carrier's hold loop — "please stay on the line",
"hold पर रखा है" — over and over, repeating "मैं लाइन पर हूँ" into the void.
**Root cause:** Deepgram faithfully transcribes IVR/hold announcements as
"the user," and the LLM has no reason to think otherwise, so it keeps replying.
**Fix:** Two layers. (1) Tell the agent in the prompt that hold music / IVR
recordings / a phrase repeating means the parent stepped away — acknowledge
once, then offer a callback and `end_call`. (2) A code backstop: if the agent
emits the *exact same reply* 3× in a call (something a real conversation never
does), force a graceful sign-off and hang up so we don't pay for a Cloud Run
seat talking to a dial tone.
> A voice agent's "user" is whatever the STT heard — not necessarily a human.
> Anything that can put audio on the line (hold music, IVR, a TV in the room) is
> an input you have to design for.

### Make the picker endpoint do only the picker's work
**Symptom:** Five personas took >8s to load with a single visitor.
**Root cause:** The picker reused the CRM dashboard endpoint, which hydrates ~4
Firestore reads *per parent* (latest call, objection, callback — several of them
composite-index `order_by` queries).
**Fix:** A dedicated lightweight endpoint reading only parent + first child (one
read each). >8s → ~0.3s.
> A read-only endpoint that's "close enough" to reuse will quietly cost you a
> composite index scan per row. Shape the query to the screen.

---

## Security & Git

### Push protection is a feature — redact, never bypass
A real Groq/Sarvam/Vobiz key set had crept into `.env.example` (it should only
ever hold placeholders). GitHub's secret scanning blocked the push. The right move
is to redact the file and rewrite the commit — *not* click the "allow secret"
bypass link. The example file documents shape, not credentials.

### Merging two unrelated histories without losing the remote's files
The local project and the remote repo had divergent roots (the remote was just an
auto-created LICENSE + README). `git merge --allow-unrelated-histories -X ours`
keeps your code and README while still absorbing the remote's LICENSE — no
force-push, nothing lost.

---

*Maintained alongside `FUTURE.md` (roadmap) and `CONCURRENCY.md` (load picture).*
