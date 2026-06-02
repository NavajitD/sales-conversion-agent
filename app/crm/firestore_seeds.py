"""Idempotent Firestore seeder.

Mirrors the structure of the previous SQLite seeder (COURSES, PARENTS,
COMPETITORS). Run on startup; safe to call repeatedly.

ID conventions:
  parents/{phone}                          phone is the natural key
  parents/{phone}/children/{child_uuid}    child_uuid stored as field child_id too
  courses/{code}                           code is the doc id
  competitors/{auto}                       doc id is auto
  demos/{auto}                             field parent_phone for queries
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore as _fs

from app.crm.firestore_client import db


def _today() -> date:
    return date.today()


def _dob_with_birthday_in_days(days: int, age_years: int) -> str:
    target = _today() + timedelta(days=days)
    return date(target.year - age_years, target.month, target.day).isoformat()


def _demo_attended_hours_ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


COURSES = [
    {
        "code": "VED-JEE-XI-2YR",
        "name": "Vedantu Tatva JEE — 2-Year (Class 11–12)",
        "grade": "Class 11",
        "board": "CBSE",
        "exam_target": "JEE",
        "subjects": "Physics,Chemistry,Maths",
        "duration": "2 years",
        "fee_amount": 84000,
        "fee_spoken": "chaurasi hazaar rupaye",
        "payment_plan_available": 1,
        "scholarship_available": 1,
        "batch_options": "weekday evening 7–9; weekend morning 9–12",
        "current_offer": "10% off if enrolled within 48 hours of demo",
        "offer_expires_at": None,
    },
    {
        "code": "VED-JEE-XII-1YR",
        "name": "Vedantu Tatva JEE — 1-Year Crash (Class 12)",
        "grade": "Class 12",
        "board": "CBSE",
        "exam_target": "JEE",
        "subjects": "Physics,Chemistry,Maths",
        "duration": "1 year",
        "fee_amount": 58000,
        "fee_spoken": "athawan hazaar rupaye",
        "payment_plan_available": 1,
        "scholarship_available": 1,
        "batch_options": "weekday 6–9 PM",
        "current_offer": "EMI starting fourteen-five hundred rupees per month",
        "offer_expires_at": None,
    },
    {
        "code": "VED-NEET-XI-2YR",
        "name": "Vedantu Tatva NEET — 2-Year (Class 11–12)",
        "grade": "Class 11",
        "board": "CBSE",
        "exam_target": "NEET",
        "subjects": "Physics,Chemistry,Biology",
        "duration": "2 years",
        "fee_amount": 79000,
        "fee_spoken": "uneasi hazaar rupaye",
        "payment_plan_available": 1,
        "scholarship_available": 1,
        "batch_options": "weekday evening 6–9",
        "current_offer": "Sibling discount fifteen percent",
        "offer_expires_at": None,
    },
    {
        "code": "VED-VPRO-X",
        "name": "Vedantu V-Pro Foundation — Class 10",
        "grade": "Class 10",
        "board": "CBSE",
        "exam_target": "Boards + Olympiads",
        "subjects": "Maths,Science",
        "duration": "1 year",
        "fee_amount": 32000,
        "fee_spoken": "battees hazaar rupaye",
        "payment_plan_available": 1,
        "scholarship_available": 0,
        "batch_options": "weekday evening 5–7; weekend morning 10–12",
        "current_offer": "Pay in three instalments, no interest",
        "offer_expires_at": None,
    },
    {
        "code": "VED-VPRO-IX",
        "name": "Vedantu V-Pro Foundation — Class 9",
        "grade": "Class 9",
        "board": "CBSE",
        "exam_target": "Foundation",
        "subjects": "Maths,Science",
        "duration": "1 year",
        "fee_amount": 28000,
        "fee_spoken": "atthais hazaar rupaye",
        "payment_plan_available": 1,
        "scholarship_available": 0,
        "batch_options": "weekday evening 5–7",
        "current_offer": "First-month free trial",
        "offer_expires_at": None,
    },
]

PARENTS = [
    {
        "name": "Mr. Sharma",
        "phone": "+919999900001",
        "preferred_language": "hi-IN",
        "city": "Lucknow",
        "children": [
            {
                "name": "Aarav",
                "dob": _dob_with_birthday_in_days(12, 16),
                "grade": "Class 11",
                "board": "CBSE",
                "exam_target": "JEE",
                "exam_date": "2027",
            }
        ],
        "demo": {
            "course_code": "VED-JEE-XI-2YR",
            "subject": "Physics",
            "teacher": "Ms. Kapoor",
            "weak_topic": "Rotational Motion",
            "hours_ago": 3,
        },
    },
    {
        "name": "Mrs. Reddy",
        "phone": "+919999900002",
        "preferred_language": "mixed",
        "city": "Hyderabad",
        "children": [
            {
                "name": "Pranavi",
                "dob": _dob_with_birthday_in_days(180, 17),
                "grade": "Class 12",
                "board": "CBSE",
                "exam_target": "JEE",
                "exam_date": "2026",
            }
        ],
        "demo": {
            "course_code": "VED-JEE-XII-1YR",
            "subject": "Chemistry",
            "teacher": "Mr. Ranjan",
            "weak_topic": "Chemical Bonding",
            "hours_ago": 2,
        },
    },
    {
        "name": "Mr. Iyer",
        "phone": "+919999900003",
        "preferred_language": "en-IN",
        "city": "Bengaluru",
        "children": [
            {
                "name": "Nehal",
                "dob": _dob_with_birthday_in_days(3, 16),
                "grade": "Class 11",
                "board": "CBSE",
                "exam_target": "NEET",
                "exam_date": "2027",
            }
        ],
        "demo": {
            "course_code": "VED-NEET-XI-2YR",
            "subject": "Biology",
            "teacher": "Dr. Sen",
            "weak_topic": "Human Physiology — Endocrine",
            "hours_ago": 4,
        },
    },
    {
        "name": "Mrs. Verma",
        "phone": "+919999900004",
        "preferred_language": "hi-IN",
        "city": "Patna",
        "children": [
            {
                "name": "Ishaan",
                "dob": _dob_with_birthday_in_days(85, 15),
                "grade": "Class 10",
                "board": "CBSE",
                "exam_target": "Boards",
                "exam_date": "2026",
            }
        ],
        "demo": {
            "course_code": "VED-VPRO-X",
            "subject": "Mathematics",
            "teacher": "Mr. Khanna",
            "weak_topic": "Trigonometry",
            "hours_ago": 2,
        },
    },
    {
        "name": "Mr. Nath",
        "phone": "+919999900005",
        "preferred_language": "mixed",
        "city": "Kolkata",
        "children": [
            {
                "name": "Anaya",
                "dob": _dob_with_birthday_in_days(28, 14),
                "grade": "Class 9",
                "board": "ICSE",
                "exam_target": "Foundation",
                "exam_date": "2028",
            }
        ],
        "demo": {
            "course_code": "VED-VPRO-IX",
            "subject": "Science",
            "teacher": "Ms. Pillai",
            "weak_topic": "Motion & Force",
            "hours_ago": 3,
        },
    },
]

COMPETITORS = [
    {
        "name": "Physics Wallah (PW)",
        "axis": "price",
        "parent_concern": "PW sasta hai",
        "vedantu_counter": (
            "PW ka price advantage real hai, agreed. Lekin Vedantu mein har bacche ka "
            "personal mentor hota hai jo weekly attendance, homework aur test scores "
            "track karta hai — yeh discipline layer PW ke open YouTube model mein nahi hai."
        ),
        "proof_point": "1:1 mentor + weekly parent update",
    },
    {
        "name": "Physics Wallah (PW)",
        "axis": "outcomes",
        "parent_concern": "PW ke results bhi acche hain",
        "vedantu_counter": (
            "Dono ke results hain, but Vedantu ka selectivity strong hai — small batch, "
            "live teacher feedback. PW scale par chalata hai, hum focus par."
        ),
        "proof_point": "Smaller batches; live doubt resolution",
    },
    {
        "name": "Aakash",
        "axis": "outcomes",
        "parent_concern": "Aakash ka brand naam bada hai, results bhi",
        "vedantu_counter": (
            "Aakash ka legacy strong hai offline, no doubt. Vedantu ka edge online live "
            "format mein hai — teacher se daily interaction, recording usi din, aur travel "
            "time bach jaata hai jise revision mein laga sakte hain."
        ),
        "proof_point": "Zero commute; same-day recordings",
    },
    {
        "name": "Aakash",
        "axis": "price",
        "parent_concern": "Aakash ka offline center sasta lag raha hai",
        "vedantu_counter": (
            "Offline center fees kam dikhte hain, lekin transport aur material extra hota hai. "
            "Vedantu ka all-in price compare karein toh aksar 15–20% kam padta hai."
        ),
        "proof_point": "All-inclusive pricing; no hidden extras",
    },
    {
        "name": "BYJU'S",
        "axis": "trust",
        "parent_concern": "BYJU'S ka naam bhi aata hai but news acche nahi sune",
        "vedantu_counter": (
            "BYJU'S ka recorded video model alag hai. Vedantu live live class hai, daily "
            "teacher ke saath direct contact — recording nahi, real time doubt."
        ),
        "proof_point": "Live, not recorded; daily teacher interaction",
    },
    {
        "name": "Allen",
        "axis": "outcomes",
        "parent_concern": "Allen JEE Advanced mein top karta hai",
        "vedantu_counter": (
            "Allen ka top-of-funnel result strong hai, Kota model. Vedantu online format "
            "se {grade} ke bachon ko ghar par focus milta hai, mental health bhi behtar "
            "rehti hai — yeh long preparation mein matter karta hai."
        ),
        "proof_point": "Home environment; lower burnout risk",
    },
    {
        "name": "Unacademy",
        "axis": "logistics",
        "parent_concern": "Unacademy ka schedule flexible hai",
        "vedantu_counter": (
            "Flexibility dono ke paas hai. Vedantu mein har batch ka fixed teacher hota hai, "
            "isse bacche ka teacher ke saath rapport banta hai — Unacademy mein educators "
            "rotate hote hain."
        ),
        "proof_point": "Fixed-teacher batches",
    },
]


async def seed(demo_phone: str | None = None) -> dict[str, int]:
    """Idempotently seed Firestore. Returns counts of newly-added docs."""
    fs = db()
    counts = {"parents": 0, "children": 0, "courses": 0, "demos": 0, "competitors": 0}

    # Courses (doc id = code)
    for c in COURSES:
        ref = fs.collection("courses").document(c["code"])
        if not (await ref.get()).exists:
            payload = {k: v for k, v in c.items() if k != "code"}
            await ref.set(payload)
            counts["courses"] += 1

    # Competitors (skip if any exist)
    existing_competitors = 0
    async for _ in fs.collection("competitors").limit(1).stream():
        existing_competitors += 1
        break
    if existing_competitors == 0:
        for c in COMPETITORS:
            await fs.collection("competitors").add(c)
            counts["competitors"] += 1

    # Parents → children → demos
    for p in PARENTS:
        phone = p["phone"]
        if demo_phone and p is PARENTS[0]:
            phone = demo_phone

        parent_ref = fs.collection("parents").document(phone)
        parent_snap = await parent_ref.get()
        if not parent_snap.exists:
            await parent_ref.set(
                {
                    "name": p["name"],
                    "phone": phone,
                    "preferred_language": p["preferred_language"],
                    "city": p["city"],
                    "created_at": _demo_attended_hours_ago(0),
                }
            )
            counts["parents"] += 1
        else:
            # Idempotently rename: if the seed name has changed since last seed
            # (e.g. Bose → Nath), force the doc to match the seed file. We do
            # NOT wipe history; existing call_attempts/objections/callbacks for
            # this parent_id are preserved.
            existing = parent_snap.to_dict() or {}
            if existing.get("name") != p["name"]:
                await parent_ref.set({"name": p["name"]}, merge=True)

        for ch in p["children"]:
            # Look up existing by name first.
            child_doc_id = None
            async for snap in (
                parent_ref.collection("children")
                .where(filter=_fs.FieldFilter("name", "==", ch["name"]))
                .limit(1)
                .stream()
            ):
                child_doc_id = snap.id
                break

            # If not found by current seed name, fall back to the parent's
            # first existing child (so a rename like Diya→Nehal renames the
            # existing record in place rather than creating a duplicate).
            if child_doc_id is None:
                async for snap in (
                    parent_ref.collection("children").limit(1).stream()
                ):
                    child_doc_id = snap.id
                    await snap.reference.set({"name": ch["name"]}, merge=True)
                    break

            if child_doc_id is None:
                child_doc_id = uuid.uuid4().hex
                await parent_ref.collection("children").document(child_doc_id).set(
                    {
                        "child_id": child_doc_id,  # so collection_group queries work
                        "name": ch["name"],
                        "dob": ch["dob"],
                        "grade": ch["grade"],
                        "board": ch["board"],
                        "exam_target": ch["exam_target"],
                        "exam_date": ch["exam_date"],
                    }
                )
                counts["children"] += 1

            demo = p["demo"]
            course_code = demo["course_code"]

            # Demo deduplicated by (child_id, course_id)
            existing_demo = None
            async for snap in (
                fs.collection("demos")
                .where(filter=_fs.FieldFilter("child_id", "==", child_doc_id))
                .where(filter=_fs.FieldFilter("course_id", "==", course_code))
                .limit(1)
                .stream()
            ):
                existing_demo = snap
                break
            if existing_demo is None:
                await fs.collection("demos").add(
                    {
                        "parent_phone": phone,  # for get_latest_demo_for_parent query
                        "child_id": child_doc_id,
                        "course_id": course_code,
                        "subject": demo["subject"],
                        "teacher": demo["teacher"],
                        "weak_topic": demo["weak_topic"],
                        "attended_at": _demo_attended_hours_ago(demo["hours_ago"]),
                    }
                )
                counts["demos"] += 1

    return counts
