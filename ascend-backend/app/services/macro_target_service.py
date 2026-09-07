"""Macro target service (see `app/models/macro_target.py`)."""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, ROLE_NUTRITIONIST
from app.core.security import utc_now
from app.models.macro_target import MacroTarget
from app.models.meal_log import MealLog
from app.models.user import User
from app.schemas.macro_target import MacroTargetSet

# Same real tolerance used for the cohort "on-target band" metric
# (`provider_dashboard_service.MACRO_ON_TARGET_TOLERANCE_PCT`) - kept as its
# own constant here to avoid a cross-service import for one shared number.
ON_TARGET_TOLERANCE_PCT = 10.0


class MacroTargetService:
    """Set and read a real, dated per-operator macro-split target history."""

    async def set_target(self, actor: User, target_user_id: str, payload: MacroTargetSet) -> dict[str, Any]:
        """Only a Nutritionist/Admin can set an operator's macro target.

        Real history: the operator's current active target (if any) is
        closed - not overwritten - before the new one is inserted.
        """
        if actor.role not in (*ADMIN_ROLES, ROLE_NUTRITIONIST):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only a Nutritionist/Admin can set a macro target.")

        target = await User.get(target_user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        now = utc_now()
        current = await MacroTarget.find_one(MacroTarget.user_id == target.id, MacroTarget.status == "active")
        if current is not None:
            current.status = "closed"
            current.ended_at = now
            current.updated_at = now
            await current.save()

        record = MacroTarget(
            user_id=target.id,
            title=payload.title,
            carbs_pct=payload.carbs_pct,
            protein_pct=payload.protein_pct,
            fat_pct=payload.fat_pct,
            set_by_id=actor.id,
            started_at=now,
        )
        await record.insert()

        return await self._serialize(record)

    async def get_target(self, viewer: User, target_user_id: str) -> dict[str, Any] | None:
        """The operator's current real active target, if one has been set."""
        if viewer.id != PydanticObjectId(target_user_id) and viewer.role not in (*ADMIN_ROLES, ROLE_NUTRITIONIST):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this macro target.")

        record = await MacroTarget.find_one(
            MacroTarget.user_id == PydanticObjectId(target_user_id), MacroTarget.status == "active"
        )
        return await self._serialize(record) if record else None

    async def list_history(self, viewer: User, target_user_id: str) -> dict[str, Any]:
        """Every real macro target ever set for this operator, most recent first.

        Each entry's `adherence_pct` is computed on read from that entry's
        real `MealLog` window (`started_at` to `ended_at` or now) - never
        stored, so it always reflects the latest logged meals.
        """
        if viewer.id != PydanticObjectId(target_user_id) and viewer.role not in (*ADMIN_ROLES, ROLE_NUTRITIONIST):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to view this macro target history.")

        records = await MacroTarget.find(MacroTarget.user_id == PydanticObjectId(target_user_id)).to_list()
        records.sort(key=lambda r: r.started_at, reverse=True)
        return {"targets": [await self._serialize(r) for r in records]}

    async def _serialize(self, record: MacroTarget) -> dict[str, Any]:
        window_end = record.ended_at or utc_now()
        entries = await MealLog.find(
            {
                "user_id": record.user_id,
                "meal_date": {"$gte": record.started_at, "$lt": window_end},
                "carbs_g": {"$ne": None},
                "protein_g": {"$ne": None},
                "fat_g": {"$ne": None},
            }
        ).to_list()

        on_target = 0
        for entry in entries:
            entry_kcal = entry.carbs_g * 4 + entry.protein_g * 4 + entry.fat_g * 9
            if entry_kcal <= 0:
                continue
            entry_carbs_pct = entry.carbs_g * 4 / entry_kcal * 100
            entry_protein_pct = entry.protein_g * 4 / entry_kcal * 100
            entry_fat_pct = entry.fat_g * 9 / entry_kcal * 100
            if (
                abs(entry_carbs_pct - record.carbs_pct) <= ON_TARGET_TOLERANCE_PCT
                and abs(entry_protein_pct - record.protein_pct) <= ON_TARGET_TOLERANCE_PCT
                and abs(entry_fat_pct - record.fat_pct) <= ON_TARGET_TOLERANCE_PCT
            ):
                on_target += 1

        adherence_pct = round(on_target / len(entries) * 100, 1) if entries else None

        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "title": record.title,
            "carbs_pct": record.carbs_pct,
            "protein_pct": record.protein_pct,
            "fat_pct": record.fat_pct,
            "status": record.status,
            "set_by_id": str(record.set_by_id),
            "started_at": record.started_at.isoformat(),
            "ended_at": record.ended_at.isoformat() if record.ended_at else None,
            "adherence_pct": adherence_pct,
            "entries_with_macros": len(entries),
            "updated_at": record.updated_at.isoformat(),
        }
