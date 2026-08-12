"""Provider-facing dashboard routes (DOCX section 11, Table 25).

Deliberately a separate module/folder from `app/modules/dashboards/`
(plural - the end-user Home/Trends/Wellness-Report screens). Same API
router, different code folder, so the two concepts never get mixed in the
codebase even though both mount under the shared `/api/v1` prefix.
"""

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import (
    ADMIN_ROLES,
    ROLE_CHAPLAIN,
    ROLE_LEADERSHIP,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_NUTRITIONIST,
    ROLE_PTIM,
    ROLE_SCS,
)
from app.models.user import User
from app.schemas.briefing import BriefingCreateRequest, BriefingOutlineUpdateRequest
from app.schemas.leadership_annotation import LeadershipAnnotationCreate
from app.schemas.scheduled_export import ScheduledExportCreate
from app.services.briefing_service import BRIEFING_TEMPLATES, BriefingService
from app.services.coverage_service import CoverageService
from app.services.leadership_aggregate_service import LeadershipAggregateService
from app.services.leadership_annotation_service import LeadershipAnnotationService
from app.services.oft_service import OFTService
from app.services.provider_dashboard_service import ProviderDashboardService
from app.services.report_export_service import REPORT_TEMPLATES, ReportExportService
from app.services.reports_service import ReportsService
from app.services.scheduled_export_service import ScheduledExportService

router = APIRouter()
provider_dashboard_service = ProviderDashboardService()
leadership_aggregate_service = LeadershipAggregateService()
leadership_annotation_service = LeadershipAnnotationService()
reports_service = ReportsService()
coverage_service = CoverageService()
oft_service = OFTService()
report_export_service = ReportExportService()
scheduled_export_service = ScheduledExportService()
briefing_service = BriefingService()

PERIOD_TO_DAYS = {"7d": 7, "30d": 30, "3mo": 92, "6mo": 183, "12mo": 366}

SPECIALIST_ROLES = (ROLE_NUTRITIONIST, ROLE_MENTAL_PERFORMANCE, ROLE_CHAPLAIN)
LEADERSHIP_ROLES = (*ADMIN_ROLES, ROLE_LEADERSHIP)


@router.get("/scs", status_code=status.HTTP_200_OK)
async def get_scs_dashboard(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_SCS)),
) -> dict[str, Any]:
    """SCS Dashboard - assigned operators' check-in status, OPS, workouts, OFT, risk flags."""
    data = await provider_dashboard_service.get_scs_dashboard(current_user)
    return success_response("SCS dashboard loaded successfully.", data)


@router.get("/ptim", status_code=status.HTTP_200_OK)
async def get_ptim_dashboard(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_PTIM)),
) -> dict[str, Any]:
    """PT/IM Dashboard - injury/recovery, reconditioning, return-to-performance, rehab needs."""
    data = await provider_dashboard_service.get_ptim_dashboard(current_user)
    return success_response("PT/IM dashboard loaded successfully.", data)


@router.get("/specialist", status_code=status.HTTP_200_OK)
async def get_specialist_dashboard(
    current_user: User = Depends(require_roles(*SPECIALIST_ROLES)),
) -> dict[str, Any]:
    """Specialist Dashboard - shared shape for Nutritionist/Mental Performance/Chaplain."""
    data = await provider_dashboard_service.get_specialist_dashboard(current_user)
    return success_response("Specialist dashboard loaded successfully.", data)


@router.get("/leadership", status_code=status.HTTP_200_OK)
async def get_leadership_dashboard(
    current_user: User = Depends(require_roles(*ADMIN_ROLES, ROLE_LEADERSHIP)),
) -> dict[str, Any]:
    """Leadership Dashboard - org-wide aggregate OPS, utilization, OFT, assessment trends."""
    data = await provider_dashboard_service.get_leadership_dashboard()
    return success_response("Leadership dashboard loaded successfully.", data)


