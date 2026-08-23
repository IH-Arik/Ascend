"""Quarterly reports (DOCX section 12, Report Templates and Exports;
Technical Exhibit 1 PRS).

Every figure here is computed from real, already-tracked data - no report
invents a number that isn't backed by a real collection. Where the DOCX
implies a concept this backend has no data source for (e.g. "corrective
actions" on the PRS/QCP report), it is simply omitted rather than
fabricated - each report method's docstring says what's included and why.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.contract_reports import REQUIRED_CONTRACT_REPORTS
from app.core.roles import ROLE_PTIM, ROLE_SCS
from app.models.assessment import Assessment
from app.models.equipment_gap import EquipmentGap
from app.models.idmt_handoff import IdmtHandoff
from app.models.medical_record import MedicalRecord, MedicalRecordAccessEvent
from app.models.performance_summary import PerformanceSummary
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.report_export import ReportExport
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.services.coverage_service import CoverageService
from app.services.leadership_aggregate_service import LeadershipAggregateService
from app.services.utilization_service import UtilizationService

PRS_TARGET_HOURS = {ROLE_SCS: 2080.0, ROLE_PTIM: 512.0}
PRS_COVERAGE_EVIDENCE_THRESHOLD = 0.95


class ReportsService:
    """Build the four quarterly reports from real tracked data."""

    def __init__(self) -> None:
        self.coverage_service = CoverageService()
        self.utilization_service = UtilizationService()
        self.leadership_aggregate_service = LeadershipAggregateService()

    async def get_required_contract_reports_status(self) -> dict[str, Any]:
        """The real 9 required contract reports (DOCX Table 26) + each one's real generation history.

        `last_generated_at`/`last_export_id` come from the most recent real
        `ReportExport` row for that `report_type` - `None` if it has never
        actually been generated. No due date, no named approver, no "CUI"
        label - see `app/core/contract_reports.py` for why those aren't
        reproduced here.
        """
        rows = []
        for entry in REQUIRED_CONTRACT_REPORTS:
            exports = await ReportExport.find(
                ReportExport.report_type == entry["report_type"]
            ).to_list()
            latest = max(exports, key=lambda e: e.created_at) if exports else None
            rows.append(
                {
                    **entry,
                    "last_generated_at": latest.created_at.isoformat() if latest else None,
                    "last_export_id": str(latest.id) if latest else None,
                    "last_export_status": latest.export_log_status if latest else None,
                    "ever_generated": latest is not None,
                }
            )
        return {
            "required_count": len(REQUIRED_CONTRACT_REPORTS),
            "generated_at_least_once_count": sum(1 for r in rows if r["ever_generated"]),
            "reports": rows,
        }

    async def get_injury_report(self, days: int = 90) -> dict[str, Any]:
        """Injury/Recovery Report: real reconditioning plans + limitation-flagged workouts.

        Sourced from `ReconditioningPlan` (injury flags, PT/IM clearance,
        phase, plus the real DOCX Section 8.4 fields added 2026-08-13:
        limitation_flag/rehab_strategy_summary/scs_coordination_status, and
        the net-new severity_level/days_out) and
        `WorkoutLog.reported_limitation` in the window.
        """
        cutoff = date.today() - timedelta(days=days)
        plans = await ReconditioningPlan.find().to_list()
        # Filter reported_limitation in Python, not `== True` in the query -
        # same documented Beanie boolean-equality gotcha noted in scheduler.py.
        recent_workouts = await WorkoutLog.find(WorkoutLog.activity_date >= cutoff).to_list()
        flagged_workouts = [w for w in recent_workouts if w.reported_limitation]

        workouts_by_user: dict[Any, int] = {}
        for workout in flagged_workouts:
            workouts_by_user[workout.user_id] = workouts_by_user.get(workout.user_id, 0) + 1

        relevant_user_ids = {p.user_id for p in plans} | set(workouts_by_user.keys())
        rows = []
        severity_breakdown: dict[str, int] = {}
        for user_id in relevant_user_ids:
            user = await User.get(user_id)
            plan = next((p for p in plans if p.user_id == user_id), None)
            days_out = (
                (date.today() - plan.injury_reported_on).days
                if plan and plan.injury_reported_on and plan.phase != "completed"
                else None
            )
            if plan and plan.severity_level:
                severity_breakdown[plan.severity_level] = severity_breakdown.get(plan.severity_level, 0) + 1
            rows.append(
                {
                    "user_id": str(user_id),
                    "user_name": user.full_name if user else None,
                    "reconditioning_phase": plan.phase if plan else None,
                    "ptim_clearance_status": plan.ptim_clearance_status if plan else None,
                    "injury_flags": plan.injury_flags if plan else [],
                    "limitation_flag": plan.limitation_flag if plan else False,
                    "rehab_strategy_summary": plan.rehab_strategy_summary if plan else None,
                    "scs_coordination_status": plan.scs_coordination_status if plan else None,
                    "severity_level": plan.severity_level if plan else None,
                    "days_out": days_out,
                    "limitation_flagged_workouts_in_window": workouts_by_user.get(user_id, 0),
                }
            )
        return {
            "window_days": days,
            "operator_count": len(rows),
            # Real per-severity counts of what's actually in the window - not
            # a fabricated per-100-airmen rate (no DOCX or real cohort-size
            # basis exists for that), matching the DOCX's own "unresolved
            # issues" framing for this report.
            "severity_breakdown": severity_breakdown,
            "operators": rows,
        }

    async def get_assessment_completion_report(self) -> dict[str, Any]:
        """Assessment Completion Report: real initial-assessment completion rates.

        Cohorts by time since account creation (<=6 months, <=12 months),
        against the DOCX's 50%-by-6-months / 90%-by-12-months targets.
        Feedback-session completion is a separate real aggregate -
        `get_feedback_session_summary` - not merged into this report.
        """
        operators = await User.find(User.role == "Airman").to_list()
        assessments = await Assessment.find(Assessment.assessment_type == "initial").to_list()
        assessment_by_user = {a.user_id: a for a in assessments}

        today = date.today()
        six_months_ago = today - timedelta(days=182)
        twelve_months_ago = today - timedelta(days=365)

        cohort_6mo = [u for u in operators if u.created_at.date() <= six_months_ago]
        cohort_12mo = [u for u in operators if u.created_at.date() <= twelve_months_ago]

        def completion_rate(cohort: list[User]) -> float | None:
            if not cohort:
                return None
            completed = sum(
                1 for u in cohort if assessment_by_user.get(u.id) and assessment_by_user[u.id].status == "completed"
            )
            return round(completed / len(cohort) * 100, 1)

        return {
            "total_operators": len(operators),
            "eligible_6_month_cohort_size": len(cohort_6mo),
            "eligible_6_month_completion_pct": completion_rate(cohort_6mo),
            "eligible_6_month_target_pct": 50.0,
            "eligible_12_month_cohort_size": len(cohort_12mo),
            "eligible_12_month_completion_pct": completion_rate(cohort_12mo),
            "eligible_12_month_target_pct": 90.0,
        }

    async def get_feedback_session_summary(self, period_start: date, period_end: date) -> dict[str, Any]:
        """Real feedback-session completion aggregate for a real date period.

        Not DOCX-sourced (a Figma Leadership "Aggregate readiness" screen
        triggered this). Scoped to `Assessment.completed_date` within the
        period - a feedback session is a follow-up to a completed
        assessment, so an assessment that never completed can't have one.
        `feedback_session_status` is a real per-record field
        (`app/schemas/assessment.py`: offered/completed/declined/pending)
        that already existed but was never aggregated across users before.
        """
        assessments = await Assessment.find().to_list()
        in_period = [
            a for a in assessments if a.completed_date is not None and period_start <= a.completed_date <= period_end
        ]
        completed_count = sum(1 for a in in_period if a.feedback_session_status == "completed")
        total = len(in_period)

        return {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "total_assessments_in_period": total,
            "feedback_sessions_completed": completed_count,
            "completion_pct": round(completed_count / total * 100, 1) if total else None,
        }

    async def get_utilization_report(self, days: int = 90) -> dict[str, Any]:
        """Utilization Report: real UtilizationEvent data over the window."""
        data = await self.utilization_service.list_recent(days)
        events = data["events"]
        by_type: dict[str, int] = {}
        total_attendance = 0
        actual_use_count = 0
        for event in events:
            by_type[event["event_type"]] = by_type.get(event["event_type"], 0) + 1
            total_attendance += event["attendance_count"]
            if event["actual_use"]:
                actual_use_count += 1

        return {
            "window_days": days,
            "total_events": len(events),
            "by_event_type": by_type,
            "total_attendance": total_attendance,
            "actual_use_count": actual_use_count,
            "events": events,
        }

    async def get_prs_qcp_report(self, year: int | None = None) -> dict[str, Any]:
        """PRS/QCP Support Report: real coverage hours vs the DOCX's fixed annual targets.

        SCS target 2,080 annual hours, PT/IM target 512 annual hours, both
        against a 95% coverage-evidence threshold. Also includes the
        assessment-completion rate from `get_assessment_completion_report`.
        Does not include "corrective actions" or "issue categories" - not
        tracked anywhere in this backend. `rsd_coverage` is real (DOCX line
        239: "Track RSD weekend support coverage separately from normal
        operating hours") - `CoverageLog.is_weekend_rsd` has always
        captured this, it just wasn't surfaced separately until now.
        """
        year = year or date.today().year
        providers = await User.find().to_list()
        providers = [u for u in providers if u.role in PRS_TARGET_HOURS]

        provider_rows = []
        for provider in providers:
            hours = await self.coverage_service.total_hours_for_provider(provider.id, year)
            rsd_hours = await self.coverage_service.total_rsd_hours_for_provider(provider.id, year)
            target = PRS_TARGET_HOURS[provider.role]
            coverage_pct = round(hours / target * 100, 1) if target else 0.0
            provider_rows.append(
                {
                    "provider_id": str(provider.id),
                    "provider_name": provider.full_name,
                    "role": provider.role,
                    "logged_hours": hours,
                    "rsd_hours": rsd_hours,
                    "target_hours": target,
                    "coverage_pct": coverage_pct,
                    "meets_95pct_evidence": coverage_pct >= PRS_COVERAGE_EVIDENCE_THRESHOLD * 100,
                }
            )

        assessment_compliance = await self.get_assessment_completion_report()
        rsd_coverage = await self.coverage_service.get_rsd_summary(year)
        return {
            "year": year,
            "providers": provider_rows,
            "assessment_compliance": assessment_compliance,
            "rsd_coverage": rsd_coverage,
        }

    async def get_leadership_aggregate_readiness_report(self) -> dict[str, Any]:
        """Leadership Aggregate Readiness Report (DOCX Table 26, report #6).

        Required Sections per DOCX: "Aggregate OPS, readiness component
        trends, HPO/H2F component trends, support category usage,
        reconditioning status, utilization summary, equipment gaps,
        recommendations." A real composite, not the pre-existing
        `wing_weekly_ops`/`monthly_cohort_review`/`annual_wing_readiness`
        (all 3 explicitly "not DOCX-sourced", each narrower than this list)
        - built 2026-08-23 while realigning the report catalog against
        DOCX's actual 9-report list. "Recommendations" is omitted: no real
        aggregate/org-wide recommendation-summary data source exists in
        this backend (`Recommendation` is per-operator, not aggregable
        into a leadership-facing summary anywhere else either).
        """
        ops_trend = await self.leadership_aggregate_service.get_period_trend("30d")

        plans = await ReconditioningPlan.find().to_list()
        by_phase: dict[str, int] = {}
        for plan in plans:
            by_phase[plan.phase] = by_phase.get(plan.phase, 0) + 1

        utilization = await self.get_utilization_report()

        open_gaps = await EquipmentGap.find(EquipmentGap.status == "open").to_list()
        by_priority: dict[str, int] = {}
        for gap in open_gaps:
            by_priority[gap.priority] = by_priority.get(gap.priority, 0) + 1

        return {
            "ops_trend": ops_trend,
            "reconditioning_status": {"active_count": len(plans), "by_phase": by_phase},
            "utilization_summary": {
                "total_events": utilization["total_events"],
                "actual_use_count": utilization["actual_use_count"],
            },
            "equipment_gaps": {"open_count": len(open_gaps), "by_priority": by_priority},
        }

    async def get_idmt_handoff_summary_report(self, days: int = 90) -> dict[str, Any]:
        """IDMT Documentation Handoff Summary (DOCX Table 26, report #7).

        Required Sections per DOCX: "Operator identifier as approved; export
        type; prepared by; recipient role; date prepared/transmitted;
        acknowledgement status; content category." All real `IdmtHandoff`
        fields - never the underlying record content (this model never
        stores raw medical-record bytes, see `app/models/idmt_handoff.py`).
        """
        cutoff = date.today() - timedelta(days=days)
        handoffs = await IdmtHandoff.find(IdmtHandoff.created_at >= cutoff).to_list()

        rows = []
        by_status: dict[str, int] = {}
        for handoff in handoffs:
            user = await User.get(handoff.user_id)
            preparer = await User.get(handoff.prepared_by)
            by_status[handoff.status] = by_status.get(handoff.status, 0) + 1
            rows.append(
                {
                    "user_id": str(handoff.user_id),
                    "user_name": user.full_name if user else None,
                    "export_type": handoff.export_type,
                    "content_category": handoff.content_category,
                    "prepared_by_role": preparer.role if preparer else None,
                    "recipient_role": handoff.recipient_role,
                    "status": handoff.status,
                    "prepared_date": handoff.prepared_date.isoformat(),
                    "transmitted_date": handoff.transmitted_date.isoformat() if handoff.transmitted_date else None,
                    "acknowledgement_status": handoff.acknowledgement_status,
                }
            )
        return {
            "window_days": days,
            "handoff_count": len(rows),
            "by_status": by_status,
            "handoffs": rows,
        }

    async def get_medical_records_audit_report(self, days: int = 90) -> dict[str, Any]:
        """Medical Records Upload and Access Audit Report (DOCX Table 26, report #8).

        Required Sections per DOCX: "Date range; documents uploaded;
        document types; review status; access events; exports/downloads;
        recipient roles; unresolved review items; retention/disposition
        status; anomalies or unauthorized-access flags." Everything here is
        real except the last one - this backend tracks no anomaly/
        unauthorized-access detection, so it is simply omitted rather than
        fabricated, same "omit what isn't tracked" precedent as the other
        reports in this file.
        """
        cutoff = date.today() - timedelta(days=days)
        records = await MedicalRecord.find(MedicalRecord.uploaded_at >= cutoff).to_list()
        record_ids = [r.id for r in records]
        events = (
            await MedicalRecordAccessEvent.find({"record_id": {"$in": record_ids}}).to_list()
            if record_ids
            else []
        )

        by_document_type: dict[str, int] = {}
        by_review_status: dict[str, int] = {}
        for record in records:
            by_document_type[record.document_type] = by_document_type.get(record.document_type, 0) + 1
            by_review_status[record.status] = by_review_status.get(record.status, 0) + 1

        return {
            "window_days": days,
            "documents_uploaded": len(records),
            "by_document_type": by_document_type,
            "by_review_status": by_review_status,
            "unresolved_review_count": by_review_status.get("pending", 0),
            "access_event_count": len(events),
            "view_count": sum(1 for e in events if e.action == "view_record"),
            "download_count": sum(1 for e in events if e.action == "download"),
            "recipient_roles": sorted({e.actor_role for e in events}),
            "retention_expiring_30d_count": sum(
                1
                for r in records
                if r.access_expires_at and 0 <= (r.access_expires_at.date() - date.today()).days <= 30
            ),
        }

    async def get_performance_summary_export_report(self, days: int = 90) -> dict[str, Any]:
        """Medical History Performance Summary Export (DOCX Table 26, report #9).

        Required Sections per DOCX: "Minimum-necessary performance
        implications from uploaded medical history; approved limitations;
        return-to-performance considerations; reconditioning considerations;
        specialist visibility level; reviewer name/role; review date." Row-
        level content fields are deliberately omitted here (this is a
        contract-compliance rollup, not a clinical viewer) - only the real
        `approved_visibility_level` and metadata, matching the DOCX phrase
        "minimum-necessary" that the field-scoping in
        `PerformanceSummaryService` already enforces elsewhere.
        """
        cutoff = date.today() - timedelta(days=days)
        summaries = await PerformanceSummary.find(PerformanceSummary.review_date >= cutoff).to_list()

        by_visibility: dict[str, int] = {}
        rows = []
        for summary in summaries:
            by_visibility[summary.approved_visibility_level] = (
                by_visibility.get(summary.approved_visibility_level, 0) + 1
            )
            rows.append(
                {
                    "user_id": str(summary.user_id),
                    "reviewer_role": summary.reviewer_role,
                    "review_date": summary.review_date.isoformat(),
                    "approved_visibility_level": summary.approved_visibility_level,
                    "expiration_or_review_due_date": (
                        summary.expiration_or_review_due_date.isoformat()
                        if summary.expiration_or_review_due_date
                        else None
                    ),
                }
            )
        return {
            "window_days": days,
            "summary_count": len(rows),
            "by_visibility_level": by_visibility,
            "summaries": rows,
        }
