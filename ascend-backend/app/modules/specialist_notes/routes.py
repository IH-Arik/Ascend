"""Specialist note routes (DOCX Section 17 - see model docstring)."""

from typing import Any

from fastapi import APIRouter, Depends, status

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, SPECIALIST_ROLES
from app.models.user import User
from app.schemas.specialist_note import SpecialistNoteCreate, SpecialistNoteRevealRequest, SpecialistNoteStatusUpdate
from app.services.specialist_note_service import SpecialistNoteService

router = APIRouter()
specialist_note_service = SpecialistNoteService()


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
async def create_specialist_note(
    user_id: str,
    payload: SpecialistNoteCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """A specialist records a real, lightweight note about an operator."""
    data = await specialist_note_service.create(current_user, user_id, payload)
    return success_response("Specialist note recorded successfully.", data)


@router.get("/{user_id}", status_code=status.HTTP_200_OK)
async def get_specialist_notes(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """Real notes for an operator - pathway-siloed to the caller's own specialist type, unless Admin."""
    data = await specialist_note_service.list_for_user(current_user, user_id)
    return success_response("Specialist notes loaded successfully.", data)


@router.patch("/{note_id}/status", status_code=status.HTTP_200_OK)
async def update_specialist_note_status(
    note_id: str,
    payload: SpecialistNoteStatusUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """Only the authoring specialist or Admin may update a note's status."""
    data = await specialist_note_service.update_status(current_user, note_id, payload.status)
    return success_response("Specialist note status updated successfully.", data)


@router.patch("/{note_id}/sign", status_code=status.HTTP_200_OK)
async def sign_specialist_note(
    note_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """The authoring specialist (or Admin) signs a draft note."""
    data = await specialist_note_service.sign(current_user, note_id)
    return success_response("Specialist note signed successfully.", data)


@router.post("/{note_id}/reveal-field", status_code=status.HTTP_200_OK)
async def reveal_specialist_note_field(
    note_id: str,
    payload: SpecialistNoteRevealRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, *SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """A non-authoring viewer's reason-required, one-time reveal of a redacted field."""
    data = await specialist_note_service.reveal_field(
        current_user, note_id, payload.field_name, payload.reason, payload.reason_category
    )
    return success_response("Field revealed successfully.", data)
