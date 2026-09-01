"""Support pathway ("My Support Team") routes."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_CHAPLAIN, ROLE_MENTAL_PERFORMANCE, ROLE_NUTRITIONIST, ROLE_PTIM, ROLE_SCS
from app.models.user import User
from app.schemas.support import ReflectionCadenceRequest
from app.schemas.support import SupportRequestCreate
from app.schemas.support import TogglePathwayRequest
from app.schemas.support import WitnessedOptInRequest
from app.schemas.support import UpdateReasonCategoryRequest
from app.schemas.support import UpdateRequestStatusRequest
from app.services.support_service import SupportService
from app.services.team_service import TeamService

router = APIRouter()
support_service = SupportService()
team_service = TeamService()

SPECIALIST_PROVIDER_ROLES = (
    *ADMIN_ROLES,
    ROLE_SCS,
    ROLE_PTIM,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_NUTRITIONIST,
    ROLE_CHAPLAIN,
)


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
    # Real fix: was scoped to only SCS/PT-IM, so the other 3 support
    # pathways (Mental Performance, Nutritionist, Chaplain) had no way to
    # list their own assigned requests through this route - even though
    # `get_specialist_dashboard`'s `recent_requests` field already exposed
    # the same data without this restriction. Widened to match, needed for
    # the MP dashboard's real referral-reason tagging to be usable.
    current_user: User = Depends(require_roles(*SPECIALIST_PROVIDER_ROLES)),
) -> dict[str, Any]:
    """Return support requests routed to the calling provider's role (Admin sees all)."""
    data = await support_service.list_assigned_requests(current_user)
    return success_response("Assigned support requests loaded successfully.", data)


@router.patch("/requests/{request_id}/status", status_code=status.HTTP_200_OK)
async def update_support_request_status(
    request_id: str,
    payload: UpdateRequestStatusRequest,
    # Same real widen as `/requests/assigned` above - a specialist
    # provider needs this to work the requests their own `assigned`
    # listing now correctly shows them.
    current_user: User = Depends(require_roles(*SPECIALIST_PROVIDER_ROLES)),
) -> dict[str, Any]:
    """Update a support request's status (provider or Admin only)."""
    data = await support_service.update_request_status(current_user, request_id, payload.status)
    return success_response("Support request status updated successfully.", data)


@router.patch("/requests/{request_id}/reason-category", status_code=status.HTTP_200_OK)
async def update_support_request_reason_category(
    request_id: str,
    payload: UpdateReasonCategoryRequest,
    current_user: User = Depends(require_roles(*SPECIALIST_PROVIDER_ROLES)),
) -> dict[str, Any]:
    """Tag a support request with a real triage category (receiving specialist or Admin only)."""
    data = await support_service.update_reason_category(current_user, request_id, payload.reason_category)
    return success_response("Reason category updated successfully.", data)


@router.get("/requests/referral-reasons", status_code=status.HTTP_200_OK)
async def get_referral_reason_distribution(
    days: int = 30,
    current_user: User = Depends(require_roles(*SPECIALIST_PROVIDER_ROLES)),
) -> dict[str, Any]:
    """Real referral-reason category distribution for the calling provider's own pathway."""
    data = await support_service.get_referral_reason_distribution(current_user, days)
    return success_response("Referral reason distribution loaded successfully.", data)


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


@router.post("/team/{pathway_key}/{user_id}/witnessed-opt-in", status_code=status.HTTP_200_OK)
async def record_witnessed_opt_in(
    pathway_key: str,
    user_id: str,
    payload: WitnessedOptInRequest,
    current_user: User = Depends(require_roles(*SPECIALIST_PROVIDER_ROLES)),
) -> dict[str, Any]:
    """A specialist records a real, witnessed opt-in for an operator (in-person/form/casual contact)."""
    data = await team_service.record_witnessed_opt_in(current_user, user_id, pathway_key, payload.method)
    return success_response("Witnessed opt-in recorded successfully.", data)


@router.patch("/team/chaplain/{user_id}/reflection-cadence", status_code=status.HTTP_200_OK)
async def set_reflection_cadence(
    user_id: str,
    payload: ReflectionCadenceRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_CHAPLAIN)),
) -> dict[str, Any]:
    """A Chaplain sets their own real reflection-pacing preference for one operator."""
    data = await team_service.set_reflection_cadence(current_user, user_id, payload.cadence)
    return success_response("Reflection cadence updated successfully.", data)
