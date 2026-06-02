"""Pipecat pipeline: Vobiz Media Streams ↔ Deepgram STT ↔ LLM ↔ Sarvam TTS.

STT: Deepgram Nova-3 (multi-language Hinglish codemix, interim results, VAD).
TTS: Sarvam Bulbul v3 (Indian-accent Hinglish, single voice from env).

ElevenLabs was previously the primary but is removed end-to-end: the build
owner's account ran out of credits and the realtime sessions failed silently
in production (server-side closes with quota_exceeded after 0.5 s, but the
client treats the session as live — bot speaks into a closed pipe). See
FUTURE.md for re-enable steps if credits return.

LLM is our local OpenAI-compatible /llm proxy (key-rotating across Groq →
Cerebras → Gemini). Pipecat's OpenAILLMService talks OpenAI Chat Completions;
we set base_url to point at our FastAPI app.

`run_bot` is invoked by the Vobiz websocket route in `app.telephony.vobiz_routes`
*after* parse_vobiz_start has consumed the initial handshake.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    EndFrame,
    EndTaskFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMTextFrame,
    MetricsFrame,
    TTSSpeakFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import ProcessingMetricsData, TTFBMetricsData
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.serializers.vobiz import VobizFrameSerializer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)

from app.config import (
    DEEPGRAM_API_KEY,
    SARVAM_API_KEY,
    SARVAM_TTS_MODEL,
    SARVAM_TTS_SPEAKER,
    SERVER_PORT,
    VOBIZ_AUTH_ID,
    VOBIZ_AUTH_TOKEN,
    VOBIZ_L16_ENDIAN,
)
from app.crm import repository
from app.panel.ws import hub as _panel_hub
from app.pipecat_bot.call_state import (
    CallContext,
    handle_log_call_state,
    handle_schedule_callback_request,
)
from app.pipecat_bot.prompts import ALL_TOOLS, build_system_prompt


class AgentSpeechBroadcaster(FrameProcessor):
    """Accumulate LLM text deltas and broadcast the final assistant turn to /panel.

    Sits between the LLM and TTS. Broadcasts via `_panel_hub.broadcast` which
    fans out to viewers using fire-and-forget tasks — no added bot latency.
    Forwards every frame through unchanged.
    """

    def __init__(self) -> None:
        super().__init__()
        self._buf: list[str] = []

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMTextFrame) and getattr(frame, "text", None):
            self._buf.append(frame.text)
        elif isinstance(frame, LLMFullResponseEndFrame):
            text = "".join(self._buf).strip()
            self._buf.clear()
            if text:
                # Fire-and-forget so we don't block the frame chain.
                asyncio.create_task(
                    _panel_hub.broadcast({"kind": "agent_speech", "text": text})
                )
        await self.push_frame(frame, direction)


class LatencyLogger(FrameProcessor):
    """Logs component-wise and end-to-end turn latency at INFO level.
    Also triggers greeting on first user speech and absorbs that first
    utterance so the LLM doesn't produce a duplicate greeting."""

    def __init__(self, call_uuid: str, greeting_callback=None) -> None:
        super().__init__()
        self._call_uuid = call_uuid
        self._user_stopped_at: float | None = None
        self._greeting_callback = greeting_callback
        # When True, drop the first transcription (the "hello" that triggers greeting)
        self._absorb_next_transcript = greeting_callback is not None

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame):
            if self._absorb_next_transcript and frame.text:
                # First real transcript — trigger greeting and absorb this turn
                self._absorb_next_transcript = False
                if self._greeting_callback:
                    cb = self._greeting_callback
                    self._greeting_callback = None
                    asyncio.create_task(cb())
                logger.info(f"[latency] Absorbed first utterance: \"{frame.text[:60]}\"")
                return  # Don't forward to LLM
            if frame.text:
                logger.info(f"[latency] STT transcript ready: \"{frame.text[:60]}\"")
                # Mirror the parent's ACTUAL STT turn to the live panel. Fire-and-
                # forget (never awaited in the frame path) so the voice pipeline is
                # never blocked — same pattern as AgentSpeechBroadcaster. This makes
                # the transcript complete instead of depending on the LLM echoing
                # each turn back via log_call_state.
                asyncio.create_task(
                    _panel_hub.broadcast({"kind": "user_transcript", "text": frame.text})
                )

        elif isinstance(frame, UserStartedSpeakingFrame):
            pass  # Just log, don't use for greeting trigger

        elif isinstance(frame, UserStoppedSpeakingFrame):
            if not self._absorb_next_transcript:
                self._user_stopped_at = time.monotonic()

        elif isinstance(frame, MetricsFrame):
            for m in frame.data:
                if isinstance(m, TTFBMetricsData):
                    logger.info(f"[latency] {m.processor} TTFB {m.value * 1000:.0f}ms")
                elif isinstance(m, ProcessingMetricsData):
                    logger.info(f"[latency] {m.processor} total {m.value * 1000:.0f}ms")

        elif isinstance(frame, BotStartedSpeakingFrame) and self._user_stopped_at:
            e2e_ms = (time.monotonic() - self._user_stopped_at) * 1000
            logger.info(f"[latency] end-to-end (speech-end → first audio): {e2e_ms:.0f}ms")
            self._user_stopped_at = None

        await self.push_frame(frame, direction)


