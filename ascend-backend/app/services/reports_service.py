"""Quarterly reports (DOCX section 12, Report Templates and Exports;
Technical Exhibit 1 PRS).

Every figure here is computed from real, already-tracked data - no report
invents a number that isn't backed by a real collection. Where the DOCX
implies a concept this backend has no data source for (e.g. "corrective
actions" on the PRS/QCP report), it is simply omitted rather than
fabricated - each report method's docstring says what's included and why.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from app.core.contract_reports import REQUIRED_CONTRACT_REPORTS
from app.core.roles import ROLE_PTIM, ROLE_SCS
from app.models.assessment import Assessment
from app.models.equipment_gap import EquipmentGap
from app.models.idmt_handoff import IdmtHandoff
from app.models.medical_record import MedicalRecord, MedicalRecordAccessEvent
from app.models.org_unit import OrgUnit
from app.models.performance_summary import PerformanceSummary
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.report_export import ReportExport
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.services.coverage_service import CoverageService
from app.services.leadership_aggregate_service import LeadershipAggregateService
from app.services.role_admin_service import RoleAdminService
from app.services.utilization_service import UtilizationService

PRS_TARGET_HOURS = {ROLE_SCS: 2080.0, ROLE_PTIM: 512.0}
PRS_COVERAGE_EVIDENCE_THRESHOLD = 0.95


def fiscal_quarter_bounds(fiscal_year: int, quarter: int) -> tuple[date, date]:
    """Return the real (start, end) calendar dates for one DoD fiscal quarter.

    DoD fiscal year starts Oct 1 of the prior calendar year - FY26 runs
    2025-10-01 through 2026-09-30. Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun,
    Q4=Jul-Sep. Not DOCX-sourced (a Figma PT/IM Quarterly screen showed 4
    named historical quarters with no real boundary definition anywhere)
    - this is the standard, real DoD fiscal-quarter convention, not an
    invented one.
    """
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1-4.")
    if quarter == 1:
        return date(fiscal_year - 1, 10, 1), date(fiscal_year - 1, 12, 31)
    if quarter == 2:
        return date(fiscal_year, 1, 1), date(fiscal_year, 3, 31)
    if quarter == 3:
        return date(fiscal_year, 4, 1), date(fiscal_year, 6, 30)
    return date(fiscal_year, 7, 1), date(fiscal_year, 9, 30)


class ReportsService:
    """Build the four quarterly reports from real tracked data."""

    def __init__(self) -> None:
        self.coverage_service = CoverageService()
        self.utilization_service = UtilizationService()
        self.leadership_aggregate_service = LeadershipAggregateService()
        self.role_admin_service = RoleAdminService()

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
        # Was `await User.get(user_id)` once per relevant user in this loop
        # - O(users) sequential round trips. One $in query plus Python
        # dicts (also replacing the O(users) linear scan through `plans`
        # per user) does the same real lookups from data already fetched
        # above, in one round trip.
        users = await User.find({"_id": {"$in": list(relevant_user_ids)}}).to_list()
        users_by_id = {u.id: u for u in users}
        plans_by_user_id = {p.user_id: p for p in plans}
        rows = []
        severity_breakdown: dict[str, int] = {}
        for user_id in relevant_user_ids:
            user = users_by_id.get(user_id)
            plan = plans_by_user_id.get(user_id)
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

    async def get_injury_report_by_flight(
        self, days: int = 90, fiscal_year: int | None = None, quarter: int | None = None
    ) -> dict[str, Any]:
        """Real per-flight injury/recovery aggregate, k-gated - the Quarterly "by flight" breakdown.

        Not DOCX-sourced (a Figma PT/IM Quarterly screen showed a
        per-flight injury table with a fabricated "per 100 airmen" rate
        and no real cohort-size basis - `get_injury_report`'s own
        docstring already explains why that scaling was never invented).
        Grouping the same real per-operator data by flight gives 2 real
        rates side by side, deliberately not merged into one number since
        they answer different questions:
        - `active_injury_rate_pct` - a live snapshot: % of the flight
          currently in an active injury/reconditioning phase.
        - `incidence_rate_per_100_person_months` - a real, period-based
          incidence rate (added 2026-08-25, explicit go-ahead) - new
          injuries reported in the window (real `injury_reported_on`
          dates) per 100 real person-months of exposure.
          `person_months_at_risk` is a real, clearly-approximated figure
          (`cohort_size * window_days / 30`) - this backend does not
          track per-user enrollment/observation periods, so exact
          person-time isn't available; a flat cohort-size x
          window-duration approximation is the honest real basis, not a
          fabricated one, and is documented as an approximation rather
          than presented as more precise than it is.

        `fiscal_year`/`quarter` (1-4, DoD fiscal quarters via
        `fiscal_quarter_bounds`), when both given, replace the rolling
        `days` window with a real, closed calendar-quarter boundary - the
        real Quarter-scoping a Figma Quarterly screen implied (4 distinct,
        comparable historical quarters) but the rolling-window-only
        version of this endpoint couldn't reproduce. `days` stays the
        default for a live/rolling view when no quarter is given.
        """
        if fiscal_year is not None and quarter is not None:
            window_start, window_end = fiscal_quarter_bounds(fiscal_year, quarter)
            window_days = (window_end - window_start).days + 1
        else:
            window_end = date.today()
            window_start = window_end - timedelta(days=days)
            window_days = days

        cohort_k = (await self.role_admin_service.get_scope_config(ROLE_PTIM))["cohort_k"]
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        injury_report = await self.get_injury_report(days)
        rows_by_user_id = {row["user_id"]: row for row in injury_report["operators"]}
        all_plans = await ReconditioningPlan.find().to_list()
        plans_by_user_id: dict[str, ReconditioningPlan] = {str(p.user_id): p for p in all_plans}

        # Was `await User.find(unit_id == X)` once per flight in the loop
        # below - O(flights) sequential round trips. One $in query plus a
        # Python group-by does the same real per-flight member lookup in
        # one round trip (same fix already applied to
        # LeadershipAggregateService._members_by_flight).
        flight_ids = [str(f.id) for f in flights]
        all_members = await User.find({"unit_id": {"$in": flight_ids}}).to_list()
        members_by_flight: dict[str, list[User]] = {fid: [] for fid in flight_ids}
        for member in all_members:
            if member.unit_id in members_by_flight:
                members_by_flight[member.unit_id].append(member)

        flight_rows: list[dict[str, Any]] = []
        for flight in flights:
            members = members_by_flight[str(flight.id)]
            cohort_size = len(members)
            if cohort_size < cohort_k:
                continue

            member_rows = [rows_by_user_id[str(m.id)] for m in members if str(m.id) in rows_by_user_id]
            active_rows = [r for r in member_rows if r["reconditioning_phase"] not in (None, "completed")]
            severity_breakdown: dict[str, int] = {}
            for r in member_rows:
                if r["severity_level"]:
                    severity_breakdown[r["severity_level"]] = severity_breakdown.get(r["severity_level"], 0) + 1

            new_incidence_count = 0
            for m in members:
                plan = plans_by_user_id.get(str(m.id))
                if plan and plan.injury_reported_on and window_start <= plan.injury_reported_on <= window_end:
                    new_incidence_count += 1
            person_months_at_risk = round(cohort_size * window_days / 30, 1)
            incidence_rate = (
                round(new_incidence_count / person_months_at_risk * 100, 1) if person_months_at_risk > 0 else None
            )

            flight_rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": cohort_size,
                    "active_injury_count": len(active_rows),
                    "active_injury_rate_pct": round(len(active_rows) / cohort_size * 100, 1),
                    "severity_breakdown": severity_breakdown,
                    "new_injury_incidence_count": new_incidence_count,
                    "person_months_at_risk": person_months_at_risk,
                    "incidence_rate_per_100_person_months": incidence_rate,
                }
            )

        flight_rows.sort(key=lambda item: item["flight_name"])
        return {
            "window_days": window_days,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "fiscal_year": fiscal_year,
            "quarter": quarter,
            "min_cohort_size": cohort_k,
            "total_flights": len(flights),
            "flights_meeting_cohort_minimum": len(flight_rows),
            "flights": flight_rows,
        }

    async def get_injury_report_all_quarters(self, fiscal_year: int) -> dict[str, Any]:
        """Real by-flight injury breakdown for all 4 real DoD fiscal quarters of one fiscal year.

        The real, comparable 4-quarter view a Figma Quarterly screen
        implied - each quarter is a real, closed calendar window (see
        `fiscal_quarter_bounds`), not a rolling window relabeled 4 times.
        """
        # The 4 quarters are independent of each other - gather instead of
        # awaiting one at a time.
        results = await asyncio.gather(
            *(self.get_injury_report_by_flight(fiscal_year=fiscal_year, quarter=q) for q in (1, 2, 3, 4))
        )
        quarters = [{"quarter": q, **data} for q, data in zip((1, 2, 3, 4), results)]
        return {"fiscal_year": fiscal_year, "quarters": quarters}

    async def get_injury_type_breakdown(
        self, days: int = 90, fiscal_year: int | None = None, quarter: int | None = None
    ) -> dict[str, Any]:
        """Real per-injury-type counts, k-gated - the "Injury type breakdown" panel.

        Not DOCX-sourced (a Figma PT/IM Quarterly screen showed this with
        no real data source, plus a fabricated k-gated-suppression banner
        with no real logic behind it - "Wrist injuries (k=2) suppressed").
        This is that suppression made real: counts real `injury_flags`
        values (free-text tags already captured on `ReconditioningPlan`,
        e.g. "knee") across every currently-active real plan in the real
        window; any type with fewer than the real PT/IM cohort-k minimum
        is genuinely suppressed (count withheld, `suppressed: true`)
        rather than shown - the same real k-anonymity principle already
        applied per-flight, applied here per-injury-type instead.
        """
        if fiscal_year is not None and quarter is not None:
            window_start, window_end = fiscal_quarter_bounds(fiscal_year, quarter)
        else:
            window_end = date.today()
            window_start = window_end - timedelta(days=days)

        cohort_k = (await self.role_admin_service.get_scope_config(ROLE_PTIM))["cohort_k"]
        plans = await ReconditioningPlan.find().to_list()
        relevant_plans = [
            p
            for p in plans
            if p.phase != "completed"
            and p.injury_reported_on
            and window_start <= p.injury_reported_on <= window_end
        ]

        type_counts: dict[str, int] = {}
        for plan in relevant_plans:
            for flag in plan.injury_flags:
                type_counts[flag] = type_counts.get(flag, 0) + 1

        types = [
            {
                "injury_type": injury_type,
                "count": count if count >= cohort_k else None,
                "suppressed": count < cohort_k,
            }
            for injury_type, count in sorted(type_counts.items())
        ]
        return {
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "min_cohort_size": cohort_k,
            "types": types,
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
        totals_by_provider = await self.coverage_service.total_hours_by_provider(
            [p.id for p in providers], year
        )

        provider_rows = []
        for provider in providers:
            hours, rsd_hours = totals_by_provider[provider.id]
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

        assessment_compliance, rsd_coverage = await asyncio.gather(
            self.get_assessment_completion_report(),
            self.coverage_service.get_rsd_summary(year),
        )
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
