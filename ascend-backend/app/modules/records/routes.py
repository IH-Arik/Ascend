"""Records module routes (DOCX sections 8.1, 8.2, 8.6, 8.8 - Records home)."""

import base64
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.deps import get_current_user, require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES, ROLE_PTIM, ROLE_SCS
from app.models.user import User
from app.schemas.medical_record import AccessLevelUpdateRequest, RecordReviewRequest, RevealFieldRequest
from app.schemas.reconditioning import ReconditioningPlanUpdate
from app.schemas.restriction import RestrictionCreate
from app.schemas.rom_measurement import RomMeasurementCreate
from app.services.file_storage_service import guess_content_type
from app.services.fly_away_kit_service import FlyAwayKitService
from app.services.medical_record_service import MedicalRecordService
from app.services.reconditioning_service import ReconditioningService
from app.services.records_service import RecordsService
from app.services.restriction_service import RestrictionService
from app.services.rom_measurement_service import RomMeasurementService

router = APIRouter()
records_service = RecordsService()
medical_record_service = MedicalRecordService()
reconditioning_service = ReconditioningService()
fly_away_kit_service = FlyAwayKitService()
rom_measurement_service = RomMeasurementService()
restriction_service = RestrictionService()


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
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin create/update an operator's reconditioning plan."""
    target_user = await User.get(user_id)
    if target_user is None:
        return success_response("User not found.", {"available": False})
    data = await reconditioning_service.upsert_for_user(target_user, payload, current_user.id)
    return success_response("Reconditioning plan updated successfully.", data)


@router.get("/reconditioning-plan/timeline", status_code=status.HTTP_200_OK)
async def get_my_reconditioning_timeline(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated operator's real reconditioning-event timeline."""
    data = await reconditioning_service.get_timeline(current_user.id)
    return success_response("Reconditioning timeline loaded successfully.", data)


@router.get("/reconditioning-plan/rom-measurements", status_code=status.HTTP_200_OK)
async def get_my_rom_measurements(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated operator's real ROM measurements."""
    data = await rom_measurement_service.list_for_user(current_user.id)
    return success_response("ROM measurements loaded successfully.", data)


@router.get("/reconditioning-plan/{user_id}/timeline", status_code=status.HTTP_200_OK)
async def get_reconditioning_timeline(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin views an operator's real reconditioning-event timeline."""
    data = await reconditioning_service.get_timeline(user_id)
    return success_response("Reconditioning timeline loaded successfully.", data)


@router.get("/reconditioning-plan/{user_id}/rom-measurements", status_code=status.HTTP_200_OK)
async def get_rom_measurements(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin views an operator's real ROM measurements."""
    data = await rom_measurement_service.list_for_user(user_id)
    return success_response("ROM measurements loaded successfully.", data)


@router.post("/reconditioning-plan/{user_id}/rom-measurements", status_code=status.HTTP_201_CREATED)
async def add_rom_measurement(
    user_id: str,
    payload: RomMeasurementCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin records a real ROM measurement for an operator."""
    target_user = await User.get(user_id)
    if target_user is None:
        return success_response("User not found.", {"available": False})
    data = await rom_measurement_service.add_measurement(
        target_user, payload.movement, payload.value_degrees, payload.measured_date, current_user.id, payload.note
    )
    return success_response("ROM measurement recorded successfully.", data)


@router.get("/reconditioning-plan/restrictions", status_code=status.HTTP_200_OK)
async def get_my_restrictions(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Return the authenticated operator's real duty/training restrictions."""
    data = await restriction_service.list_for_user(current_user.id)
    return success_response("Restrictions loaded successfully.", data)


@router.get("/reconditioning-plan/{user_id}/restrictions", status_code=status.HTTP_200_OK)
async def get_restrictions(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin views an operator's real duty/training restrictions."""
    data = await restriction_service.list_for_user(user_id)
    return success_response("Restrictions loaded successfully.", data)


@router.post("/reconditioning-plan/{user_id}/restrictions", status_code=status.HTTP_201_CREATED)
async def add_restriction(
    user_id: str,
    payload: RestrictionCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin records a real duty/training restriction for an operator."""
    target_user = await User.get(user_id)
    if target_user is None:
        return success_response("User not found.", {"available": False})
    data = await restriction_service.add_restriction(
        target_user, payload.description, payload.required_phase, current_user.id
    )
    return success_response("Restriction recorded successfully.", data)


@router.post("/reconditioning-plan/restrictions/{restriction_id}/release", status_code=status.HTTP_200_OK)
async def release_restriction(
    restriction_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM, SCS, or Admin explicitly signs off to release a restriction - only once the required phase is reached."""
    data = await restriction_service.release_restriction(restriction_id, current_user.id)
    return success_response("Restriction released successfully.", data)


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
) -> dict[str, Any]:
    """Return the decrypted file for a medical record as base64-encoded JSON."""
    content, file_name = await medical_record_service.get_file(current_user, record_id)
    data = {
        "file_name": file_name,
        "content_type": guess_content_type(file_name),
        "file_size_bytes": len(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    return success_response("Record file loaded successfully.", data)


@router.post("/uploads/{record_id}/review", status_code=status.HTTP_200_OK)
async def review_medical_record(
    record_id: str,
    payload: RecordReviewRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM or Admin marks a record reviewed - approved or denied."""
    data = await medical_record_service.review(current_user, record_id, payload.note, payload.approve)
    return success_response("Record marked reviewed.", data)


@router.patch("/uploads/{record_id}/access-level", status_code=status.HTTP_200_OK)
async def update_record_access_level(
    record_id: str,
    payload: AccessLevelUpdateRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Admin narrows/sets a specific record's real approved-access role list. Audit logged."""
    data = await medical_record_service.update_access_level(current_user, record_id, payload.approved_access_level)
    return success_response("Access level updated successfully.", data)


@router.post("/uploads/{record_id}/reveal-field", status_code=status.HTTP_200_OK)
async def reveal_record_field(
    record_id: str,
    payload: RevealFieldRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """A masked non-clinical viewer's reason-required, one-time reveal of a redacted field. Audit logged."""
    data = await medical_record_service.reveal_field(
        current_user, record_id, payload.field_name, payload.reason, payload.reason_category
    )
    return success_response("Field revealed successfully.", data)
