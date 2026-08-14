"""Recommendation engine / assigned-action routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_CHAPLAIN, ROLE_MENTAL_PERFORMANCE, ROLE_NUTRITIONIST, ROLE_PTIM, ROLE_SCS
from app.models.recommendation import Recommendation
from app.models.user import User
from app.schemas.recommendation import AssignActionRequest
from app.services.recommendation_service import RecommendationService

router = APIRouter()
recommendation_service = RecommendationService()


async def _get_target_user(user_id: str) -> User:
    """Return the target operator or raise 404."""
    user = await User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("/active", status_code=status.HTTP_200_OK)
async def get_active_recommendation(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the current active recommendation, if any."""
    data = await recommendation_service.get_active_for_user(current_user)
    return success_response("Active recommendation loaded successfully.", data)


@router.post("/{user_id}/assign", status_code=status.HTTP_201_CREATED)
async def assign_action(
    user_id: str,
    payload: AssignActionRequest,
    current_user: User = Depends(
        require_roles(
            *ADMIN_ROLES, ROLE_SCS, ROLE_PTIM, ROLE_NUTRITIONIST, ROLE_MENTAL_PERFORMANCE, ROLE_CHAPLAIN
        )
    ),
) -> dict[str, Any]:
    """Assign a provider-authored action to a user (any assigned-provider role, or Admin)."""
    target_user = await _get_target_user(user_id)
    data = await recommendation_service.assign_action(
        target_user, payload, assigned_by=current_user.id, assigned_by_role=current_user.role
    )
    return success_response("Action assigned successfully.", data)


@router.post("/{recommendation_id}/send-for-signoff", status_code=status.HTTP_200_OK)
async def send_recommendation_for_signoff(
    recommendation_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """SCS, PT/IM, or Admin sends a joint-coordination item for PT/IM signoff."""
    record = await Recommendation.get(recommendation_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
    owner = await _get_target_user(str(record.user_id))
    data = await recommendation_service.send_for_signoff(owner, recommendation_id, current_user.id, current_user.role)
    return success_response("Sent for signoff successfully.", data)


@router.post("/{recommendation_id}/sign-off", status_code=status.HTTP_200_OK)
async def sign_off_recommendation(
    recommendation_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM (or Admin) signs off a coordination item previously sent for signoff."""
    record = await Recommendation.get(recommendation_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
    owner = await _get_target_user(str(record.user_id))
    data = await recommendation_service.sign_off(owner, recommendation_id, current_user.id, current_user.role)
    return success_response("Signed off successfully.", data)


@router.get("/{recommendation_id}", status_code=status.HTTP_200_OK)
async def get_recommendation(
    recommendation_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a single recommendation or assigned action by id."""
    data = await recommendation_service.get_by_id(current_user, recommendation_id)
    return success_response("Recommendation loaded successfully.", data)


@router.post("/{recommendation_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_recommendation(
    recommendation_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Dismiss an active recommendation."""
    data = await recommendation_service.dismiss(current_user, recommendation_id)
    return success_response("Recommendation dismissed successfully.", data)


@router.post("/{recommendation_id}/complete", status_code=status.HTTP_200_OK)
async def complete_recommendation(
    recommendation_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a recommendation's action as completed."""
    data = await recommendation_service.complete(current_user, recommendation_id)
    return success_response("Recommendation completed successfully.", data)


@router.post("/{recommendation_id}/steps/{step_index}/complete", status_code=status.HTTP_200_OK)
async def complete_action_step(
    recommendation_id: str,
    step_index: int,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a single step of an assigned action as completed."""
    data = await recommendation_service.complete_step(current_user, recommendation_id, step_index)
    return success_response("Step marked as completed.", data)
