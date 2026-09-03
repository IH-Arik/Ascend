"""Provider-facing dashboards (DOCX section 11, Table 25: SCS/PT-IM/
Specialist/Leadership/Admin Dashboard).

Every field here is computed from real, already-tracked data reused from
services built earlier this session (`OFTService`, `ReconditioningService`,
`ReportsService`, `UtilizationService`, `CredentialService`) - no new
tracking model exists just for these dashboards. Where Table 25's "Must
Answer"/"Required Views" columns imply something this backend has no real
source for, it is left out rather than fabricated (documented per method).

The Specialist Dashboard is DOCX's single generic shape reused for all 3
optional pathways (Nutritionist/Mental Performance/Chaplain) - filtered by
the calling provider's own role, not 3 separate custom dashboards. This
works because pathway key and role value are identical strings for all 5
pathways (`app/core/support_pathways.py`), so `provider.role` doubles as
the pathway key directly.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

from app.core.recommendation_rules import COMPONENT_PRIORITY_ORDER
from app.core.security import utc_now
from app.core.roles import (
    ADMIN_ROLES,
    ROLE_CHAPLAIN,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_NUTRITIONIST,
    ROLE_PTIM,
    ROLE_SCS,
    SUPPORTED_ROLES,
)
from app.models.audit_log import AuditLog
from app.models.checkin_answer import CheckinAnswer
from app.models.deactivation_request import DeactivationRequest
from app.models.equipment_gap import EquipmentGap
from app.models.medical_record import MedicalRecord
from app.models.oft_record import OFTRecord
from app.models.onboarding_answer import OnboardingAnswer
from app.models.org_unit import OrgUnit
from app.models.recommendation import Recommendation
from app.models.report_export import ReportExport
from app.models.scheduler_job_run import SchedulerJobRun
from app.models.support_request import SupportRequest
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.services.admin_confirmation_service import AdminConfirmationService
from app.services.credential_service import CredentialService
from app.services.oft_service import OFTService
from app.services.reconditioning_service import ReconditioningService
from app.services.reports_service import ReportsService
from app.services.role_admin_service import RoleAdminService
from app.services.utilization_service import UtilizationService

LOW_OPS_THRESHOLD = 55.0
RECENT_WORKOUTS_WINDOW = 5
SYSTEM_HEALTH_WINDOW_DAYS = 30

SPECIALIST_COMPONENT_BY_ROLE = {
    ROLE_NUTRITIONIST: "Nutritional Readiness",
    ROLE_MENTAL_PERFORMANCE: "Mental Readiness",
    ROLE_CHAPLAIN: "Spiritual Readiness",
}

# DOCX Nutritionist role-scope text: "review meal consistency, skipped
# meals, hydration, quick/processed meal patterns, and related energy/
# recovery summaries." All 5 real question codes below are tagged
# `readiness_component: "Nutritional Readiness"` in the daily/weekly/
# monthly question banks. No question anywhere covers "quick/processed
# meal patterns" specifically (checked, zero matches across the question
# banks) - that DOCX phrase has no scored data behind it and is
# deliberately not approximated with a fabricated field.
NUTRITION_SIGNAL_QUESTION_CODES = ("d0_04", "w_03", "w_04", "m_03", "m_04")
NUTRITION_SIGNAL_WINDOW_DAYS = 60

# Mental Performance dashboard's real, question-mapped sub-drivers. DOCX
# doesn't define these as a named breakdown - built at the user's explicit
# go-ahead after mapping each label to real question codes. A 6th mock
# label, "Mood," was dropped: zero question anywhere (onboarding/daily/
# weekly/monthly) covers it, confirmed against the DOCX too (no mention),
# and it was deliberately not approximated with a duplicate of another
# driver's signal. "Sleep quality" and "Connection" are real, but pulled
# from the Sleep Readiness / Spiritual Readiness question sets respectively
# - the mock groups them into this one panel as cross-component
# psychological-support signals, not because they belong to the Mental
# Readiness component itself.
MENTAL_DRIVER_QUESTION_CODES: dict[str, tuple[str, ...]] = {
    "Stress mgmt": ("ob_08", "d0_05", "w_05", "m_05"),
    "Focus": ("ob_07", "d0_05", "w_06"),
    "Resilience": ("ob_09", "m_06"),
    "Sleep quality": ("d0_02", "d0_03", "w_09", "w_10", "m_09", "m_10"),
    "Connection": ("w_08", "m_08"),
}
MENTAL_DRIVER_WINDOW_DAYS = 28


class ProviderDashboardService:
    """Build the 5 provider-facing dashboards from real tracked data."""

    def __init__(self) -> None:
        self.oft_service = OFTService()
        self.reconditioning_service = ReconditioningService()
        self.reports_service = ReportsService()
        self.utilization_service = UtilizationService()
        self.credential_service = CredentialService()
        self.admin_confirmation_service = AdminConfirmationService()
        self.role_admin_service = RoleAdminService()

    async def get_scs_dashboard(self, provider: User) -> dict[str, Any]:
        """SCS Dashboard - who checked in, low OPS, missed workouts, referral/reconditioning need.

        Admin/Superadmin get the org-wide view across every SCS provider's
        assignments (there's no single "my assigned users" for an account
        that isn't actually an SCS); a real SCS sees only their own.

        Component-score fields are filtered by the calling provider's real,
        admin-set `visible_components` (`RoleScopeConfig` - see
        `RoleAdminService.get_scope_config`) - not DOCX-sourced, but a real
        enforced setting, not a stored value nobody reads.
        """
        is_admin_view = provider.role in ADMIN_ROLES
        user_ids = await self._assigned_user_ids(None if is_admin_view else provider.id, "SCS")
        scope_config = await self.role_admin_service.get_scope_config(provider.role)
        visible_components = scope_config["visible_components"]
        today = date.today()

        # Each user's row needs ~7 sequential DB round trips (User.get,
        # checkin lookup, recent workouts, OFT status, reconditioning,
        # active recommendation, PT/IM referral). Looping `await` one user
        # at a time turned this into O(users x 7) round trips - 52s for a
        # handful of operators on this network. Building all rows
        # concurrently via gather collapses that to ~7 round-trip *rounds*
        # total, run in parallel across users.
        maybe_rows = await asyncio.gather(
            *(self._build_scs_row(user_id, visible_components, today) for user_id in user_ids)
        )
        rows = [row for row in maybe_rows if row is not None]
        checked_in_count = sum(1 for row in rows if row["checked_in_today"])
        low_ops_count = sum(
            1
            for row in rows
            if row["current_ops_score"] is not None and row["current_ops_score"] < LOW_OPS_THRESHOLD
        )

        # Real caseload-snapshot aggregates (SCS Overview "Flight snapshot"
        # panel) - reuses the rows already built above (no extra per-user
        # round trips) plus one bulk OFTRecord query. No "+N this month"/
        # "+N since Mon" trend deltas are computed - no historical snapshot
        # of these counts is stored anywhere to diff against, so those
        # deltas from the old mock are dropped rather than fabricated.
        oft_cleared_today_count = await OFTRecord.find(
            {"user_id": {"$in": user_ids}, "test_date": today, "pass_fail": "pass"}
        ).count()
        reconditioning_awaiting_review_count = sum(
            1 for row in rows if row["ptim_clearance_status"] == "pending_review"
        )

        return {
            "assigned_count": len(rows),
            "checked_in_today_count": checked_in_count,
            "missed_checkin_today_count": len(rows) - checked_in_count,
            "low_ops_count": low_ops_count,
            "oft_cleared_today_count": oft_cleared_today_count,
            "reconditioning_awaiting_review_count": reconditioning_awaiting_review_count,
            "operators": rows,
        }

    async def _build_scs_row(
        self, user_id: Any, visible_components: list[str], today: date
    ) -> dict[str, Any] | None:
        """Build one SCS dashboard operator row - the per-user body of get_scs_dashboard's old loop."""
        user = await User.get(user_id)
        if user is None:
            return None

        checked_in_today, recent_workouts, oft_status, reconditioning, active_recommendation, ptim_referral = (
            await asyncio.gather(
                CheckinAnswer.find_one(
                    CheckinAnswer.user_id == user_id,
                    CheckinAnswer.cadence == "daily",
                    CheckinAnswer.checkin_date == today,
                ),
                self._recent_workouts(user_id),
                self.oft_service.get_status_for_user(user),
                self.reconditioning_service.get_for_user(user_id),
                self._active_recommendation(user_id),
                self._latest_request_status(user_id, "PT/IM"),
            )
        )
        checked_in_today = checked_in_today is not None

        return {
            "user_id": str(user_id),
            "user_name": user.full_name,
            "current_ops_score": user.current_ops_score,
            "current_ops_band": user.current_ops_band,
            "physical_readiness": (
                (user.current_component_scores or {}).get("Physical Readiness")
                if "Physical Readiness" in visible_components
                else None
            ),
            "sleep_readiness": (
                (user.current_component_scores or {}).get("Sleep Readiness")
                if "Sleep Readiness" in visible_components
                else None
            ),
            "checked_in_today": checked_in_today,
            "missed_workouts_recent": sum(1 for w in recent_workouts if w.completion_status == "missed"),
            "reported_limitation_recent": any(w.reported_limitation for w in recent_workouts),
            "oft_status": oft_status["current_status"],
            "reconditioning_active": reconditioning["available"],
            "ptim_clearance_status": reconditioning.get("ptim_clearance_status"),
            "active_risk_flag": active_recommendation.title if active_recommendation else None,
            # Real L0-L5 escalation level (DOCX Table 20,
            # `app/core/routing_levels.py`) already computed on the
            # active recommendation - `None` (L0/no flag) when there
            # isn't one. Not a fabricated per-component chip.
            "driver_flag": active_recommendation.route_level if active_recommendation else None,
            "ptim_referral_status": ptim_referral,
        }

    async def get_ptim_dashboard(self, provider: User) -> dict[str, Any]:
        """PT/IM Dashboard - injury/recovery concerns, limitations, return-to-performance, rehab needs.

        Admin/Superadmin get the org-wide view, same reasoning as the SCS
        dashboard above. No `visible_components` filtering here (unlike the
        SCS/Specialist dashboards) - this dashboard has no readiness
        component-score fields to filter in the first place.
        """
        is_admin_view = provider.role in ADMIN_ROLES
        user_ids = await self._assigned_user_ids(None if is_admin_view else provider.id, "PT/IM")
        # Same fix as get_scs_dashboard: each user's row needs 4 sequential
        # DB round trips (User.get, reconditioning lookup, recent workouts,
        # pending records) - looping `await` one user at a time turned this
        # into O(users x 4) round trips - 27.5s for 23 operators on this
        # network. Building all rows concurrently collapses that to ~4
        # round-trip *rounds* total, run in parallel across users.
        maybe_rows = await asyncio.gather(*(self._build_ptim_row(user_id) for user_id in user_ids))
        rows = [row for row in maybe_rows if row is not None]

        return {
            "assigned_count": len(rows),
            "active_reconditioning_count": sum(1 for r in rows if r["reconditioning_phase"] is not None),
            "pending_review_total": sum(r["pending_medical_record_reviews"] for r in rows),
            "operators": rows,
        }

    async def _build_ptim_row(self, user_id: Any) -> dict[str, Any] | None:
        """Build one PT/IM dashboard operator row - the per-user body of get_ptim_dashboard's old loop."""
        user = await User.get(user_id)
        if user is None:
            return None

        reconditioning, recent_workouts, pending_records = await asyncio.gather(
            self.reconditioning_service.get_for_user(user_id),
            self._recent_workouts(user_id),
            MedicalRecord.find(MedicalRecord.user_id == user_id, MedicalRecord.status == "pending").to_list(),
        )

        return {
            "user_id": str(user_id),
            "user_name": user.full_name,
            "reconditioning_phase": reconditioning.get("phase"),
            "ptim_clearance_status": reconditioning.get("ptim_clearance_status"),
            "injury_flags": reconditioning.get("injury_flags"),
            "next_review_date": reconditioning.get("next_review_date"),
            "reported_limitation_recent": any(w.reported_limitation for w in recent_workouts),
            "pending_medical_record_reviews": len(pending_records),
        }

    async def get_specialist_dashboard(self, provider: User) -> dict[str, Any]:
        """Specialist Dashboard - shared shape for Nutritionist/Mental Performance/Chaplain.

        `provider.role` doubles as the pathway key (identical strings by
        design in `support_pathways.py`), so this filters to whichever
        specialty the calling provider actually is.

        `relevant_component_score` is additionally gated by the provider's
        real, admin-set `visible_components` (`RoleScopeConfig`) - same
        real-enforcement pattern as the SCS dashboard.
        """
        pathway_key = provider.role
        component = SPECIALIST_COMPONENT_BY_ROLE.get(pathway_key)
        scope_config = await self.role_admin_service.get_scope_config(provider.role)
        if component and component not in scope_config["visible_components"]:
            component = None
        user_ids = await self._assigned_user_ids(provider.id, pathway_key)

        requests = await SupportRequest.find(SupportRequest.pathway_key == pathway_key).to_list()
        requests.sort(key=lambda r: r.created_at, reverse=True)

        today = date.today()
        # Same fix as get_scs_dashboard/get_ptim_dashboard: build every
        # user's row concurrently instead of awaiting each user's 2-3
        # sequential DB round trips one user at a time.
        maybe_rows = await asyncio.gather(
            *(
                self._build_specialist_row(user_id, pathway_key, component, requests, today)
                for user_id in user_ids
            )
        )
        rows = [row for row in maybe_rows if row is not None]

        return {
            "pathway_key": pathway_key,
            "relevant_readiness_component": component,
            "assigned_count": len(rows),
            "open_request_count": sum(1 for r in requests if r.status == "open"),
            # Real count over the provider's own already-visible caseload -
            # no k-anonymity concern (same access level they already have to
            # each individual's score). `None` for non-Nutrition pathways,
            # not fabricated for MP/Chaplain.
            "low_consistency_operator_count": (
                sum(
                    1
                    for r in rows
                    if r.get("nutrition_signals", {}).get("skipped_meals_or_low_hydration_flags_60d", 0) > 0
                )
                if pathway_key == ROLE_NUTRITIONIST
                else None
            ),
            "operators": rows,
            "recent_requests": [
                {
                    "id": str(r.id),
                    "user_id": str(r.user_id),
                    "status": r.status,
                    "message": r.message,
                    "created_at": r.created_at.isoformat(),
                }
                for r in requests[:10]
            ],
        }

    async def _build_specialist_row(
        self,
        user_id: Any,
        pathway_key: str,
        component: str | None,
        requests: list[SupportRequest],
        today: date,
    ) -> dict[str, Any] | None:
        """Build one specialist-dashboard operator row - the per-user body of get_specialist_dashboard's old loop."""
        user = await User.get(user_id)
        if user is None:
            return None

        if pathway_key == ROLE_NUTRITIONIST:
            active_recommendation, nutrition_signals = await asyncio.gather(
                self._active_recommendation(user_id, specialist_route=pathway_key),
                self._build_nutrition_signals(user_id, today),
            )
        else:
            active_recommendation = await self._active_recommendation(user_id, specialist_route=pathway_key)
            nutrition_signals = None

        user_requests = [r for r in requests if r.user_id == user_id]
        row: dict[str, Any] = {
            "user_id": str(user_id),
            "user_name": user.full_name,
            "relevant_component_score": (
                (user.current_component_scores or {}).get(component) if component else None
            ),
            "assigned_action_title": active_recommendation.title if active_recommendation else None,
            "latest_request_status": user_requests[0].status if user_requests else None,
        }
        if pathway_key == ROLE_NUTRITIONIST:
            row["nutrition_signals"] = nutrition_signals
        return row

    async def _build_nutrition_signals(self, user_id: Any, today: date) -> dict[str, Any]:
        """Real meal-consistency/hydration signals from `CheckinAnswer` (Nutritionist-only).

        Reuses the same real query-then-first-vs-last-delta pattern as
        `DashboardService._build_influences` (`d0_03` recovery trend),
        applied to `NUTRITION_SIGNAL_QUESTION_CODES` instead. No "quick/
        processed meal patterns" field - see the module-level constant's
        docstring for why.
        """
        cutoff = today - timedelta(days=NUTRITION_SIGNAL_WINDOW_DAYS)
        # Filtered in Python, not via a multi-value Mongo query - same
        # documented preference elsewhere in this codebase for keeping
        # Beanie query construction simple and predictable.
        all_answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user_id, CheckinAnswer.checkin_date >= cutoff
        ).to_list()
        answers = [a for a in all_answers if a.question_code in NUTRITION_SIGNAL_QUESTION_CODES]

        def trend_for(code: str) -> str | None:
            series = sorted((a for a in answers if a.question_code == code), key=lambda a: a.checkin_date)
            if len(series) < 2:
                return None
            delta = (series[-1].numeric_score_100 or 0) - (series[0].numeric_score_100 or 0)
            return "improving" if delta > 0 else "declining" if delta < 0 else "stable"

        flagged = [a for a in answers if a.raw_score_1_to_4 is not None and a.raw_score_1_to_4 <= 2]

        return {
            "meal_consistency_trend": trend_for("w_03") or trend_for("m_03"),
            "hydration_energy_trend": trend_for("w_04") or trend_for("d0_04"),
            "skipped_meals_or_low_hydration_flags_60d": len(flagged),
            "checkins_logged_60d": len({a.checkin_date for a in answers}),
        }

    async def get_mental_driver_scores(self, provider: User) -> dict[str, Any]:
        """Cohort-aggregate Mental Performance sub-driver scores.

        k-gated the same way as every other cohort aggregate in this
        codebase (`RoleAdminService.get_scope_config`'s real `cohort_k`) -
        genuinely suppressed below the real minimum, not just hidden
        cosmetically. See `MENTAL_DRIVER_QUESTION_CODES` for how each
        driver maps to real question codes.
        """
        is_admin_view = provider.role in ADMIN_ROLES
        user_ids = await self._assigned_user_ids(
            None if is_admin_view else provider.id, ROLE_MENTAL_PERFORMANCE
        )
        scope_config = await self.role_admin_service.get_scope_config(ROLE_MENTAL_PERFORMANCE)
        cohort_k = scope_config["cohort_k"]

        if len(user_ids) < cohort_k:
            return {
                "cohort_size": len(user_ids),
                "cohort_k": cohort_k,
                "window_days": MENTAL_DRIVER_WINDOW_DAYS,
                "suppressed": True,
                "drivers": None,
            }

        cutoff = date.today() - timedelta(days=MENTAL_DRIVER_WINDOW_DAYS)
        checkin_answers: list[Any] = []
        onboarding_answers: list[Any] = []
        for user_id in user_ids:
            checkin_answers.extend(
                await CheckinAnswer.find(
                    CheckinAnswer.user_id == user_id, CheckinAnswer.checkin_date >= cutoff
                ).to_list()
            )
            onboarding_answers.extend(
                await OnboardingAnswer.find(OnboardingAnswer.user_id == user_id).to_list()
            )
        scores_by_code: dict[str, list[float]] = {}
        for answer in (*checkin_answers, *onboarding_answers):
            if answer.scoreable and answer.numeric_score_100 is not None:
                scores_by_code.setdefault(answer.question_code, []).append(answer.numeric_score_100)

        drivers: dict[str, float | None] = {}
        for driver_name, codes in MENTAL_DRIVER_QUESTION_CODES.items():
            values = [v for code in codes for v in scores_by_code.get(code, [])]
            drivers[driver_name] = round(sum(values) / len(values), 1) if values else None

        return {
            "cohort_size": len(user_ids),
            "cohort_k": cohort_k,
            "window_days": MENTAL_DRIVER_WINDOW_DAYS,
            "suppressed": False,
            "drivers": drivers,
        }

    async def get_meal_consistency_by_flight(self, provider: User) -> dict[str, Any]:
        """Real, k-gated per-flight meal-consistency aggregate for the Nutritionist dashboard.

        Not DOCX-sourced (the Figma Nutritionist dashboard showed a "Meal
        consistency by flight" table with Acknowledged/Completed/Pending
        review/NS Signal columns implying an action-tracking system that
        doesn't exist - Nutritional Readiness recommendations route to SCS,
        not Nutritionist, confirmed intentional design, so there is no real
        per-flight "Nutrition Action" volume to report). Built instead from
        the real signal this backend actually has: each member's
        `_build_nutrition_signals` (meal-consistency/hydration flags),
        rolled up per flight. `consistency_level` is a real, disclosed
        classification of the real flagged-rate, not a fabricated metric -
        thresholds are this service's own choice, not DOCX-sourced.
        `pending_review_count` is a real count of open Nutritionist
        `SupportRequest`s from flight members, the closest real analogue to
        "pending review".
        """
        cohort_k = (await self.role_admin_service.get_scope_config(ROLE_NUTRITIONIST))["cohort_k"]
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        today = date.today()
        open_requests = await SupportRequest.find(
            SupportRequest.pathway_key == ROLE_NUTRITIONIST, SupportRequest.status == "open"
        ).to_list()
        requester_ids_pending = {r.user_id for r in open_requests}

        flight_rows: list[dict[str, Any]] = []
        for flight in flights:
            members = await User.find(User.unit_id == str(flight.id)).to_list()
            cohort_size = len(members)
            if cohort_size < cohort_k:
                continue

            flagged_members = 0
            for member in members:
                signals = await self._build_nutrition_signals(member.id, today)
                if signals["skipped_meals_or_low_hydration_flags_60d"] > 0:
                    flagged_members += 1
            flagged_rate_pct = round(flagged_members / cohort_size * 100, 1)
            consistency_level = (
                "High" if flagged_rate_pct < 20 else "Mixed" if flagged_rate_pct < 50 else "Lagging"
            )
            pending_review_count = sum(1 for m in members if m.id in requester_ids_pending)

            flight_rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": cohort_size,
                    "flagged_members": flagged_members,
                    "flagged_rate_pct": flagged_rate_pct,
                    "consistency_level": consistency_level,
                    "pending_review_count": pending_review_count,
                }
            )

        flight_rows.sort(key=lambda item: item["flight_name"])
        return {
            "window_days": NUTRITION_SIGNAL_WINDOW_DAYS,
            "min_cohort_size": cohort_k,
            "total_flights": len(flights),
            "flights_meeting_cohort_minimum": len(flight_rows),
            "flights": flight_rows,
        }

    async def get_leadership_dashboard(self) -> dict[str, Any]:
        """Leadership Dashboard - program usage, readiness gaps, assessment/OFT/utilization trends.

        Org-wide aggregate only, same k-anonymity-driven "never individual-
        level" principle as `DashboardService.get_unit_report` - Leadership
        is authorized for aggregate views, never a per-operator score list.
        """
        operators = await User.find(User.role == "Airman").to_list()
        ops_scores = [u.current_ops_score for u in operators if u.current_ops_score is not None]
        average_ops_score = round(sum(ops_scores) / len(ops_scores), 2) if ops_scores else None

        band_distribution: dict[str, int] = {}
        for u in operators:
            band = u.current_ops_band or "Unavailable"
            band_distribution[band] = band_distribution.get(band, 0) + 1

        component_averages: dict[str, float | None] = {}
        for component in COMPONENT_PRIORITY_ORDER:
            values = [
                (u.current_component_scores or {}).get(component)
                for u in operators
                if (u.current_component_scores or {}).get(component) is not None
            ]
            component_averages[component] = round(sum(values) / len(values), 2) if values else None

        oft_records = await OFTRecord.find().to_list()
        oft_status_counts: dict[str, int] = {}
        for record in oft_records:
            oft_status_counts[record.status] = oft_status_counts.get(record.status, 0) + 1

        support_by_pathway: dict[str, int] = {}
        for request in await SupportRequest.find().to_list():
            support_by_pathway[request.pathway_key] = support_by_pathway.get(request.pathway_key, 0) + 1

        utilization = await self.utilization_service.list_recent(90)
        assessment_completion = await self.reports_service.get_assessment_completion_report()
        recent_exports = await ReportExport.find().to_list()
        recent_exports.sort(key=lambda r: r.created_at, reverse=True)

        return {
            "enrolled_operator_count": len(operators),
            "average_ops_score": average_ops_score,
            "band_distribution": band_distribution,
            "component_averages": component_averages,
            "oft_status_counts": oft_status_counts,
            "support_requests_by_pathway": support_by_pathway,
            "utilization_event_count_90d": len(utilization["events"]),
            "assessment_completion": assessment_completion,
            "recent_report_exports": [
                {"report_type": r.report_type, "date_range": r.date_range, "created_at": r.created_at.isoformat()}
                for r in recent_exports[:5]
            ],
        }

    async def get_admin_dashboard(self) -> dict[str, Any]:
        """Admin Dashboard - accounts, roles, deactivation queue, compliance, export/audit logs.

        Also serves as the data source for the Admin/Superadmin "Control
        plane" Overview screen: `roles_configured`, `system_health`, and
        `pending_admin_confirmations` are not DOCX-sourced (see
        `app/models/pending_confirmation.py`) but are real, not fabricated.
        """
        users = await User.find().to_list()
        role_counts: dict[str, int] = {}
        for u in users:
            role_counts[u.role] = role_counts.get(u.role, 0) + 1

        # `pending_deactivation_count` is the older, unrelated self-service
        # `DeactivationRequest` queue (Airman-initiated). It is kept separate
        # from `pending_admin_confirmations` (the new second-reviewer queue
        # for provider/admin deactivations, admin-level role changes, and
        # restricted exports) - conflating the two would misrepresent what's
        # actually pending and why.
        pending_deactivations = await DeactivationRequest.find(
            DeactivationRequest.status == "pending"
        ).to_list()
        open_equipment_gaps = await EquipmentGap.find(EquipmentGap.status == "open").to_list()
        credentials = await self.credential_service.list_all()
        expiring_credentials = [c for c in credentials["credentials"] if c["status"] == "expiring_soon"]
        pending_medical_reviews = await MedicalRecord.find(MedicalRecord.status == "pending").to_list()

        # Sort/limit at the query level rather than loading the entire
        # collection into memory every call.
        recent_audit = (
            await AuditLog.find().sort(-AuditLog.created_at).limit(10).to_list()
        )
        recent_exports = (
            await ReportExport.find().sort(-ReportExport.created_at).limit(5).to_list()
        )

        pending_confirmations = await self.admin_confirmation_service.list_pending("pending")
        system_health = await self.get_system_health()
        access_expiration = self._access_expiration_summary(users)

        return {
            "total_accounts": len(users),
            "accounts_by_role": role_counts,
            "roles_configured": len(SUPPORTED_ROLES),
            "system_health": system_health,
            "access_expiration": access_expiration,
            "pending_deactivation_count": len(pending_deactivations),
            "pending_admin_confirmations": {
                "count": len(pending_confirmations["confirmations"]),
                "items": pending_confirmations["confirmations"],
            },
            "open_equipment_gap_count": len(open_equipment_gaps),
            "expiring_credential_count": len(expiring_credentials),
            "pending_medical_review_count": len(pending_medical_reviews),
            "recent_audit_log": [
                {
                    "event_type": a.event_type,
                    "actor_role": a.actor_role,
                    "summary_message": a.summary_message,
                    "created_at": a.created_at.isoformat(),
                }
                for a in recent_audit
            ],
            "recent_report_exports": [
                {"report_type": r.report_type, "generated_by": str(r.generated_by), "created_at": r.created_at.isoformat()}
                for r in recent_exports
            ],
        }

    async def get_system_health(self, window_days: int = SYSTEM_HEALTH_WINDOW_DAYS) -> dict[str, Any]:
        """Real scheduler job-run success rate - not DOCX-sourced, not fabricated.

        Returns `percentage=None` with an "insufficient_data" label until the
        daily scheduler job has actually run at least once, rather than
        inventing a number for a fresh install. Public (was `_system_health`)
        so the System-screen overview endpoint can reuse it directly instead
        of a second implementation.
        """
        cutoff = utc_now() - timedelta(days=window_days)
        runs = await SchedulerJobRun.find(SchedulerJobRun.started_at >= cutoff).to_list()
        if not runs:
            return {"percentage": None, "label": "insufficient_data", "window_days": window_days}
        success_count = sum(1 for r in runs if r.status == "success")
        percentage = round(success_count / len(runs) * 100, 2)
        label = "Healthy" if percentage >= 99 else "Degraded" if percentage >= 90 else "Unhealthy"
        return {"percentage": percentage, "label": label, "window_days": window_days}

    def _access_expiration_summary(self, users: list[User], expiring_soon_days: int = 30) -> dict[str, Any]:
        """Real `User.access_expires_at` counts - not DOCX-sourced (see `app/models/user.py`).

        Filters in Python over the already-fetched `users` list rather than
        a separate query with an inequality-vs-`None` filter, the same
        avoid-cute-query-tricks precedent used elsewhere in this codebase
        (e.g. `TeamService._find_active_provider`).
        """
        now = utc_now()
        soon_cutoff = now + timedelta(days=expiring_soon_days)
        with_expiry = [u for u in users if u.access_expires_at is not None]
        expired_count = sum(1 for u in with_expiry if u.access_expires_at < now)
        expiring_soon_count = sum(1 for u in with_expiry if now <= u.access_expires_at <= soon_cutoff)
        return {"expiring_soon_30d_count": expiring_soon_count, "expired_count": expired_count}

    async def _assigned_user_ids(self, provider_id: Any | None, pathway_key: str) -> list[Any]:
        """Return the user ids assigned to a provider for one pathway.

        `provider_id=None` returns every assignment for that pathway across
        all providers (the Admin/Superadmin org-wide view).
        """
        if provider_id is None:
            assignments = await TeamAssignment.find(TeamAssignment.pathway_key == pathway_key).to_list()
        else:
            assignments = await TeamAssignment.find(
                TeamAssignment.pathway_key == pathway_key, TeamAssignment.provider_user_id == provider_id
            ).to_list()
        return [a.user_id for a in assignments if a.provider_user_id is not None]

    async def _recent_workouts(self, user_id: Any) -> list[WorkoutLog]:
        """Return a user's most recent logged workouts (small, fixed window)."""
        records = await WorkoutLog.find(WorkoutLog.user_id == user_id).to_list()
        records.sort(key=lambda w: w.activity_date, reverse=True)
        return records[:RECENT_WORKOUTS_WINDOW]

    async def _active_recommendation(
        self, user_id: Any, specialist_route: str | None = None
    ) -> Recommendation | None:
        """Return a user's active recommendation, optionally filtered to one specialist route."""
        records = await Recommendation.find(
            Recommendation.user_id == user_id, Recommendation.status == "active"
        ).to_list()
        if specialist_route is not None:
            records = [r for r in records if r.specialist_route == specialist_route]
        return records[0] if records else None

    async def _latest_request_status(self, user_id: Any, pathway_key: str) -> str | None:
        """Return the status of a user's most recent support request to one pathway."""
        records = await SupportRequest.find(
            SupportRequest.user_id == user_id, SupportRequest.pathway_key == pathway_key
        ).to_list()
        if not records:
            return None
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[0].status
