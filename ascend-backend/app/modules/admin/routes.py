"""Admin routes."""

from typing import Any

import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core import database as database_module
from app.core.config import get_settings
from app.core.question_registry import build_question_registry
from app.core.roles import ADMIN_ROLES, ROLE_IDMT, ROLE_LEADERSHIP, ROLE_PTIM, ROLE_SCS
from app.core.scheduler import (
    DAILY_REMINDERS_JOB,
    EXPIRE_STALE_CONFIRMATIONS_JOB,
    L2_DROP_POINTS,
    L3_DROP_POINTS,
    L4_DROP_POINTS,
    SCHEDULED_EXPORTS_JOB,
    UNIT_THRESHOLD_CHECK_JOB,
)
from app.core.security import decode_token
from app.models.audit_log import AuditLog
from app.models.report_export import ReportExport
from app.models.scheduler_job_run import SchedulerJobRun
from app.models.idmt_handoff import IdmtHandoff
from app.models.user import User
from app.schemas.admin_confirmation import ConfirmationRejectRequest
from app.schemas.admin_user import (
    AdminCreateUserRequest,
    AdminDeactivationRequest,
    ProviderAssignRequest,
    RoleChangeRequest,
    UnitAssignRequest,
)
from app.schemas.coverage_log import CoverageLogCreate
from app.schemas.emergency_contact import EmergencyContactUpdate
from app.schemas.equipment_gap import EquipmentGapCreate, EquipmentGapUpdate
from app.schemas.idmt_handoff import IdmtHandoffCreateRequest
from app.schemas.org_unit import OrgUnitCreate
from app.schemas.provider_credential import CredentialCreate
from app.schemas.question_bank_version import QuestionBankVersionCreate
from app.schemas.scheduled_export import ScheduledExportCreate, ScheduledExportUpdate
from app.schemas.recommendation_threshold_config import RecommendationThresholdConfigCreate
from app.schemas.report_export import ReportLifecycleUpdate
from app.schemas.scoring_config import ScoringConfigCreate
from app.schemas.utilization_event import UtilizationEventCreate
from app.services.account_management_service import AccountManagementService
from app.services.admin_confirmation_service import EXPORT_APPROVAL_WINDOW_HOURS, AdminConfirmationService
from app.services.admin_user_service import INACTIVITY_GRACE_DAYS, AdminUserService
from app.services.audit_log_service import AuditLogService
from app.services.coverage_service import CoverageService
from app.services.credential_service import CredentialService
from app.services.equipment_gap_service import EquipmentGapService
from app.services.fly_away_kit_service import FlyAwayKitService
from app.services.idmt_handoff_service import IdmtHandoffService
from app.services.leadership_aggregate_service import LeadershipAggregateService
from app.services.oft_service import OFTService
from app.services.org_unit_service import OrgUnitService
from app.services.provider_dashboard_service import ProviderDashboardService
from app.services.question_bank_version_service import QuestionBankVersionService
from app.services.role_admin_service import RoleAdminService
from app.services.recommendation_threshold_config_service import (
    RecommendationThresholdConfigService,
)
from app.services.report_export_service import (
    REPORT_SENSITIVITY,
    ReportExportService,
    compute_risk_tier,
    report_rows,
)
from app.services.scheduled_export_service import ScheduledExportService
from app.services.reports_service import ReportsService
from app.services.scoring_config_service import ScoringConfigService
from app.services.utilization_service import UtilizationService

router = APIRouter()
account_management_service = AccountManagementService()
fly_away_kit_service = FlyAwayKitService()
admin_user_service = AdminUserService()
admin_confirmation_service = AdminConfirmationService()
org_unit_service = OrgUnitService()
audit_log_service = AuditLogService()
scheduled_export_service = ScheduledExportService()
provider_dashboard_service = ProviderDashboardService()
role_admin_service = RoleAdminService()
credential_service = CredentialService()
equipment_gap_service = EquipmentGapService()
utilization_service = UtilizationService()
coverage_service = CoverageService()
scoring_config_service = ScoringConfigService()
question_bank_version_service = QuestionBankVersionService()
recommendation_threshold_config_service = RecommendationThresholdConfigService()
reports_service = ReportsService()
report_export_service = ReportExportService()
oft_service = OFTService()
leadership_aggregate_service = LeadershipAggregateService()
idmt_handoff_service = IdmtHandoffService()

PROVIDER_ROLES = (*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM)

