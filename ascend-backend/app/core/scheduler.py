"""Background scheduler for cadence-due reminders (DOCX: "login/activity
tracking" implies proactive reminders, not just reminders triggered when a
user happens to open a screen).

Before this, every reminder in this backend only fired when a user's own
request touched the relevant code path (e.g. opening the daily check-in
screen). That meant a user who never opened the app would never be
reminded a weekly check-in was opening, or that an OFT/assessment was
coming up - the exact case a proactive reminder exists to cover.

This runs one in-process daily job (APScheduler, `AsyncIOScheduler`) that
reuses the same reminder methods/dedup logic already used by the
request-triggered paths, so nothing here duplicates notification rules -
it just makes sure they fire even if no one opens the app that day. This
is in-process, not a distributed task queue - acceptable for a single
backend instance; would need Celery/RQ + a broker for multi-instance
deployment (still an open item in `TASKS.MD`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.cadence import next_weekly_open
from app.models.user import User
from app.services.assessment_service import AssessmentService
from app.services.checkin_service import CheckinService
from app.services.credential_service import CredentialService
from app.services.oft_service import OFTService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_daily_reminders() -> None:
    """Run every cadence-due reminder check once, for every active user."""
    checkin_service = CheckinService()
    oft_service = OFTService()
    assessment_service = AssessmentService()
    credential_service = CredentialService()

    now = datetime.now(timezone.utc)
    today = now.date()
    next_open = next_weekly_open(now)
    days_until_open = max((next_open.date() - today).days, 0)

    # Filter is_active in Python rather than `User.is_active == True` - this
    # project has a documented Beanie boolean-equality query gotcha (see
    # `TeamService._find_active_provider`), so every other active-user
    # lookup already avoids it the same way.
    all_users = await User.find().to_list()
    users = [u for u in all_users if u.is_active]
    for user in users:
        try:
            await checkin_service.remind_daily_checkin_open(user, today)
            if days_until_open <= 2:
                await checkin_service.remind_weekly_checkin_opening(user, next_open.date())
        except Exception:
            logger.warning("Daily reminder failed for user %s", user.id, exc_info=True)

    oft_sent = await oft_service.remind_due_soon()
    assessment_sent = await assessment_service.remind_due_soon()
    credential_sent = await credential_service.remind_expiring_soon()
    logger.info(
        "Daily reminder job complete: %d users checked, %d OFT, %d assessment, %d credential reminders sent",
        len(users),
        oft_sent,
        assessment_sent,
        credential_sent,
    )


def start_scheduler() -> None:
    """Start the in-process daily reminder job (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        run_daily_reminders,
        trigger="cron",
        hour=6,
        minute=0,
        id="daily_reminders",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Background scheduler started (daily_reminders job at 06:00 UTC).")


def stop_scheduler() -> None:
    """Stop the scheduler, if running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
