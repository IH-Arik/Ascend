"""Records module routes (DOCX sections 8.1, 8.2, 8.6, 8.8 - Records home)."""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ROLE_ADMIN, ROLE_PTIM, ROLE_SCS
from app.models.user import User
from app.schemas.medical_record import RecordReviewRequest
from app.schemas.reconditioning import ReconditioningPlanUpdate
from app.services.fly_away_kit_service import FlyAwayKitService
from app.services.medical_record_service import MedicalRecordService
from app.services.reconditioning_service import ReconditioningService
from app.services.records_service import RecordsService

router = APIRouter()
records_service = RecordsService()
medical_record_service = MedicalRecordService()
reconditioning_service = ReconditioningService()
fly_away_kit_service = FlyAwayKitService()


@router.get("/home", status_code=status.HTTP_200_OK)
async def get_records_home(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the 6-category Records home summary."""
    data = await records_service.get_home(current_user)
    return success_response("Records home loaded successfully.", data)


@router.get("/data-use-summary", status_code=status.HTTP_200_OK)
async def get_data_use_summary(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the plain-language data-use summary."""
    data = records_service.get_data_use_summary()
    return success_response("Data-use summary loaded successfully.", data)


@router.get("/reconditioning-plan", status_code=status.HTTP_200_OK)
async def get_my_reconditioning_plan(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated operator's reconditioning plan."""
    data = await reconditioning_service.get_for_user(current_user.id)
    return success_response("Reconditioning plan loaded successfully.", data)


@router.put("/reconditioning-plan/{user_id}", status_code=status.HTTP_200_OK)
async def update_reconditioning_plan(
    user_id: str,
    payload: ReconditioningPlanUpdate,
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin create/update an operator's reconditioning plan."""
    target_user = await User.get(user_id)
    if target_user is None:
        return success_response("User not found.", {"available": False})
    data = await reconditioning_service.upsert_for_user(target_user, payload, current_user.id)
    return success_response("Reconditioning plan updated successfully.", data)


@router.get("/fly-away-kit", status_code=status.HTTP_200_OK)
async def get_fly_away_kit(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the Fly Away Kit view for the authenticated operator."""
    data = await fly_away_kit_service.get_for_user(current_user)
    return success_response("Fly Away Kit loaded successfully.", data)


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def upload_medical_record(
    document_type: str = Form(...),
    access_reason: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload a medical record (controlled copy, not a system of record)."""
    data = await medical_record_service.upload(current_user, document_type, access_reason, file)
    return success_response("Record uploaded successfully.", data)


@router.get("/uploads", status_code=status.HTTP_200_OK)
async def list_medical_records(
    document_type: str = "all",
    search: str | None = None,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's uploaded medical records."""
    data = await medical_record_service.list_for_user(current_user, document_type, search)
    return success_response("Records loaded successfully.", data)


@router.get("/uploads/{record_id}", status_code=status.HTTP_200_OK)
async def get_medical_record_detail(
    record_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a medical record's full detail + access-reason log."""
    data = await medical_record_service.get_detail(current_user, record_id)
    return success_response("Record detail loaded successfully.", data)


@router.get("/uploads/{record_id}/file")
async def download_medical_record_file(
    record_id: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Download the decrypted file for a medical record."""
    content, file_name = await medical_record_service.get_file(current_user, record_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/uploads/{record_id}/review", status_code=status.HTTP_200_OK)
async def review_medical_record(
    record_id: str,
    payload: RecordReviewRequest,
    current_user: User = Depends(require_roles(ROLE_ADMIN, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM or Admin marks a record reviewed."""
    data = await medical_record_service.review(current_user, record_id, payload.note)
    return success_response("Record marked reviewed.", data)
