#!/usr/bin/env bash
# Deploy Aria to Cloud Run + Firebase Hosting + Firestore indexes.
#
# Prerequisites (one-time):
#   - gcloud auth login + gcloud config set project aria-crm-2e680
#   - firebase login
#   - All required APIs enabled (Cloud Run, Secret Manager, Firestore, Artifact
#     Registry, Cloud Build, Firebase Hosting)
#   - Secrets pushed to Secret Manager via scripts/push_secrets.sh
#
# Idempotent: safe to re-run after code changes. Picks up the current source
# tree, rebuilds the container, redeploys, and re-publishes Hosting.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-aria-crm-2e680}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-aria}"

echo "── 1. Cloud Run deploy (source build → Artifact Registry → Cloud Run) ──"
# `--source .` triggers Cloud Build with our Dockerfile; we do NOT need a
# local docker install.
#
# Memory: ElevenLabs realtime + pipecat pipeline + Silero VAD comfortably
# fit in 1Gi; bump to 2Gi if you see OOM at concurrency.
#
# Concurrency = 8: Cloud Run will route up to 8 simultaneous calls to one
# instance. Pipecat's per-call CPU is modest in steady state (mostly WS I/O).
# Bump down to 4 if latency suffers.
#
# Timeout = 3600s: a single call can run that long. Cloud Run's default 5min
# would kill the WS mid-conversation.
gcloud run deploy "${SERVICE}" \
  --source . \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --cpu-boost \
  --clear-base-image \
  --concurrency 8 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 3600 \
  --port 8080 \
  --set-secrets="CEREBRAS_API_KEY_1=CEREBRAS_API_KEY_1:latest,CEREBRAS_API_KEY_2=CEREBRAS_API_KEY_2:latest,GROQ_API_KEY_1=GROQ_API_KEY_1:latest,GROQ_API_KEY_2=GROQ_API_KEY_2:latest,GROQ_API_KEY_3=GROQ_API_KEY_3:latest,GEMINI_API_KEY=GEMINI_API_KEY:latest,DEEPGRAM_API_KEY=DEEPGRAM_API_KEY:latest,SARVAM_API_KEY=SARVAM_API_KEY:latest,VOBIZ_AUTH_ID=VOBIZ_AUTH_ID:latest,VOBIZ_AUTH_TOKEN=VOBIZ_AUTH_TOKEN:latest,VOBIZ_PHONE_NUMBER=VOBIZ_PHONE_NUMBER:latest"

# Capture the deployed URL.
# IMPORTANT: status.url returns the legacy *.a.run.app alias, which Vobiz can
# call /answer on but FAILS to open a WSS to /vobiz/stream from (the bot never
# starts and the parent hears silence). The regional URL
# aria-<projectNumber>.<region>.run.app works for WSS. We derive it explicitly.
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')
SERVICE_URL="https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app"
echo "Pinning PUBLIC_URL=${SERVICE_URL} (regional URL, supports WSS)"

echo "── 2. Pinning PUBLIC_URL=${SERVICE_URL} for Vobiz webhooks ──"
# PUBLIC_URL is used by /vobiz/answer to build the answer_url and ws URL.
# We point it at the direct Cloud Run URL (Vobiz hits Cloud Run directly,
# not Firebase Hosting — Hosting's WS rewrite path is not the recommended
# transport for long-lived Pipecat sessions).
gcloud run services update "${SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --update-env-vars "PUBLIC_URL=${SERVICE_URL},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"

echo "── 3. Firestore indexes ──"
firebase deploy --only firestore:indexes --project "${PROJECT_ID}"

echo "── 4. Firebase Hosting (visitor demo + REST rewrites) ──"
firebase deploy --only hosting --project "${PROJECT_ID}"

HOSTING_URL="https://${PROJECT_ID}.web.app"
echo
echo "Done."
echo "  Cloud Run service:   ${SERVICE_URL}"
echo "  Public demo (Hosting): ${HOSTING_URL}"
echo "  Health:              ${HOSTING_URL}/health  (via rewrite)"
echo "                       ${SERVICE_URL}/health  (direct)"
