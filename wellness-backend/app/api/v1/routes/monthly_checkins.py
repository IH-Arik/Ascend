"""Monthly check-in routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.assessment import MonthlyCheckInCreate
from app.services.monthly_checkin_service import MonthlyCheckInService
from app.utils.response import success_response

router = APIRouter()
monthly_checkin_service = MonthlyCheckInService()


@router.get("/questions", status_code=status.HTTP_200_OK)
async def list_monthly_checkin_questions(page: int = 1) -> dict[str, Any]:
    """Return paginated monthly check-in questions ordered for display."""
    data = await monthly_checkin_service.list_questions(page=page)
    return success_response(
        "Monthly check-in questions fetched successfully.",
        data,
    )


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_monthly_checkin_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return monthly check-in eligibility status."""
    data = await monthly_checkin_service.get_status(current_user)
    return success_response("Monthly check-in status fetched successfully.", data)


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_monthly_checkin(
    payload: MonthlyCheckInCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new monthly check-in."""
    data = await monthly_checkin_service.submit_monthly_checkin(current_user, payload)
    return success_response("Monthly check-in submitted successfully.", data)
