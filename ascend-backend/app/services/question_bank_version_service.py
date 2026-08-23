"""Question Bank Version service (DOCX Table 22 data dictionary).

`get_active_version` mirrors `ScoringConfigService.get_active_config`'s
effective-dating logic, plus the `retired_date` gate that entity doesn't
have: the active version is the most recent one (by `effective_date`)
that is both in effect today and not yet retired.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.models.question_bank_version import QuestionBankVersion
from app.models.user import User
from app.schemas.question_bank_version import QuestionBankVersionCreate
from app.services.audit_log_service import AuditLogService


class QuestionBankVersionService:
    """Create, retire, and read the real Question Bank Version history."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def get_active_version(self) -> QuestionBankVersion | None:
        """Return the currently effective, non-retired version, if any exists."""
        today = date.today()
        candidates = await QuestionBankVersion.find(
            QuestionBankVersion.effective_date <= today
        ).to_list()
        in_effect = [v for v in candidates if v.retired_date is None or v.retired_date > today]
        if not in_effect:
            return None
        return max(in_effect, key=lambda item: item.effective_date)

    async def get_active_version_summary(self) -> dict[str, Any] | None:
        """Return the serialized active version, or `None` if an Admin has never recorded one."""
        active = await self.get_active_version()
        return await self._serialize(active) if active else None

    async def create_version(self, actor: User, payload: QuestionBankVersionCreate) -> dict[str, Any]:
        """Admin/Superadmin records a new approved question bank version. Audit logged."""
        record = QuestionBankVersion(
            version_id=payload.version_id,
            effective_date=payload.effective_date,
            approved_by=actor.id,
            onboarding_question_set_id=payload.onboarding_question_set_id,
            daily_question_set_id=payload.daily_question_set_id,
            weekly_question_set_id=payload.weekly_question_set_id,
            monthly_question_set_id=payload.monthly_question_set_id,
            change_reason=payload.change_reason,
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="question_bank_version_created",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="question_bank_version",
            target_entity_id=str(record.id),
            summary_message=f"{actor.role} approved question bank version {record.version_id}.",
            metadata_payload={"version_id": record.version_id},
        )
        return await self._serialize(record)

    async def retire_version(self, actor: User, version_object_id: str) -> dict[str, Any]:
        """Admin/Superadmin retires a version as of today. Audit logged."""
        record = await QuestionBankVersion.get(version_object_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question bank version not found.")
        if record.retired_date is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This version is already retired.")

        record.retired_date = date.today()
        await record.save()

        await self.audit_log_service.record(
            event_type="question_bank_version_retired",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="question_bank_version",
            target_entity_id=str(record.id),
            summary_message=f"{actor.role} retired question bank version {record.version_id}.",
            metadata_payload={"version_id": record.version_id},
        )
        return await self._serialize(record)

    async def list_versions(self) -> dict[str, Any]:
        """Return every recorded version, newest first."""
        records = await QuestionBankVersion.find().to_list()
        records.sort(key=lambda item: item.effective_date, reverse=True)
        return {"versions": [await self._serialize(r) for r in records]}

    async def _serialize(self, record: QuestionBankVersion) -> dict[str, Any]:
        active = await self.get_active_version()
        return {
            "id": str(record.id),
            "version_id": record.version_id,
            "effective_date": record.effective_date.isoformat(),
            "retired_date": record.retired_date.isoformat() if record.retired_date else None,
            "approved_by": str(record.approved_by),
            "onboarding_question_set_id": record.onboarding_question_set_id,
            "daily_question_set_id": record.daily_question_set_id,
            "weekly_question_set_id": record.weekly_question_set_id,
            "monthly_question_set_id": record.monthly_question_set_id,
            "change_reason": record.change_reason,
            "is_active": active is not None and active.id == record.id,
            "created_at": record.created_at.isoformat(),
        }
