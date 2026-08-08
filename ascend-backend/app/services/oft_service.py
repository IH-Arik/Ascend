"""OFT (Operational Fitness Test) tracking service (DOCX section 8.2).

Scheduling and result recording are SCS/Admin actions (no automated
scheduler exists). This is status tracking only - it does not implement
reconditioning plan assignment or the monthly leadership metrics report,
both of which are separate provider/leadership-facing work.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.cadence import phrase_relative_date
from app.core.notification_rules import OFT_DUE_REMINDERS
from app.models.oft_record import OFTRecord
from app.models.user import User
from app.schemas.oft import OFTRecordResultRequest
from app.schemas.oft import OFTScheduleRequest
from app.services.notification_service import NotificationService

COMPLETED_STATUSES = {"current", "not_current", "exempt"}
DUE_SOON_DAYS = 7


class OFTService:
    """Track OFT scheduling, results, and status for users."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()

    async def remind_due_soon(self) -> int:
        """Send an "OFT coming up" reminder for every scheduled test within DUE_SOON_DAYS.

        Deduped per record (not per day) via a stable `related_entity_id`, so
        this is safe to call from a daily scheduled job without re-notifying.
        Returns the number of reminders actually sent.
        """
        today = date.today()
        cutoff = today + timedelta(days=DUE_SOON_DAYS)
        upcoming = await OFTRecord.find(
            OFTRecord.status == "scheduled",
            OFTRecord.test_date >= today,
            OFTRecord.test_date <= cutoff,
        ).to_list()

        sent = 0
        for record in upcoming:
            already_sent = await self.notification_service.exists_since(
                record.user_id,
                family=OFT_DUE_REMINDERS,
                related_entity_type="oft_due_soon",
                related_entity_id=str(record.id),
            )
            if already_sent:
                continue
            relative = phrase_relative_date(record.test_date, today)
            await self.notification_service.notify(
                record.user_id,
                family=OFT_DUE_REMINDERS,
                title="OFT coming up",
                body=f"Your OFT is scheduled {relative}.",
                related_entity_type="oft_due_soon",
                related_entity_id=str(record.id),
            )
            sent += 1
        return sent

    async def schedule(
        self,
        user: User,
        payload: OFTScheduleRequest,
        recorded_by: Any,
    ) -> dict[str, Any]:
        """Schedule an upcoming OFT test."""
        record = OFTRecord(
            user_id=user.id,
            test_date=payload.test_date,
            status="scheduled",
            notes=payload.notes,
            recorded_by=recorded_by,
        )
        await record.insert()
        relative = phrase_relative_date(payload.test_date, date.today())
        await self.notification_service.notify(
            user.id,
            family=OFT_DUE_REMINDERS,
            title="OFT scheduled",
            body=f"Your OFT is scheduled for {relative}.",
            related_entity_type="oft_record",
            related_entity_id=str(record.id),
        )
        return await self.get_status_for_user(user)

    async def record_result(
        self,
        user: User,
        payload: OFTRecordResultRequest,
        recorded_by: Any,
    ) -> dict[str, Any]:
        """Record a completed OFT test result."""
        record = OFTRecord(
            user_id=user.id,
            test_date=payload.test_date,
            status=payload.status,
            pass_fail=payload.pass_fail,
            items_passed=payload.items_passed,
            items_total=payload.items_total,
            entered_into_government_system=payload.entered_into_government_system,
            notes=payload.notes,
            recorded_by=recorded_by,
        )
        await record.insert()
        return await self.get_status_for_user(user)

    async def get_status_for_user(self, user: User) -> dict[str, Any]:
        """Return the current OFT status summary for a user."""
        records = await OFTRecord.find(OFTRecord.user_id == user.id).to_list()
        today = date.today()

        completed = sorted(
            (r for r in records if r.status in COMPLETED_STATUSES),
            key=lambda item: item.test_date,
            reverse=True,
        )
        upcoming = sorted(
            (r for r in records if r.status == "scheduled" and r.test_date >= today),
            key=lambda item: item.test_date,
        )
        latest = completed[0] if completed else None
        year_cutoff = today - timedelta(days=365)
        annual_test_count = sum(1 for r in completed if r.test_date >= year_cutoff)

        current_status = latest.status if latest else ("scheduled" if upcoming else "no_record")
        next_scheduled_date = upcoming[0].test_date if upcoming else None
        return {
            "current_status": current_status,
            "latest_pass_fail": latest.pass_fail if latest else None,
            "latest_test_date": latest.test_date.isoformat() if latest else None,
            "items_passed": latest.items_passed if latest else None,
            "items_total": latest.items_total if latest else None,
            "next_scheduled_date": next_scheduled_date.isoformat() if next_scheduled_date else None,
            "next_scheduled_relative": (
                f"in {(next_scheduled_date - today).days} days" if next_scheduled_date else None
            ),
            "annual_test_count": annual_test_count,
        }