REPORT_BUILDERS = {
    "injury": lambda: reports_service.get_injury_report(),
    "assessment_completion": lambda: reports_service.get_assessment_completion_report(),
    "utilization": lambda: reports_service.get_utilization_report(),
    "prs_qcp": lambda: reports_service.get_prs_qcp_report(),
    "audit_log": lambda: audit_log_service.search(page=1, page_size=1000),
    "oft_metrics": lambda: oft_service.get_leadership_metrics_report(),
    "wing_weekly_ops": lambda: leadership_aggregate_service.get_wing_weekly_report(),
    "monthly_cohort_review": lambda: leadership_aggregate_service.get_monthly_cohort_report(),
    "annual_wing_readiness": lambda: leadership_aggregate_service.get_annual_wing_report(),
    "leadership_aggregate_readiness": lambda: reports_service.get_leadership_aggregate_readiness_report(),
    "idmt_handoff_summary": lambda: reports_service.get_idmt_handoff_summary_report(),
    "medical_records_audit": lambda: reports_service.get_medical_records_audit_report(),
    "performance_summary_export": lambda: reports_service.get_performance_summary_export_report(),
}


@router.get("/overview", summary="Admin overview placeholder")
async def get_admin_overview(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
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
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return deactivation requests pending Admin review (or all, with ?status_filter=all)."""
    data = await account_management_service.list_deactivation_requests(status_filter)
    return success_response("Deactivation requests loaded successfully.", data)


@router.post("/deactivation-requests/{request_id}/approve", summary="Approve a deactivation request")
async def approve_deactivation_request(
    request_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Approve a pending deactivation request - deactivates the target account."""
    data = await account_management_service.review_deactivation_request(
        current_user, request_id, approve=True
    )
    return success_response("Deactivation request approved.", data)


@router.post("/deactivation-requests/{request_id}/reject", summary="Reject a deactivation request")
async def reject_deactivation_request(
    request_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Reject a pending deactivation request - the account remains active."""
    data = await account_management_service.review_deactivation_request(
        current_user, request_id, approve=False
    )
    return success_response("Deactivation request rejected.", data)


@router.post(
    "/org-units",
    status_code=status.HTTP_201_CREATED,
    summary="Create a real org unit (Wing/Detachment/Flight)",
)
async def create_org_unit(
    payload: OrgUnitCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin creates a real org unit node. Audit logged."""
    data = await org_unit_service.create(current_user, payload)
    return success_response("Org unit created successfully.", data)


@router.get("/org-units", summary="List org units with resolved ancestor paths")
async def list_org_units(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every real org unit, each with its resolved Wing -> ... -> unit ancestor path."""
    data = await org_unit_service.list_all()
    return success_response("Org units loaded successfully.", data)


@router.get("/audit-log", summary="Search/filter/paginate the real audit log")
async def search_audit_log(
    actor_role: str | None = None,
    event_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    query: str | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Real filter/search/paginate over `AuditLog` - no fabricated retention field."""
    data = await audit_log_service.search(actor_role, event_type, date_from, date_to, query, page, page_size)
    return success_response("Audit log loaded successfully.", data)


@router.get("/audit-log/category-rollup", summary="Real 24h/7d/30d counts per audit category")
async def get_audit_log_category_rollup(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """6 real categories - mapping stated in `app/services/audit_log_service.py`."""
    data = await audit_log_service.get_category_rollup()
    return success_response("Audit log category rollup loaded successfully.", data)


@router.get("/audit-log/stats", summary="Real audit-log overview stats")
async def get_audit_log_stats(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """24h/7d totals, real % vs 7d average, real 24h medical-record-access count."""
    data = await audit_log_service.get_stats()
    return success_response("Audit log stats loaded successfully.", data)


@router.websocket("/audit-log/live")
async def audit_log_live_tail(websocket: WebSocket, token: str = "") -> None:
    """Real-time audit-log stream via a MongoDB change stream (not polling).

    Not DOCX-sourced (a Figma "Live tail" panel triggered this). WebSocket
    routes can't use the normal `Depends(require_roles(...))` auth chain, so
    the token is decoded manually here using the same `decode_token`
    (`app/core/security.py`) the regular HTTP auth dependency
    (`app/api/deps.py`) already uses.
    """
    try:
        payload = decode_token(token)
        user = await User.get(payload.get("sub")) if payload.get("token_type") == "access" else None
    except ValueError:
        user = None
    if user is None or not user.is_active or user.role not in ADMIN_ROLES:
        await websocket.close(code=4403)
        return

    await websocket.accept()
    # `.watch()` is itself a coroutine returning the change-stream object
    # (pymongo's async API) - it must be awaited before use, not passed
    # directly to `async with`.
    stream = await AuditLog.get_motor_collection().watch([{"$match": {"operationType": "insert"}}])
    try:
        async for change in stream:
            doc = change.get("fullDocument", {})
            await websocket.send_json(
                {
                    "event_type": doc.get("event_type"),
                    "actor_role": doc.get("actor_role"),
                    "target_entity_type": doc.get("target_entity_type"),
                    "target_entity_id": doc.get("target_entity_id"),
                    "summary_message": doc.get("summary_message"),
                    "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                }
            )
    except WebSocketDisconnect:
        return
    finally:
        await stream.close()


@router.post(
    "/scheduled-exports",
    status_code=status.HTTP_201_CREATED,
    summary="Create a real recurring export schedule",
)
async def create_scheduled_export(
    payload: ScheduledExportCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin creates a real recurring export. Audit logged."""
    data = await scheduled_export_service.create(current_user, payload)
    return success_response("Scheduled export created successfully.", data)


@router.get("/scheduled-exports", summary="List real recurring export schedules")
async def list_scheduled_exports(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every real scheduled export."""
    data = await scheduled_export_service.list_all()
    return success_response("Scheduled exports loaded successfully.", data)


@router.patch("/scheduled-exports/{schedule_id}", summary="Edit a real recurring export (name/cadence/format/recipient/status)")
async def update_scheduled_export(
    schedule_id: str,
    payload: ScheduledExportUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin edits a real schedule - only the fields given are changed. Audit logged."""
    data = await scheduled_export_service.update(current_user, schedule_id, payload)
    return success_response("Scheduled export updated successfully.", data)


@router.delete("/scheduled-exports/{schedule_id}", summary="Delete a real recurring export")
async def delete_scheduled_export(
    schedule_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin deletes a real schedule. Audit logged."""
    await scheduled_export_service.delete(current_user, schedule_id)
    return success_response("Scheduled export deleted successfully.", {})


@router.get("/exports/overview", summary="Exports screen overview - real pending/recent/schedules/available reports")
async def get_exports_overview(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Compose real data already tracked - no fabricated due-dates/approvals/recipients."""
    pending = await admin_confirmation_service.list_pending("pending")
    pending_exports = [c for c in pending["confirmations"] if c["action_type"] == "export"]
    for confirmation in pending_exports:
        confirmation["risk_tier"] = compute_risk_tier(
            confirmation["payload"].get("sensitivity_level", "restricted"),
            confirmation["payload"].get("row_count", 0),
        )

    # `ReportExport` itself has no row-count field - for a restricted export
    # the real count lives on its matching `PendingConfirmation.payload`
    # (any status, since an approved one is no longer "pending"), looked up
    # by the real `target_entity_id` link between the two.
    all_confirmations = await admin_confirmation_service.list_pending("all")
    row_count_by_export_id = {
        c["target_entity_id"]: c["payload"].get("row_count", 0)
        for c in all_confirmations["confirmations"]
        if c["action_type"] == "export"
    }

    recent = await report_export_service.list_export_log()
    recent_exports = recent["exports"][:6]
    for export_row in recent_exports:
        row_count = row_count_by_export_id.get(export_row["id"], 0)
        export_row["risk_tier"] = compute_risk_tier(export_row["sensitivity_level"], row_count)

    schedules = await scheduled_export_service.list_all()

    all_exports = recent["exports"]
    available_reports = []
    for report_type in REPORT_BUILDERS:
        matching = [e for e in all_exports if e["report_type"] == report_type]
        last_generated = matching[0]["created_at"] if matching else None
        available_reports.append(
            {
                "report_type": report_type,
                "sensitivity_level": REPORT_SENSITIVITY.get(report_type, "controlled"),
                "last_generated_at": last_generated,
            }
        )

    return success_response(
        "Exports overview loaded successfully.",
        {
            "pending_confirmations": pending_exports,
            "recent_exports": recent_exports,
            "schedules": schedules["schedules"],
            "available_reports": available_reports,
        },
    )


@router.get(
    "/reports/required-contract-reports",
    summary="The real 9 required contract reports (DOCX Table 26) + real generation status",
)
async def get_required_contract_reports(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Backs the Exports 'X required contract reports' panel with DOCX-verbatim names/sections/users."""
    data = await reports_service.get_required_contract_reports_status()
    return success_response("Required contract reports loaded successfully.", data)


@router.get("/system/diagnostics", summary="Real system diagnostics - DB ping, scheduler job health, AI config")
async def get_system_diagnostics(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Not DOCX-sourced (a Figma 'System' screen's fake service/latency table triggered this) -
    every field here is a real, no-cost check, not a fabricated microservice list.
    """
    db_status = "offline"
    db_latency_ms = None
    if database_module.database is not None:
        started = time.perf_counter()
        try:
            await database_module.database.command("ping")
            db_status = "online"
            db_latency_ms = round((time.perf_counter() - started) * 1000, 1)
        except Exception:
            db_status = "offline"

    job_names = [DAILY_REMINDERS_JOB, UNIT_THRESHOLD_CHECK_JOB, SCHEDULED_EXPORTS_JOB, EXPIRE_STALE_CONFIRMATIONS_JOB]
    all_runs = await SchedulerJobRun.find().sort(-SchedulerJobRun.started_at).to_list()
    jobs = []
    for job_name in job_names:
        latest = next((r for r in all_runs if r.job_name == job_name), None)
        jobs.append(
            {
                "job_name": job_name,
                "last_run_status": latest.status if latest else "never_run",
                "last_run_at": latest.started_at.isoformat() if latest else None,
            }
        )

    settings = get_settings()
    return success_response(
        "System diagnostics loaded successfully.",
        {
            "database": {"status": db_status, "latency_ms": db_latency_ms},
            "scheduler_jobs": jobs,
            "ai_provider_configured": bool(settings.ai_provider_api_key),
        },
    )


ACTIVE_SESSION_WINDOW_MINUTES = 30


@router.get("/system/overview", summary="System screen overview - real uptime/thresholds/queues, no fabricated panels")
async def get_system_overview(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Composes real data already tracked. See app/core/scheduler.py for the tiered threshold
    constants and app/services/coverage_service.py for the real RSD aggregate.

    `active_sessions`/`pending_transmission_count` added 2026-08-23 closing
    2 of the System screen's real gaps (found alongside 3 that stay
    genuinely unbacked - 24h uptime %, a backup system, and a "Compliance
    - 55d" day-count - none of which this backend tracks anywhere, and
    none built here rather than invented). `active_sessions` is not a
    real session store (this app is stateless-JWT, no server-side session
    table) - it is a real, explicitly-labeled proxy: users whose real
    `last_login_at` falls within the last `ACTIVE_SESSION_WINDOW_MINUTES`,
    our own reasonable inference for "active" since no design or DOCX
    source defines the term. `pending_transmission_count` is real -
    `IdmtHandoff` records already track a real `approved -> transmitted`
    state transition (DOCX Section 8.5), so "approved but not yet
    transmitted" is a real, not inferred, count.
    """
    system_health = await provider_dashboard_service.get_system_health()
    question_registry = build_question_registry()

    leadership_scope = await role_admin_service.get_scope_config(ROLE_LEADERSHIP)

    pending = await admin_confirmation_service.list_pending("pending")
    pending_deactivation_confirmations = [c for c in pending["confirmations"] if c["action_type"] == "deactivation"]
    self_service_deactivations = await account_management_service.list_deactivation_requests("pending")

    inactive_accounts = await admin_user_service.list_inactive_accounts(INACTIVITY_GRACE_DAYS)

    rsd_coverage = await coverage_service.get_rsd_summary(datetime.now(timezone.utc).year)

    session_cutoff = datetime.now(timezone.utc) - timedelta(minutes=ACTIVE_SESSION_WINDOW_MINUTES)
    recently_active = await User.find(User.last_login_at >= session_cutoff).to_list()
    staff_count = sum(1 for u in recently_active if u.role not in ADMIN_ROLES and u.role != ROLE_IDMT)
    admin_count = sum(1 for u in recently_active if u.role in ADMIN_ROLES)
    imt_count = sum(1 for u in recently_active if u.role == ROLE_IDMT)

    pending_transmission_count = await IdmtHandoff.find(IdmtHandoff.status == "approved").count()

    return success_response(
        "System overview loaded successfully.",
        {
            "system_health": system_health,
            "question_bank": {"total_questions": question_registry["total_questions"]},
            "threshold_rules": {
                "cohort_minimum_k": leadership_scope["cohort_k"],
                "l2_drop_points": L2_DROP_POINTS,
                "l3_drop_points": L3_DROP_POINTS,
                "l4_drop_points": L4_DROP_POINTS,
                "export_approval_window_hours": EXPORT_APPROVAL_WINDOW_HOURS,
                "deactivation_grace_days": INACTIVITY_GRACE_DAYS,
                "confidence_rule": (
                    "high: 5/5 real components valid + 0 stale; "
                    "medium: 3+/5 valid + <=1 stale; low: otherwise "
                    "(app/core/scoring.py calculate_confidence - categorical, "
                    "not a numeric percentage)."
                ),
            },
            "reverse_scoring_status": (
                "No weekly/monthly question requires reverse-scoring - every question's "
                "options are already ordered worst-to-best, which the default (non-reversed) "
                "scoring path already handles correctly. Verified against all 20 real "
                "weekly/monthly questions."
            ),
            "deactivation_queue": {
                "admin_initiated_pending": pending_deactivation_confirmations,
                "self_service_pending": self_service_deactivations["requests"],
            },
            "inactive_accounts_count": len(inactive_accounts),
            "rsd_coverage": rsd_coverage,
            "privacy_cohort_suppression": {"leadership_k": leadership_scope["cohort_k"]},
            "active_sessions": {
                "window_minutes": ACTIVE_SESSION_WINDOW_MINUTES,
                "total": len(recently_active),
                "staff": staff_count,
                "admin": admin_count,
                "imt": imt_count,
            },
            "pending_transmission_count": pending_transmission_count,
        },
    )


@router.get("/question-registry", summary="Contract Question Registry - real 46-question view")
async def get_question_registry(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Simplified, real registry over the 4 existing question banks (not DOCX-sourced, see `app/core/question_registry.py`).

    `current_version` is the real active `QuestionBankVersion`, if an Admin has recorded one (`POST /admin/question-bank-versions`) - `None` otherwise, never fabricated.
    """
    data = build_question_registry()
    data["current_version"] = await question_bank_version_service.get_active_version_summary()
    return success_response("Question registry loaded successfully.", data)


# --- Question Bank Version (DOCX Table 22: version_id, effective_date, retired_date, approved_by, ...) ---


@router.post(
    "/question-bank-versions",
    status_code=status.HTTP_201_CREATED,
    summary="Record a new approved question bank version",
)
async def create_question_bank_version(
    payload: QuestionBankVersionCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin/Superadmin approves and records a new question bank version."""
    data = await question_bank_version_service.create_version(current_user, payload)
    return success_response("Question bank version recorded successfully.", data)


@router.get("/question-bank-versions", summary="List question bank version history")
async def list_question_bank_versions(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every recorded question bank version, newest first."""
    data = await question_bank_version_service.list_versions()
    return success_response("Question bank versions loaded successfully.", data)


@router.post("/question-bank-versions/{version_id}/retire", summary="Retire a question bank version")
async def retire_question_bank_version(
    version_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin/Superadmin retires a version as of today."""
    data = await question_bank_version_service.retire_version(current_user, version_id)
    return success_response("Question bank version retired successfully.", data)


@router.get("/confirmations", summary="List second-reviewer confirmations")
async def list_confirmations(
    status_filter: str = "pending",
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return pending (or all, with ?status_filter=all) second-reviewer confirmations."""
    data = await admin_confirmation_service.list_pending(status_filter)
    return success_response("Confirmations loaded successfully.", data)


@router.post("/confirmations/{confirmation_id}/approve", summary="Approve a pending confirmation")
async def approve_confirmation(
    confirmation_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Approve a pending confirmation (must be a different Admin/Superadmin than the requester)."""
    data = await admin_confirmation_service.approve(current_user, confirmation_id)
    return success_response("Confirmation approved.", data)


@router.post("/confirmations/{confirmation_id}/reject", summary="Reject a pending confirmation")
async def reject_confirmation(
    confirmation_id: str,
    payload: ConfirmationRejectRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Reject a pending confirmation. No underlying action is applied."""
    data = await admin_confirmation_service.reject(current_user, confirmation_id, payload.reason)
    return success_response("Confirmation rejected.", data)


@router.post("/confirmations/{confirmation_id}/revert", summary="Revert an approved confirmation")
async def revert_confirmation(
    confirmation_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Revert an already-approved role_change/deactivation using its stored snapshot."""
    data = await admin_confirmation_service.revert(current_user, confirmation_id)
    return success_response("Confirmation reverted.", data)


# --- IDMT documentation handoff (DOCX Section 8.5) ---


@router.post("/idmt-handoffs", summary="Prepare a real IDMT documentation handoff (pending second-reviewer approval)")
async def prepare_idmt_handoff(
    payload: IdmtHandoffCreateRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_PTIM)),
):
    """PT/IM or Admin prepares a documentation handoff for IDMT. Never applied immediately."""
    data = await idmt_handoff_service.prepare(
        current_user, payload.user_id, payload.export_type, payload.export_format
    )
    return JSONResponse(
        status_code=202,
        content=success_response("Handoff pending second-reviewer approval.", data),
    )


@router.get("/idmt-handoffs", summary="List IDMT documentation handoffs")
async def list_idmt_handoffs(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_IDMT)),
):
    """IDMT sees only transmitted/acknowledged handoffs; Admin sees every status."""
    data = (
        await idmt_handoff_service.list_for_idmt()
        if current_user.role == ROLE_IDMT
        else await idmt_handoff_service.list_all()
    )
    return success_response("IDMT handoffs loaded successfully.", data)


@router.post("/idmt-handoffs/{handoff_id}/transmit", summary="Mark an approved handoff transmitted")
async def transmit_idmt_handoff(
    handoff_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_PTIM)),
):
    """A real, distinct state from 'approved' - DOCX tracks prepared/transmitted/acknowledged separately."""
    data = await idmt_handoff_service.transmit(current_user, handoff_id)
    return success_response("Handoff marked transmitted.", data)


@router.post("/idmt-handoffs/{handoff_id}/acknowledge", summary="IDMT acknowledges receipt of a handoff")
async def acknowledge_idmt_handoff(
    handoff_id: str,
    current_user: User = Depends(require_roles(ROLE_IDMT, *ADMIN_ROLES)),
):
    """Real, DOCX-sourced `acknowledgement_status` field - not a fabricated read-receipt object."""
    data = await idmt_handoff_service.acknowledge(current_user, handoff_id)
    return success_response("Handoff acknowledged.", data)


@router.get("/idmt-handoffs/{handoff_id}/download", summary="Download a transmitted handoff's real summary content")
async def download_idmt_handoff(
    handoff_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_IDMT)),
):
    """Real structured summary (reconditioning/medical-record-category counts/OFT status) - never raw file bytes."""
    content, filename = await idmt_handoff_service.download(current_user, handoff_id)
    media_type = "application/pdf" if filename.endswith(".pdf") else "text/csv"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/emergency-contacts/{unit_id}", summary="Set a unit's Fly Away Kit emergency contacts")
async def update_emergency_contacts(
    unit_id: str,
    payload: EmergencyContactUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin-only: set the real emergency contact numbers shown on the Fly Away Kit."""
    data = await fly_away_kit_service.upsert_emergency_contacts(unit_id, payload, current_user.id)
    return success_response("Emergency contacts updated successfully.", data)


# --- User / role / unit / provider assignment (DOCX Admin Panel) ---


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    summary="Admin directly provisions a new account",
)
async def create_user(
    payload: AdminCreateUserRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin provisions a new account (DOCX 2A Step 1). Returns the initial password once."""
    data = await admin_user_service.create_user(current_user, payload)
    return success_response("Account provisioned successfully.", data)


@router.get("/users", summary="List users")
async def list_users(
    role: str | None = None,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every user, optionally filtered by role."""
    data = await admin_user_service.list_users(role)
    return success_response("Users loaded successfully.", data)


@router.patch("/users/{user_id}/role", summary="Change a user's role")
async def change_user_role(
    user_id: str,
    payload: RoleChangeRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin changes a user's role. Audit logged as `role_changed`."""
    data = await admin_user_service.change_role(current_user, user_id, payload)
    return success_response("Role updated successfully.", data)


@router.patch("/users/{user_id}/unit", summary="Assign a user to a unit")
async def assign_user_unit(
    user_id: str,
    payload: UnitAssignRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin assigns a user to a unit. Audit logged as `unit_assigned`."""
    data = await admin_user_service.assign_unit(current_user, user_id, payload)
    return success_response("Unit updated successfully.", data)


@router.post(
    "/users/{user_id}/deactivate",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request deactivation of a provider/admin-level account",
)
async def request_user_deactivation(
    user_id: str,
    payload: AdminDeactivationRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin requests deactivation of a provider/admin-level account (second-reviewer gated).

    Airman targets (no caseload) are out of scope here - use the existing
    self-deactivation-request flow (`/deactivation-requests`) for them.
    """
    confirmation = await admin_confirmation_service.request_deactivation(
        current_user, user_id, payload.reason
    )
    return success_response(
        "Deactivation pending second-reviewer approval.",
        {
            "confirmation_id": str(confirmation.id),
            "target_summary": confirmation.target_summary,
            "consequence_summary": confirmation.consequence_summary,
        },
    )


@router.post("/users/{user_id}/renew-access", summary="Manually renew a user's access expiration")
async def renew_user_access(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin extends `access_expires_at` by another `ACCESS_EXPIRY_DAYS`. Audit logged."""
    data = await admin_user_service.renew_access(current_user, user_id)
    return success_response("Access renewed successfully.", data)


@router.post("/users/{user_id}/reset-password", summary="Admin generates and emails a real temp password")
async def reset_user_password(
    user_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin resets a user's password. The temp password is emailed only - never returned here."""
    data = await admin_user_service.reset_password(current_user, user_id)
    return success_response("Password reset successfully.", data)


@router.post("/users/{user_id}/assign-provider", summary="Manually assign a My Support Team provider")
async def assign_user_provider(
    user_id: str,
    payload: ProviderAssignRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin manually assigns/overrides a pathway's provider for a user."""
    data = await admin_user_service.assign_provider(current_user, user_id, payload)
    return success_response("Provider assigned successfully.", data)


# --- Provider credential / certification tracker ---


@router.post(
    "/credentials",
    status_code=status.HTTP_201_CREATED,
    summary="Add a provider credential/certification",
)
async def add_credential(
    payload: CredentialCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin adds a credential/certification record for a provider."""
    data = await credential_service.add_credential(payload, current_user.id)
    return success_response("Credential added successfully.", data)


@router.get("/credentials", summary="List all provider credentials")
async def list_credentials(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every credential on file (the Admin credential dashboard)."""
    data = await credential_service.list_all()
    return success_response("Credentials loaded successfully.", data)


# --- Equipment and Supply Gap Tracker (DOCX 8.7) ---


@router.post(
    "/equipment-gaps",
    status_code=status.HTTP_201_CREATED,
    summary="Log an equipment/supply gap",
)
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
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin updates a gap's status and/or report-inclusion flag."""
    data = await equipment_gap_service.update_status(gap_id, payload)
    return success_response("Equipment gap updated successfully.", data)


# --- Utilization events (feeds the Utilization Report) ---


@router.post(
    "/utilization-events",
    status_code=status.HTTP_201_CREATED,
    summary="Log a utilization event",
)
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


@router.post(
    "/coverage-logs",
    status_code=status.HTTP_201_CREATED,
    summary="Log provider coverage hours",
)
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


@router.get("/coverage/reconditioning-load-by-flight", summary="Real per-flight reconditioning/rehab caseload, k-gated")
async def get_reconditioning_load_by_flight(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS)),
):
    """SCS or Admin views real reconditioning/rehab caseload by flight."""
    data = await coverage_service.get_reconditioning_load_by_flight()
    return success_response("Reconditioning load by flight loaded successfully.", data)


# --- Admin-configurable OPS scoring weights/thresholds ---


@router.post(
    "/scoring-config",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new versioned scoring configuration",
)
async def create_scoring_config(
    payload: ScoringConfigCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin creates a new effective-dated OPS weight/threshold configuration."""
    data = await scoring_config_service.create_config(payload, current_user.id)
    return success_response("Scoring configuration created successfully.", data)


@router.get("/scoring-config", summary="List scoring configuration history")
async def list_scoring_configs(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every scoring configuration version, newest first."""
    data = await scoring_config_service.list_configs()
    return success_response("Scoring configurations loaded successfully.", data)


# --- Admin-configurable recommendation trigger thresholds ---


@router.post(
    "/recommendation-thresholds",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new versioned recommendation threshold configuration",
)
async def create_recommendation_threshold_config(
    payload: RecommendationThresholdConfigCreate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Admin creates a new effective-dated recommendation trigger threshold configuration."""
    data = await recommendation_threshold_config_service.create_config(payload, current_user.id)
    return success_response("Recommendation threshold configuration created successfully.", data)


@router.get("/recommendation-thresholds", summary="List recommendation threshold configuration history")
async def list_recommendation_threshold_configs(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return every recommendation threshold configuration version, newest first."""
    data = await recommendation_threshold_config_service.list_configs()
    return success_response("Recommendation threshold configurations loaded successfully.", data)


# --- Quarterly reports + CSV export (DOCX section 12) ---


@router.get("/reports/prs_evidence/export", summary="Export real per-entry PRS coverage-hours evidence")
async def export_prs_evidence(
    year: int | None = None,
    export_format: str = "csv",
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> Response:
    """Real per-entry `CoverageLog` rows for every SCS/PT-IM provider - the evidence
    artifact backing `meets_95pct_evidence` on the PRS/QCP report. Writes a
    `ReportExport` audit-log entry like every other report export.

    Registered before `/reports/{report_type}/export` below - FastAPI
    matches path templates in registration order, and `prs_evidence/export`
    would otherwise be swallowed by that generic parameterized route.
    """
    if export_format not in ("csv", "pdf"):
        return Response(content="export_format must be 'csv' or 'pdf'.", status_code=400)
    resolved_year = year or date.today().year
    rows = await coverage_service.export_prs_evidence(resolved_year)
    content_bytes, _ = report_export_service.render("prs_evidence", {}, export_format, rows=rows)
    file_name = f"prs_evidence_{resolved_year}.{export_format}"

    await ReportExport(
        report_type="prs_evidence",
        date_range=str(resolved_year),
        generated_by=current_user.id,
        recipient_role=current_user.role,
        export_format=export_format,
        sensitivity_level="aggregate",
    ).insert()

    media_type = "application/pdf" if export_format == "pdf" else "text/csv"
    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/reports/{report_type}", summary="View a quarterly report")
async def get_report(
    report_type: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Return one of: injury, assessment_completion, utilization, prs_qcp, audit_log, oft_metrics."""
    builder = REPORT_BUILDERS.get(report_type)
    if builder is None:
        return success_response(
            "Unknown report type.", {"allowed": list(REPORT_BUILDERS.keys())}
        )
    data = await builder()
    return success_response("Report loaded successfully.", data)


@router.get("/reports/{report_type}/export", summary="Export a quarterly report as CSV or PDF")
async def export_report(
    report_type: str,
    date_range: str = "current",
    export_format: str = "csv",
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> Response:
    """Export a report as CSV or real PDF; writes a `ReportExport` audit-log entry.

    "restricted"-sensitivity reports (currently `injury`/`audit_log` - see
    `REPORT_SENSITIVITY`) are second-reviewer gated: this returns a pending
    JSON response instead of the file, and it's only downloadable via
    `/reports/export-log/{export_id}/download` after a *different*
    Admin/Superadmin approves it. "aggregate" reports keep exporting
    immediately, unchanged.
    """
    if export_format not in ("csv", "pdf"):
        return Response(content="export_format must be 'csv' or 'pdf'.", status_code=400)
    builder = REPORT_BUILDERS.get(report_type)
    if builder is None:
        return Response(content="Unknown report type.", status_code=400)
    report_data = await builder()

    if REPORT_SENSITIVITY.get(report_type, "controlled") == "restricted":
        row_count = len(report_rows(report_type, report_data))
        confirmation, export_log = await admin_confirmation_service.request_export(
            current_user, report_type, date_range, "restricted", row_count, export_format
        )
        return JSONResponse(
            status_code=202,
            content=success_response(
                "Export pending second-reviewer approval.",
                {
                    "confirmation_id": str(confirmation.id),
                    "export_id": str(export_log.id),
                    "status": "pending_approval",
                },
            ),
        )

    content_bytes, file_name = await report_export_service.export_report(
        report_type, report_data, current_user, date_range, export_format
    )
    media_type = "application/pdf" if export_format == "pdf" else "text/csv"
    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/reports/export-log/history", summary="View the report export log")
async def get_export_log(
    report_type: str | None = None,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Return the append-only report export log (DOCX: "Report control and OPSEC/CUI audit")."""
    data = await report_export_service.list_export_log(report_type)
    return success_response("Export log loaded successfully.", data)


@router.get("/reports/export-log/search", summary="Real search across the report export log")
async def search_export_log(
    q: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Real case-insensitive substring search over title, resolved flight name, and report_type."""
    data = await report_export_service.search(q)
    return success_response("Search results loaded successfully.", data)


@router.get("/reports/export-log/{export_id}/download", summary="Download an approved/completed export as CSV or PDF")
async def download_export(
    export_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> Response:
    """Download an export whose log status is `completed` or `approved`, in its real recorded format.

    Re-runs the same report builder live rather than storing sensitive
    bytes at rest - matches how these reports already work as live queries,
    not point-in-time snapshots.
    """
    export_log = await ReportExport.get(export_id)
    if export_log is None:
        return Response(content="Export not found.", status_code=404)
    if export_log.export_log_status not in ("completed", "approved"):
        return Response(
            content=f"This export is '{export_log.export_log_status}' and is not downloadable.",
            status_code=403,
        )
    builder = REPORT_BUILDERS.get(export_log.report_type)
    if builder is None:
        return Response(content="Unknown report type.", status_code=400)
    report_data = await builder()
    content_bytes, _ = report_export_service.render(export_log.report_type, report_data, export_log.export_format)
    if export_log.file_size_bytes is None:
        export_log.file_size_bytes = len(content_bytes)
        await export_log.save()
    file_name = f"{export_log.report_type}_{export_log.date_range}.{export_log.export_format}"
    media_type = "application/pdf" if export_log.export_format == "pdf" else "text/csv"
    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.patch("/reports/export-log/{export_id}/lifecycle", summary="Set a real Leadership-facing report lifecycle status")
async def update_export_lifecycle(
    export_id: str,
    payload: ReportLifecycleUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
):
    """Explicitly transition to draft/ready/sent/archived/in_review. Audit logged.

    The only way to reach "sent"/"archived"/"draft" - "in_review"/"ready"
    are set automatically alongside the second-reviewer approval gate.
    """
    try:
        data = await report_export_service.set_lifecycle_status(export_id, payload.lifecycle_status)
    except ValueError as exc:
        return Response(content=str(exc), status_code=400)
    await audit_log_service.record(
        event_type="report_lifecycle_updated",
        actor_id=current_user.id,
        actor_role=current_user.role,
        target_entity_type="report_export",
        target_entity_id=export_id,
        summary_message=f"Report lifecycle set to '{payload.lifecycle_status}'.",
    )
    return success_response("Lifecycle status updated successfully.", data)


