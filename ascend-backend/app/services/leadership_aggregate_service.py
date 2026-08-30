"""Leadership workspace "Aggregate readiness" surface (2026-08-10).

Not DOCX-sourced (a Figma Leadership screen triggered this - the DOCX only
says Leadership gets aggregate-only views by default, line 100/200). Real
per-flight breakdown reuses the existing, already-real mechanism instead of
adding a new field: `OrgUnit.unit_type == "flight"` already exists
(`app/models/org_unit.py`), and that file's own docstring already states
the intended design - `User.unit_id` (a free-text string) resolves to a
real org unit "when it happens to match a real `OrgUnit.id`". Assigning a
user to a real flight is already possible today via the existing
`PATCH /admin/users/{id}/unit` (`admin_user_service.py`) - nothing new
needed there, only the aggregation itself.

k-anonymity gating reuses the exact same real source
`DashboardService.get_unit_report` already uses for its own cohort gate -
`RoleAdminService.get_scope_config(ROLE_LEADERSHIP)["cohort_k"]` - not a
second, disconnected threshold.

Score-band labels reuse the real DOCX bands (`app/core/scoring.py`'s
`build_score_band`) - Ready/Monitor/Caution/Action Needed/High Priority -
never a second, invented label system.

`confidence` tiers on the by-flight comparison are a new, explicitly-stated
rule (not DOCX-sourced): "High" if a flight's real cohort is at least 2x
the real k minimum, else "Medium" - stated here plainly rather than implied
as DOCX-backed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.core.recommendation_rules import COMPONENT_PRIORITY_ORDER
from app.core.roles import ROLE_AIRMAN, ROLE_LEADERSHIP
from app.core.scoring import build_score_band
from app.models.ops_snapshot import OpsSnapshot
from app.models.org_unit import OrgUnit
from app.models.reconditioning_plan import ReconditioningPlan
from app.models.user import User
from app.schemas.reconditioning import PHASE_LABELS, PHASES
from app.services.role_admin_service import RoleAdminService

# Real, explicitly-stated rule (not DOCX-sourced) - see module docstring.
HIGH_CONFIDENCE_MULTIPLIER = 2
# Real approximation, confirmed with the user (2026-08-10) - the real
# "Monitor" band lower threshold (`app/core/scoring.py`), used as the
# closest real stand-in for the screenshot's fabricated "Target 75" line.
APPROXIMATE_TARGET_SCORE = 70.0


# Real-but-distinct numeric severity for the risk heatmap's score bands.
# Deliberately NOT "L"-prefixed: this codebase already has two other real,
# differently-meaning L-prefixed scales (routing_levels.py's L0-L5 clinical
# escalation levels, and reconditioning's own L1-L4 injury-severity tier -
# see app/schemas/reconditioning.py's SEVERITY_LEVELS). A third L-prefixed
# scale here would recreate the exact collision report_export_service.py
# already documented avoiding for export risk tiers. "R" for Risk instead.
RISK_SEVERITY_BY_BAND: dict[str, int] = {
    "Ready": 1,
    "Monitor": 2,
    "Caution": 3,
    "Action Needed": 4,
    "High Priority": 5,
}


def risk_severity_label(band: str | None) -> str | None:
    """Return the real 'R1'-'R5' risk-severity label for a score band, or None if unavailable."""
    if band is None:
        return None
    level = RISK_SEVERITY_BY_BAND.get(band)
    return f"R{level}" if level is not None else None


class LeadershipAggregateService:
    """Real, k-anonymity-gated aggregate views for the Leadership workspace."""

    def __init__(self) -> None:
        self.role_admin_service = RoleAdminService()

    async def _get_cohort_k(self) -> int:
        """Return the real configured Leadership cohort-k minimum."""
        scope_config = await self.role_admin_service.get_scope_config(ROLE_LEADERSHIP)
        return scope_config["cohort_k"]

    async def get_flight_comparison(self) -> dict[str, Any]:
        """Real per-flight OPS comparison, k-gated - never a per-operator list."""
        cohort_k = await self._get_cohort_k()
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        monthly_trend = await self.get_monthly_trend(months=2)
        by_month = monthly_trend["months"]

        rows: list[dict[str, Any]] = []
        for flight in flights:
            members = await User.find(User.unit_id == str(flight.id)).to_list()
            cohort_size = len(members)
            if cohort_size < cohort_k:
                continue

            ops_scores = [m.current_ops_score for m in members if m.current_ops_score is not None]
            average_ops_score = round(sum(ops_scores) / len(ops_scores), 2) if ops_scores else None

            flight_trend = await self.get_monthly_trend(months=2, unit_id=str(flight.id))
            flight_months = flight_trend["months"]
            mom_delta = None
            if len(flight_months) >= 2 and flight_months[-1]["average_ops_score"] is not None:
                mom_delta = round(
                    flight_months[-1]["average_ops_score"] - flight_months[-2]["average_ops_score"], 1
                )

            confidence = "High" if cohort_size >= cohort_k * HIGH_CONFIDENCE_MULTIPLIER else "Medium"

            rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": cohort_size,
                    "average_ops_score": average_ops_score,
                    "score_band": build_score_band(average_ops_score),
                    "mom_delta": mom_delta,
                    "confidence": confidence,
                }
            )

        rows.sort(key=lambda item: item["flight_name"])
        return {
            "min_cohort_size": cohort_k,
            "total_flights": len(flights),
            "flights_meeting_cohort_minimum": len(rows),
            "flights": rows,
            "reference_months": [m["month"] for m in by_month],
        }

    async def get_risk_heatmap(self) -> dict[str, Any]:
        """Real per-flight x per-driver score band, k-gated per flight."""
        cohort_k = await self._get_cohort_k()
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()

        rows: list[dict[str, Any]] = []
        for flight in flights:
            members = await User.find(User.unit_id == str(flight.id)).to_list()
            cohort_size = len(members)
            suppressed = cohort_size < cohort_k

            cells: dict[str, str | None] = {}
            severity_cells: dict[str, str | None] = {}
            for component in COMPONENT_PRIORITY_ORDER:
                if suppressed:
                    cells[component] = None
                    severity_cells[component] = None
                    continue
                values = [
                    (m.current_component_scores or {}).get(component)
                    for m in members
                    if (m.current_component_scores or {}).get(component) is not None
                ]
                average = round(sum(values) / len(values), 2) if values else None
                band = build_score_band(average) if average is not None else None
                cells[component] = band
                severity_cells[component] = risk_severity_label(band)

            rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": cohort_size,
                    "suppressed": suppressed,
                    "driver_bands": cells,
                    # Real, non-collision severity view of the same cells (R1
                    # lowest concern - R5 highest) - see RISK_SEVERITY_BY_BAND.
                    "driver_severity": severity_cells,
                }
            )

        rows.sort(key=lambda item: item["flight_name"])
        return {"min_cohort_size": cohort_k, "flights": rows}

    async def get_recovery_program_summary(self) -> dict[str, Any]:
        """Real per-flight active-reconditioning caseload, k-gated - the "Recovery program" view.

        Not DOCX-sourced (a Figma Leadership screen showed a "Recovery
        program" stat card and a "Recovery Rollout" briefing template with
        no real backing at all - no before/after cohort comparison, no
        adherence percentage, no "control" group exists anywhere in this
        system, and none is invented here either). What genuinely exists
        is `ReconditioningPlan` - this surfaces the same real per-flight
        active-caseload shape `CoverageService.get_reconditioning_load_by_flight`
        already uses for SCS, but under Leadership's own configured
        cohort-k (not SCS's), plus a real phase distribution and a real,
        plainly-defined "on track" signal (no plan in that flight has an
        overdue `next_review_date`) - honest, not a fabricated adherence
        score.
        """
        cohort_k = await self._get_cohort_k()
        flights = await OrgUnit.find(OrgUnit.unit_type == "flight").to_list()
        active_plans = await ReconditioningPlan.find(ReconditioningPlan.phase != "completed").to_list()
        plans_by_user_id = {p.user_id: p for p in active_plans}

        today = date.today()
        rows: list[dict[str, Any]] = []
        for flight in flights:
            members = await User.find(User.unit_id == str(flight.id)).to_list()
            cohort_size = len(members)
            if cohort_size < cohort_k:
                continue

            flight_plans = [plans_by_user_id[m.id] for m in members if m.id in plans_by_user_id]
            phase_distribution = {phase: 0 for phase in PHASES if phase != "completed"}
            for plan in flight_plans:
                if plan.phase in phase_distribution:
                    phase_distribution[plan.phase] += 1
            overdue_review_count = sum(
                1 for plan in flight_plans if plan.next_review_date is not None and plan.next_review_date < today
            )

            rows.append(
                {
                    "flight_id": str(flight.id),
                    "flight_name": flight.name,
                    "cohort_size": cohort_size,
                    "active_plan_count": len(flight_plans),
                    "phase_distribution": {PHASE_LABELS[phase]: count for phase, count in phase_distribution.items()},
                    "overdue_review_count": overdue_review_count,
                    "on_track": overdue_review_count == 0,
                }
            )

        rows.sort(key=lambda item: item["flight_name"])
        return {
            "min_cohort_size": cohort_k,
            "total_flights": len(flights),
            "flights_meeting_cohort_minimum": len(rows),
            "flights_with_active_recovery": sum(1 for r in rows if r["active_plan_count"] > 0),
            "on_track_flight_count": sum(1 for r in rows if r["on_track"] and r["active_plan_count"] > 0),
            "total_active_plans": len(active_plans),
            "flights": rows,
        }

    async def get_monthly_trend(self, months: int = 12, unit_id: str | None = None) -> dict[str, Any]:
        """Real monthly cohort OPS/component trend, k-gated per month.

        `unit_id`, when given, scopes the cohort to one real flight;
        omitted, the cohort is every enrolled Airman (matches
        `ProviderDashboardService.get_leadership_dashboard`'s existing
        `enrolled_operator_count` population, so the two stay consistent).
        A month is only reported if that month's distinct contributing
        user count meets the real cohort-k minimum - an under-k month is
        omitted entirely, never shown as a fabricated data point.

        `PvP` (period-vs-period, not DOCX-sourced) is defined here plainly:
        the average of the second half of the reported window vs the
        average of the first half.
        """
        cohort_k = await self._get_cohort_k()
        if unit_id:
            cohort_users = await User.find(User.unit_id == unit_id).to_list()
        else:
            cohort_users = await User.find(User.role == ROLE_AIRMAN).to_list()
        cohort_user_ids = {u.id for u in cohort_users}

        today = date.today()
        window_start = date(today.year, today.month, 1) - timedelta(days=31 * months)
        snapshots = await OpsSnapshot.find(OpsSnapshot.snapshot_date >= window_start).to_list()
        snapshots = [s for s in snapshots if s.user_id in cohort_user_ids]

        by_month: dict[str, list[OpsSnapshot]] = {}
        for snapshot in snapshots:
            key = f"{snapshot.snapshot_date.year:04d}-{snapshot.snapshot_date.month:02d}"
            by_month.setdefault(key, []).append(snapshot)

        month_keys = sorted(by_month.keys())[-months:]
        reported_months: list[dict[str, Any]] = []
        for key in month_keys:
            month_snapshots = by_month[key]
            contributing_users = {s.user_id for s in month_snapshots}
            if len(contributing_users) < cohort_k:
                continue

            ops_values = [s.ops_score for s in month_snapshots if s.ops_score is not None]
            average_ops_score = round(sum(ops_values) / len(ops_values), 2) if ops_values else None

            component_averages: dict[str, float | None] = {}
            for component in COMPONENT_PRIORITY_ORDER:
                values = [
                    s.component_scores.get(component)
                    for s in month_snapshots
                    if s.component_scores.get(component) is not None
                ]
                component_averages[component] = round(sum(values) / len(values), 2) if values else None

            reported_months.append(
                {
                    "month": key,
                    "cohort_size": len(contributing_users),
                    "average_ops_score": average_ops_score,
                    "component_averages": component_averages,
                }
            )

        mom_delta = None
        if len(reported_months) >= 2 and reported_months[-1]["average_ops_score"] is not None:
            mom_delta = round(
                reported_months[-1]["average_ops_score"] - reported_months[-2]["average_ops_score"], 1
            )

        pvp_delta = None
        if len(reported_months) >= 2:
            midpoint = len(reported_months) // 2
            first_half = [m["average_ops_score"] for m in reported_months[:midpoint] if m["average_ops_score"] is not None]
            second_half = [m["average_ops_score"] for m in reported_months[midpoint:] if m["average_ops_score"] is not None]
            if first_half and second_half:
                pvp_delta = round(sum(second_half) / len(second_half) - sum(first_half) / len(first_half), 1)

        return {
            "min_cohort_size": cohort_k,
            "months": reported_months,
            "mom_delta": mom_delta,
            "pvp_delta": pvp_delta,
        }

    async def get_daily_trend(self, days: int = 7, unit_id: str | None = None) -> dict[str, Any]:
        """Real daily cohort OPS/component trend, k-gated per day.

        Same real structure as `get_monthly_trend` (see that method's
        docstring for the cohort-resolution/k-gating/PvP-definition
        details), just bucketed by calendar day (`OpsSnapshot.snapshot_date`)
        instead of by month - for the Trends screen's 7d/30d period
        selector, which `get_monthly_trend` can't serve (it only has
        month-level granularity).
        """
        cohort_k = await self._get_cohort_k()
        if unit_id:
            cohort_users = await User.find(User.unit_id == unit_id).to_list()
        else:
            cohort_users = await User.find(User.role == ROLE_AIRMAN).to_list()
        cohort_user_ids = {u.id for u in cohort_users}

        today = date.today()
        window_start = today - timedelta(days=days - 1)
        snapshots = await OpsSnapshot.find(OpsSnapshot.snapshot_date >= window_start).to_list()
        snapshots = [s for s in snapshots if s.user_id in cohort_user_ids]

        by_day: dict[str, list[OpsSnapshot]] = {}
        for snapshot in snapshots:
            by_day.setdefault(snapshot.snapshot_date.isoformat(), []).append(snapshot)

        day_keys = sorted(by_day.keys())
        reported_days: list[dict[str, Any]] = []
        for key in day_keys:
            day_snapshots = by_day[key]
            contributing_users = {s.user_id for s in day_snapshots}
            if len(contributing_users) < cohort_k:
                continue

            ops_values = [s.ops_score for s in day_snapshots if s.ops_score is not None]
            average_ops_score = round(sum(ops_values) / len(ops_values), 2) if ops_values else None

            component_averages: dict[str, float | None] = {}
            for component in COMPONENT_PRIORITY_ORDER:
                values = [
                    s.component_scores.get(component)
                    for s in day_snapshots
                    if s.component_scores.get(component) is not None
                ]
                component_averages[component] = round(sum(values) / len(values), 2) if values else None

            reported_days.append(
                {
                    "day": key,
                    "cohort_size": len(contributing_users),
                    "average_ops_score": average_ops_score,
                    "component_averages": component_averages,
                }
            )

        day_over_day_delta = None
        if len(reported_days) >= 2 and reported_days[-1]["average_ops_score"] is not None:
            day_over_day_delta = round(
                reported_days[-1]["average_ops_score"] - reported_days[-2]["average_ops_score"], 1
            )

        pvp_delta = None
        if len(reported_days) >= 2:
            midpoint = len(reported_days) // 2
            first_half = [d["average_ops_score"] for d in reported_days[:midpoint] if d["average_ops_score"] is not None]
            second_half = [d["average_ops_score"] for d in reported_days[midpoint:] if d["average_ops_score"] is not None]
            if first_half and second_half:
                pvp_delta = round(sum(second_half) / len(second_half) - sum(first_half) / len(first_half), 1)

        return {
            "min_cohort_size": cohort_k,
            "days": reported_days,
            "day_over_day_delta": day_over_day_delta,
            "pvp_delta": pvp_delta,
        }

    async def get_period_trend(self, period: str = "12mo", unit_id: str | None = None) -> dict[str, Any]:
        """Real trend dispatcher for the Trends screen's period selector.

        Not DOCX-sourced (a Figma Leadership "Trends" screen). Routes
        `7d`/`30d` to real day-level buckets (`get_daily_trend`), and
        `3mo`/`6mo`/`12mo` to real month-level buckets (`get_monthly_trend`)
        - a single real entry point so the route doesn't need to know the
        day-vs-month distinction.
        """
        period_map = {"7d": ("daily", 7), "30d": ("daily", 30), "3mo": ("monthly", 3), "6mo": ("monthly", 6), "12mo": ("monthly", 12)}
        if period not in period_map:
            raise ValueError(f"Unknown period '{period}'. Allowed: {list(period_map.keys())}")

        granularity, value = period_map[period]
        if granularity == "daily":
            result = await self.get_daily_trend(days=value, unit_id=unit_id)
            return {"period": period, "granularity": "daily", **result}
        result = await self.get_monthly_trend(months=value, unit_id=unit_id)
        return {"period": period, "granularity": "monthly", **result}

    async def get_band_distribution_trend(self, months: int = 2) -> dict[str, Any]:
        """Real per-band (Ready/Monitor/Caution/Action Needed/High Priority) headcount trend.

        Not DOCX-sourced (a Figma Leadership "Trends" screen showed a
        fabricated 3-bucket "High/Mid/Watch" grouping with no DOCX/code
        basis - this uses the real 5 DOCX bands instead, see
        `app/core/scoring.py`'s `build_score_band`). For each of the most
        recent real reported months, classifies each real cohort member's
        real per-month average `ops_score` into a band and tallies real
        headcounts - never a fabricated 3-way collapse.
        """
        cohort_k = await self._get_cohort_k()
        cohort_users = await User.find(User.role == ROLE_AIRMAN).to_list()
        cohort_user_ids = {u.id for u in cohort_users}

        today = date.today()
        window_start = date(today.year, today.month, 1) - timedelta(days=31 * months)
        snapshots = await OpsSnapshot.find(OpsSnapshot.snapshot_date >= window_start).to_list()
        snapshots = [s for s in snapshots if s.user_id in cohort_user_ids]

        by_month: dict[str, list[OpsSnapshot]] = {}
        for snapshot in snapshots:
            key = f"{snapshot.snapshot_date.year:04d}-{snapshot.snapshot_date.month:02d}"
            by_month.setdefault(key, []).append(snapshot)

        month_keys = sorted(by_month.keys())[-months:]
        reported_months: list[dict[str, Any]] = []
        for key in month_keys:
            month_snapshots = by_month[key]
            per_user_scores: dict[Any, list[float]] = {}
            for snapshot in month_snapshots:
                if snapshot.ops_score is not None:
                    per_user_scores.setdefault(snapshot.user_id, []).append(snapshot.ops_score)

            if len(per_user_scores) < cohort_k:
                continue

            band_counts: dict[str, int] = {}
            for scores in per_user_scores.values():
                user_month_avg = sum(scores) / len(scores)
                band = build_score_band(user_month_avg)
                band_counts[band] = band_counts.get(band, 0) + 1

            reported_months.append({"month": key, "cohort_size": len(per_user_scores), "band_counts": band_counts})

        latest = reported_months[-1] if reported_months else None
        previous = reported_months[-2] if len(reported_months) >= 2 else None
        bands = ["Ready", "Monitor", "Caution", "Action Needed", "High Priority"]
        current_distribution = [
            {
                "band": band,
                "count": latest["band_counts"].get(band, 0) if latest else 0,
                "delta": (
                    (latest["band_counts"].get(band, 0) - previous["band_counts"].get(band, 0))
                    if latest and previous
                    else None
                ),
            }
            for band in bands
        ]

        return {
            "min_cohort_size": cohort_k,
            "months": reported_months,
            "current_distribution": current_distribution,
        }

    async def get_aggregate_view(self) -> dict[str, Any]:
        """Compose the full real Leadership "Aggregate readiness" response."""
        monthly_trend = await self.get_monthly_trend(months=12)
        flight_comparison = await self.get_flight_comparison()
        risk_heatmap = await self.get_risk_heatmap()
        recovery_program_summary = await self.get_recovery_program_summary()

        latest_month = monthly_trend["months"][-1] if monthly_trend["months"] else None
        return {
            "hero": {
                "cohort_size": latest_month["cohort_size"] if latest_month else 0,
                "average_ops_score": latest_month["average_ops_score"] if latest_month else None,
                "score_band": (
                    build_score_band(latest_month["average_ops_score"]) if latest_month else None
                ),
                "mom_delta": monthly_trend["mom_delta"],
                "pvp_delta": monthly_trend["pvp_delta"],
                "months": monthly_trend["months"],
                "approximate_target_score": APPROXIMATE_TARGET_SCORE,
                "target_is_approximated": True,
            },
            "driver_trends": [
                {
                    "component": component,
                    "average_score": latest_month["component_averages"].get(component) if latest_month else None,
                    "score_band": (
                        build_score_band(latest_month["component_averages"].get(component))
                        if latest_month and latest_month["component_averages"].get(component) is not None
                        else None
                    ),
                }
                for component in COMPONENT_PRIORITY_ORDER
            ],
            "flight_comparison": flight_comparison,
            "risk_heatmap": risk_heatmap,
            "recovery_program_summary": recovery_program_summary,
            "min_cohort_size": monthly_trend["min_cohort_size"],
        }

    async def get_wing_weekly_report(self) -> dict[str, Any]:
        """Real "Wing Weekly" report - composite OPS + 5 drivers + by-flight, 7-day window.

        Not DOCX-sourced (a Figma Leadership "Reports" screen's template
        description triggered this). Reuses `get_period_trend("7d")` and
        `get_flight_comparison()` directly - no new aggregation logic.
        """
        trend = await self.get_period_trend("7d")
        flight_comparison = await self.get_flight_comparison()
        return {"report_type": "wing_weekly_ops", "period": "7d", "trend": trend, "flight_comparison": flight_comparison}

    async def get_monthly_cohort_report(self) -> dict[str, Any]:
        """Real "Monthly Cohort" report - real 5-band cohort breakdown, 30-day window.

        Not DOCX-sourced. Reuses `get_band_distribution_trend()` and
        `get_period_trend("30d")` directly - the real 5 DOCX bands, not the
        screenshot's fabricated 3-bucket "High/Mid/Watch" language.
        """
        band_distribution = await self.get_band_distribution_trend()
        trend = await self.get_period_trend("30d")
        return {
            "report_type": "monthly_cohort_review",
            "period": "30d",
            "trend": trend,
            "band_distribution": band_distribution,
        }

    async def get_annual_wing_report(self) -> dict[str, Any]:
        """Real "Annual Wing" report - 12-month trend with a real period-over-period delta.

        Not DOCX-sourced. Reuses `get_period_trend("12mo")` directly - its
        real `pvp_delta` (second-half-of-window vs first-half) is the real
        period-over-period comparison, stated plainly as that rather than a
        literal "FY-over-FY" claim this backend has no fiscal-year concept
        for.
        """
        trend = await self.get_period_trend("12mo")
        return {"report_type": "annual_wing_readiness", "period": "12mo", "trend": trend}
