const { WebSocket } = require('ws');

const SARVAM_STT_URL =
  'wss://api.sarvam.ai/speech-to-text/ws?model=saaras:v3&language_code=hi-IN&mode=codemix';

// Downmix 16-bit stereo PCM → 16-bit mono PCM
function stereoToMono(buf) {
  const samples = Math.floor(buf.length / 4);
  const mono = Buffer.alloc(samples * 2);
  for (let i = 0; i < samples; i++) {
    const l = buf.readInt16LE(i * 4);
    const r = buf.readInt16LE(i * 4 + 2);
    mono.writeInt16LE(Math.round((l + r) / 2), i * 2);
  }
  return mono;
}

module.exports = function handleSttConnection(vapiWs) {
  let sarvamWs = null;
  let started = false;

  function openSarvam() {
    sarvamWs = new WebSocket(SARVAM_STT_URL, {
      headers: { 'api-subscription-key': process.env.SARVAM_API_KEY },
    });

    sarvamWs.on('open', () => {
      console.log('[stt] Sarvam WS open');
    });

    sarvamWs.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());
        // Sarvam sends transcript in various shapes; normalise
        const text =
          msg.transcript ||
          msg.transcription ||
          msg.alternatives?.[0]?.transcript ||
          msg.speech_final?.transcript ||
          '';
        const isFinal =
          msg.speech_final !== undefined
            ? !!msg.speech_final
            : msg.type === 'final' || msg.is_final === true;

        if (text) {
          const response = JSON.stringify({
            type: 'transcriber-response',
            transcription: text,
            channel: 'customer',
            transcriptType: isFinal ? 'final' : 'partial',
          });
          if (vapiWs.readyState === 1) vapiWs.send(response);
        }
      } catch {
        // non-JSON frame, ignore
      }
    });

    sarvamWs.on('error', (err) => console.error('[stt] Sarvam error', err.message));
    sarvamWs.on('close', () => {
      console.log('[stt] Sarvam WS closed');
      if (vapiWs.readyState === 1) vapiWs.close();
    });
  }

  vapiWs.on('message', (data, isBinary) => {
    if (!isBinary) {
      // Text frame — could be the start message
      try {
        const msg = JSON.parse(data.toString());
        if (msg.type === 'start' && !started) {
          started = true;
          console.log('[stt] Vapi start received:', msg);
          openSarvam();
        }
      } catch {
        // ignore parse errors
      }
      return;
    }

    // Binary frame — raw PCM audio from Vapi (16kHz, 16-bit, stereo)
    if (!sarvamWs || sarvamWs.readyState !== 1) return;
    const mono = stereoToMono(data);
    sarvamWs.send(mono);
  });

  vapiWs.on('close', () => {
    console.log('[stt] Vapi WS closed');
    if (sarvamWs && sarvamWs.readyState === 1) sarvamWs.close();
  });

  vapiWs.on('error', (err) => console.error('[stt] Vapi error', err.message));
};
