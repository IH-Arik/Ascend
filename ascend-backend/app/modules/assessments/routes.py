"""Operator assessment tracking routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_SCS
from app.models.user import User
from app.schemas.assessment import AssessmentCompleteRequest, AssessmentScheduleRequest
from app.services.assessment_service import AssessmentService

router = APIRouter()
assessment_service = AssessmentService()


async def _get_target_user(user_id: str) -> User:
    """Return the target operator or raise 404."""
    user = await User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_my_assessments(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's assessment records."""
    data = await assessment_service.list_for_user(current_user)
    return success_response("Assessments loaded successfully.", data)


@router.post("/{user_id}/schedule", status_code=status.HTTP_200_OK)
async def schedule_assessment(
    user_id: str,
    payload: AssessmentScheduleRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS)),
) -> dict[str, Any]:
    """Schedule an assessment for a user (SCS/Admin only)."""
    target_user = await _get_target_user(user_id)
    data = await assessment_service.schedule(target_user, payload, created_by=current_user.id)
    return success_response("Assessment scheduled successfully.", data)


@router.post("/{user_id}/{assessment_type}/complete", status_code=status.HTTP_200_OK)
async def complete_assessment(
    user_id: str,
    assessment_type: str,
    payload: AssessmentCompleteRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS)),
) -> dict[str, Any]:
    """Record a completed assessment result for a user (SCS/Admin only)."""
    target_user = await _get_target_user(user_id)
    data = await assessment_service.complete(target_user, assessment_type, payload)
    return success_response("Assessment completed successfully.", data)
