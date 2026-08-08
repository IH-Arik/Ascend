"""First-use onboarding routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.onboarding import BaselineFinalizeResponse
from app.schemas.onboarding import ConsentSubmitRequest
from app.schemas.onboarding import OnboardingAnswerSubmission
from app.schemas.onboarding import StepProgressRequest
from app.services.onboarding_service import OnboardingService

router = APIRouter()
onboarding_service = OnboardingService()


@router.get("/first-use/status", status_code=status.HTTP_200_OK)
async def get_first_use_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return first-use routing state for the authenticated user."""
    data = await onboarding_service.get_first_use_status(current_user)
    return success_response("First-use status loaded successfully.", data)


@router.get("/intro", status_code=status.HTTP_200_OK)
async def get_onboarding_intro(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return welcome and consent screen content."""
    data = await onboarding_service.get_intro(current_user)
    return success_response("Onboarding intro loaded successfully.", data)


@router.get("/questions", status_code=status.HTTP_200_OK)
async def get_onboarding_questions(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the normalized onboarding question bank."""
    data = await onboarding_service.get_questions(current_user)
    return success_response("Onboarding questions loaded successfully.", data)


@router.post("/consent", status_code=status.HTTP_200_OK)
async def submit_consent(
    payload: ConsentSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Persist the required onboarding consent fields."""
    data = await onboarding_service.submit_consent(current_user, payload)
    return success_response("Onboarding consent saved successfully.", data)


@router.post("/step-progress", status_code=status.HTTP_200_OK)
async def save_step_progress(
    payload: StepProgressRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Persist current onboarding step progress."""
    data = await onboarding_service.save_step_progress(current_user, payload)
    return success_response("Onboarding progress saved successfully.", data)


@router.post("/answer", status_code=status.HTTP_200_OK)
async def save_onboarding_answer(
    payload: OnboardingAnswerSubmission,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Persist one onboarding answer."""
    data = await onboarding_service.save_answer(current_user, payload)
    return success_response("Onboarding answer saved successfully.", data)


@router.get("/baseline/preview", status_code=status.HTTP_200_OK)
async def get_baseline_preview(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Preview the current onboarding baseline score."""
    data = await onboarding_service.get_baseline_preview(current_user)
    return success_response("Baseline preview loaded successfully.", data)


@router.post("/baseline/complete", status_code=status.HTTP_200_OK)
async def complete_baseline(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Finalize onboarding baseline scoring and unlock Day 0 handoff."""
    data = await onboarding_service.complete_baseline(current_user)
    return success_response("Onboarding baseline completed successfully.", data)
