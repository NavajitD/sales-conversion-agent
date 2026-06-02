# Aria — Post-Demo Parent Conversion Agent (PS4)

Pipecat + Vobiz + Deepgram + Sarvam voice agent that calls parents within 2–4 hours of their child's free demo class, handles objections in Hinglish, and lands one of: enrolment, second session, senior callback, or nurture follow-up.

> **Status: alpha-ready.** 47/47 tests green, including real-API smoke tests against Sarvam Bulbul TTS, Deepgram Nova-3, and a full 5-turn scripted conversation against the live LLM. Outbound calling is wired to Vobiz; needs you to set `PUBLIC_URL` to a live ngrok tunnel before the first real call.

---

## Architecture

```
Vobiz REST: POST /Account/{auth_id}/Call/
            ▲ (place_call)
            │
        ┌───┴───┐
        │  app  │ ──── /vobiz/answer  → returns <Stream> XML
        └───────┘                       pointing at wss://.../vobiz/stream
            ▲
            │  parent answers
            ▼
   Vobiz Media Streams ←──── bidirectional µ-law @ 8 kHz ────→ /vobiz/stream
                                                                    │
                                                                    ▼
                                                            Pipecat pipeline
                                                                    │
                ┌───────────────────────────────────────────────────┼─────────────────┐
                ▼                          ▼                        ▼                 ▼
        Deepgram STT             LLM (/llm proxy:         Sarvam Bulbul TTS    log_call_state
        nova-3 multi          Cerebras→Groq rotator)        WS streaming        → SQLite CRM
        (Hinglish codemix)                                                       → /panel WS
                                                                                 → React panel
```

Key choices, deliberately:

| Decision | Reason |
|---|---|
| **Full Python** rewrite (FastAPI + Pipecat) | Pipecat is Python-native; mixing with Node would split state and ops. |
| **Pipecat 1.3.0 + pipecat-vobiz 0.0.3** | Pipecat ships first-class Deepgram + Sarvam (Bulbul WS); pipecat-vobiz adds the Vobiz `<Stream>` XML contract, `parse_vobiz_start` handshake, and `VobizFrameSerializer` for µ-law/L16 + auto-hangup. No glue code needed. |
| **Vobiz over Twilio** | Twilio key-generation was blocked at the time of build. Vobiz exposes the same outbound + media-stream pattern; XML format and WS protocol are minor variants. |
| **Cerebras → Groq fallback with key rotation** | Ports your existing `keyRotator.js` semantics. Cheapest fast inference for gpt-oss-120b / llama-3.3-70b. Proxy strips provider-specific `reasoning` fields so rotation mid-conversation is safe. |
| **Deepgram Nova-3 `language=multi`** | Best Hinglish codemix STT today; built-in interim results + VAD events for low-latency turn-taking. |
| **Sarvam Bulbul WS streaming** | Native Indian accent for TTS. Pipecat handles the resampling to Vobiz's 8 kHz µ-law. |
| **SQLite from day one** | The PS calls out structured objection logging + callback cadence. Real schema beats JSON. Migrate to Postgres later by swapping `aiosqlite` for `asyncpg`. |
| **Polling callback worker** (30s) | Simpler than APScheduler/Celery for alpha. Replace if you go to production. |
| **Live reasoning panel kept** | Reused from your prior project; talks to FastAPI's `/panel` WS. |

What's intentionally NOT built:
- No real CRM integration (SQLite is your demo CRM).
- No agent dashboard yet — but `objections`, `call_turns`, `callbacks` tables are ready for one.
- No TRAI DND compliance check (add before any real customer pilot).
- Calling-hours window is hardcoded to 10:00–20:30 IST. Edit `app/telephony/cadence.py` to adjust.
- No call-recording auto-download. The `/vobiz/recording-ready` callback receives the MP3 URL but we don't fetch yet.

---

## Repo layout

```
.
├── app/
│   ├── main.py                FastAPI entrypoint
│   ├── config.py              env loading
│   ├── llm/
│   │   ├── key_rotator.py     Cerebras→Groq pool
│   │   └── proxy.py           OpenAI-compatible /llm endpoint
│   ├── crm/
│   │   ├── db.py              SQLite schema
│   │   ├── repository.py      data access
│   │   └── seeds.py           5 test parents + 5 courses + battle card
│   ├── pipecat_bot/
│   │   ├── prompts.py         system prompt builder + tool schema
│   │   ├── call_state.py      log_call_state + schedule_callback handlers
│   │   └── bot.py             Pipecat pipeline assembly
│   ├── telephony/
│   │   ├── vobiz_routes.py    /vobiz/answer, /vobiz/stream, /vobiz/status, recording callbacks
│   │   ├── outbound.py        place_call() via Vobiz REST
│   │   ├── cadence.py         no-pickup retry policy (urban IN)
│   │   └── callback_worker.py 30s polling worker
│   └── panel/ws.py            WebSocket fan-out for the React panel
├── panel/                     React reasoning panel (Vite)
├── scripts/
│   ├── seed_db.py             standalone seeder
│   ├── trigger_call.py        CLI to place one outbound call
│   └── test_llm_proxy.py      smoke test the LLM proxy
├── tests/
│   ├── unit/                  31 unit tests (key rotator, cadence, repo, prompts, call_state)
│   └── integration/           16 integration tests (LLM proxy, panel WS, Vobiz routes, Sarvam, Deepgram, conversation sim)
├── legacy/                    old Node code, kept for reference; not used
├── pyproject.toml
├── pytest.ini
├── .env.example
└── README.md
```

