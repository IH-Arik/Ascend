"""Meal log routes (see `app/models/meal_log.py`)."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_AIRMAN, SPECIALIST_ROLES
from app.models.user import User
from app.schemas.macro_target import MacroTargetSet
from app.schemas.meal_log import MealLogCreate, MealLogFlagUpdate
from app.services.macro_target_service import MacroTargetService
from app.services.meal_log_service import MealLogService

router = APIRouter()
meal_log_service = MealLogService()
macro_target_service = MacroTargetService()


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def create_meal_log(
    user_id: str,
    payload: MealLogCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES, ROLE_AIRMAN)),
) -> dict[str, Any]:
    """The operator logs their own meal, or a Nutritionist/Admin logs one on their behalf."""
    data = await meal_log_service.create(current_user, user_id, payload)
    return success_response("Meal logged successfully.", data)


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
async def get_meal_logs(
    user_id: str,
    days: int = Query(default=60, ge=1, le=365),
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES, ROLE_AIRMAN)),
) -> dict[str, Any]:
    """Real logged meals for an operator over the trailing `days`."""
    data = await meal_log_service.list_for_user(current_user, user_id, days=days)
    return success_response("Meal logs loaded successfully.", data)


@router.patch("/{meal_log_id}/flag", status_code=status.HTTP_200_OK)
async def update_meal_log_flag(
    meal_log_id: str,
    payload: MealLogFlagUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """A Nutritionist/Admin flags a meal entry for review."""
    data = await meal_log_service.update_flag(current_user, meal_log_id, payload)
    return success_response("Meal log flag updated successfully.", data)


@router.put("/targets/{user_id}", status_code=status.HTTP_200_OK)
async def set_macro_target(
    user_id: str,
    payload: MacroTargetSet,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """A Nutritionist/Admin sets an operator's real macro-split target."""
    data = await macro_target_service.set_target(current_user, user_id, payload)
    return success_response("Macro target set successfully.", data)


@router.get("/targets/{user_id}", status_code=status.HTTP_200_OK)
async def get_macro_target(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES, ROLE_AIRMAN)),
) -> dict[str, Any]:
    """Real current macro-split target for an operator, if one has been set."""
    data = await macro_target_service.get_target(current_user, user_id)
    return success_response("Macro target loaded successfully.", data)


@router.get("/targets/{user_id}/history", status_code=status.HTTP_200_OK)
async def get_macro_target_history(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES, ROLE_AIRMAN)),
) -> dict[str, Any]:
    """Every real macro target ever set for this operator, with real computed adherence per entry."""
    data = await macro_target_service.list_history(current_user, user_id)
    return success_response("Macro target history loaded successfully.", data)
