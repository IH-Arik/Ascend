"""Mental Performance dashboard aggregate routes. See `mp_service.py`."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_MENTAL_PERFORMANCE
from app.models.user import User
from app.services.mp_service import MpDashboardService

router = APIRouter()
mp_service = MpDashboardService()


@router.get("/caseload", status_code=status.HTTP_200_OK)
async def get_mp_caseload(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_MENTAL_PERFORMANCE)),
) -> dict[str, Any]:
    """Real opted-in caseload - anonymized codes only, no name/rank."""
    data = await mp_service.get_caseload(current_user)
    return success_response("Caseload loaded successfully.", data)


@router.get("/dashboard-summary", status_code=status.HTTP_200_OK)
async def get_mp_dashboard_summary(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_MENTAL_PERFORMANCE)),
) -> dict[str, Any]:
    """Real active-caseload/referral/session/follow-up counts."""
    data = await mp_service.get_dashboard_summary(current_user)
    return success_response("Dashboard summary loaded successfully.", data)
