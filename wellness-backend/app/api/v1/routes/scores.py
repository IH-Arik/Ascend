"""Score routes."""

from typing import Any

from fastapi import APIRouter, Depends, Path, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.assessment_service import AssessmentService
from app.utils.response import success_response

router = APIRouter()
assessment_service = AssessmentService()


@router.get("/latest", status_code=status.HTTP_200_OK)
async def get_latest_score(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the most recent score for the authenticated user."""
    data = await assessment_service.get_latest_score(current_user)
    return success_response("Latest score fetched successfully.", data)


@router.get("/history", status_code=status.HTTP_200_OK)
async def get_score_history(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return score history for the authenticated user."""
    data = await assessment_service.get_score_history(current_user)
    return success_response("Score history fetched successfully.", data)


@router.get("/{checkin_id}", status_code=status.HTTP_200_OK)
async def get_score_by_checkin(
    checkin_id: str = Path(..., description="Check-in identifier"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a score by related check-in identifier."""
    data = await assessment_service.get_score_by_checkin(current_user, checkin_id)
    return success_response("Score fetched successfully.", data)
