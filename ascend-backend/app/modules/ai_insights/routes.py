"""AI insight routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.services.ai_insights_service import AIInsightsService
from app.services.onboarding_service import OnboardingService

router = APIRouter()
ai_insights_service = AIInsightsService()
onboarding_service = OnboardingService()


@router.get("/onboarding/latest", status_code=status.HTTP_200_OK)
async def get_latest_onboarding_insight(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the latest saved onboarding AI insight."""
    data = await ai_insights_service.get_latest_for_user(current_user)
    return success_response("Latest onboarding insight loaded successfully.", data)


@router.post("/onboarding/generate", status_code=status.HTTP_200_OK)
async def generate_onboarding_insight(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate and persist an onboarding insight from saved answers."""
    baseline = await onboarding_service.complete_baseline(current_user)
    return success_response(
        "Onboarding insight generated successfully.",
        baseline["ai_summary"],
    )
