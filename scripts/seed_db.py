"""Standalone DB seeder. Picks up DEMO_PHONE_NUMBER from .env."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import DEMO_PHONE_NUMBER  # noqa: E402
from app.crm.db import init_db  # noqa: E402
from app.crm.seeds import seed  # noqa: E402


async def main():
    await init_db()
    counts = await seed(demo_phone=DEMO_PHONE_NUMBER or None)
    print("Seeded:", counts)


if __name__ == "__main__":
    asyncio.run(main())
