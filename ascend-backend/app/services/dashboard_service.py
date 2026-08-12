"""Home dashboard aggregation service.

Composes current OPS, driver trends, today's check-in status, the active
recommendation, a support-pathway preview, and cadence-derived upcoming
items (weekly check-in, OFT, initial assessment) into one payload for the
Home screen. OFT and assessment "Upcoming" items only appear once an
SCS/Admin has actually scheduled one - no dates are fabricated.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.core.cadence import next_monthly_review
from app.core.cadence import next_weekly_open
from app.core.checkin_question_bank import get_daily_checkin_question_bank
from app.core.driver_detail_content import get_try_this_suggestions
from app.core.recommendation_rules import COMPONENT_PRIORITY_ORDER
from app.core.recommendation_rules import get_recommendation_rule
from app.core.scoring import READINESS_COMPONENT_WEIGHTS
from app.core.scoring import build_score_band
from app.core.scoring import get_band_meaning
from app.core.support_pathways import get_support_pathways
from app.models.checkin_answer import CheckinAnswer
from app.models.ops_snapshot import OpsSnapshot
from app.models.user import User
from app.schemas.dashboard import ComponentTrendSeries
from app.schemas.dashboard import CurrentOpsBlock
from app.schemas.dashboard import DriverDetailResponse
from app.schemas.dashboard import DriverInfluence
from app.schemas.dashboard import DriverOverviewItem
from app.schemas.dashboard import DriverTrend
from app.schemas.dashboard import HomeDashboardResponse
from app.schemas.dashboard import OpsHistoryDay
from app.schemas.dashboard import PublicAggregateBlock
from app.schemas.dashboard import SupportPathwayPreview
from app.schemas.dashboard import TodaysCheckinBlock
from app.schemas.dashboard import TrendPoint
from app.schemas.dashboard import TrendsResponse
from app.schemas.dashboard import UpcomingItem
from app.schemas.wellness_report import DriverSummaryItem
from app.schemas.wellness_report import StandoutInsight
from app.schemas.wellness_report import WellnessReportResponse
from app.services.assessment_service import AssessmentService
from app.services.oft_service import OFTService
from app.services.recommendation_service import RecommendationService
from app.services.role_admin_service import RoleAdminService

# Real fallback only - a role with no explicit `RoleScopeConfig` saved
# (`app/models/role_scope_config.py`) still k-anonymity-gates at this
# default, same value as before that config became admin-editable.
MIN_UNIT_COHORT_SIZE = 5
OPS_HISTORY_DAYS = 30
WELLNESS_REPORT_WINDOW_DAYS = 30
WELLNESS_REPORT_BASELINE_DAYS = 60
TREND_UP_THRESHOLD_WEEKS = 3
DIP_DROP_THRESHOLD = 10.0
LOWEST_DRIVER_WATCH_THRESHOLD = 70.0

# Screenshot-confirmed override: the Driver Detail screen routes Physical
# Readiness support to PT/IM (injury/pain-safety-first), not SCS, even
# though the recommendation engine's coaching action for Physical Readiness
# is an SCS action. Other components reuse the recommendation engine's
# specialist routing as the best available inference - not screenshot-confirmed.
DRIVER_DETAIL_SUPPORT_ROUTE_OVERRIDES: dict[str, str] = {
    "Physical Readiness": "PT/IM",
}

TREND_HISTORY_DAYS = 14
TRENDS_SCREEN_DEFAULT_DAYS = 30


class DashboardService:
    """Build the Home dashboard payload for the authenticated user."""

    def __init__(self) -> None:
        self.recommendation_service = RecommendationService()
        self.oft_service = OFTService()
        self.assessment_service = AssessmentService()
        self.role_admin_service = RoleAdminService()

    async def get_home_dashboard(self, user: User) -> dict[str, Any]:
        """Return the aggregated Home dashboard payload."""
        now = datetime.now(timezone.utc)
        today = date.today()

        snapshots = await self.get_recent_snapshots(user, TREND_HISTORY_DAYS)
        latest_snapshot = snapshots[-1] if snapshots else None
        previous_snapshot = snapshots[-2] if len(snapshots) >= 2 else None

        today_answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id,
            CheckinAnswer.cadence == "daily",
            CheckinAnswer.checkin_date == today,
        ).to_list()

        current_ops = self._build_current_ops_block(user, latest_snapshot, previous_snapshot)
        todays_checkin = self._build_todays_checkin_block(user, len(today_answers))
        driver_trends = self._build_driver_trends(user, snapshots)
        recommendation = await self.recommendation_service.get_active_for_user(user)
        support_preview = self._build_support_preview()
        upcoming = await self._build_upcoming(user, today)

        payload = HomeDashboardResponse(
            greeting=self._greeting(user, now),
            subtitle="Here's a quick look at how things are going.",
            date_label=f"{now.strftime('%A').upper()} · {now.day} {now.strftime('%B').upper()}",
            current_ops=CurrentOpsBlock(**current_ops),
            todays_checkin=TodaysCheckinBlock(**todays_checkin),
            driver_trends=[DriverTrend(**trend) for trend in driver_trends],
            component_scores=user.current_component_scores or {},
            today_for_you=recommendation,
            support_preview=[SupportPathwayPreview(**item) for item in support_preview],
            upcoming=[UpcomingItem(**item) for item in upcoming],
            last_updated_label=self._relative_time_label(
                latest_snapshot.created_at if latest_snapshot else None, now
            ),
        )
        return payload.model_dump(mode="json")

    async def get_trends(self, user: User, days: int = TRENDS_SCREEN_DEFAULT_DAYS) -> dict[str, Any]:
        """Return the full Trends screen payload for a selected period (7/30/90 days)."""
        days = max(1, min(days, 180))
        today = date.today()
        now = datetime.now(timezone.utc)
        snapshots = await self.get_recent_snapshots(user, days)
        history_snapshots = await self.get_recent_snapshots(user, OPS_HISTORY_DAYS)
        latest_snapshot = snapshots[-1] if snapshots else None

        ops_series = [
            TrendPoint(
                date=snapshot.snapshot_date.isoformat(),
                ops_score=snapshot.ops_score,
                ops_band=snapshot.ops_band,
                confidence_level=snapshot.confidence_level,
            )
            for snapshot in snapshots
        ]
        component_series = [
            ComponentTrendSeries(
                readiness_component=component,
                signal_label=component.replace(" Readiness", ""),
                points=[
                    {
                        "date": snapshot.snapshot_date.isoformat(),
                        "score": snapshot.component_scores.get(component),
                        "stale": component in snapshot.stale_components,
                    }
                    for snapshot in snapshots
                    if snapshot.component_scores.get(component) is not None
                ],
            )
            for component in COMPONENT_PRIORITY_ORDER
        ]

        driver_overview = self.build_driver_overview(user, snapshots, today, days)
        ops_history = self._build_ops_history(history_snapshots)
        next_windows = await self._build_next_windows(user, today)
        public_aggregate = await self._build_public_aggregate(user)

        payload = TrendsResponse(
            range_days=days,
            period_label=f"Last {days} days",
            ops_series=ops_series,
            component_series=component_series,
            driver_overview=[DriverOverviewItem(**item) for item in driver_overview],
            ops_history=[OpsHistoryDay(**item) for item in ops_history],
            next_windows=[UpcomingItem(**item) for item in next_windows],
            public_aggregate=PublicAggregateBlock(**public_aggregate),
            last_updated_label=self._relative_time_label(
                latest_snapshot.created_at if latest_snapshot else None, now
            ),
        )
        return payload.model_dump(mode="json")

    def build_driver_overview(
        self,
        user: User,
        snapshots: list[OpsSnapshot],
        today: date,
        period_days: int,
    ) -> list[dict[str, Any]]:
        """Build the "Driver overview" cards: score, weight, trend, delta vs prior period."""
        current_scores = user.current_component_scores or {}
        overview = []
        for component in COMPONENT_PRIORITY_ORDER:
            trend_points = [
                snapshot.component_scores.get(component)
                for snapshot in snapshots
                if snapshot.component_scores.get(component) is not None
            ]
            prior_score = self._nearest_component_score(
                snapshots, component, today - timedelta(days=period_days)
            )
            current_score = current_scores.get(component)
            delta = (
                round(current_score - prior_score, 2)
                if current_score is not None and prior_score is not None
                else None
            )
            overview.append(
                {
                    "readiness_component": component,
                    "signal_label": component.replace(" Readiness", ""),
                    "current_score": current_score,
                    "weight": READINESS_COMPONENT_WEIGHTS[component],
                    "has_daily_trend": component != "Spiritual Readiness",
                    "trend_points": trend_points,
                    "delta_vs_prior_period": delta,
                }
            )
        return overview

    def _build_ops_history(self, snapshots: list[OpsSnapshot]) -> list[dict[str, Any]]:
        """Build the 30-day OPS band history with a dominant (weakest) driver per day."""
        history = []
        for snapshot in snapshots:
            valid_scores = {
                component: score
                for component, score in snapshot.component_scores.items()
                if score is not None
            }
            dominant_driver = min(valid_scores, key=valid_scores.get) if valid_scores else None
            history.append(
                {
                    "date": snapshot.snapshot_date.isoformat(),
                    "ops_band": snapshot.ops_band,
                    "dominant_driver": dominant_driver,
                }
            )
        return history

    async def _build_oft_window_item(self, user: User) -> dict[str, Any] | None:
        """Build the shared OFT "next window"/"upcoming" item, if one is scheduled."""
        oft_status = await self.oft_service.get_status_for_user(user)
        if oft_status["next_scheduled_date"] is None:
            return None
        return {
            "key": "oft",
            "title": "OFT - monthly components",
            "subtitle": f"Scheduled · {oft_status['next_scheduled_date']}",
            "tag": "Operational",
        }

    async def _build_next_windows(self, user: User, today: date) -> list[dict[str, Any]]:
        """Build the Trends screen's "Next windows": OFT and the next monthly review."""
        windows: list[dict[str, Any]] = []

        oft_item = await self._build_oft_window_item(user)
        if oft_item is not None:
            windows.append(oft_item)

        if user.monthly_cadence_start_date is not None:
            next_review = next_monthly_review(user.monthly_cadence_start_date.date(), today)
            status_word = "Available" if next_review <= today else "Due"
            windows.append(
                {
                    "key": "monthly_review",
                    "title": "Monthly review",
                    "subtitle": f"{status_word} · {next_review.isoformat()}",
                    "tag": "Cadence",
                }
            )

        return windows

    async def _build_public_aggregate(self, user: User) -> dict[str, Any]:
        """Build the k-anonymity-gated unit aggregate report CTA descriptor.

        `min_cohort_size` is the real, admin-configurable `cohort_k` for
        this user's role (`RoleScopeConfig`) - falls back to
        `MIN_UNIT_COHORT_SIZE` if no config has been explicitly saved.
        """
        scope_config = await self.role_admin_service.get_scope_config(user.role)
        min_cohort_size = scope_config["cohort_k"]
        if not user.unit_id:
            return {
                "available": False,
                "min_cohort_size": min_cohort_size,
                "reason": "No unit is assigned to your account yet.",
            }
        cohort_size = await User.find(User.unit_id == user.unit_id).count()
        if cohort_size < min_cohort_size:
            return {
                "available": False,
                "min_cohort_size": min_cohort_size,
                "reason": f"Your unit has {cohort_size} enrolled operator(s); at least {min_cohort_size} are required to protect anonymity.",
            }
        return {
            "available": True,
            "min_cohort_size": min_cohort_size,
            "reason": f"Unit-level readiness, aggregated across {cohort_size} operators.",
        }

    async def get_driver_detail(self, user: User, component: str) -> dict[str, Any]:
        """Return the Driver Detail payload for one readiness component.

        "Peer cohort" percentile and steps-based "Activity band" signals from
        the mock are intentionally omitted - both need real infrastructure
        this project doesn't have yet (a defined comparison cohort with a
        k-anonymity minimum size, and a wearable/steps data source). Faking
        either would show real users invented numbers, which is worse than
        not showing the field.
        """
        if component not in COMPONENT_PRIORITY_ORDER:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown readiness component.",
            )

        today = date.today()
        snapshots = await self.get_recent_snapshots(user, 30)
        latest_snapshot = snapshots[-1] if snapshots else None
        current_score = (user.current_component_scores or {}).get(component)

        trend_points = [
            {"date": s.snapshot_date.isoformat(), "score": s.component_scores.get(component)}
            for s in snapshots
            if s.component_scores.get(component) is not None
        ]

        score_7d_ago = self._nearest_component_score(snapshots, component, today - timedelta(days=7))
        score_30d_ago = self._nearest_component_score(snapshots, component, today - timedelta(days=30))
        delta_7d = (
            round(current_score - score_7d_ago, 2)
            if current_score is not None and score_7d_ago is not None
            else None
        )
        delta_30d = (
            round(current_score - score_30d_ago, 2)
            if current_score is not None and score_30d_ago is not None
            else None
        )
        if delta_7d is None:
            trend_direction = "unavailable"
        elif delta_7d > 1:
            trend_direction = "up"
        elif delta_7d < -1:
            trend_direction = "down"
        else:
            trend_direction = "flat"

        influences = await self._build_influences(user, component, today)

        rule = get_recommendation_rule(component)
        support_route = DRIVER_DETAIL_SUPPORT_ROUTE_OVERRIDES.get(
            component, rule["specialist_route"] if rule else None
        )

        payload = DriverDetailResponse(
            readiness_component=component,
            signal_label=component.replace(" Readiness", ""),
            current_score=current_score,
            score_band=build_score_band(current_score),
            last_updated_at=latest_snapshot.created_at.isoformat() if latest_snapshot else None,
            trend_points=trend_points,
            trend_direction=trend_direction,
            delta_7d=delta_7d,
            delta_30d=delta_30d,
            try_this=get_try_this_suggestions(component),
            influences=[DriverInfluence(**item) for item in influences],
            support_cta_label=f"Talk to my {support_route}" if support_route else "Talk to my support team",
            support_route=support_route,
        )
        return payload.model_dump(mode="json")

    async def get_unit_report(self, user: User) -> dict[str, Any]:
        """Return the unit-level aggregate readiness report, k-anonymity gated.

        Returns individual-level data for nobody, ever - only counts and
        averages, and only once at least MIN_UNIT_COHORT_SIZE users share the
        unit. Matches the DOCX's repeated "aggregate only" leadership-view
        rule; the specific k>=5 threshold comes from the Trends screen's own
        "k-anonymity protected (k >= 5)" copy, not the DOCX.
        """
        scope_config = await self.role_admin_service.get_scope_config(user.role)
        min_cohort_size = scope_config["cohort_k"]
        if not user.unit_id:
            return {
                "available": False,
                "unit_id": None,
                "cohort_size": 0,
                "min_cohort_size": min_cohort_size,
                "reason": "No unit is assigned to your account yet.",
            }

        unit_users = await User.find(User.unit_id == user.unit_id).to_list()
        cohort_size = len(unit_users)
        if cohort_size < min_cohort_size:
            return {
                "available": False,
                "unit_id": user.unit_id,
                "cohort_size": cohort_size,
                "min_cohort_size": min_cohort_size,
                "reason": f"Your unit has {cohort_size} enrolled operator(s); at least {min_cohort_size} are required to protect anonymity.",
            }

        ops_scores = [u.current_ops_score for u in unit_users if u.current_ops_score is not None]
        average_ops_score = round(sum(ops_scores) / len(ops_scores), 2) if ops_scores else None

        band_distribution: dict[str, int] = {}
        for u in unit_users:
            band = u.current_ops_band or "Unavailable"
            band_distribution[band] = band_distribution.get(band, 0) + 1

        component_averages: dict[str, float | None] = {}
        for component in COMPONENT_PRIORITY_ORDER:
            values = [
                (u.current_component_scores or {}).get(component)
                for u in unit_users
                if (u.current_component_scores or {}).get(component) is not None
            ]
            component_averages[component] = round(sum(values) / len(values), 2) if values else None

        return {
            "available": True,
            "unit_id": user.unit_id,
            "cohort_size": cohort_size,
            "min_cohort_size": min_cohort_size,
            "reason": None,
            "average_ops_score": average_ops_score,
            "band_distribution": band_distribution,
            "component_averages": component_averages,
        }

    async def get_wellness_report(self, user: User) -> dict[str, Any]:
        """Build the personal 30-day wellness report ("Your readiness story").

        `average_ops`/`band`/`driver_summary` reuse already DOCX-verified
        scoring logic. `standout_insights` are generated from real pattern
        detection over stored `OpsSnapshot` history - the list holds
        whatever the data actually supports (0-3 items), never a fabricated
        fixed set.
        """
        today = date.today()
        baseline_snapshots = await self.get_recent_snapshots(user, WELLNESS_REPORT_BASELINE_DAYS)
        cutoff = today - timedelta(days=WELLNESS_REPORT_WINDOW_DAYS)
        recent = [s for s in baseline_snapshots if s.snapshot_date >= cutoff]
        prior = [s for s in baseline_snapshots if s.snapshot_date < cutoff]

        average_ops = self._average_ops(recent)
        average_ops_delta = (
            round(average_ops - self._average_ops(prior), 2)
            if average_ops is not None and self._average_ops(prior) is not None
            else None
        )
        band = build_score_band(average_ops)

        driver_summary = [
            DriverSummaryItem(
                readiness_component=component,
                signal_label=component.replace(" Readiness", ""),
                average_score=self._average_component(recent, component),
            )
            for component in COMPONENT_PRIORITY_ORDER
        ]

        standout_insights = self._build_standout_insights(recent, baseline_snapshots, today)
        band_narrative = self._build_band_narrative(band, standout_insights)

        payload = WellnessReportResponse(
            period_label=f"Last {WELLNESS_REPORT_WINDOW_DAYS} days",
            average_ops=average_ops,
            average_ops_delta=average_ops_delta,
            band=band,
            band_narrative=band_narrative,
            driver_summary=driver_summary,
            standout_insights=[StandoutInsight(**item) for item in standout_insights],
            footer_note=(
                "Your personal wellness report. k-anonymity protected; "
                "unit-level views live on the leadership surface."
            ),
        )
        return payload.model_dump(mode="json")

    def _average_ops(self, snapshots: list[OpsSnapshot]) -> float | None:
        """Return the average OPS score across a set of snapshots."""
        scores = [s.ops_score for s in snapshots if s.ops_score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    def _average_component(self, snapshots: list[OpsSnapshot], component: str) -> float | None:
        """Return a component's average score across a set of snapshots."""
        scores = [
            s.component_scores.get(component)
            for s in snapshots
            if s.component_scores.get(component) is not None
        ]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    def _weekly_buckets(
        self, snapshots: list[OpsSnapshot], component: str, today: date, weeks: int = 4
    ) -> list[float]:
        """Return up to `weeks` most-recent 7-day average scores, newest first."""
        buckets = []
        for week_index in range(weeks):
            end = today - timedelta(days=7 * week_index)
            start = end - timedelta(days=7)
            week_scores = [
                s.component_scores.get(component)
                for s in snapshots
                if start <= s.snapshot_date < end and s.component_scores.get(component) is not None
            ]
            if week_scores:
                buckets.append(round(sum(week_scores) / len(week_scores), 2))
        return buckets

    def _build_standout_insights(
        self,
        recent: list[OpsSnapshot],
        baseline_snapshots: list[OpsSnapshot],
        today: date,
    ) -> list[dict[str, Any]]:
        """Detect up to 3 real, explainable highlights from snapshot history."""
        insights: list[dict[str, Any]] = []

        # 1. Trending up: a component where a majority of the last 4 weekly
        # buckets beat the 60-day baseline average for that component.
        best_trend: tuple[str, int, int] | None = None
        for component in COMPONENT_PRIORITY_ORDER:
            baseline_avg = self._average_component(baseline_snapshots, component)
            if baseline_avg is None:
                continue
            buckets = self._weekly_buckets(recent, component, today)
            if not buckets:
                continue
            beats = sum(1 for value in buckets if value > baseline_avg)
            if beats >= TREND_UP_THRESHOLD_WEEKS and (
                best_trend is None or beats > best_trend[1]
            ):
                best_trend = (component, beats, len(buckets))
        if best_trend is not None:
            component, beats, total = best_trend
            insights.append(
                {
                    "key": "trending_up",
                    "severity": "positive",
                    "title": f"{component.replace(' Readiness', '')} is trending up",
                    "body": f"{self._number_word(beats).capitalize()} of the last {self._number_word(total)} weeks beat your 60-day average.",
                }
            )

        # 2. Lowest driver, worth watching if under the DOCX moderate threshold.
        averages = {
            component: self._average_component(recent, component)
            for component in COMPONENT_PRIORITY_ORDER
        }
        valid_averages = {k: v for k, v in averages.items() if v is not None}
        if valid_averages:
            lowest_component = min(valid_averages, key=valid_averages.get)
            lowest_score = valid_averages[lowest_component]
            if lowest_score < LOWEST_DRIVER_WATCH_THRESHOLD + 10:
                # Screenshot-confirmed: this card is always "watch" (orange),
                # even when the score is already under the threshold (e.g.
                # Mental=69 < 70 still rendered orange, not red) - "notable"
                # (red) is reserved for the mid-period dip pattern below.
                insights.append(
                    {
                        "key": "lowest_driver",
                        "severity": "watch",
                        "title": f"{lowest_component.replace(' Readiness', '')} is steady but lowest",
                        "body": f"Worth a conversation with your team if it stays under {LOWEST_DRIVER_WATCH_THRESHOLD:.0f}.",
                    }
                )

        # 3. Mid-window dip and recovery: a weekly bucket well below the
        # period average, followed by a more recent bucket recovering back
        # near or above it.
        best_dip: tuple[str, float] | None = None
        for component in COMPONENT_PRIORITY_ORDER:
            period_avg = self._average_component(recent, component)
            buckets = self._weekly_buckets(recent, component, today)
            if period_avg is None or len(buckets) < 2:
                continue
            # buckets[0] is most recent; look for an older, lower bucket followed by recovery.
            for i in range(1, len(buckets)):
                dip = period_avg - buckets[i]
                recovered = buckets[0] >= period_avg - 2
                if dip >= DIP_DROP_THRESHOLD and recovered:
                    if best_dip is None or dip > best_dip[1]:
                        best_dip = (component, dip)
                    break
        if best_dip is not None:
            component, _ = best_dip
            insights.append(
                {
                    "key": "mid_window_dip",
                    "severity": "notable",
                    "title": "Mid-period dip",
                    "body": f"A one-week dip in {component.replace(' Readiness', '').lower()}, now recovered. Worth noting.",
                }
            )

        return insights[:3]

    def _number_word(self, value: int) -> str:
        """Spell out small counts (matches the mock's "Three of the last four")."""
        words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
        return words.get(value, str(value))

    def _build_band_narrative(self, band: str, standout_insights: list[dict[str, Any]]) -> str:
        """Build a short band summary line, noting a dip if one was detected."""
        has_dip = any(item["key"] == "mid_window_dip" for item in standout_insights)
        if has_dip:
            return "Mostly stable, one dip mid-period."
        if band in {"Ready", "Monitor"}:
            return "Stable across the period."
        return get_band_meaning(band)

    def _nearest_component_score(
        self,
        snapshots: list[OpsSnapshot],
        component: str,
        target_date: date,
    ) -> float | None:
        """Return the component score from the snapshot closest to (at or before) a date."""
        candidates = [s for s in snapshots if s.snapshot_date <= target_date]
        if not candidates:
            return None
        closest = max(candidates, key=lambda item: item.snapshot_date)
        return closest.component_scores.get(component)

    async def _build_influences(
        self, user: User, component: str, today: date
    ) -> list[dict[str, Any]]:
        """Build real, data-backed explainability signals for a component."""
        influences: list[dict[str, Any]] = []

        cutoff = today - timedelta(days=7)
        recent_answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id,
            CheckinAnswer.cadence == "daily",
            CheckinAnswer.checkin_date >= cutoff,
        ).to_list()
        logged_days = len({a.checkin_date for a in recent_answers})
        influences.append(
            {
                "key": "daily_checkins",
                "title": "Daily check-ins",
                "detail": f"Last 7 days: {logged_days}/7 logged",
            }
        )

        if component == "Sleep Readiness":
            recovery_cutoff = today - timedelta(days=4)
            recovery_answers = sorted(
                (
                    a
                    for a in recent_answers
                    if a.question_code == "d0_03" and a.checkin_date >= recovery_cutoff
                ),
                key=lambda item: item.checkin_date,
            )
            if len(recovery_answers) >= 2:
                delta = (recovery_answers[-1].numeric_score_100 or 0) - (
                    recovery_answers[0].numeric_score_100 or 0
                )
                direction = "improving" if delta > 0 else "declining" if delta < 0 else "stable"
                influences.append(
                    {
                        "key": "recovery_trend",
                        "title": "Recovery trend",
                        "detail": f"Recovery score {direction} across last {len(recovery_answers)} check-ins",
                    }
                )

        return influences

    async def get_recent_snapshots(self, user: User, days: int) -> list[OpsSnapshot]:
        """Return the user's OPS snapshots from the last N days, oldest first."""
        cutoff = date.today() - timedelta(days=days)
        snapshots = await OpsSnapshot.find(
            OpsSnapshot.user_id == user.id, OpsSnapshot.snapshot_date >= cutoff
        ).to_list()
        return sorted(snapshots, key=lambda item: item.snapshot_date)

    def _build_current_ops_block(
        self,
        user: User,
        latest_snapshot: OpsSnapshot | None,
        previous_snapshot: OpsSnapshot | None,
    ) -> dict[str, Any]:
        """Build the current OPS summary card."""
        ops_score = user.current_ops_score
        ops_band = user.current_ops_band or "Unavailable"
        trend_delta = None
        if latest_snapshot is not None and previous_snapshot is not None:
            if latest_snapshot.ops_score is not None and previous_snapshot.ops_score is not None:
                trend_delta = round(latest_snapshot.ops_score - previous_snapshot.ops_score, 2)
        return {
            "ops_score": ops_score,
            "ops_band": ops_band,
            "band_meaning": get_band_meaning(ops_band),
            "confidence_level": user.ops_confidence_level,
            "trend_delta": trend_delta,
            "last_updated_at": (
                latest_snapshot.created_at.isoformat() if latest_snapshot is not None else None
            ),
        }

    def _build_todays_checkin_block(self, user: User, answered_count: int) -> dict[str, Any]:
        """Build the today's check-in prompt card."""
        total = len(get_daily_checkin_question_bank())
        already_completed = answered_count >= total
        if already_completed:
            return {
                "already_completed_today": True,
                "title": "Today's check-in is complete",
                "body": "Come back tomorrow for your next check-in.",
                "cta_label": None,
                "total_questions": total,
            }
        return {
            "already_completed_today": False,
            "title": "Five questions, about a minute.",
            "body": "Daily check-ins keep your OPS current and your support team informed.",
            "cta_label": "Start daily check-in",
            "total_questions": total,
        }

    def _build_driver_trends(self, user: User, snapshots: list[OpsSnapshot]) -> list[dict[str, Any]]:
        """Build per-component current score and recent trend points."""
        latest_snapshot = snapshots[-1] if snapshots else None
        current_scores = user.current_component_scores or {}
        stale_components = set(latest_snapshot.stale_components) if latest_snapshot else set()

        trends = []
        for component in COMPONENT_PRIORITY_ORDER:
            trend_points = [
                snapshot.component_scores.get(component)
                for snapshot in snapshots
                if snapshot.component_scores.get(component) is not None
            ]
            trends.append(
                {
                    "readiness_component": component,
                    "signal_label": component.replace(" Readiness", ""),
                    "current_score": current_scores.get(component),
                    "stale": component in stale_components,
                    "trend_points": trend_points,
                }
            )
        return trends

    def _build_support_preview(self) -> list[dict[str, Any]]:
        """Return the always-available pathway tiles shown on the home card."""
        return [
            {
                "key": pathway["key"],
                "label": pathway["label"],
                "description": pathway["description"],
                "availability_status": "Available",
            }
            for pathway in get_support_pathways()
            if pathway["always_available"]
        ]

    async def _build_upcoming(self, user: User, today: date) -> list[dict[str, Any]]:
        """Return derivable upcoming cadence items.

        Each item is only included when there is real data to source it from -
        no fabricated dates. Weekly check-in is computed from
        `weekly_cadence_start_date`; OFT and the initial assessment only
        appear once an SCS/Admin has actually scheduled one via the `oft` or
        `assessments` modules.
        """
        upcoming: list[dict[str, Any]] = []
        if user.weekly_cadence_start_date is not None:
            now = datetime.now(timezone.utc)
            next_open = next_weekly_open(now)
            days_until = (next_open.date() - today).days
            subtitle = "Available now" if days_until <= 0 else f"Available in {days_until} days"
            upcoming.append(
                {
                    "key": "weekly_checkin",
                    "title": "Weekly check-in",
                    "subtitle": subtitle,
                    "tag": "Cadence",
                }
            )

        oft_item = await self._build_oft_window_item(user)
        if oft_item is not None:
            upcoming.append(oft_item)

        initial_assessment = await self.assessment_service.get_initial_assessment(user)
        if initial_assessment is not None and initial_assessment.status != "completed" and initial_assessment.due_date is not None:
            days_left = (initial_assessment.due_date - today).days
            days_label = f"{days_left} days left" if days_left >= 0 else "overdue"
            upcoming.append(
                {
                    "key": "initial_assessment",
                    "title": "Initial HPO/H2F assessment",
                    "subtitle": f"Complete by {initial_assessment.due_date.isoformat()} · {days_label}",
                    "tag": "Program",
                }
            )

        return upcoming

    def _greeting(self, user: User, now: datetime) -> str:
        """Return a time-of-day greeting using the user's first name."""
        hour = now.hour
        if hour < 12:
            part = "Morning"
        elif hour < 17:
            part = "Afternoon"
        else:
            part = "Evening"
        first_name = (user.full_name or "Operator").split(" ")[0]
        return f"{part}, {first_name}"

    def _relative_time_label(self, when: datetime | None, now: datetime) -> str | None:
        """Return a compact 'Updated N min ago' style label."""
        if when is None:
            return None
        delta_seconds = max((now - when).total_seconds(), 0)
        minutes = int(delta_seconds // 60)
        if minutes < 1:
            return "Updated just now"
        if minutes < 60:
            return f"Updated {minutes} min ago"
        hours = minutes // 60
        if hours < 24:
            return f"Updated {hours}h ago"
        days = hours // 24
        return f"Updated {days}d ago"
