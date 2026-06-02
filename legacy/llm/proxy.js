'use strict';

const fetch = require('node-fetch');
const rotator = require('./keyRotator');

// Hold phrases in Hinglish — spoken aloud by TTS if we must rotate mid-turn.
const HOLD_PHRASES = [
  'Ek second, please hold.',
  'Ek moment, main check kar rahi hoon.',
  'Bas ek second rukiye.',
];
let holdIdx = 0;
function nextHold() {
  return HOLD_PHRASES[holdIdx++ % HOLD_PHRASES.length];
}

// Build a well-formed SSE chunk that Vapi's custom-LLM parser will accept.
function sseChunk(content) {
  return (
    'data: ' +
    JSON.stringify({
      id: `chatcmpl-hold-${Date.now()}`,
      object: 'chat.completion.chunk',
      created: Math.floor(Date.now() / 1000),
      model: 'key-rotator',
      choices: [{ index: 0, delta: { content }, finish_reason: null }],
    }) +
    '\n\n'
  );
}

function sseDone() {
  return 'data: [DONE]\n\n';
}

function setupSseHeaders(res) {
  if (!res.headersSent) {
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
  }
}

// ── Main handler ─────────────────────────────────────────────────────────────
// Vapi POSTs an OpenAI-compatible chat/completions body here.
// We forward it to Cerebras (priority) or Groq (fallback), rotating keys on
// rate-limit / quota errors. On a mid-stream error we inject a hold phrase so
// TTS bridges the gap; the next Vapi turn lands on the rotated key.

module.exports = async function handleLlmRequest(req, res) {
  const body = req.body;
  const useStream = body.stream !== false; // Vapi almost always sends stream:true

  const maxAttempts = Math.max(rotator.poolSize(), 1) + 1;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const entry = rotator.getCurrent();
    if (!entry) {
      if (!res.headersSent) return res.status(503).json({ error: 'All LLM API keys exhausted' });
      if (useStream && !res.writableEnded) { res.write(sseDone()); res.end(); }
      return;
    }

    const { provider, key, label } = entry;
    const url = `${rotator.getBaseUrl(provider)}/chat/completions`;
    const model = rotator.getModel(provider);

    try {
      const llmRes = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${key}`,
        },
        // Override model with our chosen one; preserve everything else (tools, messages, etc.)
        body: JSON.stringify({ ...body, model }),
      });

      // ── Non-2xx ──────────────────────────────────────────────────────────
      if (!llmRes.ok) {
        const errText = await llmRes.text();
        console.error(`[llm] ${label} HTTP ${llmRes.status}:`, errText.slice(0, 300));

        if (rotator.isQuotaError(llmRes.status, errText)) {
          rotator.rotateNext();

          if (!res.headersSent) {
            // Nothing sent yet → silently retry with next key
            continue;
          }

          // We already started a streaming response — inject hold phrase, close stream.
          // Next Vapi turn will use the rotated key automatically.
          if (useStream && !res.writableEnded) {
            res.write(sseChunk(' ' + nextHold()));
            res.write(sseDone());
            res.end();
          }
          return;
        }

        // Non-quota error: propagate as-is
        if (!res.headersSent) return res.status(llmRes.status).send(errText);
        if (useStream && !res.writableEnded) { res.write(sseDone()); res.end(); }
        return;
      }

      // ── Success ──────────────────────────────────────────────────────────
      if (attempt > 0) console.log(`[llm] Active key after ${attempt} rotation(s): ${label}`);

      if (useStream) {
        setupSseHeaders(res);

        // Prefix a hold phrase so TTS has something to say during the rotation delay
        if (attempt > 0) res.write(sseChunk(nextHold() + ' '));

        // Pipe the provider's SSE stream straight through
        await new Promise((resolve, reject) => {
          llmRes.body.on('data', (chunk) => {
            if (!res.writableEnded) res.write(chunk);
          });
          llmRes.body.on('end', () => {
            if (!res.writableEnded) res.end();
            resolve();
          });
          llmRes.body.on('error', (err) => {
            console.error(`[llm] Mid-stream error from ${label}:`, err.message);
            rotator.rotateNext();
            if (!res.writableEnded) {
              res.write(sseChunk(' ' + nextHold()));
              res.write(sseDone());
              res.end();
            }
            reject(err);
          });
          // Client closed connection — resolve quietly
          res.on('close', resolve);
        });
      } else {
        // Non-streaming: pass the JSON body through unmodified
        const json = await llmRes.json();
        return res.json(json);
      }

      return; // done

    } catch (err) {
      // Network / timeout error before or during streaming
      if (res.headersSent) return; // mid-stream path already handled above
      console.error(`[llm] ${label} error:`, err.message);
      rotator.rotateNext();
      // loop will retry
    }
  }

  if (!res.headersSent) res.status(503).json({ error: 'LLM request failed after all retries' });
};
