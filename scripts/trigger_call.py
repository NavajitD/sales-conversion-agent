"""CLI: place a single test call.

Usage:
  python scripts/trigger_call.py                  # uses DEMO_PHONE_NUMBER
  python scripts/trigger_call.py +9198XXXXXXXX    # overrides
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEMO_PHONE_NUMBER  # noqa: E402
from app.crm import repository  # noqa: E402
from app.crm.db import init_db  # noqa: E402
from app.telephony.outbound import place_call  # noqa: E402


async def main():
    phone = sys.argv[1] if len(sys.argv) > 1 else DEMO_PHONE_NUMBER
    if not phone:
        print("Usage: trigger_call.py <E164>  (or set DEMO_PHONE_NUMBER)")
        sys.exit(1)
    await init_db()
    parent = await repository.get_parent_by_phone(phone)
    if not parent:
        print(f"No parent for {phone} — run scripts/seed_db.py first")
        sys.exit(1)
    demo = await repository.get_latest_demo_for_parent(parent["id"])
    out = await place_call(phone, parent["id"], demo["id"] if demo else None)
    print("Call placed via Vobiz:", out)


if __name__ == "__main__":
    asyncio.run(main())
