"""Weekly check-in routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.assessment import WeeklyCheckInCreate
from app.services.weekly_checkin_service import WeeklyCheckInService
from app.utils.response import success_response

router = APIRouter()
weekly_checkin_service = WeeklyCheckInService()


@router.get("/questions", status_code=status.HTTP_200_OK)
async def list_weekly_checkin_questions(page: int = 1) -> dict[str, Any]:
    """Return paginated weekly check-in questions ordered for display."""
    data = await weekly_checkin_service.list_questions(page=page)
    return success_response(
        "Weekly check-in questions fetched successfully.",
        data,
    )


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_weekly_checkin_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return weekly check-in eligibility status."""
    data = await weekly_checkin_service.get_status(current_user)
    return success_response("Weekly check-in status fetched successfully.", data)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_weekly_checkin(
    payload: WeeklyCheckInCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new weekly check-in."""
    data = await weekly_checkin_service.submit_weekly_checkin(current_user, payload)
    return success_response("Weekly check-in submitted successfully.", data)
