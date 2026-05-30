'use strict';

// Cerebras first, then Groq as fallback.
// Models chosen for Hindi/Hinglish conversational reasoning:
//   Cerebras: llama-3.3-70b (best multilingual, fast inference chip)
//   Groq:     llama-3.3-70b-versatile (same underlying model on Groq infra)

const CEREBRAS_BASE = 'https://api.cerebras.ai/v1';
const GROQ_BASE = 'https://api.groq.com/openai/v1';

const CEREBRAS_MODEL = 'llama-3.3-70b';
const GROQ_MODEL = 'llama-3.3-70b-versatile';

let pool = [];
let currentIdx = 0;

function init() {
  pool = [];
  currentIdx = 0;

  for (let i = 1; i <= 3; i++) {
    const k = process.env[`CEREBRAS_API_KEY_${i}`];
    if (k && k.trim()) {
      pool.push({ provider: 'cerebras', key: k.trim(), label: `cerebras-${i}` });
    }
  }
  for (let i = 1; i <= 3; i++) {
    const k = process.env[`GROQ_API_KEY_${i}`];
    if (k && k.trim()) {
      pool.push({ provider: 'groq', key: k.trim(), label: `groq-${i}` });
    }
  }

  if (pool.length === 0) {
    console.warn('[llm] WARNING: No Cerebras or Groq API keys configured — set CEREBRAS_API_KEY_1..3 / GROQ_API_KEY_1..3 in .env');
  } else {
    console.log(`[llm] Key pool (${pool.length}): ${pool.map(e => e.label).join(', ')}`);
  }
}

function getCurrent() {
  return currentIdx < pool.length ? pool[currentIdx] : null;
}

function rotateNext() {
  if (currentIdx >= pool.length) return null;
  const exhausted = pool[currentIdx];
  currentIdx++;
  const next = getCurrent();
  if (next) {
    console.log(`[llm] Key rotated: ${exhausted.label} → ${next.label}`);
  } else {
    console.error(`[llm] All keys exhausted after ${exhausted.label}`);
  }
  return next;
}

function getBaseUrl(provider) {
  return provider === 'cerebras' ? CEREBRAS_BASE : GROQ_BASE;
}

function getModel(provider) {
  return provider === 'cerebras' ? CEREBRAS_MODEL : GROQ_MODEL;
}

// Matches rate-limit / quota / credit exhaustion from any of these providers.
function isQuotaError(status, text) {
  if (status === 402 || status === 429) return true;
  const t = String(text).toLowerCase();
  return (
    t.includes('rate_limit') ||
    t.includes('ratelimit') ||
    t.includes('quota') ||
    t.includes('credits') ||
    t.includes('limit_exceeded') ||
    t.includes('insufficient_quota') ||
    t.includes('too many requests')
  );
}

// Expose pool size for MAX_ATTEMPTS cap in proxy.
function poolSize() {
  return pool.length;
}

module.exports = { init, getCurrent, rotateNext, getBaseUrl, getModel, isQuotaError, poolSize };
