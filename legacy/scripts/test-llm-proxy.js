#!/usr/bin/env node
'use strict';

/**
 * Tests for the LLM key-rotation module.
 *
 * Section 1 — unit tests for keyRotator (no network calls)
 * Section 2 — integration test: mock "LLM API" server that returns 429 on the
 *             first two keys, then 200 on the third, verifying seamless rotation
 * Section 3 — live smoke test (skipped if no real keys are in .env)
 */

require('dotenv').config({ path: require('path').join(__dirname, '../.env') });

const assert = require('assert').strict;
const http = require('http');
const express = require('express');

let passed = 0;
let failed = 0;

function ok(label, condition) {
  if (condition) {
    console.log(`  ✓ ${label}`);
    passed++;
  } else {
    console.error(`  ✗ ${label}`);
    failed++;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 1: keyRotator unit tests
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n── Section 1: keyRotator unit tests ─────────────────────────────');

// Inject fake keys
process.env.CEREBRAS_API_KEY_1 = 'ck1';
process.env.CEREBRAS_API_KEY_2 = 'ck2';
process.env.CEREBRAS_API_KEY_3 = 'ck3';
process.env.GROQ_API_KEY_1 = 'gk1';
process.env.GROQ_API_KEY_2 = 'gk2';
process.env.GROQ_API_KEY_3 = 'gk3';

// Require fresh module (wipe from cache so re-init works)
delete require.cache[require.resolve('../llm/keyRotator')];
const rotator = require('../llm/keyRotator');
rotator.init();

ok('initial key is cerebras-1', rotator.getCurrent()?.label === 'cerebras-1');
ok('initial provider is cerebras', rotator.getCurrent()?.provider === 'cerebras');

rotator.rotateNext();
ok('after 1 rotation → cerebras-2', rotator.getCurrent()?.label === 'cerebras-2');

rotator.rotateNext();
ok('after 2 rotations → cerebras-3', rotator.getCurrent()?.label === 'cerebras-3');

rotator.rotateNext();
ok('after 3 rotations (all Cerebras gone) → groq-1', rotator.getCurrent()?.label === 'groq-1');

rotator.rotateNext();
ok('after 4 rotations → groq-2', rotator.getCurrent()?.label === 'groq-2');

rotator.rotateNext();
ok('after 5 rotations → groq-3', rotator.getCurrent()?.label === 'groq-3');

rotator.rotateNext();
ok('after 6 rotations → null (all exhausted)', rotator.getCurrent() === null);

ok('429 is quota error', rotator.isQuotaError(429, ''));
ok('402 is quota error', rotator.isQuotaError(402, ''));
ok('"rate_limit" body is quota error', rotator.isQuotaError(200, 'rate_limit exceeded'));
ok('"quota" body is quota error', rotator.isQuotaError(200, 'quota reached'));
ok('"credits" body is quota error', rotator.isQuotaError(200, 'insufficient credits'));
ok('"too many requests" body is quota error', rotator.isQuotaError(200, 'too many requests'));
ok('500 internal error is NOT quota error', !rotator.isQuotaError(500, 'internal server error'));
ok('401 unauthorized is NOT quota error', !rotator.isQuotaError(401, 'invalid api key'));

ok('getModel cerebras → llama-3.3-70b', rotator.getModel('cerebras') === 'llama-3.3-70b');
ok('getModel groq → llama-3.3-70b-versatile', rotator.getModel('groq') === 'llama-3.3-70b-versatile');
ok('getBaseUrl cerebras', rotator.getBaseUrl('cerebras').includes('cerebras.ai'));
ok('getBaseUrl groq', rotator.getBaseUrl('groq').includes('groq.com'));

// ─────────────────────────────────────────────────────────────────────────────
// Section 2: integration test with a mock LLM API server
// ─────────────────────────────────────────────────────────────────────────────
console.log('\n── Section 2: proxy integration test (mock LLM server) ──────────');

// We set up a mock LLM server that:
//   - returns 429 for the first two Cerebras keys
//   - returns a valid SSE stream for the third key (cerebras-3)
// Then we call our proxy and verify it rotates and returns content.

async function runIntegrationTest() {
  // Fresh rotator state: keys ck1,ck2 → 429; ck3 → 200
  delete require.cache[require.resolve('../llm/keyRotator')];
  delete require.cache[require.resolve('../llm/proxy')];
  const rot = require('../llm/keyRotator');
  const handleLlm = require('../llm/proxy');

  process.env.CEREBRAS_API_KEY_1 = 'quota-key-1';
  process.env.CEREBRAS_API_KEY_2 = 'quota-key-2';
  process.env.CEREBRAS_API_KEY_3 = 'good-key-3';
  delete process.env.GROQ_API_KEY_1;
  delete process.env.GROQ_API_KEY_2;
  delete process.env.GROQ_API_KEY_3;
  rot.init();

  // ── Mock "Cerebras API" server ──
  const mockApp = express();
  mockApp.use(express.json());
  const callLog = [];

  // Proxy builds: getBaseUrl() + "/chat/completions"
  // We override getBaseUrl to return "http://127.0.0.1:port", so route is /chat/completions
  mockApp.post('/chat/completions', (req, res) => {
    const authKey = (req.headers.authorization || '').replace('Bearer ', '');
    callLog.push(authKey);

    if (authKey === 'quota-key-1' || authKey === 'quota-key-2') {
      return res.status(429).json({ error: { message: 'rate_limit exceeded', type: 'rate_limit_error' } });
    }

    // good-key-3: stream a minimal valid response
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    const chunk = (content) =>
      'data: ' + JSON.stringify({
        id: 'test-id',
        object: 'chat.completion.chunk',
        created: 1,
        model: req.body.model,
        choices: [{ index: 0, delta: { content }, finish_reason: null }],
      }) + '\n\n';
    res.write(chunk('Hello '));
    res.write(chunk('parent!'));
    res.write('data: [DONE]\n\n');
    res.end();
  });

  const mockServer = http.createServer(mockApp);
  await new Promise((r) => mockServer.listen(0, '127.0.0.1', r));
  const { port } = mockServer.address();

  // Point keyRotator at our mock server
  const origGetBaseUrl = rot.getBaseUrl;
  rot.getBaseUrl = () => `http://127.0.0.1:${port}`;

  // ── Proxy server ──
  const proxyApp = express();
  proxyApp.use(express.json());
  proxyApp.post('/llm', handleLlm);
  const proxyServer = http.createServer(proxyApp);
  await new Promise((r) => proxyServer.listen(0, '127.0.0.1', r));
  const proxyPort = proxyServer.address().port;

  // ── Send test request ──
  const responseChunks = [];
  const rawBody = JSON.stringify({
    model: 'aria-llama',
    stream: true,
    messages: [{ role: 'user', content: 'Namaste' }],
  });

  await new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: '127.0.0.1', port: proxyPort, path: '/llm', method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(rawBody) } },
      (res) => {
        ok('response is 200', res.statusCode === 200);
        ok('Content-Type is text/event-stream', (res.headers['content-type'] || '').includes('text/event-stream'));
        res.on('data', (c) => responseChunks.push(c.toString()));
        res.on('end', resolve);
      }
    );
    req.on('error', reject);
    req.write(rawBody);
    req.end();
  });

  const fullBody = responseChunks.join('');

  // Verify key rotation happened
  ok('proxy tried quota-key-1 first', callLog[0] === 'quota-key-1');
  ok('proxy tried quota-key-2 second', callLog[1] === 'quota-key-2');
  ok('proxy used good-key-3 third', callLog[2] === 'good-key-3');
  ok('total LLM calls = 3', callLog.length === 3);

  // Verify hold phrase injected (attempt > 0)
  ok('hold phrase injected into stream', fullBody.includes('rukiye') || fullBody.includes('moment') || fullBody.includes('second'));

  // Verify actual content reached the client
  ok('actual LLM content reached client', fullBody.includes('Hello') && fullBody.includes('parent'));
  ok('stream ends with [DONE]', fullBody.includes('[DONE]'));

  // Verify model override
  ok('model overridden to cerebras model', fullBody.includes('llama-3.3-70b'));

  // Cleanup
  rot.getBaseUrl = origGetBaseUrl;
  await new Promise((r) => proxyServer.close(r));
  await new Promise((r) => mockServer.close(r));
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 3: non-streaming fallback test
// ─────────────────────────────────────────────────────────────────────────────
async function runNonStreamingTest() {
  console.log('\n── Section 3: non-streaming fallback test ───────────────────────');

  delete require.cache[require.resolve('../llm/keyRotator')];
  delete require.cache[require.resolve('../llm/proxy')];
  const rot = require('../llm/keyRotator');
  const handleLlm = require('../llm/proxy');

  process.env.CEREBRAS_API_KEY_1 = 'good-key-ns';
  delete process.env.CEREBRAS_API_KEY_2;
  delete process.env.CEREBRAS_API_KEY_3;
  delete process.env.GROQ_API_KEY_1;
  delete process.env.GROQ_API_KEY_2;
  delete process.env.GROQ_API_KEY_3;
  rot.init();

  const mockApp = express();
  mockApp.use(express.json());
  mockApp.post('/chat/completions', (_req, res) => {
    res.json({
      id: 'chatcmpl-ns',
      object: 'chat.completion',
      choices: [{ index: 0, message: { role: 'assistant', content: 'Non-stream reply' }, finish_reason: 'stop' }],
    });
  });

  const mockServer = http.createServer(mockApp);
  await new Promise((r) => mockServer.listen(0, '127.0.0.1', r));
  const { port } = mockServer.address();
  rot.getBaseUrl = () => `http://127.0.0.1:${port}`;

  const proxyApp = express();
  proxyApp.use(express.json());
  proxyApp.post('/llm', handleLlm);
  const proxyServer = http.createServer(proxyApp);
  await new Promise((r) => proxyServer.listen(0, '127.0.0.1', r));
  const proxyPort = proxyServer.address().port;

  const rawBody = JSON.stringify({
    model: 'aria-llama',
    stream: false,
    messages: [{ role: 'user', content: 'test' }],
  });

  const chunks = [];
  await new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: '127.0.0.1', port: proxyPort, path: '/llm', method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(rawBody) } },
      (res) => {
        ok('non-streaming: status 200', res.statusCode === 200);
        ok('non-streaming: content-type is json', (res.headers['content-type'] || '').includes('json'));
        res.on('data', (c) => chunks.push(c.toString()));
        res.on('end', resolve);
      }
    );
    req.on('error', reject);
    req.write(rawBody);
    req.end();
  });

  const json = JSON.parse(chunks.join(''));
  ok('non-streaming: response has choices', Array.isArray(json.choices));
  ok('non-streaming: content is correct', json.choices[0]?.message?.content === 'Non-stream reply');

  await new Promise((r) => proxyServer.close(r));
  await new Promise((r) => mockServer.close(r));
}

