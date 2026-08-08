"""Operator assessment tracking service (DOCX section 8.1).

Scheduling and completion are SCS/Admin actions (no automated scheduler
exists). This tracks per-user assessment status only - it does not
implement the cohort-level "50% within 6 months / 90% within 12 months"
compliance rollup or the PRS evidence export, both of which are
leadership/admin-reporting work.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from datetime import date, timedelta

from app.core.cadence import phrase_relative_date
from app.core.notification_rules import ASSESSMENT_DUE_REMINDERS
from app.core.security import utc_now
from app.models.assessment import Assessment
from app.models.user import User
from app.schemas.assessment import ASSESSMENT_TYPE_LABELS
from app.schemas.assessment import RESULT_BAND_LABELS
from app.schemas.assessment import AssessmentCompleteRequest
from app.schemas.assessment import AssessmentScheduleRequest
from app.services.notification_service import NotificationService

DUE_SOON_DAYS = 7


class AssessmentService:
    """Track operator assessment scheduling, completion, and status."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()

    async def remind_due_soon(self) -> int:
        """Send an "assessment coming up" reminder for scheduled assessments due within DUE_SOON_DAYS.

        Deduped per record via a stable `related_entity_id`. Returns the
        number of reminders actually sent.
        """
        today = date.today()
        cutoff = today + timedelta(days=DUE_SOON_DAYS)
        candidates = await Assessment.find(
            Assessment.due_date >= today, Assessment.due_date <= cutoff
        ).to_list()
        upcoming = [r for r in candidates if r.status in ("scheduled", "not_started")]

        sent = 0
        for record in upcoming:
            already_sent = await self.notification_service.exists_since(
                record.user_id,
                family=ASSESSMENT_DUE_REMINDERS,
                related_entity_type="assessment_due_soon",
                related_entity_id=str(record.id),
            )
            if already_sent:
                continue
            relative = phrase_relative_date(record.due_date, today)
            label = ASSESSMENT_TYPE_LABELS.get(record.assessment_type, record.assessment_type)
            await self.notification_service.notify(
                record.user_id,
                family=ASSESSMENT_DUE_REMINDERS,
                title="Assessment coming up",
                body=f"{label} is due {relative}.",
                related_entity_type="assessment_due_soon",
                related_entity_id=str(record.id),
            )
            sent += 1
        return sent

    async def schedule(
        self,
        user: User,
        payload: AssessmentScheduleRequest,
        created_by: Any,
    ) -> dict[str, Any]:
        """Schedule (or reschedule) an assessment for a user."""
        record = await Assessment.find_one(
            Assessment.user_id == user.id,
            Assessment.assessment_type == payload.assessment_type,
        )
        if record is None:
            record = Assessment(
                user_id=user.id,
                assessment_type=payload.assessment_type,
                created_by=created_by,
            )
        record.status = "scheduled"
        record.due_date = payload.due_date
        record.scheduled_date = payload.scheduled_date
        record.updated_at = utc_now()
        await record.save()

        target_date = payload.scheduled_date or payload.due_date
        relative = phrase_relative_date(target_date, date.today())
        display_title = ASSESSMENT_TYPE_LABELS.get(payload.assessment_type, payload.assessment_type)
        await self.notification_service.notify(
            user.id,
            family=ASSESSMENT_DUE_REMINDERS,
            title=f"{display_title} scheduled",
            body=f"Your {display_title.lower()} is scheduled for {relative}.",
            related_entity_type="assessment",
            related_entity_id=str(record.id),
        )
        return self._serialize(record)

    async def complete(
        self,
        user: User,
        assessment_type: str,
        payload: AssessmentCompleteRequest,
    ) -> dict[str, Any]:
        """Record a completed assessment result."""
        record = await Assessment.find_one(
            Assessment.user_id == user.id, Assessment.assessment_type == assessment_type
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No scheduled assessment found for this type.",
            )
        record.status = "completed"
        record.completed_date = payload.completed_date
        record.result_band = payload.result_band
        record.physical_result_summary = payload.physical_result_summary
        record.mental_result_summary = payload.mental_result_summary
        record.feedback_session_status = payload.feedback_session_status
        record.updated_at = utc_now()
        await record.save()
        return self._serialize(record)

    async def list_for_user(self, user: User, completed_limit: int = 5) -> dict[str, Any]:
        """Return a user's assessment records, with the most recent completed ones first."""
        records = await Assessment.find(Assessment.user_id == user.id).to_list()
        completed = sorted(
            (r for r in records if r.status == "completed" and r.completed_date is not None),
            key=lambda item: item.completed_date,
            reverse=True,
        )
        active = [r for r in records if r.status != "completed"]
        return {
            "completed": [self._serialize(r) for r in completed[:completed_limit]],
            "completed_total": len(completed),
            "active": [self._serialize(r) for r in active],
        }

    async def get_initial_assessment(self, user: User) -> Assessment | None:
        """Return the user's initial assessment record, if any."""
        return await Assessment.find_one(
            Assessment.user_id == user.id, Assessment.assessment_type == "initial"
        )

    def _serialize(self, record: Assessment) -> dict[str, Any]:
        """Convert a stored assessment to a transport-safe, qualitative-only dict."""
        return {
            "id": str(record.id),
            "assessment_type": record.assessment_type,
            "display_title": ASSESSMENT_TYPE_LABELS.get(record.assessment_type, record.assessment_type),
            "status": record.status,
            "due_date": record.due_date.isoformat() if record.due_date else None,
            "scheduled_date": record.scheduled_date.isoformat() if record.scheduled_date else None,
            "completed_date": record.completed_date.isoformat() if record.completed_date else None,
            "result_band": record.result_band,
            "result_band_label": RESULT_BAND_LABELS.get(record.result_band) if record.result_band else None,
            "physical_result_summary": record.physical_result_summary,
            "mental_result_summary": record.mental_result_summary,
            "feedback_session_status": record.feedback_session_status,
        }
