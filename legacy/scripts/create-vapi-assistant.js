require('dotenv').config({ path: require('path').join(__dirname, '../.env') });

const fs = require('fs');
const path = require('path');
const fetch = require('node-fetch');
const context = require('../server/context');

const VAPI_API = 'https://api.vapi.ai/assistant';

function hydrate(template, vars) {
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
    const val = vars[key];
    if (val === undefined) return `{{${key}}}`;
    return String(val);
  });
}

async function main() {
  const systemPromptRaw = fs.readFileSync(
    path.join(__dirname, '../agent/system-prompt.md'),
    'utf8'
  );

  // The system prompt file contains a markdown code block — extract just the prompt body
  const codeBlockMatch = systemPromptRaw.match(/```\n([\s\S]*?)```/);
  const promptBody = codeBlockMatch ? codeBlockMatch[1].trim() : systemPromptRaw.trim();

  const hydratedPrompt = hydrate(promptBody, context);

  const templateRaw = fs.readFileSync(
    path.join(__dirname, '../agent/vapi-assistant.json'),
    'utf8'
  );

  const serverUrl = process.env.SERVER_PUBLIC_URL;
  if (!serverUrl) {
    console.error('ERROR: SERVER_PUBLIC_URL is not set in .env');
    process.exit(1);
  }

  // Replace template placeholders
  const configStr = templateRaw
    .replace(/__SYSTEM_PROMPT__/g, JSON.stringify(hydratedPrompt).slice(1, -1)) // strip outer quotes — already inside a JSON string
    .replace(/__SERVER_PUBLIC_URL__/g, serverUrl);

  const config = JSON.parse(configStr);

  console.log('Creating Vapi assistant...');
  const res = await fetch(VAPI_API, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${process.env.VAPI_API_KEY}`,
    },
    body: JSON.stringify(config),
  });

  if (!res.ok) {
    const err = await res.text();
    console.error('Vapi error', res.status, err);
    process.exit(1);
  }

  const assistant = await res.json();
  console.log('\nAssistant created!');
  console.log('  ID  :', assistant.id);
  console.log('  Name:', assistant.name);
  console.log('\nAdd this to your .env:');
  console.log(`  VAPI_ASSISTANT_ID=${assistant.id}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
