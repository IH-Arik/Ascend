"""User routes."""

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.account import DeactivationRequestCreate
from app.schemas.auth import ChangePasswordRequest
from app.schemas.profile import ChangeEmailRequest, UpdateProfileSettingsRequest
from app.services.account_management_service import AccountManagementService
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService

router = APIRouter()
auth_service = AuthService()
profile_service = ProfileService()
account_management_service = AccountManagementService()


async def _get_target_user(user_id: str) -> User:
    """Return the target user or raise 404."""
    user = await User.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


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


@router.post("/change-email", summary="Change your own login email")
async def change_email(
    payload: ChangeEmailRequest,
    current_user: User = Depends(get_current_user),
):
    """Change the signed-in user's own email, verifying the current password first.

    The new address starts unverified - a fresh verification code is sent to it.
    """
    data = await auth_service.change_email(current_user, payload)
    return success_response("Email updated. Please verify your new address.", data)


@router.post(
    "/profile/avatar",
    status_code=status.HTTP_201_CREATED,
    summary="Upload/replace your own profile photo",
)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a profile photo (JPG/PNG/HEIC, up to 5 MB)."""
    data = await profile_service.upload_avatar(current_user, file)
    return success_response("Profile photo updated successfully.", data)


@router.delete("/profile/avatar", summary="Remove your own profile photo")
async def delete_avatar(current_user: User = Depends(get_current_user)):
    """Remove the signed-in user's profile photo, if any."""
    data = await profile_service.delete_avatar(current_user)
    return success_response("Profile photo removed.", data)


@router.get("/{user_id}/avatar", summary="Direct image URL for a user's profile photo")
async def get_user_avatar(user_id: str) -> Response:
    """Return a user's raw profile photo bytes - a real, direct image URL.

    Deliberately public (no auth) so it can be dropped straight into an
    `<img src>`/`Image source={{uri}}` without attaching a bearer token,
    which browsers and RN's Image component don't do for plain URLs. Safe
    to leave open: a profile photo isn't sensitive PII the way medical
    records or message attachments are (both of those stay auth-gated,
    JSON+base64), and this already had no team-assignment gate even when
    it required auth. `avatar_url` on `GET /users/profile` is this same
    path, precomputed - use that instead of building the URL by hand.
    """
    target = await _get_target_user(user_id)
    content, content_type = await profile_service.get_avatar_bytes(target)
    return Response(content=content, media_type=content_type)


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
