"""Idempotent seeding of demo data.

NOTE on data provenance:
  - Course names / structures: representative of Vedantu's public catalog
    (JEE Crash, NEET Crash, V-Pro Class 9/10) but prices and offers are
    plausible mocks, not scraped. Replace with real values before any real
    customer pilot.
  - Children's DoBs are deliberately spread so at least one child has a
    birthday within the next 7-30 days from "today" — exercises the
    birthday-aware sales angle.
  - Phone numbers use the docs/test ranges where possible. Replace
    parents[0].phone with your own mobile (or set DEMO_PHONE_NUMBER in .env)
    before running a live Twilio call.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.crm.db import connect, init_db


def _today() -> date:
    return date.today()


def _dob_with_birthday_in_days(days: int, age_years: int) -> str:
    target = _today() + timedelta(days=days)
    return date(target.year - age_years, target.month, target.day).isoformat()


def _demo_attended_hours_ago(hours: int) -> str:
    return (datetime.utcnow() - timedelta(hours=hours)).isoformat()


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
        "offer_expires_at": None,  # filled at runtime relative to call time
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

# Five test parents. parents[0] uses a placeholder you should replace with
# your own number before the live Twilio call. The seeder picks up
# DEMO_PHONE_NUMBER from the environment for parents[0] automatically.
PARENTS = [
    {
        "name": "Mr. Sharma",
        "phone": "+919999900001",  # overridden by DEMO_PHONE_NUMBER if set
        "preferred_language": "hi-IN",
        "city": "Lucknow",
        "children": [
            {
                "name": "Aarav",
                "dob": _dob_with_birthday_in_days(12, 16),  # birthday in 12 days
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
                "name": "Diya",
                "dob": _dob_with_birthday_in_days(3, 16),  # birthday in 3 days
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
        "name": "Mr. Bose",
        "phone": "+919999900005",
        "preferred_language": "mixed",
        "city": "Kolkata",
        "children": [
            {
                "name": "Anaya",
                "dob": _dob_with_birthday_in_days(28, 14),  # birthday in 28 days
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

# Battle card — concise, defensible, never trash-talks the competitor.
# Sourced from public claims; treat as starting point and refine with sales.
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


async def seed(database_path: str | None = None, demo_phone: str | None = None) -> dict:
    """Seed the DB idempotently. Returns counts."""
    await init_db(database_path)
    counts = {"parents": 0, "children": 0, "courses": 0, "demos": 0, "competitors": 0}

    async with connect(database_path) as db:
        # Courses
        for c in COURSES:
            cur = await db.execute("SELECT id FROM courses WHERE code = ?", (c["code"],))
            existing = await cur.fetchone()
            if existing:
                continue
            await db.execute(
                """INSERT INTO courses (code, name, grade, board, exam_target, subjects, duration,
                                          fee_amount, fee_spoken, payment_plan_available,
                                          scholarship_available, batch_options, current_offer)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    c["code"], c["name"], c["grade"], c["board"], c["exam_target"],
                    c["subjects"], c["duration"], c["fee_amount"], c["fee_spoken"],
                    c["payment_plan_available"], c["scholarship_available"],
                    c["batch_options"], c["current_offer"],
                ),
            )
            counts["courses"] += 1

        # Competitors
        cur = await db.execute("SELECT COUNT(*) AS n FROM competitors")
        n_comp = (await cur.fetchone())["n"]  # type: ignore[index]
        if n_comp == 0:
            for c in COMPETITORS:
                await db.execute(
                    """INSERT INTO competitors (name, axis, parent_concern, vedantu_counter, proof_point)
                       VALUES (?, ?, ?, ?, ?)""",
                    (c["name"], c["axis"], c["parent_concern"], c["vedantu_counter"], c["proof_point"]),
                )
                counts["competitors"] += 1

        # Parents → children → demos
        for p in PARENTS:
            phone = p["phone"]
            if demo_phone and p is PARENTS[0]:
                phone = demo_phone

            cur = await db.execute("SELECT id FROM parents WHERE phone = ?", (phone,))
            existing = await cur.fetchone()
            if existing:
                parent_id = existing["id"]  # type: ignore[index]
            else:
                cur = await db.execute(
                    "INSERT INTO parents (name, phone, preferred_language, city) VALUES (?, ?, ?, ?)",
                    (p["name"], phone, p["preferred_language"], p["city"]),
                )
                parent_id = cur.lastrowid
                counts["parents"] += 1

            for ch in p["children"]:
                cur = await db.execute(
                    "SELECT id FROM children WHERE parent_id = ? AND name = ?",
                    (parent_id, ch["name"]),
                )
                existing = await cur.fetchone()
                if existing:
                    child_id = existing["id"]  # type: ignore[index]
                else:
                    cur = await db.execute(
                        """INSERT INTO children (parent_id, name, dob, grade, board, exam_target, exam_date)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (parent_id, ch["name"], ch["dob"], ch["grade"], ch["board"],
                         ch["exam_target"], ch["exam_date"]),
                    )
                    child_id = cur.lastrowid
                    counts["children"] += 1

                demo = p["demo"]
                cur = await db.execute("SELECT id FROM courses WHERE code = ?", (demo["course_code"],))
                course_row = await cur.fetchone()
                course_id = course_row["id"]  # type: ignore[index]

                cur = await db.execute(
                    "SELECT id FROM demos WHERE child_id = ? AND course_id = ?",
                    (child_id, course_id),
                )
                if (await cur.fetchone()) is None:
                    await db.execute(
                        """INSERT INTO demos (child_id, course_id, subject, teacher, weak_topic, attended_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            child_id, course_id, demo["subject"], demo["teacher"],
                            demo["weak_topic"],
                            _demo_attended_hours_ago(demo["hours_ago"]),
                        ),
                    )
                    counts["demos"] += 1

        await db.commit()
    return counts
