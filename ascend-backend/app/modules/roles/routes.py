"""Role and permission routes."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ROLE_ADMIN
from app.core.roles import ROLE_PERMISSIONS
from app.core.roles import SUPPORTED_ROLES
from app.core.roles import permissions_for_role
from app.models.user import User

router = APIRouter()


@router.get("", summary="List supported roles")
async def list_roles(
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict[str, Any]:
    """Return the supported roles and their permissions."""
    return success_response(
        "Roles loaded successfully.",
        {
            "roles": list(SUPPORTED_ROLES),
            "permission_matrix": ROLE_PERMISSIONS,
            "requested_by": {
                "id": str(current_user.id),
                "role": current_user.role,
            },
        },
    )


@router.get("/me", summary="List current role permissions")
async def get_my_role_permissions(
    current_user: User = Depends(require_roles(*SUPPORTED_ROLES)),
) -> dict[str, Any]:
    """Return the permissions for the current user's role."""
    return success_response(
        "Role permissions loaded successfully.",
        {
            "role": current_user.role,
            "permissions": permissions_for_role(current_user.role),
        },
    )
