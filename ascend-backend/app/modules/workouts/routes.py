"""Workout/activity logging routes (DOCX section 9)."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.workout import WorkoutLogCreate
from app.services.workout_service import WorkoutService

router = APIRouter()
workout_service = WorkoutService()


@router.post("", status_code=status.HTTP_201_CREATED)
async def log_workout(
    payload: WorkoutLogCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Log a single workout/activity session."""
    data = await workout_service.log_workout(current_user, payload)
    return success_response("Workout logged successfully.", data)


@router.get("", status_code=status.HTTP_200_OK)
async def list_workouts(
    days: int = Query(default=30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return recent workout logs."""
    data = await workout_service.list_for_user(current_user, days)
    return success_response("Workouts loaded successfully.", data)


@router.get("/summary", status_code=status.HTTP_200_OK)
async def get_workout_summary(
    days: int = Query(default=30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return an aggregate workout summary."""
    data = await workout_service.get_summary(current_user, days)
    return success_response("Workout summary loaded successfully.", data)