// ─────────────────────────────────────────────────────────────────────────────
// Section 4: all-keys-exhausted test
// ─────────────────────────────────────────────────────────────────────────────
async function runExhaustedTest() {
  console.log('\n── Section 4: all keys exhausted test ───────────────────────────');

  delete require.cache[require.resolve('../llm/keyRotator')];
  delete require.cache[require.resolve('../llm/proxy')];
  const rot = require('../llm/keyRotator');
  const handleLlm = require('../llm/proxy');

  process.env.CEREBRAS_API_KEY_1 = 'bad1';
  process.env.CEREBRAS_API_KEY_2 = 'bad2';
  delete process.env.CEREBRAS_API_KEY_3;
  delete process.env.GROQ_API_KEY_1;
  delete process.env.GROQ_API_KEY_2;
  delete process.env.GROQ_API_KEY_3;
  rot.init();

  const mockApp = express();
  mockApp.use(express.json());
  mockApp.post('/chat/completions', (_req, res) => {
    res.status(429).json({ error: { message: 'rate_limit exceeded' } });
  });

  const mockServer = http.createServer(mockApp);
  await new Promise((r) => mockServer.listen(0, '127.0.0.1', r));
  rot.getBaseUrl = () => `http://127.0.0.1:${mockServer.address().port}`;

  const proxyApp = express();
  proxyApp.use(express.json());
  proxyApp.post('/llm', handleLlm);
  const proxyServer = http.createServer(proxyApp);
  await new Promise((r) => proxyServer.listen(0, '127.0.0.1', r));

  const rawBody = JSON.stringify({ model: 'aria', stream: true, messages: [{ role: 'user', content: 'hi' }] });
  await new Promise((resolve, reject) => {
    const req = http.request(
      { hostname: '127.0.0.1', port: proxyServer.address().port, path: '/llm', method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(rawBody) } },
      (res) => {
        ok('503 returned when all keys exhausted', res.statusCode === 503);
        res.resume();
        res.on('end', resolve);
      }
    );
    req.on('error', reject);
    req.write(rawBody);
    req.end();
  });

  await new Promise((r) => proxyServer.close(r));
  await new Promise((r) => mockServer.close(r));
}

