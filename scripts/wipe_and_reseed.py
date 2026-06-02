"""Wipe demo Firestore collections, then reseed.

Use after persona renames to clear stale parent docs, child subcollections,
call_attempts (+turns), objections, callbacks, and rate_limits — leaves
nothing behind that would surface old names in the CRM.

Run with `--yes` to skip the confirm prompt (for CI / deploy hook).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.crm.firestore_client import db  # noqa: E402
from app.crm.firestore_seeds import seed  # noqa: E402

COLLECTIONS_TO_WIPE = [
    "parents",          # also wipes /children subcollection per-doc
    "demos",
    "call_attempts",    # also wipes /turns subcollection per-doc
    "objections",
    "callbacks",
    "rate_limits",
    "courses",
    "competitors",
]

# Subcollections to drain before deleting the parent doc.
SUBCOLLECTIONS = {
    "parents": ["children"],
    "call_attempts": ["turns"],
}


async def _wipe_collection(name: str, batch_size: int = 200) -> int:
    """Delete every doc in a top-level collection, including known subcollections."""
    deleted = 0
    coll = db().collection(name)
    while True:
        docs = [d async for d in coll.limit(batch_size).stream()]
        if not docs:
            break
        for d in docs:
            for sub in SUBCOLLECTIONS.get(name, []):
                async for sd in d.reference.collection(sub).stream():
                    await sd.reference.delete()
            await d.reference.delete()
            deleted += 1
        print(f"  {name}: deleted {deleted}…")
    return deleted


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="skip confirm prompt")
    args = ap.parse_args()

    project = db().project
    print(f"About to WIPE collections in Firestore project: {project}")
    print(f"  collections: {', '.join(COLLECTIONS_TO_WIPE)}")
    if not args.yes:
        resp = input("Type 'WIPE' to continue: ").strip()
        if resp != "WIPE":
            print("Aborted.")
            return

    totals = {}
    for c in COLLECTIONS_TO_WIPE:
        print(f"Wiping {c}…")
        totals[c] = await _wipe_collection(c)

    print(f"Wiped: {totals}")
    print("Reseeding…")
    counts = await seed()
    print(f"Seeded: {counts}")


if __name__ == "__main__":
    asyncio.run(main())