@router.get("/leadership/aggregate", status_code=status.HTTP_200_OK)
async def get_leadership_aggregate(
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Leadership workspace "Aggregate readiness" surface.

    Not DOCX-sourced (a Figma Leadership screen). Composes the real,
    k-anonymity-gated flight comparison/risk heatmap/monthly trend
    (`LeadershipAggregateService`) with the already-real PRS/QCP hours +
    assessment-target report, OFT leadership metrics + due-soon count, and
    the new real feedback-session/scheduled-hours aggregates.
    """
    today = date.today()
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    quarter_start = date(today.year, quarter_start_month, 1)

    aggregate = await leadership_aggregate_service.get_aggregate_view()
    prs_qcp = await reports_service.get_prs_qcp_report(year=today.year)
    feedback_sessions = await reports_service.get_feedback_session_summary(quarter_start, today)
    oft_metrics = await oft_service.get_leadership_metrics_report()
    oft_due_soon = await oft_service.get_due_soon_count(days=30)
    scs_hours = await coverage_service.get_schedule_vs_worked_summary(ROLE_SCS, today.year)
    ptim_hours = await coverage_service.get_schedule_vs_worked_summary(ROLE_PTIM, today.year)

    return success_response(
        "Leadership aggregate readiness loaded successfully.",
        {
            **aggregate,
            "assessment_targets": prs_qcp["assessment_compliance"],
            "feedback_sessions": feedback_sessions,
            "scs_hours_coverage": scs_hours,
            "ptim_hours_coverage": ptim_hours,
            "prs_providers": prs_qcp["providers"],
            "rsd_coverage": prs_qcp["rsd_coverage"],
            "oft_metrics": oft_metrics,
            "oft_due_soon_count": oft_due_soon,
        },
    )


@router.get("/leadership/trends", status_code=status.HTTP_200_OK)
async def get_leadership_trends(
    period: str = "12mo",
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Leadership workspace "Trends" surface.

    Not DOCX-sourced (a Figma Leadership screen). `period` in
    `7d/30d/3mo/6mo/12mo` drives the real day-or-month-granularity trend
    (`LeadershipAggregateService.get_period_trend`). Composes the real
    5-band distribution trend and real admin-authored annotations scoped
    to the same period window.
    """
    if period not in PERIOD_TO_DAYS:
        return success_response(
            "Unknown period.", {"allowed": list(PERIOD_TO_DAYS.keys())}
        )
    period_end = date.today()
    period_start = period_end - timedelta(days=PERIOD_TO_DAYS[period])

    trend = await leadership_aggregate_service.get_period_trend(period)
    band_distribution = await leadership_aggregate_service.get_band_distribution_trend()
    annotations = await leadership_annotation_service.list_for_period(period_start, period_end)

    return success_response(
        "Leadership trends loaded successfully.",
        {
            "trend": trend,
            "band_distribution": band_distribution,
            "annotations": annotations["annotations"],
        },
    )


@router.post("/leadership/annotations", status_code=status.HTTP_201_CREATED)
async def create_leadership_annotation(
    payload: LeadershipAnnotationCreate,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Author a real editorial annotation for the Leadership "Trends" timeline. Audit logged."""
    data = await leadership_annotation_service.create(current_user, payload)
    return success_response("Annotation created successfully.", data)


@router.delete("/leadership/annotations/{annotation_id}", status_code=status.HTTP_200_OK)
async def delete_leadership_annotation(
    annotation_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Delete a real editorial annotation (Admin/Superadmin-only). Audit logged."""
    await leadership_annotation_service.delete(annotation_id, current_user)
    return success_response("Annotation deleted successfully.", {})


@router.get("/leadership/reports", status_code=status.HTTP_200_OK)
async def get_leadership_reports(
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Leadership workspace "Reports" surface - recent reports + real schedules.

    Not DOCX-sourced (a Figma Leadership screen). Composes the real
    export log (`ReportExportService.list_export_log`) and real
    `ScheduledExport` schedules - no fabricated report rows.
    """
    recent = await report_export_service.list_export_log()
    schedules = await scheduled_export_service.list_all()
    return success_response(
        "Leadership reports loaded successfully.",
        {"recent_reports": recent["exports"][:6], "schedules": schedules["schedules"]},
    )


@router.get("/leadership/report-templates", status_code=status.HTTP_200_OK)
async def list_report_templates(
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Real minimal template registry - Wing Weekly/Monthly Cohort/Quarterly OFT/Annual Wing."""
    return success_response(
        "Report templates loaded successfully.",
        {"templates": [{"key": key, **config} for key, config in REPORT_TEMPLATES.items()]},
    )


@router.post("/leadership/report-templates/{template_key}/use", status_code=status.HTTP_201_CREATED)
async def use_report_template(
    template_key: str,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Real "Use" action - creates a real recurring `ScheduledExport` from a template's defaults.

    Reuses `ScheduledExportService.create` directly (same validation, same
    audit logging) rather than a parallel implementation.
    """
    template = REPORT_TEMPLATES.get(template_key)
    if template is None:
        return success_response("Unknown template.", {"allowed": list(REPORT_TEMPLATES.keys())})
    payload = ScheduledExportCreate(
        name=template["title"],
        report_type=template["report_type"],
        export_format=template["export_format"],
        cadence=template["cadence"],
    )
    data = await scheduled_export_service.create(current_user, payload)
    return success_response("Scheduled export created from template successfully.", data)


@router.get("/leadership/briefing-templates", status_code=status.HTTP_200_OK)
async def list_briefing_templates(
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Real minimal briefing-template registry - Mission Readiness/Recovery Rollout/Quarterly Wing Review."""
    return success_response(
        "Briefing templates loaded successfully.",
        {"templates": [{"key": key, **config} for key, config in BRIEFING_TEMPLATES.items()]},
    )


@router.post("/leadership/briefings", status_code=status.HTTP_201_CREATED)
async def create_briefing(
    payload: BriefingCreateRequest,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Create a real draft briefing from a template or a custom outline."""
    custom_outline = (
        [item.model_dump() for item in payload.custom_outline] if payload.custom_outline else None
    )
    data = await briefing_service.create(current_user, payload.title, payload.template_key, custom_outline)
    return success_response("Briefing created successfully.", data)


@router.get("/leadership/briefings", status_code=status.HTTP_200_OK)
async def list_briefings(
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Return every real briefing, newest first."""
    data = await briefing_service.list_all()
    return success_response("Briefings loaded successfully.", data)


@router.get("/leadership/briefings/{briefing_id}", status_code=status.HTTP_200_OK)
async def get_briefing(
    briefing_id: str,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Return a briefing - while draft, live-regenerates content from current real data."""
    data = await briefing_service.get(briefing_id)
    return success_response("Briefing loaded successfully.", data)


@router.patch("/leadership/briefings/{briefing_id}", status_code=status.HTTP_200_OK)
async def update_briefing_outline(
    briefing_id: str,
    payload: BriefingOutlineUpdateRequest,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Edit a draft briefing's outline (add/remove/reorder sections). Draft-only."""
    outline = [item.model_dump() for item in payload.outline]
    data = await briefing_service.update_outline(briefing_id, current_user, outline)
    return success_response("Briefing outline updated successfully.", data)


@router.post("/leadership/briefings/{briefing_id}/send", status_code=status.HTTP_200_OK)
async def send_briefing(
    briefing_id: str,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> dict[str, Any]:
    """Freeze the briefing's content at its final real state and mark it sent. Audit logged."""
    data = await briefing_service.send(briefing_id, current_user)
    return success_response("Briefing sent successfully.", data)


@router.get("/leadership/briefings/{briefing_id}/pdf")
async def download_briefing_pdf(
    briefing_id: str,
    current_user: User = Depends(require_roles(*LEADERSHIP_ROLES)),
) -> Response:
    """Return the briefing as a real prose PDF."""
    pdf_bytes = await briefing_service.render_pdf(briefing_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="briefing_{briefing_id}.pdf"'},
    )


@router.get("/admin", status_code=status.HTTP_200_OK)
async def get_admin_dashboard(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Admin Dashboard - accounts, roles, deactivation queue, compliance, audit/export logs."""
    data = await provider_dashboard_service.get_admin_dashboard()
    return success_response("Admin dashboard loaded successfully.", data)
