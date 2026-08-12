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
from datetime import date, datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.cadence import next_weekly_open
from app.core.recommendation_rules import COMPONENT_PRIORITY_ORDER
from app.core.roles import ROLE_AIRMAN
from app.models.ops_snapshot import OpsSnapshot
from app.models.scheduler_job_run import SchedulerJobRun
from app.models.user import User
from app.services.admin_confirmation_service import AdminConfirmationService
from app.services.assessment_service import AssessmentService
from app.services.audit_log_service import AuditLogService
from app.services.checkin_service import CheckinService
from app.services.credential_service import CredentialService
from app.services.oft_service import OFTService
from app.services.role_admin_service import RoleAdminService
from app.services.scheduled_export_service import ScheduledExportService

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

DAILY_REMINDERS_JOB = "daily_reminders"
UNIT_THRESHOLD_CHECK_JOB = "unit_threshold_check"
SCHEDULED_EXPORTS_JOB = "scheduled_exports"
EXPIRE_STALE_CONFIRMATIONS_JOB = "expire_stale_confirmations"
# Not DOCX-sourced (a Figma "System" screen's tiered "Severity L2/L3/L4
# trigger" rows triggered this) - our own reasonable tier boundaries for a
# 7-day component-score drop, reusing the DOCX's own real L0-L5 escalation
# names (`app/core/routing_levels.py`, Table 20) since this job *is* that
# same escalation concept. `L3_DROP_POINTS` is the old single threshold,
# unchanged in value.
L2_DROP_POINTS = 5.0
L3_DROP_POINTS = 10.0
L4_DROP_POINTS = 20.0
WEEK_LOOKBACK_DAYS = 7


async def run_daily_reminders() -> None:
    """Run every cadence-due reminder check once, for every active user.

    Wrapped so every real run - success or failure - is recorded as a
    `SchedulerJobRun`, the data source for the Admin Overview's real
    "system health" percentage (no fabricated uptime number).
    """
    started_at = datetime.now(timezone.utc)
    try:
        await _run_daily_reminders_body(started_at)
    except Exception as exc:
        await SchedulerJobRun(
            job_name=DAILY_REMINDERS_JOB,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error_message=str(exc),
        ).insert()
        raise


async def _run_daily_reminders_body(started_at: datetime) -> None:
    """The actual reminder work, separated so the wrapper can record success/failure."""
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
    await SchedulerJobRun(
        job_name=DAILY_REMINDERS_JOB,
        status="success",
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    ).insert()


async def run_threshold_check() -> None:
    """Real per-unit 7-day component-score drop check, wrapped for `SchedulerJobRun` tracking.

    Not DOCX-sourced (a Figma "Audit log" screen's "Threshold warning" row
    triggered this). Never a near-individual signal - gated behind the same
    real, admin-configurable k-anonymity minimum as every other unit-
    aggregate view in this codebase (`RoleAdminService.get_scope_config`).
    """
    started_at = datetime.now(timezone.utc)
    try:
        warnings_written = await check_unit_thresholds()
        logger.info("Unit threshold check complete: %d warning(s) written", warnings_written)
        await SchedulerJobRun(
            job_name=UNIT_THRESHOLD_CHECK_JOB,
            status="success",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        ).insert()
    except Exception as exc:
        await SchedulerJobRun(
            job_name=UNIT_THRESHOLD_CHECK_JOB,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error_message=str(exc),
        ).insert()
        raise


def _severity_tier(delta: float) -> str | None:
    """Return the real, highest L-tier a component-score drop crosses, or `None`."""
    if delta <= -L4_DROP_POINTS:
        return "L4"
    if delta <= -L3_DROP_POINTS:
        return "L3"
    if delta <= -L2_DROP_POINTS:
        return "L2"
    return None


