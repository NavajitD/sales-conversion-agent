const fetch = require('node-fetch');

const SARVAM_TTS_URL = 'https://api.sarvam.ai/text-to-speech';
const WAV_HEADER_BYTES = 44;

module.exports = async function handleTtsRequest(req, res) {
  try {
    // Log body shape on first call to confirm Vapi's field name
    const body = req.body;
    console.log('[tts] incoming body keys:', Object.keys(body));

    // Vapi may send the text under different keys depending on its version
    const text =
      body?.text ||
      body?.message?.text ||
      body?.message?.content ||
      body?.content ||
      '';

    if (!text) {
      console.error('[tts] no text field found in body:', JSON.stringify(body));
      return res.status(400).json({ error: 'no text in request' });
    }

    const sarvamRes = await fetch(SARVAM_TTS_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'api-subscription-key': process.env.SARVAM_API_KEY,
      },
      body: JSON.stringify({
        text,
        target_language_code: 'hi-IN',
        speaker: 'ritu',
        model: 'bulbul:v3',
        pace: 0.95,
        temperature: 0.6,
        sample_rate: 16000,
        enable_preprocessing: true,
      }),
    });

    if (!sarvamRes.ok) {
      const err = await sarvamRes.text();
      console.error('[tts] Sarvam error', sarvamRes.status, err);
      return res.status(502).json({ error: err });
    }

    const json = await sarvamRes.json();

    // Sarvam returns { audios: ["<base64-wav>"] } or { audio: "<base64-wav>" }
    const b64 = json.audios?.[0] || json.audio || '';
    if (!b64) {
      console.error('[tts] no audio in Sarvam response', json);
      return res.status(502).json({ error: 'no audio in Sarvam response' });
    }

    const wavBuf = Buffer.from(b64, 'base64');

    // Strip WAV header to return raw PCM
    const pcm = wavBuf.slice(WAV_HEADER_BYTES);

    res.set('Content-Type', 'application/octet-stream');
    res.send(pcm);
  } catch (err) {
    console.error('[tts] unexpected error', err);
    res.status(500).json({ error: err.message });
  }
};
