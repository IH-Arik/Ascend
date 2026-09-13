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
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

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
from app.models.macro_target import MacroTarget
from app.models.meal_log import MealLog
from app.models.medical_record import MedicalRecord
from app.models.oft_record import OFTRecord
from app.models.onboarding_answer import OnboardingAnswer
from app.models.ops_snapshot import OpsSnapshot
from app.models.org_unit import OrgUnit
from app.models.recommendation import Recommendation
from app.models.report_export import ReportExport
from app.models.scheduler_job_run import SchedulerJobRun
from app.models.support_request import SupportRequest
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.models.workout_log import WorkoutLog
from app.services.admin_confirmation_service import AdminConfirmationService
from app.services.audit_log_service import AuditLogService
from app.services.credential_service import CredentialService
from app.services.medical_record_service import MedicalRecordService
from app.services.oft_service import OFTService
from app.services.profile_service import compute_age, compute_bmi
from app.services.reconditioning_service import ReconditioningService
from app.services.recommendation_service import RecommendationService
from app.services.reports_service import ReportsService
from app.services.restriction_service import RestrictionService
from app.services.role_admin_service import RoleAdminService
from app.services.specialist_note_service import SpecialistNoteService
from app.services.utilization_service import UtilizationService

# Recent-activity window on the SCS operator-detail panel - small and fixed,
# same reasoning as RECENT_WORKOUTS_WINDOW below (a detail panel, not a
# full audit browser).
OPERATOR_DETAIL_ACTIVITY_WINDOW = 7
OPERATOR_DETAIL_WORKOUTS_WINDOW = 7
# All 5 real component-score keys (`COMPONENT_PRIORITY_ORDER`) - the SCS
# operator-detail panel shows every one it's authorized to see (per the
# same real `visible_components` scope config `_build_scs_row` already
# enforces), not just the 2 the summary caseload row surfaces.
OPERATOR_DETAIL_COMPONENT_GATE_REASON = {
    "Mental Readiness": "MP-authorized pathway data - not visible to SCS until authorized.",
    "Spiritual Readiness": "Chaplain-consent pathway data - not visible to SCS until authorized.",
    "Nutritional Readiness": "Nutritionist-pathway data - not visible to SCS until authorized.",
}

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

# "Macro distribution · cohort" widget - real, not DOCX-sourced (see
# `get_cohort_macro_distribution` docstring). Window matches the old
# mock's own "last 7 days" framing; tolerance is this service's own
# choice, not DOCX-sourced.
MACRO_DISTRIBUTION_WINDOW_DAYS = 7
MACRO_ON_TARGET_TOLERANCE_PCT = 10.0

