"""Admin routes."""

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ROLE_ADMIN, ROLE_PTIM, ROLE_SCS
from app.models.user import User
from app.schemas.admin_user import ProviderAssignRequest, RoleChangeRequest, UnitAssignRequest
from app.schemas.coverage_log import CoverageLogCreate
from app.schemas.emergency_contact import EmergencyContactUpdate
from app.schemas.equipment_gap import EquipmentGapCreate, EquipmentGapUpdate
from app.schemas.provider_credential import CredentialCreate
from app.schemas.scoring_config import ScoringConfigCreate
from app.schemas.utilization_event import UtilizationEventCreate
from app.services.account_management_service import AccountManagementService
from app.services.admin_user_service import AdminUserService
from app.services.coverage_service import CoverageService
from app.services.credential_service import CredentialService
from app.services.equipment_gap_service import EquipmentGapService
from app.services.fly_away_kit_service import FlyAwayKitService
from app.services.report_export_service import ReportExportService
from app.services.reports_service import ReportsService
from app.services.scoring_config_service import ScoringConfigService
from app.services.utilization_service import UtilizationService

router = APIRouter()
account_management_service = AccountManagementService()
fly_away_kit_service = FlyAwayKitService()
admin_user_service = AdminUserService()
credential_service = CredentialService()
equipment_gap_service = EquipmentGapService()
utilization_service = UtilizationService()
coverage_service = CoverageService()
scoring_config_service = ScoringConfigService()
reports_service = ReportsService()
report_export_service = ReportExportService()

PROVIDER_ROLES = (ROLE_ADMIN, ROLE_SCS, ROLE_PTIM)

REPORT_BUILDERS = {
    "injury": lambda: reports_service.get_injury_report(),
    "assessment_completion": lambda: reports_service.get_assessment_completion_report(),
    "utilization": lambda: reports_service.get_utilization_report(),
    "prs_qcp": lambda: reports_service.get_prs_qcp_report(),
}