---

## Prerequisites

- Python 3.10+ (tested on 3.14)
- Node 18+ (only for the React panel)
- `ngrok` (or any HTTPS tunnel)
- Vobiz account + a phone number that can place calls to your region
- API keys: Deepgram, Sarvam, plus one of Cerebras / Groq

Install pipecat extras explicitly:

```bash
.venv/bin/pip install "pipecat-ai[deepgram,silero,websocket,openai,sarvam]"
.venv/bin/pip install "pipecat-vobiz>=0.0.3,<0.1"
.venv/bin/pip install python-multipart
```

---

## Setup

```bash
cd post-demo-parent-conversion-agent
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .              # or: pip install -r the deps listed in pyproject.toml
.venv/bin/pip install python-multipart   # form parsing for Vobiz status callbacks
```

> If `pip install -e .` doesn't pick up the Pipecat extras, install explicitly:
> `.venv/bin/pip install "pipecat-ai[deepgram,silero,websocket,openai,sarvam]"`

Copy and fill in env vars:

```bash
cp .env.example .env
# At minimum, populate:
#   CEREBRAS_API_KEY_1 (or GROQ_API_KEY_1)
#   DEEPGRAM_API_KEY
#   SARVAM_API_KEY  (+ SARVAM_TTS_SPEAKER, SARVAM_TTS_MODEL)
#   VOBIZ_AUTH_ID, VOBIZ_AUTH_TOKEN, VOBIZ_PHONE_NUMBER
#   DEMO_PHONE_NUMBER  (your mobile, E.164 — e.g. +9198XXXXXXXX)
#   PUBLIC_URL  (the live https://....ngrok-free.app)
```

Install the panel deps (only if you want the live visualization):

```bash
cd panel && npm install && cd ..
```

---

## Run

Open three terminals.

**1. Tunnel** (Vobiz needs a public WSS URL):

```bash
ngrok http 3000
# Copy the HTTPS URL (e.g. https://abc-1-2-3-4.ngrok-free.app)
# Set PUBLIC_URL in .env to that URL (no trailing slash)
```

**2. Server**:

```bash
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 3000
# On startup: DB is created, seeds run (idempotent), callback worker starts.
# Health: curl localhost:3000/health
```

**3. Panel** (optional, for live reasoning view):

```bash
cd panel && npm run dev
# Open http://localhost:5173
```

---

## Alpha test — placing a call to your phone

1. Confirm `.env` has Vobiz creds + `DEMO_PHONE_NUMBER` set to **your** mobile (E.164, e.g. `+9198XXXXXXXX`).
2. Confirm the server is running and `PUBLIC_URL` is the live ngrok **public HTTPS** URL (not `127.0.0.1:4040` — that's ngrok's local admin dashboard).
3. Trigger a call:

```bash
.venv/bin/python scripts/trigger_call.py
# or:
curl -X POST localhost:3000/trigger-call -H 'Content-Type: application/json' -d '{}'
```

What you should see in the uvicorn log:
- `[vobiz] place_call HTTP 201` and the returned `call_uuid`.
- Once you answer: `[vobiz] /answer CallUUID=...` then `[vobiz] stream start call_uuid=... encoding=audio/x-mulaw sample_rate=8000`.
- After your first reply: `[call_state]` log lines as each `log_call_state` tool call lands.

Pick up. You should hear Aria open with your seeded child's name (default: Mr. Sharma + Aarav + Physics demo with Ms. Kapoor, JEE 2027 target, birthday in 12 days).

To run a different parent persona, edit `DEMO_PHONE_NUMBER` to overwrite one of the seeded numbers, or call `/trigger-call` with `{"phone": "+91..."}` body.

---

## Demo personas seeded

