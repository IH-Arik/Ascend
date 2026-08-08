"""Home dashboard and trends routes."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.services.dashboard_service import DashboardService
from app.services.monthly_review_service import MonthlyReviewService

router = APIRouter()
dashboard_service = DashboardService()
monthly_review_service = MonthlyReviewService()


@router.get("/home", status_code=status.HTTP_200_OK)
async def get_home_dashboard(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the aggregated Home dashboard payload."""
    data = await dashboard_service.get_home_dashboard(current_user)
    return success_response("Home dashboard loaded successfully.", data)


@router.get("/trends", status_code=status.HTTP_200_OK)
async def get_trends(
    days: int = Query(default=30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return full dated OPS and driver trend history for the Trends screen."""
    data = await dashboard_service.get_trends(current_user, days)
    return success_response("Trends loaded successfully.", data)


@router.get("/drivers/{component}", status_code=status.HTTP_200_OK)
async def get_driver_detail(
    component: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the Driver Detail payload for one readiness component."""
    data = await dashboard_service.get_driver_detail(current_user, component)
    return success_response("Driver detail loaded successfully.", data)


@router.get("/unit-report", status_code=status.HTTP_200_OK)
async def get_unit_report(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the k-anonymity-gated unit aggregate readiness report."""
    data = await dashboard_service.get_unit_report(current_user)
    return success_response("Unit report loaded successfully.", data)


@router.get("/monthly-review", status_code=status.HTTP_200_OK)
async def get_monthly_review(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the on-demand monthly review (draft - not provider-signed)."""
    data = await monthly_review_service.generate(current_user)
    return success_response("Monthly review loaded successfully.", data)


@router.get("/wellness-report", status_code=status.HTTP_200_OK)
async def get_wellness_report(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the personal 30-day wellness report ("Your readiness story")."""
    data = await dashboard_service.get_wellness_report(current_user)
    return success_response("Wellness report loaded successfully.", data)