# "Hydration reminder" alert - real, not DOCX-sourced (see
# `get_hydration_alerts` docstring). Same 2 hydration-specific question
# codes already used for `hydration_energy_trend`, not the full
# NUTRITION_SIGNAL_QUESTION_CODES set (that also mixes in meal-consistency
# codes). Threshold/streak/window are this service's own choice, matching
# the old mock's own "below 60% adherence for 5+ days" framing.
HYDRATION_QUESTION_CODES = ("d0_04", "w_04")
HYDRATION_ALERT_WINDOW_DAYS = 14
HYDRATION_ALERT_THRESHOLD_PCT = 60.0
HYDRATION_ALERT_MIN_STREAK_DAYS = 5

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
        self.medical_record_service = MedicalRecordService()
        self.specialist_note_service = SpecialistNoteService()
        self.recommendation_service = RecommendationService()
        self.restriction_service = RestrictionService()
        self.audit_log_service = AuditLogService()

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

    async def get_scs_operator_detail(self, provider: User, user_id: str) -> dict[str, Any]:
        """One assigned operator's full real detail (SCS "Active Profile" drill-in).

        Reuses `_assigned_user_ids` for the same real "is this operator
        actually on this SCS's caseload" check `get_scs_dashboard` already
        enforces - an Admin/Superadmin may open any operator, a real SCS
        only their own assignment. Every section below is sourced from an
        existing real model/service already used elsewhere in this
        codebase; nothing here is a new tracked concept invented for this
        panel (see the old mock's fabricated fields this replaces:
        `docs/DASHBOARD-AUDIT.md`-adjacent SCS findings this session).
        """
        is_admin_view = provider.role in ADMIN_ROLES
        if not is_admin_view:
            assigned_ids = await self._assigned_user_ids(provider.id, "SCS")
            if user_id not in {str(uid) for uid in assigned_ids}:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This operator is not on your caseload.",
                )

        user = await User.get(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        scope_config = await self.role_admin_service.get_scope_config(provider.role if not is_admin_view else ROLE_SCS)
        visible_components = scope_config["visible_components"]
        today = date.today()

        component_scores: dict[str, dict[str, Any]] = {}
        for component in COMPONENT_PRIORITY_ORDER:
            visible = component in visible_components
            component_scores[component] = {
                "value": (user.current_component_scores or {}).get(component) if visible else None,
                "visible": visible,
                "gated_reason": None if visible else OPERATOR_DETAIL_COMPONENT_GATE_REASON.get(component),
            }

        (
            checked_in_today,
            recent_workouts,
            oft_status,
            reconditioning,
            restrictions,
            recommendations,
            recent_activity,
            ops_snapshots,
        ) = await asyncio.gather(
            CheckinAnswer.find_one(
                CheckinAnswer.user_id == user.id,
                CheckinAnswer.cadence == "daily",
                CheckinAnswer.checkin_date == today,
            ),
            WorkoutLog.find(WorkoutLog.user_id == user.id).to_list(),
            self.oft_service.get_status_for_user(user),
            self.reconditioning_service.get_timeline(user.id),
            self.restriction_service.list_for_user(user.id),
            self.recommendation_service.list_for_user(user.id),
            self.audit_log_service.list_for_target("user", str(user.id), limit=OPERATOR_DETAIL_ACTIVITY_WINDOW),
            OpsSnapshot.find(
                OpsSnapshot.user_id == user.id, OpsSnapshot.snapshot_date >= today - timedelta(days=28)
            ).to_list(),
        )
        recent_workouts.sort(key=lambda w: w.activity_date, reverse=True)
        recent_workouts = recent_workouts[:OPERATOR_DETAIL_WORKOUTS_WINDOW]
        ops_snapshots.sort(key=lambda s: s.snapshot_date)

        ptim_referral = await self._latest_request_status(user.id, "PT/IM")

        return {
            "user_id": str(user.id),
            "user_name": user.full_name,
            "current_ops_score": user.current_ops_score,
            "current_ops_band": user.current_ops_band,
            "checked_in_today": checked_in_today is not None,
            "oft": oft_status,
            "component_scores": component_scores,
            "reconditioning_timeline": reconditioning["events"],
            "restrictions": restrictions["restrictions"],
            "ptim_referral_status": ptim_referral,
            "recommendations": recommendations["recommendations"],
            "recent_activity": recent_activity,
            "ops_score_trend_28d": [
                {"date": s.snapshot_date.isoformat(), "ops_score": s.ops_score} for s in ops_snapshots
            ],
            "recent_workouts": [
                {
                    "activity_date": w.activity_date.isoformat(),
                    "activity_type": w.custom_title or w.activity_type,
                    "duration_minutes": w.duration_minutes,
                    "intensity": w.intensity,
                    "completion_status": w.completion_status,
                    "reported_limitation": w.reported_limitation,
                    "notes": w.notes,
                }
                for w in recent_workouts
            ],
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

        reconditioning, recent_workouts, pending_records, oft_status = await asyncio.gather(
            self.reconditioning_service.get_for_user(user_id),
            self._recent_workouts(user_id),
            MedicalRecord.find(MedicalRecord.user_id == user_id, MedicalRecord.status == "pending").to_list(),
            self.oft_service.get_status_for_user(user),
        )

        return {
            "user_id": str(user_id),
            "user_name": user.full_name,
            "rank_grade": user.rank_grade,
            "flight_name": await self._flight_name_for_user(user),
            "reconditioning_phase": reconditioning.get("phase"),
            "ptim_clearance_status": reconditioning.get("ptim_clearance_status"),
            "injury_flags": reconditioning.get("injury_flags"),
            "next_review_date": reconditioning.get("next_review_date"),
            "reported_limitation_recent": any(w.reported_limitation for w in recent_workouts),
            "pending_medical_record_reviews": len(pending_records),
            # Real fields the Injury Queue view needs - severity/days_out
            # already existed on the reconditioning plan but were never
            # returned by this row before; oft_status is the real per-user
            # OFTService summary (current_status + next_scheduled_date),
            # never a fabricated "HOLD"/"CLEARED <date>" label.
            "limitation_flag": reconditioning.get("limitation_flag"),
            "days_out": reconditioning.get("days_out"),
            "oft_status": oft_status,
            # Full pending-record detail (not just the count above) so the
            # PT/IM records tab can render a real caseload-wide review
            # queue - GET /records/uploads is self-scoped to the caller and
            # can never show this, see the route's own docstring.
            "pending_records": [
                self.medical_record_service._serialize_list_item(r) for r in pending_records
            ],
            # Real reconditioning-plan fields the row previously fetched
            # but never returned - the SCS/coordination tab needs these to
            # show real per-operator coordination status instead of the
            # self-scoped (and therefore always-empty-for-staff)
            # /recommendations/active endpoint it was calling before.
            "scs_coordination_status": reconditioning.get("scs_coordination_status"),
            "scs_coordination_label": reconditioning.get("scs_coordination_label"),
            "severity_level": reconditioning.get("severity_level"),
            "rehab_strategy_summary": reconditioning.get("rehab_strategy_summary"),
            "sessions_completed": reconditioning.get("sessions_completed"),
            "sessions_total": reconditioning.get("sessions_total"),
            # Real 4-field RTD gate (DOCX: "RTD requires source-authority +
            # decision date + verification + reevaluation/expiration") -
            # fetched but never returned by this row before, so the
            # dashboard could only ever show the SCS-owned RTP status.
            "rtd_source_authority": reconditioning.get("rtd_source_authority"),
            "rtd_decision_date": reconditioning.get("rtd_decision_date"),
            "rtd_verified": reconditioning.get("rtd_verified"),
            "rtd_reevaluation_date": reconditioning.get("rtd_reevaluation_date"),
            "rtd_cleared": reconditioning.get("rtd_cleared"),
        }

    async def _flight_name_for_user(self, user: User) -> str | None:
        """Real flight name for a user's `unit_id`, if it resolves to a flight."""
        if not user.unit_id:
            return None
        flight = await OrgUnit.get(user.unit_id)
        return flight.name if flight and flight.unit_type == "flight" else None

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
        # sequential DB round trips one user at a time. The caseload-wide
        # notes fetch is already itself batched ($in query, see
        # list_for_caseload), so it runs alongside the per-row gather
        # rather than inside it.
        maybe_rows, notes_data = await asyncio.gather(
            asyncio.gather(
                *(
                    self._build_specialist_row(user_id, pathway_key, component, requests, today)
                    for user_id in user_ids
                )
            ),
            self.specialist_note_service.list_for_caseload(provider, user_ids),
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
            # Real, caseload-wide specialist notes (pathway-siloed to the
            # caller) - see SpecialistNoteService.list_for_caseload.
            "notes": notes_data["notes"],
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

        mental_signals = None
        if pathway_key == ROLE_NUTRITIONIST:
            active_recommendation, nutrition_signals = await asyncio.gather(
                self._active_recommendation(user_id, specialist_route=pathway_key),
                self._build_nutrition_signals(user_id, today),
            )
        elif pathway_key == ROLE_MENTAL_PERFORMANCE:
            active_recommendation, mental_signals = await asyncio.gather(
                self._active_recommendation(user_id, specialist_route=pathway_key),
                self._build_mental_signals(user_id, today),
            )
            nutrition_signals = None
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
            # Real, self-reported biometric profile fields (see
            # `app/models/user.py`) - nutrition counseling's own core
            # inputs (BMI/weight), not clinical/injury data, so shown
            # directly here rather than gated through PerformanceSummary.
            # Null when the operator hasn't provided them yet - never guessed.
            row["age"] = compute_age(user.date_of_birth)
            row["sex"] = user.sex
            row["height_in"] = user.height_in
            row["weight_lb"] = user.weight_lb
            row["bmi"] = compute_bmi(user.height_in, user.weight_lb)
        elif pathway_key == ROLE_MENTAL_PERFORMANCE:
            row["mental_signals"] = mental_signals
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

    async def _build_mental_signals(self, user_id: Any, today: date) -> dict[str, Any]:
        """Real per-operator MP trend flag + check-in count (DOCX Section 11:
        "who was flagged by trends" / "relevant check-ins").

        Same real query-then-first-vs-last-delta pattern as
        `_build_nutrition_signals`, applied per-driver to
        `MENTAL_DRIVER_QUESTION_CODES` instead of a cohort aggregate -
        this dashboard already had the aggregate version
        (`get_mental_driver_scores`); this is the missing per-operator one.
        """
        cutoff = today - timedelta(days=MENTAL_DRIVER_WINDOW_DAYS)
        all_codes = {code for codes in MENTAL_DRIVER_QUESTION_CODES.values() for code in codes}
        answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user_id, CheckinAnswer.checkin_date >= cutoff
        ).to_list()
        answers = [a for a in answers if a.question_code in all_codes]

        declining_drivers: list[str] = []
        for driver, codes in MENTAL_DRIVER_QUESTION_CODES.items():
            series = sorted(
                (a for a in answers if a.question_code in codes), key=lambda a: a.checkin_date
            )
            if len(series) < 2:
                continue
            delta = (series[-1].numeric_score_100 or 0) - (series[0].numeric_score_100 or 0)
            if delta < 0:
                declining_drivers.append(driver)

        return {
            "declining_drivers": declining_drivers,
            "checkins_logged_28d": len({a.checkin_date for a in answers}),
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
        # Batched via single $in queries instead of the per-user loop this
        # used to run - same N+1 fix as get_scs_dashboard/get_ptim_dashboard
        # elsewhere in this file, just for a cohort aggregate instead of a
        # per-operator row.
        checkin_answers, onboarding_answers = await asyncio.gather(
            CheckinAnswer.find(
                {"user_id": {"$in": list(user_ids)}, "checkin_date": {"$gte": cutoff}}
            ).to_list(),
            OnboardingAnswer.find({"user_id": {"$in": list(user_ids)}}).to_list(),
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
        cutoff = today - timedelta(days=NUTRITION_SIGNAL_WINDOW_DAYS)
        open_requests = await SupportRequest.find(
            SupportRequest.pathway_key == ROLE_NUTRITIONIST, SupportRequest.status == "open"
        ).to_list()
        requester_ids_pending = {r.user_id for r in open_requests}

        # Batched via a single $in query instead of the per-flight
        # User.find(...) this used to run - same fix as
        # reports_service.get_injury_report_by_flight's member lookup.
        flight_ids = [str(f.id) for f in flights]
        all_members = await User.find({"unit_id": {"$in": flight_ids}}).to_list()
        members_by_flight: dict[str, list[User]] = {fid: [] for fid in flight_ids}
        for member in all_members:
            if member.unit_id in members_by_flight:
                members_by_flight[member.unit_id].append(member)

        # Batched via a single $in query instead of one CheckinAnswer.find
        # per member inside the per-flight loop - the worst N+1 (nested,
        # O(flights x members)) found in this codebase this session.
        all_answers = await CheckinAnswer.find(
            {"user_id": {"$in": [m.id for m in all_members]}, "checkin_date": {"$gte": cutoff}}
        ).to_list()
        flagged_counts_by_user: dict[Any, int] = {}
        for answer in all_answers:
            if (
                answer.question_code in NUTRITION_SIGNAL_QUESTION_CODES
                and answer.raw_score_1_to_4 is not None
                and answer.raw_score_1_to_4 <= 2
            ):
                flagged_counts_by_user[answer.user_id] = flagged_counts_by_user.get(answer.user_id, 0) + 1

        flight_rows: list[dict[str, Any]] = []
        for flight in flights:
            members = members_by_flight.get(str(flight.id), [])
            cohort_size = len(members)
            if cohort_size < cohort_k:
                continue

            flagged_members = sum(1 for m in members if flagged_counts_by_user.get(m.id, 0) > 0)
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

    async def get_hydration_alerts(self, provider: User) -> dict[str, Any]:
        """Real, k-gated "Hydration reminder" alerts for the Nutritionist dashboard.

        Not DOCX-sourced (the Figma mock showed a static "Hydration reminder
        - Bravo + Charlie flights... below 60% adherence for 5+ days" banner
        with an "Auto-message drafted" action with no real backing for
        either). Built on explicit user go-ahead:

        - "Adherence" for a real calendar day = the real fraction of that
          day's hydration check-in answers (`d0_04`/`w_04`) scoring >=3
          of 4, among flight members. Days with zero real check-ins that
          day are skipped (not counted as 0%), so a flight's silence never
          manufactures an alert.
        - "Streak" walks backward day-by-day from the most recent real
          data day, counting consecutive real days below threshold; a
          no-data day is skipped without breaking the streak, a
          `>= threshold` day breaks it.
        - No message is auto-sent - "auto-drafted" here means the response
          includes the flagged flight's real members (id + name) so the
          frontend can let the Nutritionist compose and send a real
          per-member message via the existing 1:1 messaging system
          (`Message`/`sendMessage`) - there is no flight-wide broadcast
          message concept in this backend, so this deliberately doesn't
          invent one. A flight's real roster can include members with no
          real messaging relationship to this Nutritionist (assigned to a
          different provider, or never opted into the Nutritionist
          pathway) - `messageable` on each member reflects the same real
          `TeamAssignment` gate `MessagingService._can_message` enforces,
          so the frontend never offers to send a message that would 403.
        """
        cohort_k = (await self.role_admin_service.get_scope_config(ROLE_NUTRITIONIST))["cohort_k"]
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        flight_ids = [str(f.id) for f in flights]
        all_members = await User.find({"unit_id": {"$in": flight_ids}}).to_list()
        members_by_flight: dict[str, list[User]] = {fid: [] for fid in flight_ids}
        for member in all_members:
            if member.unit_id in members_by_flight:
                members_by_flight[member.unit_id].append(member)

        assignment_links = await TeamAssignment.find(
            {
                "$or": [
                    {"user_id": {"$in": [m.id for m in all_members]}, "provider_user_id": provider.id},
                    {"user_id": provider.id, "provider_user_id": {"$in": [m.id for m in all_members]}},
                ],
                "status": {"$ne": "disabled"},
            }
        ).to_list()
        messageable_ids = {a.user_id for a in assignment_links} | {a.provider_user_id for a in assignment_links}
        messageable_ids.discard(provider.id)

        cutoff = date.today() - timedelta(days=HYDRATION_ALERT_WINDOW_DAYS)
        all_answers = await CheckinAnswer.find(
            {
                "user_id": {"$in": [m.id for m in all_members]},
                "question_code": {"$in": list(HYDRATION_QUESTION_CODES)},
                "checkin_date": {"$gte": cutoff},
                "raw_score_1_to_4": {"$ne": None},
            }
        ).to_list()
        answers_by_user = {}
        for answer in all_answers:
            answers_by_user.setdefault(answer.user_id, []).append(answer)

        alerts: list[dict[str, Any]] = []
        for flight in flights:
            members = members_by_flight.get(str(flight.id), [])
            if len(members) < cohort_k:
                continue

            by_date: dict[date, list[int]] = {}
            for member in members:
                for answer in answers_by_user.get(member.id, []):
                    by_date.setdefault(answer.checkin_date, []).append(answer.raw_score_1_to_4)

            if not by_date:
                continue

            streak_days = 0
            latest_adherence_pct: float | None = None
            for offset in range(HYDRATION_ALERT_WINDOW_DAYS):
                day = date.today() - timedelta(days=offset)
                scores = by_date.get(day)
                if not scores:
                    continue
                adherence_pct = round(sum(1 for s in scores if s >= 3) / len(scores) * 100, 1)
                if latest_adherence_pct is None:
                    latest_adherence_pct = adherence_pct
                if adherence_pct < HYDRATION_ALERT_THRESHOLD_PCT:
                    streak_days += 1
                else:
                    break

            if streak_days >= HYDRATION_ALERT_MIN_STREAK_DAYS:
                alerts.append(
                    {
                        "flight_id": str(flight.id),
                        "flight_name": flight.name,
                        "streak_days": streak_days,
                        "latest_adherence_pct": latest_adherence_pct,
                        "threshold_pct": HYDRATION_ALERT_THRESHOLD_PCT,
                        "members": [
                            {"id": str(m.id), "name": m.full_name, "messageable": m.id in messageable_ids}
                            for m in members
                        ],
                    }
                )

        alerts.sort(key=lambda a: a["streak_days"], reverse=True)
        return {
            "window_days": HYDRATION_ALERT_WINDOW_DAYS,
            "threshold_pct": HYDRATION_ALERT_THRESHOLD_PCT,
            "min_streak_days": HYDRATION_ALERT_MIN_STREAK_DAYS,
            "min_cohort_size": cohort_k,
            "alerts": alerts,
        }

    async def get_cohort_macro_distribution(self, provider: User) -> dict[str, Any]:
        """Real, k-gated cohort macro-split for the Nutritionist dashboard.

        Not DOCX-sourced (the Figma mock's "Macro distribution · cohort"
        donut compared logged macros against "prescribed targets" with no
        real target concept behind it). Built on explicit user go-ahead:
        `MacroTarget` is a new, real per-operator target a Nutritionist can
        set (`macro_target_service.set_target`), and the actual split below
        is computed from real `MealLog` entries, not fabricated. Members
        with no macro-complete meal logged in the window, or no target set,
        simply don't contribute to the corresponding part of the aggregate
        - never backfilled with a guessed value.
        """
        cohort_k = (await self.role_admin_service.get_scope_config(ROLE_NUTRITIONIST))["cohort_k"]
        user_ids = await self._assigned_user_ids(provider.id, ROLE_NUTRITIONIST)
        cohort_size = len(user_ids)
        if cohort_size < cohort_k:
            return {
                "window_days": MACRO_DISTRIBUTION_WINDOW_DAYS,
                "min_cohort_size": cohort_k,
                "cohort_size": cohort_size,
                "meets_cohort_minimum": False,
                "carbs_pct": None,
                "protein_pct": None,
                "fat_pct": None,
                "entries_with_macros": 0,
                "on_target_band_pct": None,
                "on_target_entries": 0,
                "entries_with_target": 0,
            }

        cutoff = datetime.now(timezone.utc) - timedelta(days=MACRO_DISTRIBUTION_WINDOW_DAYS)
        entries, targets = await asyncio.gather(
            MealLog.find({"user_id": {"$in": user_ids}, "meal_date": {"$gte": cutoff}}).to_list(),
            MacroTarget.find({"user_id": {"$in": user_ids}, "status": "active"}).to_list(),
        )
        targets_by_user = {t.user_id: t for t in targets}

        macro_complete = [e for e in entries if e.carbs_g is not None and e.protein_g is not None and e.fat_g is not None]

        carbs_kcal = sum(e.carbs_g * 4 for e in macro_complete)
        protein_kcal = sum(e.protein_g * 4 for e in macro_complete)
        fat_kcal = sum(e.fat_g * 9 for e in macro_complete)
        total_kcal = carbs_kcal + protein_kcal + fat_kcal

        carbs_pct = round(carbs_kcal / total_kcal * 100, 1) if total_kcal > 0 else None
        protein_pct = round(protein_kcal / total_kcal * 100, 1) if total_kcal > 0 else None
        fat_pct = round(fat_kcal / total_kcal * 100, 1) if total_kcal > 0 else None

        on_target_entries = 0
        entries_with_target = 0
        for e in macro_complete:
            target = targets_by_user.get(e.user_id)
            if target is None:
                continue
            entry_kcal = e.carbs_g * 4 + e.protein_g * 4 + e.fat_g * 9
            if entry_kcal <= 0:
                continue
            entries_with_target += 1
            entry_carbs_pct = e.carbs_g * 4 / entry_kcal * 100
            entry_protein_pct = e.protein_g * 4 / entry_kcal * 100
            entry_fat_pct = e.fat_g * 9 / entry_kcal * 100
            if (
                abs(entry_carbs_pct - target.carbs_pct) <= MACRO_ON_TARGET_TOLERANCE_PCT
                and abs(entry_protein_pct - target.protein_pct) <= MACRO_ON_TARGET_TOLERANCE_PCT
                and abs(entry_fat_pct - target.fat_pct) <= MACRO_ON_TARGET_TOLERANCE_PCT
            ):
                on_target_entries += 1

        on_target_band_pct = (
            round(on_target_entries / entries_with_target * 100, 1) if entries_with_target > 0 else None
        )

        return {
            "window_days": MACRO_DISTRIBUTION_WINDOW_DAYS,
            "min_cohort_size": cohort_k,
            "cohort_size": cohort_size,
            "meets_cohort_minimum": True,
            "carbs_pct": carbs_pct,
            "protein_pct": protein_pct,
            "fat_pct": fat_pct,
            "entries_with_macros": len(macro_complete),
            "on_target_band_pct": on_target_band_pct,
            "on_target_entries": on_target_entries,
            "entries_with_target": entries_with_target,
        }

    async def get_leadership_dashboard(self) -> dict[str, Any]:
        """Leadership Dashboard - program usage, readiness gaps, assessment/OFT/utilization trends.

        Org-wide aggregate only, same k-anonymity-driven "never individual-
        level" principle as `DashboardService.get_unit_report` - Leadership
        is authorized for aggregate views, never a per-operator score list.
        """
        # The 6 real reads below are independent of each other - previously
        # awaited one at a time, chaining 6 round trips on a slow connection.
        # Gathering them concurrently doesn't change what's queried, just
        # stops serializing independent work (same fix pattern already
        # applied to LeadershipAggregateService.get_aggregate_view).
        (
            operators,
            oft_records,
            support_requests,
            utilization,
            assessment_completion,
            recent_exports,
        ) = await asyncio.gather(
            User.find(User.role == "Airman").to_list(),
            OFTRecord.find().to_list(),
            SupportRequest.find().to_list(),
            self.utilization_service.list_recent(90),
            self.reports_service.get_assessment_completion_report(),
            ReportExport.find().to_list(),
        )

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

        oft_status_counts: dict[str, int] = {}
        for record in oft_records:
            oft_status_counts[record.status] = oft_status_counts.get(record.status, 0) + 1

        support_by_pathway: dict[str, int] = {}
        for request in support_requests:
            support_by_pathway[request.pathway_key] = support_by_pathway.get(request.pathway_key, 0) + 1

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
