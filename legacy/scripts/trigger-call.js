require('dotenv').config({ path: require('path').join(__dirname, '../.env') });

const fetch = require('node-fetch');

async function main() {
  const assistantId = process.env.VAPI_ASSISTANT_ID;
  const phoneNumberId = process.env.VAPI_PHONE_NUMBER_ID;
  const demoPhone = process.env.DEMO_PHONE_NUMBER;

  if (!assistantId || !phoneNumberId || !demoPhone) {
    console.error('Missing required env vars: VAPI_ASSISTANT_ID, VAPI_PHONE_NUMBER_ID, DEMO_PHONE_NUMBER');
    process.exit(1);
  }

  console.log(`Triggering call to ${demoPhone}...`);

  const res = await fetch('https://api.vapi.ai/call/phone', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.VAPI_API_KEY}`,
    },
    body: JSON.stringify({
      assistantId,
      phoneNumberId,
      customer: {
        number: demoPhone,
      },
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    console.error('Vapi error', res.status, err);
    process.exit(1);
  }

  const call = await res.json();
  console.log('Call initiated!');
  console.log('  Call ID:', call.id);
  console.log('  Status :', call.status);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
