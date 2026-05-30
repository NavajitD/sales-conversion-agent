require('dotenv').config({ path: require('path').join(__dirname, '../.env') });

const express = require('express');
const cors = require('cors');
const http = require('http');
const { WebSocketServer } = require('ws');
const url = require('url');

const { addClient, broadcast } = require('./broadcast');
const handleSttConnection = require('../agent/sarvam-stt-bridge');
const handleTtsRequest = require('../agent/sarvam-tts-bridge');

const app = express();
app.use(cors());
app.use(express.json());

// In-memory event store — current call only, reset on new call start
let callEvents = [];

// Tool webhook from Vapi
app.post('/vapi/tool', (req, res) => {
  try {
    const body = req.body;
    const toolCallList = body?.message?.toolCallList || body?.toolCallList;
    if (!toolCallList || !toolCallList.length) {
      return res.status(400).json({ error: 'No toolCallList' });
    }

    const results = toolCallList.map((call) => {
      const name = call.function?.name;
      let args = call.function?.arguments;
      if (typeof args === 'string') args = JSON.parse(args);

      if (name === 'log_call_state') {
        // Reset event store on new call (final from previous call clears it)
        if (args.final) callEvents = [];
        callEvents.push(args);
        broadcast(args);
        console.log('[tool]', JSON.stringify(args));
      }

      return { toolCallId: call.id, result: 'logged' };
    });

    res.json({ results });
  } catch (err) {
    console.error('[tool] error', err);
    res.status(500).json({ error: err.message });
  }
});

// TTS bridge (Vapi custom voice → Sarvam Bulbul)
app.post('/tts', handleTtsRequest);

app.get('/health', (_req, res) => res.json({ ok: true }));

const server = http.createServer(app);
const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (req, socket, head) => {
  const { pathname } = url.parse(req.url);

  if (pathname === '/stt') {
    wss.handleUpgrade(req, socket, head, (ws) => {
      handleSttConnection(ws, req);
    });
  } else if (pathname === '/panel') {
    wss.handleUpgrade(req, socket, head, (ws) => {
      addClient(ws);
      // Replay current call events to late-connecting panel
      callEvents.forEach((evt) => {
        if (ws.readyState === 1) ws.send(JSON.stringify(evt));
      });
    });
  } else {
    socket.destroy();
  }
});

const PORT = process.env.SERVER_PORT || 3000;
server.listen(PORT, () => {
  console.log(`Server listening on port ${PORT}`);
  console.log(`  POST /vapi/tool  — Vapi tool webhook`);
  console.log(`  POST /tts        — Sarvam TTS bridge`);
  console.log(`  WS   /stt        — Sarvam STT bridge`);
  console.log(`  WS   /panel      — Live reasoning panel`);
  console.log(`  GET  /health     — Health check`);
});
