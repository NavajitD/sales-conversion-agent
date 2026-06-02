#!/usr/bin/env bash
# Push secrets from a local file into Google Secret Manager.
#
# Usage:
#   ./scripts/push_secrets.sh path/to/secrets.env
#
# secrets.env format: standard dotenv (KEY=value, one per line). Lines
# starting with # are ignored. Unset / blank values are skipped.
#
# Each line becomes a Secret Manager secret with the same name, replacing
# any existing latest version. Cloud Run reads these via --set-secrets in
# scripts/deploy.sh, which mounts them as env vars at container start.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-aria-crm-2e680}"
SOURCE="${1:-.env}"

if [[ ! -f "${SOURCE}" ]]; then
  echo "ERROR: ${SOURCE} not found. Pass a path to your secrets file."
  exit 1
fi

# Allowlist of names accepted as secrets. Keep in sync with SECRET_NAMES in
# app/secrets.py. Inlined here so the script doesn't need a python venv.
KNOWN_NAMES=$(cat <<'NAMES'
CEREBRAS_API_KEY_1
CEREBRAS_API_KEY_2
CEREBRAS_API_KEY_3
GROQ_API_KEY_1
GROQ_API_KEY_2
GROQ_API_KEY_3
GEMINI_API_KEY
DEEPGRAM_API_KEY
SARVAM_API_KEY
ELEVENLABS_API_KEY
VOBIZ_AUTH_ID
VOBIZ_AUTH_TOKEN
VOBIZ_PHONE_NUMBER
NAMES
)

echo "Pushing secrets from ${SOURCE} → Secret Manager (project=${PROJECT_ID})"
echo

while IFS= read -r line; do
  # Strip comments / blank lines
  [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
  # Split on first =
  key="${line%%=*}"
  value="${line#*=}"
  # Trim surrounding whitespace, matching quotes, AND inline `# ...` comments.
  # An inline comment is " #..." (space before #) so we don't break values
  # that legitimately contain # without a preceding space.
  key="$(echo "${key}" | xargs)"
  value="$(echo "${value}" | sed -E 's/[[:space:]]+#.*$//; s/^"(.*)"$/\1/; s/^'\''(.*)'\''$/\1/' | xargs)"

  if [[ -z "${value}" ]]; then
    echo "  · skip ${key} (empty)"
    continue
  fi
  if ! echo "${KNOWN_NAMES}" | grep -qx "${key}"; then
    echo "  · skip ${key} (not in SECRET_NAMES allowlist)"
    continue
  fi

  # Create if missing, then add a new version.
  if ! gcloud secrets describe "${key}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud secrets create "${key}" --project "${PROJECT_ID}" \
      --replication-policy=automatic >/dev/null
    echo "  + created ${key}"
  fi
  printf '%s' "${value}" | gcloud secrets versions add "${key}" \
    --project "${PROJECT_ID}" --data-file=- >/dev/null
  echo "  ✓ updated ${key}"
done < "${SOURCE}"

echo
echo "Done. The Cloud Run service must be redeployed (scripts/deploy.sh) to"
echo "pick up the new versions; the --set-secrets bindings use :latest."
