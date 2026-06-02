"""Secret bootstrap.

Cloud Run: reads secrets from Google Secret Manager and stuffs them into
os.environ so existing `os.environ.get(...)` call sites in app/config.py work
without modification.

Local dev: no-op. python-dotenv in app/config.py already loads .env.

Detection: `K_SERVICE` is set by Cloud Run; `USE_SECRET_MANAGER=1` forces it
on for local testing of the prod path.

Naming convention: each env-var name maps 1:1 to a Secret Manager secret of
the same name. e.g. `CEREBRAS_API_KEY_1` → secret `CEREBRAS_API_KEY_1`.

Failure mode: if a secret access fails, we log and skip — call sites that
need that value will still see "missing" and degrade exactly as before.
"""
from __future__ import annotations

import os
from typing import Iterable

from loguru import logger

# Every secret-eligible env var. Add new keys here as the surface grows.
SECRET_NAMES = (
    # LLM pool
    "CEREBRAS_API_KEY_1",
    "CEREBRAS_API_KEY_2",
    "CEREBRAS_API_KEY_3",
    "GROQ_API_KEY_1",
    "GROQ_API_KEY_2",
    "GROQ_API_KEY_3",
    "GEMINI_API_KEY",
    # Voice stack (Deepgram STT + Sarvam TTS)
    "DEEPGRAM_API_KEY",
    "SARVAM_API_KEY",
    # Telephony
    "VOBIZ_AUTH_ID",
    "VOBIZ_AUTH_TOKEN",
    "VOBIZ_PHONE_NUMBER",
)


def _running_on_cloud_run() -> bool:
    return bool(os.environ.get("K_SERVICE"))


def should_bootstrap() -> bool:
    return _running_on_cloud_run() or os.environ.get("USE_SECRET_MANAGER") == "1"


def _project() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or "aria-crm-2e680"
    )


def bootstrap_secrets(names: Iterable[str] = SECRET_NAMES) -> dict[str, str]:
    """Fetch each secret's latest version and set as env var if missing.

    Returns the mapping of {name: status} for logging. Status is "set",
    "skipped (already set)", or "missing (no secret)" / "error: ...".
    """
    if not should_bootstrap():
        return {}

    # Import lazily so local dev without google-cloud-secret-manager installed
    # still works.
    from google.cloud import secretmanager

    project = _project()
    client = secretmanager.SecretManagerServiceClient()
    status: dict[str, str] = {}

    for name in names:
        if os.environ.get(name):
            status[name] = "skipped (already set)"
            continue
        resource = f"projects/{project}/secrets/{name}/versions/latest"
        try:
            resp = client.access_secret_version(request={"name": resource})
            value = resp.payload.data.decode("utf-8")
            os.environ[name] = value
            status[name] = "set"
        except Exception as e:  # noqa: BLE001
            msg = str(e).splitlines()[0][:120]
            status[name] = f"error: {msg}"

    set_count = sum(1 for v in status.values() if v == "set")
    err_count = sum(1 for v in status.values() if v.startswith("error"))
    logger.info(
        f"[secrets] bootstrap from Secret Manager (project={project}): "
        f"{set_count} set, {err_count} errors, {len(status)} total"
    )
    if err_count:
        for k, v in status.items():
            if v.startswith("error"):
                logger.warning(f"[secrets] {k}: {v}")
    return status
