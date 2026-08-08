"""Cadence anchor math for weekly/monthly check-in gating.

Weekly cadence resets on a fixed calendar anchor (Tuesday 06:00), not a
rolling N-days-since-user-start window - confirmed by the "Weekly check-in
opens in N days... Cadence resets every Tuesday at 0600 local" gate screen.
Timezone handling uses UTC as "local" for now; per-user timezone is an open
question in docs/NOTIFICATION_RULES.md and is not implemented yet.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

WEEKLY_RESET_WEEKDAY = 1  # Monday=0 ... Tuesday=1
WEEKLY_RESET_HOUR = 6


def next_weekly_open(now: datetime) -> datetime:
    """Return the next Tuesday 06:00 strictly after `now`."""
    days_ahead = (WEEKLY_RESET_WEEKDAY - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=WEEKLY_RESET_HOUR, minute=0, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def current_weekly_window_start(now: datetime) -> datetime:
    """Return the most recent Tuesday 06:00 at or before `now`."""
    return next_weekly_open(now) - timedelta(days=7)


MONTHLY_CADENCE_DAYS = 30


def next_monthly_review(cadence_start: date, today: date) -> date:
    """Return the next monthly review date, rolling every 30 days from cadence start.

    Unlike weekly (confirmed fixed Tuesday-0600 anchor), no screenshot or
    DOCX text confirms a fixed calendar rule for monthly - "appears only
    when cadence is due" (docs/CHECKIN_FLOWS.md) without specifying which
    day. Rolling 30-day cycles from the user's own cadence start date is the
    best defensible inference, not a confirmed rule.
    """
    if today < cadence_start:
        return cadence_start
    elapsed = (today - cadence_start).days
    cycles_passed = elapsed // MONTHLY_CADENCE_DAYS
    return cadence_start + timedelta(days=(cycles_passed + 1) * MONTHLY_CADENCE_DAYS)


def current_monthly_window_start(cadence_start: date, today: date) -> date:
    """Return the start date of the current 30-day monthly cadence cycle."""
    return next_monthly_review(cadence_start, today) - timedelta(days=MONTHLY_CADENCE_DAYS)


_WEEKDAY_NAMES = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def phrase_relative_date(target: date, today: date) -> str:
    """Phrase a date as "today"/"tomorrow"/weekday name/formatted date."""
    days_away = (target - today).days
    if days_away == 0:
        return "today"
    if days_away == 1:
        return "tomorrow"
    if 2 <= days_away <= 6:
        return _WEEKDAY_NAMES[target.weekday()]
    return f"{target.strftime('%b')} {target.day}"
