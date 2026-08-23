"""User routes."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.account import DeactivationRequestCreate
from app.schemas.auth import ChangePasswordRequest
from app.schemas.profile import UpdateProfileSettingsRequest
from app.services.account_management_service import AccountManagementService
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService

router = APIRouter()
auth_service = AuthService()
profile_service = ProfileService()
account_management_service = AccountManagementService()


@router.get("/me", summary="Current user")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user profile."""
    data = await auth_service.get_me(current_user)
    return success_response("Current user loaded successfully.", data)


@router.get("/profile", summary="Profile screen summary")
async def get_profile(current_user: User = Depends(get_current_user)):
    """Return the aggregated Profile screen payload."""
    data = await profile_service.get_profile(current_user)
    return success_response("Profile loaded successfully.", data)


@router.patch("/profile/settings", summary="Update locally controllable profile settings")
async def update_profile_settings(
    payload: UpdateProfileSettingsRequest,
    current_user: User = Depends(get_current_user),
):
    """Update rank/grade, theme preference, and/or notification preference."""
    data = await profile_service.update_settings(current_user, payload)
    return success_response("Profile settings updated successfully.", data)


@router.post("/change-password", summary="Change your own password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    """Change the signed-in user's own password, verifying the current one first."""
    data = await auth_service.change_password(current_user, payload)
    return success_response("Password changed successfully.", data)


@router.get("/sign-in-history", summary="Sign-in & activation history")
async def get_sign_in_history(current_user: User = Depends(get_current_user)):
    """Return the last sign-in and recent login/activation audit history."""
    data = await account_management_service.get_sign_in_history(current_user)
    return success_response("Sign-in history loaded successfully.", data)


@router.post(
    "/deactivation-requests",
    status_code=201,
    summary="Request account deactivation (Admin approval required)",
)
async def request_deactivation(
    payload: DeactivationRequestCreate,
    current_user: User = Depends(get_current_user),
):
    """Queue a deactivation request for Admin review. Never immediate/self-service."""
    data = await account_management_service.request_deactivation(current_user, payload)
    return success_response("Deactivation request submitted for Admin review.", data)
