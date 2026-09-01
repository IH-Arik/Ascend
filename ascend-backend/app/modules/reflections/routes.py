"""Spiritual reflection routes (Chaplain / Purpose pathway, see model docstring)."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_CHAPLAIN
from app.models.user import User
from app.schemas.reflection import ReflectionCreate
from app.services.reflection_service import ReflectionService

router = APIRouter()
reflection_service = ReflectionService()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reflection(
    payload: ReflectionCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The operator writes a real, private reflection entry (requires an active Chaplain opt-in)."""
    data = await reflection_service.create(current_user, payload)
    return success_response("Reflection saved successfully.", data)


@router.get("", status_code=status.HTTP_200_OK)
async def list_own_reflections(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The operator's own reflection entries, most recent first."""
    data = await reflection_service.list_own(current_user)
    return success_response("Reflections loaded successfully.", data)


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
async def get_user_reflections(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_CHAPLAIN)),
) -> dict[str, Any]:
    """A Chaplain (or Admin) reads a real user's reflections - gated by live opt-in status."""
    data = await reflection_service.list_for_user(current_user, user_id)
    return success_response("Reflections loaded successfully.", data)