async def check_unit_thresholds() -> int:
    """For each real unit meeting the k-anonymity minimum, compare today's average
    component score to ~7 days ago; write one real `AuditLog` advisory entry per
    unit/component at its real, highest-crossed L2/L3/L4 severity tier. Returns
    the number written.
    """
    role_admin_service = RoleAdminService()
    audit_log_service = AuditLogService()

    all_users = await User.find().to_list()
    active_with_unit = [u for u in all_users if u.is_active and u.unit_id]
    units: dict[str, list[User]] = {}
    for user in active_with_unit:
        units.setdefault(user.unit_id, []).append(user)

    # Every unit today is a flat operator cohort - the Airman scope config's
    # cohort_k is the real, admin-configurable minimum that applies.
    scope_config = await role_admin_service.get_scope_config(ROLE_AIRMAN)
    min_cohort_size = scope_config["cohort_k"]

    week_ago = date.today() - timedelta(days=WEEK_LOOKBACK_DAYS)
    warnings_written = 0

    for unit_id, members in units.items():
        if len(members) < min_cohort_size:
            continue
        for component in COMPONENT_PRIORITY_ORDER:
            today_scores = [
                (m.current_component_scores or {}).get(component)
                for m in members
                if (m.current_component_scores or {}).get(component) is not None
            ]
            if not today_scores:
                continue
            today_avg = sum(today_scores) / len(today_scores)

            week_ago_scores = []
            for member in members:
                snapshot = (
                    await OpsSnapshot.find(
                        OpsSnapshot.user_id == member.id, OpsSnapshot.snapshot_date <= week_ago
                    )
                    .sort(-OpsSnapshot.snapshot_date)
                    .limit(1)
                    .to_list()
                )
                if snapshot and snapshot[0].component_scores.get(component) is not None:
                    week_ago_scores.append(snapshot[0].component_scores[component])
            if not week_ago_scores:
                continue
            week_ago_avg = sum(week_ago_scores) / len(week_ago_scores)

            delta = today_avg - week_ago_avg
            severity = _severity_tier(delta)
            if severity is not None:
                await audit_log_service.record(
                    event_type="threshold_warning",
                    actor_id=None,
                    actor_role="system",
                    target_entity_type="unit",
                    target_entity_id=unit_id,
                    summary_message=(
                        f"[{severity}] {component} dropped {abs(delta):.1f} points over "
                        f"{WEEK_LOOKBACK_DAYS}d for unit {unit_id} ({len(members)} members)."
                    ),
                    metadata_payload={
                        "component": component,
                        "delta_7d": round(delta, 2),
                        "cohort_size": len(members),
                        "severity_level": severity,
                    },
                )
                warnings_written += 1
    return warnings_written


async def run_scheduled_exports() -> None:
    """Execute every real due `ScheduledExport`, wrapped for `SchedulerJobRun` tracking.

    Not DOCX-sourced (a Figma "Exports" screen's recurring-export panel
    triggered this). Restricted report types still go through the real
    second-reviewer gate (`ScheduledExportService.run_due_schedules`) - a
    scheduled run is never a way to bypass it.
    """
    started_at = datetime.now(timezone.utc)
    try:
        executed = await ScheduledExportService().run_due_schedules()
        logger.info("Scheduled exports job complete: %d schedule(s) executed", executed)
        await SchedulerJobRun(
            job_name=SCHEDULED_EXPORTS_JOB,
            status="success",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        ).insert()
    except Exception as exc:
        await SchedulerJobRun(
            job_name=SCHEDULED_EXPORTS_JOB,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error_message=str(exc),
        ).insert()
        raise


async def run_expire_stale_confirmations() -> None:
    """Auto-expire real stale pending export confirmations, wrapped for `SchedulerJobRun` tracking.

    Not DOCX-sourced (a Figma "System" screen's "Export approval window:
    72h" claim triggered this) - see `AdminConfirmationService.expire_stale`.
    """
    started_at = datetime.now(timezone.utc)
    try:
        expired = await AdminConfirmationService().expire_stale()
        logger.info("Stale-confirmation expiry job complete: %d confirmation(s) expired", expired)
        await SchedulerJobRun(
            job_name=EXPIRE_STALE_CONFIRMATIONS_JOB,
            status="success",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        ).insert()
    except Exception as exc:
        await SchedulerJobRun(
            job_name=EXPIRE_STALE_CONFIRMATIONS_JOB,
            status="failed",
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error_message=str(exc),
        ).insert()
        raise


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
    _scheduler.add_job(
        run_threshold_check,
        trigger="cron",
        hour=7,
        minute=0,
        id=UNIT_THRESHOLD_CHECK_JOB,
        replace_existing=True,
    )
    _scheduler.add_job(
        run_scheduled_exports,
        trigger="cron",
        minute=0,
        id=SCHEDULED_EXPORTS_JOB,
        replace_existing=True,
    )
    _scheduler.add_job(
        run_expire_stale_confirmations,
        trigger="cron",
        minute=30,
        id=EXPIRE_STALE_CONFIRMATIONS_JOB,
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Background scheduler started (daily_reminders at 06:00 UTC, "
        "unit_threshold_check at 07:00 UTC, scheduled_exports hourly, "
        "expire_stale_confirmations hourly at :30)."
    )


def stop_scheduler() -> None:
    """Stop the scheduler, if running."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