def _internal_llm_base_url() -> str:
    """Same-container loopback URL for the /llm proxy.

    On Cloud Run, uvicorn binds to $PORT (default 8080 in our Dockerfile),
    NOT to app.config.SERVER_PORT (which is the local-dev default 3000).
    We must prefer $PORT so the bot's loopback HTTP call hits the actual
    uvicorn listener; otherwise every LLM call after the pre-baked greeting
    fails with `Connection error` and the call goes silent from turn 2.
    """
    import os
    port = os.environ.get("PORT") or str(SERVER_PORT)
    return f"http://127.0.0.1:{port}/llm"


def _create_stt_tts(sample_rate: int) -> tuple:
    """Create STT + TTS services. Deepgram Nova-3 STT + Sarvam Bulbul v3 TTS."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set — STT cannot start")
    if not SARVAM_API_KEY:
        raise RuntimeError("SARVAM_API_KEY not set — TTS cannot start")
    stt = DeepgramSTTService(
        api_key=DEEPGRAM_API_KEY,
        settings=DeepgramSTTService.Settings(
            model="nova-3",
            language="multi",
            smart_format=True,
            interim_results=True,
            endpointing=200,
            diarize=False,
        ),
    )
    tts = SarvamTTSService(
        api_key=SARVAM_API_KEY,
        settings=SarvamTTSService.Settings(
            model=SARVAM_TTS_MODEL,
            voice=SARVAM_TTS_SPEAKER,
        ),
    )
    logger.info("[stt/tts] Using Deepgram Nova-3 + Sarvam Bulbul v3")
    return stt, tts, "deepgram+sarvam"


async def _gather_call_context(
    parent_phone: str, parent_id: str | None = None
) -> dict[str, Any]:
    # The persona the agent acts on is identified by `parent_id` (the seeded
    # CRM doc, which is itself a phone-shaped ID). `parent_phone` is the
    # *visitor's* number we dialled — it is NOT in the CRM, so we must look up
    # context by parent_id and only fall back to the phone for the legacy
    # alpha path where the visitor's number == the seeded persona.
    parent = None
    if parent_id:
        parent = await repository.get_parent(parent_id)
    if not parent:
        parent = await repository.get_parent_by_phone(parent_phone)
    if not parent:
        raise RuntimeError(
            f"No parent found for parent_id={parent_id!r} / phone={parent_phone!r}"
        )
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    if not demo:
        raise RuntimeError(f"No demo found for parent {parent['id']}")
    child = await repository.get_child(demo["child_id"])
    battlecard = await repository.get_competitor_battlecard()
    return {"parent": parent, "child": child, "demo": demo, "battlecard": battlecard}


async def run_bot(
    websocket,
    *,
    call_uuid: str,
    stream_id: str,
    encoding: str,
    sample_rate: int,
    parent_phone: str,
    parent_id: str | None = None,
) -> None:
    ctx_data = await _gather_call_context(parent_phone, parent_id)
    parent = ctx_data["parent"]
    child = ctx_data["child"]
    demo = ctx_data["demo"]
    battlecard = ctx_data["battlecard"]

    attempt = await repository.get_call_attempt_by_sid(call_uuid)
    if attempt is None:
        attempt_id = await repository.create_call_attempt(
            parent_id=parent["id"], demo_id=demo["id"], twilio_call_sid=call_uuid
        )
    else:
        attempt_id = attempt["id"]
    await repository.update_call_attempt_status(attempt_id, "in-progress")

    call_ctx = CallContext(
        call_attempt_id=attempt_id,
        parent_id=parent["id"],
        demo_id=demo["id"],
    )

    system_prompt = build_system_prompt(
        parent=parent, child=child, demo=demo, battlecard=battlecard
    )

    # ── Transport: Vobiz Media Streams via Pipecat FastAPI websocket ────────
    serializer = VobizFrameSerializer(
        stream_id=stream_id,
        call_id=call_uuid,
        auth_id=VOBIZ_AUTH_ID,
        auth_token=VOBIZ_AUTH_TOKEN,
        params=VobizFrameSerializer.InputParams(
            vobiz_sample_rate=sample_rate,
            encoding=encoding,
            sample_rate=None,         # let Pipecat resample to pipeline rate
            l16_byte_order=VOBIZ_L16_ENDIAN,
            auto_hang_up=True,
        ),
    )
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            serializer=serializer,
        ),
    )

    # ── STT + TTS: ElevenLabs primary, Deepgram+Sarvam fallback ────────────────
    stt, tts, provider_label = _create_stt_tts(sample_rate)

    # ── LLM: local key-rotating proxy via OpenAILLMService ─────────────────
    llm = OpenAILLMService(
        api_key="local-rotator",
        base_url=_internal_llm_base_url(),
        model="ignored-overridden-by-proxy",
        params=OpenAILLMService.InputParams(temperature=0.4),
    )

    # ── Tool handlers ───────────────────────────────────────────────────────
    async def _tool_log_call_state(params):
        await handle_log_call_state(call_ctx, params.arguments)
        await params.result_callback({"ok": True})

    async def _tool_schedule_callback(params):
        out = await handle_schedule_callback_request(call_ctx, params.arguments)
        await params.result_callback(out)

    async def _tool_end_call(params):
        await params.result_callback({"ok": True})
        await task.queue_frames([EndTaskFrame()])

    llm.register_function("log_call_state", _tool_log_call_state)
    llm.register_function("schedule_callback_request", _tool_schedule_callback)
    llm.register_function("end_call", _tool_end_call)

    # Warm greeting spoken instantly without waiting for LLM. Built per-call
    # from the persona so we never address the wrong child (the name/subject
    # MUST match this parent's demo). Keep it SHORT (~2s).
    greet_child = (child or {}).get("name") or demo.get("child_name") or "आपके बच्चे"
    greet_subject = demo.get("subject") or "demo"
    INSTANT_GREETING = (
        f"नमस्ते! मैं Priya, Vedantu से। "
        f"आज {greet_child} ने हमारा {greet_subject} demo attend किया था, कैसा लगा उन्हें?"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        # Seed context so LLM knows greeting was already spoken — do NOT re-greet.
        {"role": "assistant", "content": INSTANT_GREETING},
    ]
    context = LLMContext(messages=messages, tools=ALL_TOOLS)
    # Pipecat 1.x: VAD goes on LLMUserAggregatorParams, not the transport.
    # Moderate thresholds — ElevenLabs server-side VAD handles STT commit,
    # local VAD is only for interruption detection.
    from pipecat.audio.vad.vad_analyzer import VADParams
    from pipecat.turns.user_start.min_words_user_turn_start_strategy import MinWordsUserTurnStartStrategy
    from pipecat.turns.user_turn_strategies import UserTurnStrategies

    vad = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.80,   # default 0.7 — slightly above default
            start_secs=0.25,   # default 0.2 — need 250ms sustained speech
            stop_secs=0.2,     # default 0.2 — standard (ElevenLabs VAD handles STT)
            min_volume=0.6,    # default 0.6 — standard threshold
        )
    )
    # Use MinWords strategy: require 3+ words to interrupt the bot mid-speech.
    # This prevents backchannels like "अच्छा", "ठीक है" from cutting the bot off.
    # When bot is NOT speaking, 1 word is enough to start a turn (default behavior).
    turn_strategies = UserTurnStrategies(
        start=[MinWordsUserTurnStartStrategy(min_words=3)],
    )
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad,
            user_turn_strategies=turn_strategies,
        ),
    )

    # ── Greeting logic: wait for user to say hello, or 3s timeout ──────────
    # Defined early so latency_logger can reference _send_greeting.
    _greeting_sent = asyncio.Event()
    # task is set after PipelineTask is created (forward ref via list)
    _task_ref: list[PipelineTask | None] = [None]

    async def _send_greeting():
        """Send greeting if not already sent."""
        if _greeting_sent.is_set():
            return
        _greeting_sent.set()
        logger.info(f"[bot] Sending greeting for call_uuid={call_uuid}")
        if _task_ref[0]:
            await _task_ref[0].queue_frames([TTSSpeakFrame(text=INSTANT_GREETING, append_to_context=False)])

    # This is an OUTBOUND call — the agent speaks first the moment the parent
    # picks up. We greet immediately on connect rather than waiting for the
    # parent to say "hello" (the old 3s timeout was the source of the long
    # pause before Aria spoke). No greeting_callback → LatencyLogger does NOT
    # absorb the parent's first utterance, so their opening reply is no longer
    # dropped from the transcript.
    latency_logger = LatencyLogger(call_uuid, greeting_callback=None)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            latency_logger,          # captures STT-done, UserStopped, MetricsFrames, BotStarted
            context_aggregator.user(),
            llm,
            AgentSpeechBroadcaster(),  # mirrors LLM text to /panel as kind:"agent_speech"
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,    # Vobiz wire rate (8 kHz µ-law)
            audio_out_sample_rate=sample_rate,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )
    _task_ref[0] = task  # allow _send_greeting to queue frames

    @transport.event_handler("on_client_connected")
    async def _on_connect(transport, client):
        logger.info(f"[bot] Vobiz stream connected call_uuid={call_uuid}")
        # Greet right away. A short delay only lets the media stream warm up so
        # the first syllable isn't clipped — far less than the old 3s wait.
        async def _greet_now():
            await asyncio.sleep(0.3)
            await _send_greeting()
        asyncio.create_task(_greet_now())

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnect(transport, client):
        logger.info(f"[bot] Vobiz stream disconnected call_uuid={call_uuid}")
        # Caller hung up — cancel immediately; any in-flight TTS is undeliverable.
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    try:
        await runner.run(task)
    finally:
        cur_attempt = await repository.get_call_attempt_by_sid(call_uuid)
        if cur_attempt and cur_attempt.get("status") == "in-progress":
            await repository.update_call_attempt_status(attempt_id, "completed")
