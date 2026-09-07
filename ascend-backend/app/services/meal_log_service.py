"""Meal log service (see `app/models/meal_log.py`)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, ROLE_NUTRITIONIST
from app.models.meal_log import MealLog
from app.models.user import User
from app.schemas.meal_log import MealLogCreate, MealLogFlagUpdate
from app.services.audit_log_service import AuditLogService


class MealLogService:
    """Create and list real logged meals; Nutritionist flags entries for review."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def create(self, actor: User, target_user_id: str, payload: MealLogCreate) -> dict[str, Any]:
        """The operator logs their own meal, or a Nutritionist logs one on the operator's behalf."""
        target = await User.get(target_user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if actor.id != target.id and actor.role not in (*ADMIN_ROLES, ROLE_NUTRITIONIST):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the operator themselves or a Nutritionist/Admin can log a meal for this user.",
            )

        record = MealLog(
            user_id=target.id,
            meal_date=payload.meal_date,
            meal_type=payload.meal_type,
            description=payload.description,
            calories=payload.calories,
            carbs_g=payload.carbs_g,
            protein_g=payload.protein_g,
            fat_g=payload.fat_g,
            logged_by_id=actor.id,
        )
        await record.insert()
        return self._serialize(record)

    async def list_for_user(self, viewer: User, target_user_id: str, days: int = 60) -> dict[str, Any]:
        """Real logged meals for an operator over the trailing `days` (default 60, matches
        the existing `nutrition_signals` window in `provider_dashboard_service`)."""
        if viewer.id != PydanticObjectId(target_user_id) and viewer.role not in (*ADMIN_ROLES, ROLE_NUTRITIONIST):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view these meal logs.")

        since = datetime.now(timezone.utc) - timedelta(days=days)
        records = await MealLog.find(
            MealLog.user_id == PydanticObjectId(target_user_id),
            MealLog.meal_date >= since,
        ).to_list()
        records.sort(key=lambda r: r.meal_date, reverse=True)
        return {"meal_logs": [self._serialize(r) for r in records]}

    async def update_flag(self, actor: User, meal_log_id: str, payload: MealLogFlagUpdate) -> dict[str, Any]:
        """Only a Nutritionist or Admin can flag a meal entry for review."""
        if actor.role not in (*ADMIN_ROLES, ROLE_NUTRITIONIST):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a Nutritionist/Admin can flag a meal entry.")

        record = await MealLog.get(meal_log_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal log not found.")

        record.flagged = payload.flagged
        record.flag_reason = payload.flag_reason if payload.flagged else None
        await record.save()
        await self.audit_log_service.record(
            event_type="meal_log_flagged" if payload.flagged else "meal_log_unflagged",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type="meal_log",
            target_entity_id=str(record.id),
            summary_message=payload.flag_reason or "Meal log flag updated.",
        )
        return self._serialize(record)

    def _serialize(self, record: MealLog) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "meal_date": record.meal_date.isoformat(),
            "meal_type": record.meal_type,
            "description": record.description,
            "calories": record.calories,
            "carbs_g": record.carbs_g,
            "protein_g": record.protein_g,
            "fat_g": record.fat_g,
            "flagged": record.flagged,
            "flag_reason": record.flag_reason,
            "logged_by_id": str(record.logged_by_id),
            "created_at": record.created_at.isoformat(),
        }