| Phone (or DEMO_PHONE_NUMBER) | Parent | Child | Grade / Target | Demo subject | Birthday |
|---|---|---|---|---|---|
| +919999900001 | Mr. Sharma | Aarav | Class 11 / JEE 2027 | Physics — Ms. Kapoor | +12 days |
| +919999900002 | Mrs. Reddy | Pranavi | Class 12 / JEE 2026 | Chemistry — Mr. Ranjan | +180 days |
| +919999900003 | Mr. Iyer | Diya | Class 11 / NEET 2027 | Biology — Dr. Sen | +3 days |
| +919999900004 | Mrs. Verma | Ishaan | Class 10 / Boards | Maths — Mr. Khanna | +85 days |
| +919999900005 | Mr. Bose | Anaya | Class 9 / Foundation | Science — Ms. Pillai | +28 days |

The birthday-aware logic fires for children within ~30 days; the prompt builder injects a subtle warmth signal, never a price hook.

---

## Tests

```bash
.venv/bin/python -m pytest tests -v
```

- **47/47 pass with your current `.env`** (Sarvam, Deepgram, Cerebras+Groq keys all valid).
- **31 deterministic unit tests** + **16 integration tests**.

The 4 integration tests that hit real services (gated on env keys, all currently passing):
- `tests/integration/test_sarvam_smoke.py` — Sarvam Bulbul TTS produces audio for a Hinglish opening line.
- `tests/integration/test_deepgram_smoke.py` — Deepgram Nova-3 multilingual accepts a 1 s WAV.
- `tests/integration/test_conversation_sim.py` — runs a full 5-turn scripted conversation against the real LLM and asserts the model emits valid `log_call_state` tool calls, the intent trajectory (ambiguous → soft_no → positive), and either schedules a callback or sets `next_step_time` for the parent-requested "kal sham 6 baje" turn. Also asserts a hostile hard-no is respected (no sales pitch in the reply).

---

## Pre-flight checklist before the first real Vobiz call

- [ ] Filled `.env`: Vobiz creds, Sarvam key, Deepgram key, ≥1 Cerebras OR Groq key, `DEMO_PHONE_NUMBER` in **E.164 form** (e.g. `+9198XXXXXXXX`, not bare digits).
- [ ] `ngrok http 3000` running; copied the **public HTTPS** URL (e.g. `https://abcd-1-2-3-4.ngrok-free.app`) into `PUBLIC_URL`. (`127.0.0.1:4040` is ngrok's local dashboard — it won't work.)
- [ ] `uvicorn app.main:app --port 3000` running; `curl localhost:3000/health` returns `{"ok": true}`.
- [ ] Optionally `cd panel && npm install && npm run dev` so you can watch reasoning live at `http://localhost:5173`.
- [ ] Ran `.venv/bin/python -m pytest tests` and all 47 pass.
- [ ] Trial-account caveat: Vobiz trial numbers may only call **verified** destinations; verify your mobile in the Vobiz console.
- [ ] Trigger: `.venv/bin/python scripts/trigger_call.py`.

If the call disconnects after one ring or no audio plays:
- Check `PUBLIC_URL` matches the live ngrok URL (free-tier URLs rotate on restart).
- Tail uvicorn logs — look for `[vobiz] /answer`, then `[vobiz] stream start … encoding=… sample_rate=…`. If those don't appear, Vobiz couldn't reach your tunnel.
- Vobiz `place_call` returning 401 → check `VOBIZ_AUTH_ID` / `VOBIZ_AUTH_TOKEN`.
- WS opens but no audio from Aria → likely Sarvam TTS or Deepgram STT; the smoke tests catch credential issues, but a wrong `SARVAM_TTS_MODEL` (e.g. `bulbul:v3` when your account only has v2) will silently fail.

---

## What gets logged where

| Event | Table | When |
|---|---|---|
| Outbound call placed | `call_attempts` | `place_call()` |
| Status from Vobiz | `call_attempts.status` | every status callback |
| Each parent turn | `call_turns` | every `log_call_state` |
| Final outcome | `objections` | last `log_call_state` (`final: true`) |
| Scheduled retry | `callbacks` | on no-answer/busy/failed |
| Parent-requested callback | `callbacks` | on `schedule_callback_request` |
| Nurture follow-up | `callbacks` (reason=nurture_followup) | after MAX_NO_ANSWER_ATTEMPTS |

A simple counsellor dashboard later can just `SELECT … FROM objections JOIN parents …` — the schema is intentionally ready for that.

---

## Future improvements (deliberately not in alpha)

- DND / TRAI compliance check before each dial.
- AMD (answering-machine detection) → voicemail-aware TwiML branch (we set `machine_detection=DetectMessageEnd` but don't yet do anything specific with the result).
- Switch to APScheduler or a job queue for the callback worker once volume > ~100/day.
- Cache the system prompt's stable prefix (parent + battle card) using Anthropic-style caching when LLM provider supports it.
- Replace the React panel's polling with the proper agent dashboard backed by the SQL views.

---

## Where the legacy Vapi code lives

`legacy/` contains the original Node/Vapi prototype. Untouched. Read for design context only; nothing in `app/` depends on it.
