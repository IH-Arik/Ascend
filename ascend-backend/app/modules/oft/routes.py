"""OFT (Operational Fitness Test) routes."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_PTIM, ROLE_SCS
from app.models.user import User
from app.schemas.oft import OFTRecordResultRequest, OFTScheduleRequest
from app.services.oft_service import OFTService

router = APIRouter()
oft_service = OFTService()


async def _get_target_user(user_id: str) -> User:
    """Return the target operator or raise 404."""
    user = await User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_my_oft_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's OFT status."""
    data = await oft_service.get_status_for_user(current_user)
    return success_response("OFT status loaded successfully.", data)


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
async def get_user_oft_status(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin views a specific operator's real OFT status."""
    target_user = await _get_target_user(user_id)
    data = await oft_service.get_status_for_user(target_user)
    return success_response("OFT status loaded successfully.", data)


@router.post("/{user_id}/schedule", status_code=status.HTTP_200_OK)
async def schedule_oft(
    user_id: str,
    payload: OFTScheduleRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS)),
) -> dict[str, Any]:
    """Schedule an upcoming OFT test for a user (SCS/Admin only)."""
    target_user = await _get_target_user(user_id)
    data = await oft_service.schedule(target_user, payload, recorded_by=current_user.id)
    return success_response("OFT test scheduled successfully.", data)


@router.post("/{user_id}/record", status_code=status.HTTP_200_OK)
async def record_oft_result(
    user_id: str,
    payload: OFTRecordResultRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS)),
) -> dict[str, Any]:
    """Record a completed OFT test result for a user (SCS/Admin only)."""
    target_user = await _get_target_user(user_id)
    data = await oft_service.record_result(target_user, payload, recorded_by=current_user.id)
    return success_response("OFT result recorded successfully.", data)
