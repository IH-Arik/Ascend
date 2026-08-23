"""Real scheduled/recurring export service (see `app/models/scheduled_export.py`).

Builders mirror `REPORT_BUILDERS` in `app/modules/admin/routes.py` -
duplicated rather than imported from there, since services should not
depend on a routes module (the reverse dependency is the normal direction).
Both dicts must stay in sync if a new report type is added.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.core.security import utc_now
from app.models.scheduled_export import CADENCES, ScheduledExport
from app.models.user import User
from app.schemas.scheduled_export import ScheduledExportCreate, ScheduledExportUpdate
from app.services.admin_confirmation_service import AdminConfirmationService
from app.services.audit_log_service import AuditLogService
from app.services.leadership_aggregate_service import LeadershipAggregateService
from app.services.oft_service import OFTService
from app.services.report_export_service import REPORT_SENSITIVITY, ReportExportService, report_rows
from app.services.reports_service import ReportsService

reports_service = ReportsService()
audit_log_service = AuditLogService()
oft_service = OFTService()
leadership_aggregate_service = LeadershipAggregateService()
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


_CADENCE_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


def _advance(dt: datetime, cadence: str) -> datetime:
    """Return the next real occurrence after `dt` for a given cadence."""
    if cadence == "weekly":
        return dt + timedelta(days=7)
    months = _CADENCE_MONTHS[cadence]
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


class ScheduledExportService:
    """Create, list, pause/resume, delete, and execute real scheduled exports."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.admin_confirmation_service = AdminConfirmationService()
        self.report_export_service = ReportExportService()

    async def create(self, admin: User, payload: ScheduledExportCreate) -> dict[str, Any]:
        """Create a real recurring export schedule. Audit logged."""
        if payload.report_type not in REPORT_BUILDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unknown report_type.", "allowed": list(REPORT_BUILDERS.keys())},
            )
        if payload.cadence not in CADENCES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unknown cadence.", "allowed": list(CADENCES)},
            )
        if payload.export_format not in ("csv", "pdf"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="export_format must be 'csv' or 'pdf'.")

        schedule = ScheduledExport(
            name=payload.name,
            report_type=payload.report_type,
            export_format=payload.export_format,
            cadence=payload.cadence,
            recipient_role=payload.recipient_role,
            sensitivity_level=REPORT_SENSITIVITY.get(payload.report_type, "controlled"),
            next_run_at=_advance(utc_now(), payload.cadence),
            created_by=admin.id,
        )
        await schedule.insert()

        await self.audit_log_service.record(
            event_type="scheduled_export_created",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="scheduled_export",
            target_entity_id=str(schedule.id),
            summary_message=f"Created recurring export '{payload.name}' ({payload.cadence}, {payload.report_type}).",
        )
        return self._serialize(schedule)

    async def list_all(self) -> dict[str, Any]:
        """Return every real scheduled export."""
        schedules = await ScheduledExport.find().to_list()
        schedules.sort(key=lambda s: s.next_run_at)
        return {"schedules": [self._serialize(s) for s in schedules]}

    async def update(self, admin: User, schedule_id: str, payload: ScheduledExportUpdate) -> dict[str, Any]:
        """Admin edits a real schedule - only the given fields change. Audit logged.

        `report_type` (and therefore `sensitivity_level`) is deliberately
        never editable here, matching the design's own Edit wizard.
        """
        schedule = await ScheduledExport.get(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")

        changes: dict[str, tuple[Any, Any]] = {}

        if payload.status is not None:
            if payload.status not in ("active", "paused"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status must be 'active' or 'paused'.")
            if payload.status != schedule.status:
                changes["status"] = (schedule.status, payload.status)
                schedule.status = payload.status

        if payload.name is not None and payload.name != schedule.name:
            changes["name"] = (schedule.name, payload.name)
            schedule.name = payload.name

        if payload.cadence is not None and payload.cadence != schedule.cadence:
            if payload.cadence not in CADENCES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Unknown cadence.", "allowed": list(CADENCES)},
                )
            changes["cadence"] = (schedule.cadence, payload.cadence)
            schedule.cadence = payload.cadence
            schedule.next_run_at = _advance(utc_now(), payload.cadence)

        if payload.export_format is not None and payload.export_format != schedule.export_format:
            if payload.export_format not in ("csv", "pdf"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="export_format must be 'csv' or 'pdf'.")
            changes["export_format"] = (schedule.export_format, payload.export_format)
            schedule.export_format = payload.export_format

        if payload.recipient_role is not None and payload.recipient_role != schedule.recipient_role:
            changes["recipient_role"] = (schedule.recipient_role, payload.recipient_role)
            schedule.recipient_role = payload.recipient_role

        if not changes:
            return self._serialize(schedule)

        schedule.updated_at = utc_now()
        await schedule.save()

        event_type = "scheduled_export_updated"
        if "status" in changes:
            event_type = "scheduled_export_paused" if schedule.status == "paused" else "scheduled_export_resumed"

        await self.audit_log_service.record(
            event_type=event_type,
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="scheduled_export",
            target_entity_id=str(schedule.id),
            summary_message=f"{schedule.name}: {', '.join(f'{k} {old} -> {new}' for k, (old, new) in changes.items())}.",
            metadata_payload={k: {"old": old, "new": new} for k, (old, new) in changes.items()},
        )
        return self._serialize(schedule)

    async def delete(self, admin: User, schedule_id: str) -> None:
        """Admin deletes a real schedule. Audit logged."""
        schedule = await ScheduledExport.get(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
        await schedule.delete()
        await self.audit_log_service.record(
            event_type="scheduled_export_deleted",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="scheduled_export",
            target_entity_id=schedule_id,
            summary_message=f"Deleted recurring export '{schedule.name}'.",
        )

    async def run_due_schedules(self) -> int:
        """Execute every real active schedule whose `next_run_at` has passed.

        Restricted report types route through the exact same real
        second-reviewer gate an on-demand export uses - never bypassed for
        a scheduled run. Returns the number of schedules executed.
        """
        now = datetime.now(timezone.utc)
        due = await ScheduledExport.find(
            ScheduledExport.status == "active", ScheduledExport.next_run_at <= now
        ).to_list()

        executed = 0
        for schedule in due:
            builder = REPORT_BUILDERS.get(schedule.report_type)
            if builder is None:
                continue
            report_data = await builder()
            creator = await User.get(schedule.created_by)
            if creator is None:
                continue

            if REPORT_SENSITIVITY.get(schedule.report_type, "controlled") == "restricted":
                row_count = len(report_rows(schedule.report_type, report_data))
                await self.admin_confirmation_service.request_export(
                    creator,
                    schedule.report_type,
                    "scheduled",
                    "restricted",
                    row_count,
                    schedule.export_format,
                    recipient_role=schedule.recipient_role,
                )
            else:
                await self.report_export_service.export_report(
                    schedule.report_type,
                    report_data,
                    creator,
                    "scheduled",
                    schedule.export_format,
                    recipient_role=schedule.recipient_role,
                )

            schedule.next_run_at = _advance(schedule.next_run_at, schedule.cadence)
            schedule.updated_at = utc_now()
            await schedule.save()
            executed += 1
        return executed

    def _serialize(self, schedule: ScheduledExport) -> dict[str, Any]:
        return {
            "id": str(schedule.id),
            "name": schedule.name,
            "report_type": schedule.report_type,
            "export_format": schedule.export_format,
            "cadence": schedule.cadence,
            "recipient_role": schedule.recipient_role,
            "sensitivity_level": schedule.sensitivity_level,
            "status": schedule.status,
            "next_run_at": schedule.next_run_at.isoformat(),
            "created_by": str(schedule.created_by),
        }
