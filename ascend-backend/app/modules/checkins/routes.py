"""Daily check-in routes (Day 0 first-use check-in and onward)."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.checkin import DailyCheckinSubmitRequest
from app.schemas.periodic_checkin import PeriodicCheckinSubmitRequest
from app.services.checkin_service import CheckinService

router = APIRouter()
checkin_service = CheckinService()


@router.get("/daily", status_code=status.HTTP_200_OK)
async def get_daily_checkin(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return today's daily check-in questions and readiness trace state."""
    data = await checkin_service.get_daily_checkin(current_user)
    return success_response("Daily check-in loaded successfully.", data)


@router.post("/daily/submit", status_code=status.HTTP_200_OK)
async def submit_daily_checkin(
    payload: DailyCheckinSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit today's daily check-in and update current OPS."""
    data = await checkin_service.submit_daily_checkin(current_user, payload)
    return success_response("Daily check-in submitted successfully.", data)


@router.get("/weekly/gate", status_code=status.HTTP_200_OK)
async def get_weekly_gate(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the weekly check-in cadence gate status."""
    data = await checkin_service.get_weekly_gate(current_user)
    return success_response("Weekly check-in gate status loaded successfully.", data)


@router.get("/weekly", status_code=status.HTTP_200_OK)
async def get_weekly_checkin(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the current week's check-in questions (W1-W10)."""
    data = await checkin_service.get_periodic_checkin(current_user, "weekly")
    return success_response("Weekly check-in loaded successfully.", data)


@router.post("/weekly/submit", status_code=status.HTTP_200_OK)
async def submit_weekly_checkin(
    payload: PeriodicCheckinSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit this week's check-in and update current OPS."""
    data = await checkin_service.submit_periodic_checkin(current_user, "weekly", payload)
    return success_response("Weekly check-in submitted successfully.", data)


@router.get("/monthly", status_code=status.HTTP_200_OK)
async def get_monthly_checkin(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the current month's check-in questions (M1-M10)."""
    data = await checkin_service.get_periodic_checkin(current_user, "monthly")
    return success_response("Monthly check-in loaded successfully.", data)


@router.post("/monthly/submit", status_code=status.HTTP_200_OK)
async def submit_monthly_checkin(
    payload: PeriodicCheckinSubmitRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit this month's check-in and update current OPS."""
    data = await checkin_service.submit_periodic_checkin(current_user, "monthly", payload)
    return success_response("Monthly check-in submitted successfully.", data)
