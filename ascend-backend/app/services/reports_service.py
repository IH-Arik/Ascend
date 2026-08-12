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

from app.core.roles import ROLE_PTIM, ROLE_SCS
from app.models.assessment import Assessment
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.services.coverage_service import CoverageService
from app.services.utilization_service import UtilizationService

PRS_TARGET_HOURS = {ROLE_SCS: 2080.0, ROLE_PTIM: 512.0}
PRS_COVERAGE_EVIDENCE_THRESHOLD = 0.95


class ReportsService:
    """Build the four quarterly reports from real tracked data."""

    def __init__(self) -> None:
        self.coverage_service = CoverageService()
        self.utilization_service = UtilizationService()

    async def get_injury_report(self, days: int = 90) -> dict[str, Any]:
        """Injury/Recovery Report: real reconditioning plans + limitation-flagged workouts.

        Sourced from `ReconditioningPlan` (injury flags, PT/IM clearance,
        phase) and `WorkoutLog.reported_limitation` in the window. Does not
        include free-text "rehab strategy summaries" - that content lives in
        provider notes/messaging, which this report does not aggregate.
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
        for user_id in relevant_user_ids:
            user = await User.get(user_id)
            plan = next((p for p in plans if p.user_id == user_id), None)
            rows.append(
                {
                    "user_id": str(user_id),
                    "user_name": user.full_name if user else None,
                    "reconditioning_phase": plan.phase if plan else None,
                    "ptim_clearance_status": plan.ptim_clearance_status if plan else None,
                    "injury_flags": plan.injury_flags if plan else [],
                    "limitation_flagged_workouts_in_window": workouts_by_user.get(user_id, 0),
                }
            )
        return {"window_days": days, "operator_count": len(rows), "operators": rows}

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
