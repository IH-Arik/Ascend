"""Daily check-in routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_current_user
from app.models.intervention_memory import CompletionStatus
from app.models.user import User
from app.schemas.assessment import DailyCheckInCreate
from app.services.daily_checkin_service import DailyCheckInService
from app.services.intervention_service import InterventionService
from app.utils.response import success_response

router = APIRouter()
daily_checkin_service = DailyCheckInService()
intervention_service = InterventionService()


@router.get("/questions", status_code=status.HTTP_200_OK)
async def list_daily_checkin_questions(page: int = 1) -> dict[str, Any]:
    """Return paginated daily check-in questions ordered for display."""
    data = await daily_checkin_service.list_questions(page=page)
    return success_response(
        "Daily check-in questions fetched successfully.",
        data,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_daily_checkin(
    payload: DailyCheckInCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new daily check-in."""
    data = await daily_checkin_service.submit_daily_checkin(current_user, payload)
    return success_response("Daily check-in submitted successfully.", data)


@router.get("/intervention", status_code=status.HTTP_200_OK)
async def get_today_intervention(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return today's single DWS intervention recommendation.

    Returns the same cached record for all calls made on the same calendar
    day (max-1-per-day rule).
    """
    data = await intervention_service.get_today_intervention(current_user.id)
    return success_response("Intervention recommendation fetched successfully.", data)


@router.post("/intervention/response", status_code=status.HTTP_200_OK)
async def record_intervention_response(
    status_payload: dict[str, str],
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Record the user's completion status for today's recommendation.

    Expected body: {"status": "completed" | "partial" | "not_completed" | "no_response"}
    """
    raw_status = status_payload.get("status", "no_response")
    valid: set[str] = {"completed", "partial", "not_completed", "no_response"}
    if raw_status not in valid:
        from fastapi import HTTPException
        from app.utils.response import error_response
        raise HTTPException(
            status_code=400,
            detail=error_response(
                "Invalid status value.",
                {"status": f"Must be one of: {', '.join(sorted(valid))}"},
            ),
        )
    data = await intervention_service.record_completion(
        current_user.id, raw_status  # type: ignore[arg-type]
    )
    return success_response("Intervention response recorded successfully.", data)
