"""Callback cadence policy."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.telephony.cadence import (
    IST,
    MAX_NO_ANSWER_ATTEMPTS,
    next_no_answer_retry,
    parent_requested_callback_at,
)


def _utc(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def test_first_retry_is_thirty_minutes_later_inside_window():
    # 12:00 IST = 06:30 UTC
    prev = datetime(2026, 6, 1, 12, 0, tzinfo=IST).astimezone(timezone.utc)
    d = next_no_answer_retry(prev, attempts_so_far=1)
    expected_ist = datetime(2026, 6, 1, 12, 30, tzinfo=IST)
    assert d.next_attempt_at_utc.astimezone(IST) == expected_ist
    assert d.attempt_number == 2
    assert d.reason == "no_answer_retry"
    assert not d.is_terminal


def test_retry_slides_out_of_late_night():
    # 22:00 IST → next retry would be 22:30 → must slide to 10:00 next day
    prev = datetime(2026, 6, 1, 22, 0, tzinfo=IST).astimezone(timezone.utc)
    d = next_no_answer_retry(prev, attempts_so_far=1)
    out_ist = d.next_attempt_at_utc.astimezone(IST)
    assert out_ist.date() == datetime(2026, 6, 2).date()
    assert out_ist.hour == 10 and out_ist.minute == 0


def test_attempt_four_targets_next_day_morning():
    prev = datetime(2026, 6, 1, 14, 0, tzinfo=IST).astimezone(timezone.utc)
    d = next_no_answer_retry(prev, attempts_so_far=3)  # → schedule attempt 4
    out_ist = d.next_attempt_at_utc.astimezone(IST)
    assert d.attempt_number == 4
    assert out_ist.date() == datetime(2026, 6, 2).date()
    assert out_ist.hour == 11


def test_attempt_five_targets_next_day_evening():
    prev = datetime(2026, 6, 1, 12, 0, tzinfo=IST).astimezone(timezone.utc)
    d = next_no_answer_retry(prev, attempts_so_far=4)  # → schedule attempt 5
    out_ist = d.next_attempt_at_utc.astimezone(IST)
    assert d.attempt_number == 5
    assert out_ist.hour == 19 and out_ist.minute == 30


def test_after_max_attempts_we_terminal_into_nurture():
    prev = datetime(2026, 6, 1, 12, 0, tzinfo=IST).astimezone(timezone.utc)
    d = next_no_answer_retry(prev, attempts_so_far=MAX_NO_ANSWER_ATTEMPTS)
    assert d.is_terminal
    assert d.reason == "nurture_followup"
    out_ist = d.next_attempt_at_utc.astimezone(IST)
    assert out_ist.hour == 11  # nurture is at 11 AM IST


def test_parent_requested_honours_time_inside_window():
    asked = datetime(2026, 6, 1, 17, 0, tzinfo=IST).astimezone(timezone.utc)
    out = parent_requested_callback_at(asked)
    assert out.astimezone(IST).hour == 17


def test_parent_requested_slides_late_request_to_next_morning():
    asked = datetime(2026, 6, 1, 23, 0, tzinfo=IST).astimezone(timezone.utc)
    out = parent_requested_callback_at(asked).astimezone(IST)
    assert out.date() == datetime(2026, 6, 2).date()
    assert out.hour == 10


def test_no_answer_retry_skips_sunday():
    # Saturday 22:00 → no-answer → next retry at 22:30 should slide past Sunday
    # because allow_sunday=False by default for retries.
    prev = datetime(2026, 6, 6, 22, 0, tzinfo=IST).astimezone(timezone.utc)  # Sat
    d = next_no_answer_retry(prev, attempts_so_far=1)
    out_ist = d.next_attempt_at_utc.astimezone(IST)
    assert out_ist.weekday() == 0  # Monday