// ─────────────────────────────────────────────────────────────────────────────
// Run all tests
// ─────────────────────────────────────────────────────────────────────────────
(async () => {
  try {
    await runIntegrationTest();
    await runNonStreamingTest();
    await runExhaustedTest();
  } catch (err) {
    console.error('\nTest suite threw:', err);
    failed++;
  }

  // ── Live smoke test ──────────────────────────────────────────────────────
  console.log('\n── Section 5: live smoke test ───────────────────────────────────');

  // Re-load env keys for live test
  delete require.cache[require.resolve('../llm/keyRotator')];
  delete require.cache[require.resolve('../llm/proxy')];

  // Restore from real .env (already loaded at top of file via dotenv)
  // Set back to env keys (they were overwritten by the tests above)
  for (let i = 1; i <= 3; i++) {
    if (!process.env[`CEREBRAS_API_KEY_${i}`] || process.env[`CEREBRAS_API_KEY_${i}`].startsWith('ck') || process.env[`CEREBRAS_API_KEY_${i}`].startsWith('quota') || process.env[`CEREBRAS_API_KEY_${i}`].startsWith('good') || process.env[`CEREBRAS_API_KEY_${i}`].startsWith('bad')) {
      delete process.env[`CEREBRAS_API_KEY_${i}`];
    }
    if (!process.env[`GROQ_API_KEY_${i}`] || process.env[`GROQ_API_KEY_${i}`].startsWith('gk') || process.env[`GROQ_API_KEY_${i}`].startsWith('bad')) {
      delete process.env[`GROQ_API_KEY_${i}`];
    }
  }

  const hasRealKeys = [1, 2, 3].some(
    (i) => process.env[`CEREBRAS_API_KEY_${i}`] || process.env[`GROQ_API_KEY_${i}`]
  );

  if (!hasRealKeys) {
    console.log('  (skipped — no real API keys in .env)');
    console.log('  Set CEREBRAS_API_KEY_1 or GROQ_API_KEY_1 and re-run for a live call.');
  } else {
    const liveRot = require('../llm/keyRotator');
    const liveProxy = require('../llm/proxy');
    liveRot.init();

    const liveApp = express();
    liveApp.use(express.json());
    liveApp.post('/llm', liveProxy);
    const liveSrv = http.createServer(liveApp);
    await new Promise((r) => liveSrv.listen(0, '127.0.0.1', r));

    const liveBody = JSON.stringify({
      model: 'aria-llama',
      stream: true,
      messages: [
        { role: 'system', content: 'Reply in one very short sentence.' },
        { role: 'user', content: 'Namaste, ek short greeting do.' },
      ],
    });

    const liveChunks = [];
    try {
      await new Promise((resolve, reject) => {
        const req = http.request(
          { hostname: '127.0.0.1', port: liveSrv.address().port, path: '/llm', method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(liveBody) } },
          (res) => {
            ok('live: status 200', res.statusCode === 200);
            res.on('data', (c) => liveChunks.push(c.toString()));
            res.on('end', resolve);
          }
        );
        req.on('error', reject);
        req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
        req.write(liveBody);
        req.end();
      });
      const liveResp = liveChunks.join('');
      ok('live: stream has content', liveResp.includes('"content"'));
      ok('live: stream ends with [DONE]', liveResp.includes('[DONE]'));
      console.log('  Live response snippet:', liveResp.slice(0, 200));
    } catch (err) {
      console.log('  Live test error:', err.message);
      failed++;
    } finally {
      await new Promise((r) => liveSrv.close(r));
    }
  }

  // ── Summary ───────────────────────────────────────────────────────────────
  console.log(`\n${'─'.repeat(60)}`);
  console.log(`Results: ${passed} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
})();
