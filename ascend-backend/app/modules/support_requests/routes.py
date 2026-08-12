"""Support pathway ("My Support Team") routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_PTIM, ROLE_SCS
from app.models.user import User
from app.schemas.support import SupportRequestCreate
from app.schemas.support import TogglePathwayRequest
from app.schemas.support import UpdateRequestStatusRequest
from app.services.support_service import SupportService
from app.services.team_service import TeamService

router = APIRouter()
support_service = SupportService()
team_service = TeamService()


@router.get("/pathways", status_code=status.HTTP_200_OK)
async def get_support_pathways(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the support pathways available to the authenticated user."""
    data = await support_service.get_pathways_for_user(current_user)
    return success_response("Support pathways loaded successfully.", data)


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def create_support_request(
    payload: SupportRequestCreate,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Submit a support request to an available pathway."""
    data = await support_service.create_request(current_user, payload)
    return success_response("Support request submitted successfully.", data)


@router.get("/requests", status_code=status.HTTP_200_OK)
async def list_support_requests(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's support requests."""
    data = await support_service.list_requests(current_user)
    return success_response("Support requests loaded successfully.", data)


@router.get("/requests/assigned", status_code=status.HTTP_200_OK)
async def get_assigned_support_requests(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """Return support requests routed to the calling provider's role (Admin sees all)."""
    data = await support_service.list_assigned_requests(current_user)
    return success_response("Assigned support requests loaded successfully.", data)


@router.patch("/requests/{request_id}/status", status_code=status.HTTP_200_OK)
async def update_support_request_status(
    request_id: str,
    payload: UpdateRequestStatusRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """Update a support request's status (provider or Admin only)."""
    data = await support_service.update_request_status(current_user, request_id, payload.status)
    return success_response("Support request status updated successfully.", data)


@router.get("/team", status_code=status.HTTP_200_OK)
async def get_my_team(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the "My Support Team" screen: assigned providers and pathway status."""
    data = await team_service.get_my_team(current_user)
    return success_response("My team loaded successfully.", data)


@router.post("/team/{pathway_key}/toggle", status_code=status.HTTP_200_OK)
async def toggle_team_pathway(
    pathway_key: str,
    payload: TogglePathwayRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Enable or disable an optional support pathway (audit logged)."""
    data = await team_service.toggle_pathway(current_user, pathway_key, payload.enabled)
    return success_response("Pathway status updated successfully.", data)
