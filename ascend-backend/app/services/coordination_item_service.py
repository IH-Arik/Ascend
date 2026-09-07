"""PT/IM-SCS coordination item service.

See `app/models/coordination_item.py` for why this is its own record. A
provider only sees items for operators actually on their real caseload
(`TeamAssignment`, same scoping `provider_dashboard_service` uses) -
never every operator in the system, unless they're Admin.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, ROLE_PTIM, ROLE_SCS
from app.core.security import utc_now
from app.models.coordination_item import CoordinationItem
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.schemas.coordination_item import AFFECTS_LABELS, TRIGGER_LABELS, CoordinationItemCreateRequest

OTHER_ROLE = {ROLE_PTIM: ROLE_SCS, ROLE_SCS: ROLE_PTIM}


class CoordinationItemService:
    """Raise, list, acknowledge, and close joint coordination items."""

    async def _assigned_user_ids(self, provider_id: Any, pathway_key: str) -> list[Any]:
        """Same real scoping `provider_dashboard_service._assigned_user_ids` uses."""
        assignments = await TeamAssignment.find(
            TeamAssignment.pathway_key == pathway_key, TeamAssignment.provider_user_id == provider_id
        ).to_list()
        return [a.user_id for a in assignments if a.provider_user_id is not None]

    async def raise_item(self, raiser: User, payload: CoordinationItemCreateRequest) -> dict[str, Any]:
        """PT/IM or SCS raises a new joint item for one of their assigned operators."""
        if raiser.role not in (ROLE_PTIM, ROLE_SCS) and raiser.role not in ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only PT/IM or SCS may raise a coordination item.")
        target = await User.get(payload.user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found.")

        raiser_role = raiser.role if raiser.role in (ROLE_PTIM, ROLE_SCS) else ROLE_PTIM
        item = CoordinationItem(
            user_id=target.id,
            title=payload.title,
            trigger_category=payload.trigger_category,
            trigger_detail=payload.trigger_detail,
            affects=payload.affects,
            raised_by=raiser.id,
            raised_by_role=raiser_role,
            pending_with_role=OTHER_ROLE[raiser_role],
        )
        await item.insert()
        return await self._serialize(item)

    async def list_for_viewer(self, viewer: User) -> dict[str, Any]:
        """Real caseload-scoped coordination items - Admin sees every item."""
        if viewer.role in ADMIN_ROLES:
            items = await CoordinationItem.find().to_list()
        elif viewer.role in (ROLE_PTIM, ROLE_SCS):
            user_ids = await self._assigned_user_ids(viewer.id, viewer.role)
            items = await CoordinationItem.find({"user_id": {"$in": user_ids}}).to_list()
        else:
            items = []
        items.sort(key=lambda i: i.updated_at, reverse=True)
        return {"items": [await self._serialize(i) for i in items]}

    async def acknowledge(self, actor: User, item_id: str) -> dict[str, Any]:
        """The role an item is pending with acknowledges it - work is now assigned to them."""
        item = await self._get(item_id)
        actor_role = actor.role if actor.role in (ROLE_PTIM, ROLE_SCS) else None
        if actor_role is None and actor.role not in ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only PT/IM or SCS may acknowledge.")
        if actor_role and item.pending_with_role != actor_role:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This item is pending with {item.pending_with_role}, not {actor_role}.",
            )
        item.status = "acknowledged"
        item.acknowledged_by = actor.id
        item.acknowledged_at = utc_now()
        item.updated_at = utc_now()
        await item.save()
        return await self._serialize(item)

    async def close(self, actor: User, item_id: str) -> dict[str, Any]:
        """Either role (or Admin) can close a resolved item."""
        item = await self._get(item_id)
        item.status = "closed"
        item.closed_by = actor.id
        item.closed_at = utc_now()
        item.updated_at = utc_now()
        await item.save()
        return await self._serialize(item)

    async def _get(self, item_id: str) -> CoordinationItem:
        item = await CoordinationItem.get(item_id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Coordination item not found.")
        return item

    async def _serialize(self, item: CoordinationItem) -> dict[str, Any]:
        target = await User.get(item.user_id)
        raiser = await User.get(item.raised_by)
        acknowledger = await User.get(item.acknowledged_by) if item.acknowledged_by else None
        return {
            "id": str(item.id),
            "user_id": str(item.user_id),
            "user_name": target.full_name if target else None,
            "rank_grade": target.rank_grade if target else None,
            "title": item.title,
            "trigger_category": item.trigger_category,
            "trigger_label": TRIGGER_LABELS.get(item.trigger_category, item.trigger_category),
            "trigger_detail": item.trigger_detail,
            "affects": item.affects,
            "affects_label": AFFECTS_LABELS.get(item.affects, item.affects),
            "raised_by_name": raiser.full_name if raiser else None,
            "raised_by_role": item.raised_by_role,
            "pending_with_role": item.pending_with_role,
            "status": item.status,
            "acknowledged_by_name": acknowledger.full_name if acknowledger else None,
            "acknowledged_at": item.acknowledged_at.isoformat() if item.acknowledged_at else None,
            "closed_at": item.closed_at.isoformat() if item.closed_at else None,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
