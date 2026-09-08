"""Chaplain / Purpose-pathway dashboard aggregate routes. See `chaplain_service.py`."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_CHAPLAIN
from app.models.user import User
from app.services.chaplain_service import ChaplainDashboardService

router = APIRouter()
chaplain_service = ChaplainDashboardService()


@router.get("/caseload", status_code=status.HTTP_200_OK)
async def get_chaplain_caseload(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_CHAPLAIN)),
) -> dict[str, Any]:
    """Real opted-in caseload - anonymized codes only, no name/rank."""
    data = await chaplain_service.get_caseload(current_user)
    return success_response("Caseload loaded successfully.", data)


@router.get("/dashboard-summary", status_code=status.HTTP_200_OK)
async def get_chaplain_dashboard_summary(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_CHAPLAIN)),
) -> dict[str, Any]:
    """Real opted-in/active-reflection/consult/first-time counts."""
    data = await chaplain_service.get_dashboard_summary(current_user)
    return success_response("Dashboard summary loaded successfully.", data)


@router.get("/pastoral-care-today", status_code=status.HTTP_200_OK)
async def get_chaplain_pastoral_care_today(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_CHAPLAIN)),
) -> dict[str, Any]:
    """Real today's schedule with a derived first-time/returning/brief category."""
    data = await chaplain_service.get_todays_pastoral_care(current_user)
    return success_response("Today's pastoral care loaded successfully.", data)


@router.get("/opt-in-audit", status_code=status.HTTP_200_OK)
async def get_chaplain_opt_in_audit(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_CHAPLAIN)),
) -> dict[str, Any]:
    """Real opt-in/opt-out audit trail for the Chaplain's caseload."""
    data = await chaplain_service.get_opt_in_audit(current_user)
    return success_response("Opt-in audit loaded successfully.", data)
