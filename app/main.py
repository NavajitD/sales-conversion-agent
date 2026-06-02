"""FastAPI app entrypoint.

Routes:
  POST /llm,  POST /llm/chat/completions  → OpenAI-compatible LLM proxy
  POST /vobiz/answer                       → Vobiz Stream XML
  WS   /vobiz/stream                       → Vobiz Media Streams
  POST /vobiz/status                       → Vobiz status callback
  WS   /panel                              → live reasoning panel
  POST /trigger-call                       → kick off a test call (private)
  POST /api/dashboard/trigger-call         → kick off a call from the public demo
  GET  /api/dashboard/*                    → CRM read endpoints
  GET  /health                             → liveness
"""
from __future__ import annotations

import asyncio

# Bootstrap secrets BEFORE anything else imports app.config.
# On Cloud Run this fetches from Secret Manager into os.environ; locally
# it's a no-op and config.py reads from .env via dotenv as before.
from app.secrets import bootstrap_secrets  # noqa: E402

bootstrap_secrets()

from fastapi import FastAPI, WebSocket  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from loguru import logger  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.config import DEMO_PHONE_NUMBER, SERVER_HOST, SERVER_PORT  # noqa: E402
from app.crm import repository  # noqa: E402
from app.crm.db import init_db  # noqa: E402
from app.crm.seeds import seed  # noqa: E402
from app.dashboard_api import router as dashboard_router  # noqa: E402
from app.llm.proxy import router as llm_router  # noqa: E402
from app.panel.ws import hub  # noqa: E402
from app.telephony.callback_worker import run_forever as callback_worker_loop  # noqa: E402
from app.telephony.outbound import place_call  # noqa: E402
from app.telephony.vobiz_routes import router as vobiz_router  # noqa: E402

app = FastAPI(title="Aria — Post-Demo Conversion Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(llm_router)
app.include_router(vobiz_router)
app.include_router(dashboard_router)


@app.on_event("startup")
async def _startup() -> None:
    await init_db()  # no-op for Firestore; warms the client
    counts = await seed(demo_phone=DEMO_PHONE_NUMBER or None)
    logger.info(f"[startup] Firestore ready; seeded {counts}")
    app.state.callback_worker_task = asyncio.create_task(callback_worker_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    t = getattr(app.state, "callback_worker_task", None)
    if t:
        t.cancel()


@app.get("/health")
async def health():
    return {"ok": True}


@app.websocket("/panel")
async def panel_ws(ws: WebSocket):
    await hub.attach(ws)


class TriggerCallBody(BaseModel):
    phone: str | None = None  # if absent, uses DEMO_PHONE_NUMBER or first seeded parent


@app.post("/trigger-call")
async def trigger_call(body: TriggerCallBody):
    phone = body.phone or DEMO_PHONE_NUMBER
    if not phone:
        return {"ok": False, "error": "no phone supplied and DEMO_PHONE_NUMBER unset"}
    parent = await repository.get_parent_by_phone(phone)
    if not parent:
        return {"ok": False, "error": f"no parent for phone {phone}; seed first"}
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    out = await place_call(phone, parent["id"], demo["id"] if demo else None)
    return {"ok": True, **out}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)
