"""Lazy singleton Firestore AsyncClient.

Cloud Run: uses ADC from the service-account attached to the service.
Local dev: uses `gcloud auth application-default login` ADC, project from
`GOOGLE_CLOUD_PROJECT` env var (or the `aria-crm-2e680` default if unset).
"""
from __future__ import annotations

import os
from typing import Optional

from google.cloud import firestore

_client: Optional[firestore.AsyncClient] = None


def _project() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or "aria-crm-2e680"
    )


def db() -> firestore.AsyncClient:
    global _client
    if _client is None:
        _client = firestore.AsyncClient(project=_project())
    return _client


SERVER_TIMESTAMP = firestore.SERVER_TIMESTAMP
