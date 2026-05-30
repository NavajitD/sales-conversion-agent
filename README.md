# PS4 Post-Demo Conversion Voice Agent

Aria — a Hinglish voice agent that calls parents post-demo, handles real objections, and lands a concrete next step. Includes a live reasoning panel showing intent classification, strategy, sentiment arc, and a CRM card that auto-fills at call end.

## Prerequisites

- Node.js 18+
- Vapi account (with a phone number)
- Sarvam API key
- OpenAI API key
- ngrok (for the Vapi webhook tunnel)

## Setup

```bash
cd ps4-conversion-agent
cp .env.example .env
# Fill in all values in .env
npm install
```

## Step 1 — Start the tunnel

```bash
ngrok http 3000
# Copy the https://xxxx.ngrok.io URL → set SERVER_PUBLIC_URL in .env
```

## Step 2 — Start the server

```bash
npm run server
# Verify: curl localhost:3000/health
```

## Step 3 — Create the Vapi assistant

```bash
npm run create-assistant
# Copy the printed assistant ID → set VAPI_ASSISTANT_ID in .env
```

## Step 4 — Open the panel

```bash
npm run panel
# Open http://localhost:5173 full-screen on the demo machine
```

**Test the panel with a fake event:**
```bash
curl -X POST localhost:3000/vapi/tool \
  -H 'Content-Type: application/json' \
  -d '{"message":{"toolCallList":[{"id":"t1","function":{"name":"log_call_state","arguments":"{\"utterance\":\"Haan accha tha par sochna padega\",\"intent_classification\":\"ambiguous\",\"intent_confidence\":0.65,\"sentiment\":\"neutral\",\"objection_primary\":\"stalling\",\"strategy_applied\":\"disambiguation_probe\"}"}}]}}'
```

## Step 5 — Trigger a demo call

```bash
# Set DEMO_PHONE_NUMBER in .env first
npm run trigger-call
```

---

## Demo rehearsal script (5-turn arc)

Run this three times before the presentation. Have someone play the parent.

| Turn | Parent says | Panel should show |
|------|-------------|-------------------|
| 1 | "Haan accha tha, par sochna padega." | AMBIGUOUS · disambiguation_probe |
| 2 | "Sach kahun toh fees thodi zyada lag rahi hai." | SOFT_NO · price · value_roi_reframe |
| 3 | "Value samajh aata hai, par ek saath dena heavy hai." | SOFT_NO · price · payment_plan |
| 4 | "Theek hai, ek aur demo ho sakta hai alag teacher ke saath?" | POSITIVE · second_session_offer · warm |
| 5 | Agent closes | final=true · second_session_booked · CRM card fills |

---

## Plan B (if Sarvam-into-Vapi stalls past 2 hours)

Switch orchestration to **Retell**. Keep the same system prompt, same `log_call_state` webhook, same panel. Change only the telephony layer. Accept weaker Hindi quality; lean harder on the reasoning-panel wow.

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key (GPT-4o) |
| `SARVAM_API_KEY` | Sarvam API key (STT + TTS) |
| `VAPI_API_KEY` | Vapi API key |
| `VAPI_PHONE_NUMBER_ID` | Vapi phone number ID for outbound calls |
| `VAPI_ASSISTANT_ID` | Filled after `npm run create-assistant` |
| `SERVER_PUBLIC_URL` | ngrok URL pointing at localhost:3000 |
| `SERVER_PORT` | Express server port (default: 3000) |
| `PANEL_PORT` | Vite dev server port (default: 5173) |
| `DEMO_PHONE_NUMBER` | Phone number to call (E.164 format, e.g. +919876543210) |

---

## Latency tuning

- If STT response feels slow: Sarvam WS may send `partial` transcripts before finals. The bridge already forwards them with `transcriptType: "partial"` so the panel text starts updating sooner.
- If TTS sounds rushed: change `pace` in `agent/sarvam-tts-bridge.js` (0.9 sounds natural for a sales call).
- If TTS sounds tinny: switch speaker from `ritu` to `priya` or `neha` in the same file.
