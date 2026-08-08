"""User routes."""

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.account import SupportRequestCreate
from app.schemas.auth import ChangePasswordRequest
from app.schemas.profile import ProfileCreate, ProfileUpdate
from app.schemas.user import OnboardingUpdateRequest, UserUpdate
from app.services.account_service import AccountService
from app.services.auth_service import AuthService
from app.services.profile_service import ProfileService
from app.utils.response import success_response

router = APIRouter()
auth_service = AuthService()
profile_service = ProfileService()
account_service = AccountService()


@router.get("/me", status_code=status.HTTP_200_OK)
async def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated user's account details."""
    data = await auth_service.get_me(current_user)
    return success_response("User fetched successfully.", data)


@router.patch("/me", status_code=status.HTTP_200_OK)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the authenticated user's account details."""
    data = await auth_service.update_me(current_user, payload)
    return success_response("User updated successfully.", data)


@router.patch("/me/onboarding", status_code=status.HTTP_200_OK)
async def update_onboarding(
    payload: OnboardingUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update onboarding organization access fields."""
    data = await auth_service.update_onboarding(current_user, payload)
    return success_response("Onboarding updated successfully.", data)


@router.get("/me/profile", status_code=status.HTTP_200_OK)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's personal profile."""
    data = await profile_service.get_my_profile(current_user)
    return success_response("Profile fetched successfully.", data)


@router.post("/me/profile", status_code=status.HTTP_201_CREATED)
async def create_my_profile(
    payload: ProfileCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create the authenticated user's personal profile."""
    data = await profile_service.create_my_profile(current_user, payload)
    return success_response("Profile created successfully.", data)


@router.patch("/me/profile", status_code=status.HTTP_200_OK)
async def update_my_profile(
    payload: ProfileUpdate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the authenticated user's personal profile."""
    data = await profile_service.update_my_profile(current_user, payload)
    return success_response("Profile updated successfully.", data)


@router.post("/me/profile-image", status_code=status.HTTP_201_CREATED)
async def upload_my_profile_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload a profile image for the authenticated user."""
    data = await profile_service.upload_profile_image(current_user, file)
    return success_response("Profile image uploaded successfully.", data)


@router.get("/me/account-summary", status_code=status.HTTP_200_OK)
async def get_account_summary(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return account screen summary data for the authenticated user."""
    data = await account_service.get_account_summary(current_user)
    return success_response("Account summary fetched successfully.", data)


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_my_account(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Permanently delete the authenticated user's account and profile."""
    data = await account_service.delete_account(current_user)
    return success_response("Account deleted successfully.", data)


@router.post("/me/change-password", status_code=status.HTTP_200_OK)
async def change_my_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Change the authenticated user's password."""
    data = await auth_service.change_password(current_user, payload)
    return success_response("Password updated successfully.", data)


@router.post("/me/support-request", status_code=status.HTTP_201_CREATED)
async def create_support_request(
    payload: SupportRequestCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit a support request for the authenticated user."""
    data = await account_service.submit_support_request(current_user, payload.issue)
    return success_response("Support request submitted successfully.", data)


@router.get("/help-center", status_code=status.HTTP_200_OK)
async def get_help_center() -> dict[str, Any]:
    """Return help center content."""
    data = await account_service.get_help_center()
    return success_response("Help center fetched successfully.", data)


@router.get("/privacy-policy", status_code=status.HTTP_200_OK)
async def get_privacy_policy() -> dict[str, Any]:
    """Return privacy policy content."""
    data = await account_service.get_privacy_policy()
    return success_response("Privacy policy fetched successfully.", data)


@router.get("/terms-of-condition", status_code=status.HTTP_200_OK)
async def get_terms_of_condition() -> dict[str, Any]:
    """Return terms of condition content."""
    data = await account_service.get_terms_of_condition()
    return success_response("Terms of condition fetched successfully.", data)


@router.get("/about-us", status_code=status.HTTP_200_OK)
async def get_about_us() -> dict[str, Any]:
    """Return about us content."""
    data = await account_service.get_about_us()
    return success_response("About us fetched successfully.", data)
