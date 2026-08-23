"""Medical History Performance Summary routes (DOCX data dictionary + Table 23)."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.models.user import User
from app.schemas.performance_summary import PerformanceSummaryCreate, PerformanceSummaryUpdate
from app.services.performance_summary_service import AUTHORING_ROLES, PerformanceSummaryService

router = APIRouter()
performance_summary_service = PerformanceSummaryService()


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def create_performance_summary(
    user_id: str,
    payload: PerformanceSummaryCreate,
    current_user: User = Depends(require_roles(*AUTHORING_ROLES)),
) -> dict[str, Any]:
    """PT/IM or Admin authors a structured performance summary for an operator."""
    data = await performance_summary_service.create(current_user, user_id, payload)
    return success_response("Performance summary created successfully.", data)


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
async def get_performance_summaries(
    user_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """An operator's summaries, each scoped to what the caller's role may see.

    Gated by role inside the service rather than at the route, because the
    operator themselves may always read their own ("Own summary/status" in
    DOCX Table 23) while other roles get a graded subset.
    """
    data = await performance_summary_service.list_for_user(current_user, user_id)
    return success_response("Performance summaries loaded successfully.", data)


@router.patch("/{summary_id}/visibility", status_code=status.HTTP_200_OK)
async def set_performance_summary_visibility(
    summary_id: str,
    payload: PerformanceSummaryUpdate,
    current_user: User = Depends(require_roles(*AUTHORING_ROLES)),
) -> dict[str, Any]:
    """PT/IM or Admin moves the summary's real approved visibility level."""
    data = await performance_summary_service.set_visibility(current_user, summary_id, payload)
    return success_response("Performance summary visibility updated successfully.", data)
