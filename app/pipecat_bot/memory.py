"""Within-call conversational memory for Aria.

Three layers of memory, ordered fastest → slowest:

  1. Raw history    — Pipecat's LLMContext keeps every (user, assistant)
                      message. For a typical 5–15 min call (<30 turns), the
                      whole history fits in any modern context window
                      (Cerebras gpt-oss-120b, Gemini Flash, Groq llama-3.3-70b
                      all have ≥128k tokens). No compression needed. The
                      pipeline already wires this in bot.py.

  2. Structured facts (this file) — a CallMemory dataclass that tracks the
                      handful of things the LLM tends to forget OR repeat:
                       • child's name + spelling already used
                       • objection arc so far (which plays we've already run)
                       • whether price has been mentioned (so we don't anchor
                         twice)
                       • parent-asked callback time captured
                       • bot-promised commitments (so we honour them)
                       • topics already explicitly closed (so we don't reopen)
                      This block is rebuilt each turn and prepended to the
                      system prompt, giving the LLM an authoritative "what
                      do we know so far" view independent of how it might
                      misremember the raw history.

  3. Cross-call RAG (Phase 3b — separate module) — soft-no transcripts from
                      past calls, retrieved by parent profile similarity at
                      call start and injected as in-context examples.

Why structured facts on top of raw history? Even with full history, LLMs
empirically:
  • drift on names ("Aarav" → "Arav" mid-call)
  • re-open objections the parent already declined ("aaj hi enrol kar lijiye"
    after the parent already said "nahi, kal call")
  • repeat the same offer twice (50% off mentioned at turn 4, then at turn 11)

A small, deterministic facts block solves all three at zero extra LLM calls.

Updates happen via the existing `log_call_state` tool: the LLM already emits
its read of the turn (intent, objection, sentiment, next_step). We just route
that into CallMemory and use it to render the facts block on the next turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CallMemory:
    """Authoritative within-call state for prompt injection.

    Updated by handle_log_call_state in call_state.py after every parent turn.
    Read by build_facts_block at the start of the next turn before LLM call.

    Field rationale:
      child_name          Authoritative spelling; bot must not drift.
      ran_plays           Objection plays we've already executed. Prevents
                          the LLM from running the same play twice.
      mentioned_price     "हमारी fee chaurasi hazaar" said? If yes, do not
                          re-anchor; switch to value/EMI framing.
      mentioned_offer     "10% off if enrolled in 48h" said? If yes, do not
                          repeat — feels desperate.
      objection_count     Total non-trivial objections raised by parent.
                          Hits 3 → bot must stop pushing and offer callback.
      closed_topics       Topics the parent explicitly closed (e.g. "spouse
                          discussion will happen tonight"). Reopening = rude.
      promises_made       e.g. "kal 7 baje call karenge". The bot must
                          honour these at call end (schedule the callback).
      parent_requested_callback_iso  parsed from a parent ask
      hard_stop           If True, bot must exit warmly without further pitch.
    """

    child_name: str = ""
    parent_name: str = ""
    ran_plays: set[str] = field(default_factory=set)
    mentioned_price: bool = False
    mentioned_offer: bool = False
    objection_count: int = 0
    closed_topics: set[str] = field(default_factory=set)
    promises_made: list[str] = field(default_factory=list)
    parent_requested_callback_iso: str | None = None
    hard_stop: bool = False
    turn_index: int = 0
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def update_from_turn(self, event: dict[str, Any]) -> None:
        """Apply the LLM's structured read of the latest turn to memory.

        `event` is the dict the LLM sends to log_call_state. We extract the
        fields that influence subsequent turns; we do NOT trust the LLM to
        manage memory itself.
        """
        self.turn_index += 1
        play = (event.get("strategy_applied") or "").strip().lower()
        if play and play != "none":
            self.ran_plays.add(play)
        obj = (event.get("objection_primary") or "").strip().lower()
        if obj and obj != "none":
            self.objection_count += 1
            # Heuristic: if the bot's reply (carried as counselor_notes) contains
            # the spoken fee or offer text, mark those as "said". The LLM is
            # asked to keep counselor_notes short and factual, so this works.
            notes = (event.get("counselor_notes") or "").lower()
            if any(
                k in notes
                for k in ("rupaye", "fee", "price", "hazaar", "thousand")
            ):
                self.mentioned_price = True
            if any(k in notes for k in ("offer", "discount", "% off", "scholarship")):
                self.mentioned_offer = True

        intent = (event.get("intent_classification") or "").strip().lower()
        if intent == "hard_no":
            self.hard_stop = True

        # next_step_time captures parent-requested callback timestamps; we
        # forward to schedule_callback when the LLM finally calls the tool.
        nst = event.get("next_step_time")
        if nst and not self.parent_requested_callback_iso:
            self.parent_requested_callback_iso = nst

    def build_facts_block(self) -> str:
        """Render the facts block to prepend to the system prompt.

        Keep it tight — every token costs latency. Skip empty fields rather
        than emit "ran_plays: (none)". The LLM treats this as ground truth.
        """
        lines: list[str] = []
        lines.append("# CALL STATE — TREAT AS AUTHORITATIVE")
        lines.append(f"- Turn: {self.turn_index}")
        if self.parent_name:
            lines.append(f"- Parent name (use this spelling): {self.parent_name}")
        if self.child_name:
            lines.append(f"- Child name (use this spelling): {self.child_name}")
        if self.ran_plays:
            lines.append(
                f"- Plays already run (do NOT run again unless explicitly "
                f"re-asked): {', '.join(sorted(self.ran_plays))}"
            )
        if self.mentioned_price:
            lines.append("- Price already anchored. Do NOT restate fee. Move to value/EMI/ROI framing.")
        if self.mentioned_offer:
            lines.append("- Offer already stated. Do NOT repeat — feels desperate.")
        if self.objection_count >= 3:
            lines.append(
                f"- Objection cycles: {self.objection_count}. STOP pushing. "
                "Offer a senior-counselor callback and close warmly."
            )
        elif self.objection_count > 0:
            lines.append(f"- Objection cycles so far: {self.objection_count}/3")
        if self.closed_topics:
            lines.append(
                f"- Topics parent closed (do NOT reopen): {', '.join(sorted(self.closed_topics))}"
            )
        if self.promises_made:
            lines.append(
                "- Promises made to parent (must honour at close):\n  "
                + "\n  ".join(f"• {p}" for p in self.promises_made)
            )
        if self.parent_requested_callback_iso:
            lines.append(
                f"- Parent requested callback at: {self.parent_requested_callback_iso}"
            )
        if self.hard_stop:
            lines.append(
                "- HARD STOP: parent has said hard no. Exit warmly NOW. "
                "Do NOT attempt any further pitch. Capture reason in ONE light "
                "question if tone allows, then close."
            )
        return "\n".join(lines)


def fresh_memory(parent: dict[str, Any], child: dict[str, Any]) -> CallMemory:
    """Initial memory at call start: names locked from CRM."""
    return CallMemory(
        child_name=(child or {}).get("name", "") or "",
        parent_name=(parent or {}).get("name", "") or "",
    )
