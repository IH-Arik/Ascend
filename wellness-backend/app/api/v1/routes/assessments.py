"""Assessment routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.assessment import AssessmentStatusRead, CheckInCreate
from app.services.assessment_service import AssessmentService
from app.utils.response import success_response

router = APIRouter()
assessment_service = AssessmentService()


@router.post("/checkins", status_code=status.HTTP_201_CREATED)
async def create_checkin(
    payload: CheckInCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new assessment submission and score it."""
    data = await assessment_service.submit_assessment(current_user, payload)
    return success_response("Assessment submitted successfully.", data)


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return initial/reassessment eligibility for the authenticated user."""
    data = await assessment_service.get_reassessment_status(current_user)
    return success_response(
        "Assessment status fetched successfully.",
        AssessmentStatusRead(**data).model_dump(),
    )
