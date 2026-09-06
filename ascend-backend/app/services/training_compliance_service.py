"""Staff training compliance service (DOCX Section 14: AT Level I, OPSEC
Initial Training, OPSEC Annual Refresher).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.core.roles import ROLE_AIRMAN, SUPPORTED_ROLES
from app.core.security import utc_now
from app.models.training_compliance import TRAINING_TYPES, TrainingCompliance
from app.models.user import User
from app.schemas.training_compliance import TrainingComplianceUpsert
from app.services.audit_log_service import AuditLogService

STAFF_ROLES = tuple(role for role in SUPPORTED_ROLES if role != ROLE_AIRMAN)


class TrainingComplianceService:
    """Record and summarize real staff training compliance."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def upsert(self, admin: User, user_id: str, payload: TrainingComplianceUpsert) -> dict[str, Any]:
        """Admin records or updates one staff member's training item. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        record = await TrainingCompliance.find_one(
            TrainingCompliance.user_id == target.id, TrainingCompliance.training_type == payload.training_type
        )
        is_new = record is None
        if is_new:
            record = TrainingCompliance(user_id=target.id, training_type=payload.training_type, due_date=payload.due_date, recorded_by=admin.id)

        record.due_date = payload.due_date
        record.completion_date = payload.completion_date
        record.certificate_uploaded = payload.certificate_uploaded
        record.submitted_to = payload.submitted_to
        record.submission_status = payload.submission_status
        record.renewal_due_date = payload.renewal_due_date
        record.recorded_by = admin.id
        record.updated_at = utc_now()
        await record.save()

        await self.audit_log_service.record(
            event_type="training_compliance_recorded" if is_new else "training_compliance_updated",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="training_compliance",
            target_entity_id=str(record.id),
            summary_message=f"{payload.training_type} recorded for {target.email} - {payload.submission_status}.",
        )
        return await self._serialize(record, target)

    async def list_for_user(self, user_id: str) -> dict[str, Any]:
        """Real training items recorded for one staff member."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        records = await TrainingCompliance.find(TrainingCompliance.user_id == target.id).to_list()
        records.sort(key=lambda r: r.training_type)
        return {"items": [await self._serialize(r, target) for r in records]}

    async def get_compliance_summary(self) -> dict[str, Any]:
        """Real org-wide compliance status across every staff member x required training type.

        Not DOCX-sourced as a single tile (a Figma "Compliance - 55d PASS"
        card triggered this) - the underlying tracking (due dates,
        completion, submission status) is DOCX Section 14, verbatim. A
        staff member's item is "compliant" only if it has a real
        completion_date and either no due_date has passed uncompleted, or
        (for opsec_annual_refresher) a real renewal_due_date is still in
        the future. Never having recorded an item is not silently
        compliant - it counts as open, matching the DOCX's own "corrective
        action" framing for missed items rather than assuming pass-by-default.
        """
        staff = await User.find({"role": {"$in": list(STAFF_ROLES)}, "is_active": True}).to_list()
        staff_ids = [u.id for u in staff]
        records = await TrainingCompliance.find({"user_id": {"$in": staff_ids}}).to_list()
        records_by_key = {(r.user_id, r.training_type): r for r in records}

        today = date.today()
        compliant_count = 0
        overdue_count = 0
        open_count = 0
        total_required = len(staff) * len(TRAINING_TYPES)

        for user_id in staff_ids:
            for training_type in TRAINING_TYPES:
                record = records_by_key.get((user_id, training_type))
                # Mutually exclusive buckets - every staff x training-type
                # combination lands in exactly one, so the 3 counts always
                # sum to total_required (never never-recorded double-
                # counted as both "open" and "overdue").
                if record is None:
                    open_count += 1
                    continue
                if record.completion_date is None:
                    if record.due_date < today:
                        overdue_count += 1
                    else:
                        open_count += 1
                    continue
                # Overdue means completed *late* (after its deadline), not
                # merely that the deadline has since passed - a real due
                # date is almost always in the past by the time anyone
                # looks at this summary, even for on-time completions.
                effective_due = record.renewal_due_date or record.due_date
                if record.completion_date > effective_due:
                    overdue_count += 1
                else:
                    compliant_count += 1

        return {
            "window_days": 55,
            "staff_count": len(staff),
            "total_required_items": total_required,
            "compliant_count": compliant_count,
            "overdue_count": overdue_count,
            "open_count": open_count,
            "status": "pass" if open_count == 0 and overdue_count == 0 else "open_items",
            "checked_at": utc_now().isoformat(),
        }

    async def _serialize(self, record: TrainingCompliance, target: User) -> dict[str, Any]:
        today = date.today()
        effective_due = record.renewal_due_date or record.due_date
        # Overdue means completed *late* (after the deadline) or, if not
        # yet completed, the deadline has already passed - not simply "the
        # due date is in the past", which would mislabel an on-time
        # completion as overdue once enough time goes by.
        if record.completion_date is None:
            is_overdue = record.due_date < today
        else:
            is_overdue = record.completion_date > effective_due
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "user_name": target.full_name,
            "training_type": record.training_type,
            "due_date": record.due_date.isoformat(),
            "completion_date": record.completion_date.isoformat() if record.completion_date else None,
            "certificate_uploaded": record.certificate_uploaded,
            "submitted_to": record.submitted_to,
            "submission_status": record.submission_status,
            "renewal_due_date": record.renewal_due_date.isoformat() if record.renewal_due_date else None,
            "is_overdue": is_overdue,
            "updated_at": record.updated_at.isoformat(),
        }