@router.get("/overview", summary="Admin overview placeholder")
async def get_admin_overview(
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Return a protected admin overview placeholder."""
    return success_response(
        "Admin overview loaded successfully.",
        {
            "requested_by": {
                "id": str(current_user.id),
                "role": current_user.role,
            },
            "next_step": "Implement admin dashboard aggregation, exports, and compliance trackers.",
        },
    )


@router.get("/deactivation-requests", summary="Deactivation queue")
async def list_deactivation_requests(
    status_filter: str = "pending",
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Return deactivation requests pending Admin review (or all, with ?status_filter=all)."""
    data = await account_management_service.list_deactivation_requests(status_filter)
    return success_response("Deactivation requests loaded successfully.", data)


@router.post("/deactivation-requests/{request_id}/approve", summary="Approve a deactivation request")
async def approve_deactivation_request(
    request_id: str,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Approve a pending deactivation request - deactivates the target account."""
    data = await account_management_service.review_deactivation_request(
        current_user, request_id, approve=True
    )
    return success_response("Deactivation request approved.", data)


@router.post("/deactivation-requests/{request_id}/reject", summary="Reject a deactivation request")
async def reject_deactivation_request(
    request_id: str,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Reject a pending deactivation request - the account remains active."""
    data = await account_management_service.review_deactivation_request(
        current_user, request_id, approve=False
    )
    return success_response("Deactivation request rejected.", data)


@router.put("/emergency-contacts/{unit_id}", summary="Set a unit's Fly Away Kit emergency contacts")
async def update_emergency_contacts(
    unit_id: str,
    payload: EmergencyContactUpdate,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin-only: set the real emergency contact numbers shown on the Fly Away Kit."""
    data = await fly_away_kit_service.upsert_emergency_contacts(unit_id, payload, current_user.id)
    return success_response("Emergency contacts updated successfully.", data)


# --- User / role / unit / provider assignment (DOCX Admin Panel) ---


@router.get("/users", summary="List users")
async def list_users(
    role: str | None = None,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Return every user, optionally filtered by role."""
    data = await admin_user_service.list_users(role)
    return success_response("Users loaded successfully.", data)


@router.patch("/users/{user_id}/role", summary="Change a user's role")
async def change_user_role(
    user_id: str,
    payload: RoleChangeRequest,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin changes a user's role. Audit logged as `role_changed`."""
    data = await admin_user_service.change_role(current_user, user_id, payload)
    return success_response("Role updated successfully.", data)


@router.patch("/users/{user_id}/unit", summary="Assign a user to a unit")
async def assign_user_unit(
    user_id: str,
    payload: UnitAssignRequest,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin assigns a user to a unit. Audit logged as `unit_assigned`."""
    data = await admin_user_service.assign_unit(current_user, user_id, payload)
    return success_response("Unit updated successfully.", data)


@router.post("/users/{user_id}/assign-provider", summary="Manually assign a My Support Team provider")
async def assign_user_provider(
    user_id: str,
    payload: ProviderAssignRequest,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin manually assigns/overrides a pathway's provider for a user."""
    data = await admin_user_service.assign_provider(current_user, user_id, payload)
    return success_response("Provider assigned successfully.", data)


# --- Provider credential / certification tracker ---


@router.post("/credentials", summary="Add a provider credential/certification")
async def add_credential(
    payload: CredentialCreate,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin adds a credential/certification record for a provider."""
    data = await credential_service.add_credential(payload, current_user.id)
    return success_response("Credential added successfully.", data)


@router.get("/credentials", summary="List all provider credentials")
async def list_credentials(
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Return every credential on file (the Admin credential dashboard)."""
    data = await credential_service.list_all()
    return success_response("Credentials loaded successfully.", data)


# --- Equipment and Supply Gap Tracker (DOCX 8.7) ---


@router.post("/equipment-gaps", summary="Log an equipment/supply gap")
async def create_equipment_gap(
    payload: EquipmentGapCreate,
    current_user: User = Depends(require_roles(*PROVIDER_ROLES)),
):
    """SCS/PT-IM/Admin flag an equipment or supply shortfall."""
    data = await equipment_gap_service.create(current_user, payload)
    return success_response("Equipment gap logged successfully.", data)


@router.get("/equipment-gaps", summary="List equipment/supply gaps")
async def list_equipment_gaps(
    status_filter: str | None = None,
    current_user: User = Depends(require_roles(*PROVIDER_ROLES)),
):
    """Return tracked equipment/supply gaps, optionally filtered by status."""
    data = await equipment_gap_service.list_all(status_filter)
    return success_response("Equipment gaps loaded successfully.", data)


@router.patch("/equipment-gaps/{gap_id}", summary="Update an equipment/supply gap's status")
async def update_equipment_gap(
    gap_id: str,
    payload: EquipmentGapUpdate,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin updates a gap's status and/or report-inclusion flag."""
    data = await equipment_gap_service.update_status(gap_id, payload)
    return success_response("Equipment gap updated successfully.", data)


# --- Utilization events (feeds the Utilization Report) ---


@router.post("/utilization-events", summary="Log a utilization event")
async def create_utilization_event(
    payload: UtilizationEventCreate,
    current_user: User = Depends(require_roles(*PROVIDER_ROLES)),
):
    """Log a training/education/feedback utilization event."""
    data = await utilization_service.create(current_user, payload)
    return success_response("Utilization event logged successfully.", data)


@router.get("/utilization-events", summary="List recent utilization events")
async def list_utilization_events(
    days: int = 90,
    current_user: User = Depends(require_roles(*PROVIDER_ROLES)),
):
    """Return utilization events from the last N days."""
    data = await utilization_service.list_recent(days)
    return success_response("Utilization events loaded successfully.", data)


# --- Provider coverage-hours log (feeds the PRS/QCP Support Report) ---


@router.post("/coverage-logs", summary="Log provider coverage hours")
async def create_coverage_log(
    payload: CoverageLogCreate,
    current_user: User = Depends(require_roles(*PROVIDER_ROLES)),
):
    """Log a block of provider coverage hours (self-logged or Admin-logged)."""
    data = await coverage_service.create(current_user.id, payload)
    return success_response("Coverage hours logged successfully.", data)


@router.get("/coverage-logs/{provider_id}", summary="List a provider's coverage log")
async def list_coverage_logs(
    provider_id: str,
    year: int | None = None,
    current_user: User = Depends(require_roles(*PROVIDER_ROLES)),
):
    """Return a provider's coverage-hours log, optionally filtered to one year."""
    data = await coverage_service.list_for_provider(provider_id, year)
    return success_response("Coverage log loaded successfully.", data)


# --- Admin-configurable OPS scoring weights/thresholds ---


@router.post("/scoring-config", summary="Create a new versioned scoring configuration")
async def create_scoring_config(
    payload: ScoringConfigCreate,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Admin creates a new effective-dated OPS weight/threshold configuration."""
    data = await scoring_config_service.create_config(payload, current_user.id)
    return success_response("Scoring configuration created successfully.", data)


@router.get("/scoring-config", summary="List scoring configuration history")
async def list_scoring_configs(
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Return every scoring configuration version, newest first."""
    data = await scoring_config_service.list_configs()
    return success_response("Scoring configurations loaded successfully.", data)


# --- Quarterly reports + CSV export (DOCX section 12) ---


@router.get("/reports/{report_type}", summary="View a quarterly report")
async def get_report(
    report_type: str,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
) -> dict[str, Any]:
    """Return one of: injury, assessment_completion, utilization, prs_qcp."""
    builder = REPORT_BUILDERS.get(report_type)
    if builder is None:
        return success_response(
            "Unknown report type.", {"allowed": list(REPORT_BUILDERS.keys())}
        )
    data = await builder()
    return success_response("Report loaded successfully.", data)


@router.get("/reports/{report_type}/export", summary="Export a quarterly report as CSV")
async def export_report(
    report_type: str,
    date_range: str = "current",
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
) -> Response:
    """Export a report as CSV; writes a `ReportExport` audit-log entry."""
    builder = REPORT_BUILDERS.get(report_type)
    if builder is None:
        return Response(content="Unknown report type.", status_code=400)
    report_data = await builder()
    csv_bytes, file_name = await report_export_service.export_csv(
        report_type, report_data, current_user, date_range
    )
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/reports/export-log/history", summary="View the report export log")
async def get_export_log(
    report_type: str | None = None,
    current_user: User = Depends(require_roles(ROLE_ADMIN)),
):
    """Return the append-only report export log (DOCX: "Report control and OPSEC/CUI audit")."""
    data = await report_export_service.list_export_log(report_type)
    return success_response("Export log loaded successfully.", data)
