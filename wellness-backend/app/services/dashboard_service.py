"""Home dashboard aggregation service."""

import asyncio
from datetime import date, datetime, timedelta
from math import ceil
from statistics import mean
from typing import Any

from fastapi import HTTPException, status

from app.core.dependencies import user_has_superadmin_access
from app.db.repositories.action_log_repo import ActionLogRepository
from app.db.repositories.app_setting_repo import AppSettingRepository
from app.db.repositories.assessment_repo import AssessmentRepository
from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.monthly_checkin_repo import MonthlyCheckInRepository
from app.db.repositories.faq_repo import FAQRepository
from app.db.repositories.profile_repo import ProfileRepository
from app.db.repositories.score_repo import ScoreRepository
from app.db.repositories.user_repo import UserRepository
from app.db.repositories.weekly_checkin_repo import WeeklyCheckInRepository
from app.models.action_log import LeaderActionLog
from app.models.score import DimensionScore, Score
from app.models.user import User
from app.schemas.dashboard import (
    LeaderSettingsCompanyUpdate,
    LeaderSettingsProfileUpdate,
    LeaderSettingsScopeUpdate,
    SuperadminFAQCreate,
    SuperadminFAQUpdate,
    SuperadminLegalContentUpdate,
    SuperadminUserUpdate,
    TeamActionLogCreate,
)
from app.services.ai_service import AIService
from app.services.account_service import AccountService
from app.services.burnout_service import BurnoutService
from app.services.meta_service import MetaService
from app.services.recommendation_service import RecommendationService
from app.services.streak_service import StreakService
from app.utils.response import error_response


class DashboardService:
    """Service for dashboard aggregation and view models."""

    def __init__(self) -> None:
        """Initialize repository and helper services."""
        self.action_log_repository = ActionLogRepository()
        self.app_setting_repository = AppSettingRepository()
        self.score_repository = ScoreRepository()
        self.assessment_repository = AssessmentRepository()
        self.daily_checkin_repository = DailyCheckInRepository()
        self.weekly_checkin_repository = WeeklyCheckInRepository()
        self.monthly_checkin_repository = MonthlyCheckInRepository()
        self.profile_repository = ProfileRepository()
        self.user_repository = UserRepository()
        self.burnout_service = BurnoutService()
        self.recommendation_service = RecommendationService()
        self.streak_service = StreakService()
        self.ai_service = AIService()
        self.account_service = AccountService()
        self.meta_service = MetaService()
        self.faq_repository = FAQRepository()
        self.dimension_labels = {
            "PC": "Physical Capacity",
            "MR": "Mental Resilience",
            "MC": "Morale & Cohesion",
            "PA": "Purpose Alignment",
            "RC": "Recovery Capacity",
        }
        self.top_risk_priority = [
            "recovery_deficit",
            "high_stress",
            "fatigue",
            "workload_strain",
            "morale_decline",
        ]
        self.top_risk_actions = {
            "recovery_deficit": [
                "Reduce workload intensity for next 3-5 days",
                "Reinforce recovery breaks",
                "Encourage consistent sleep schedule",
            ],
            "high_stress": [
                "Run short private check-ins this week",
                "Reduce nonessential pressure",
                "Reinforce stress reset breaks",
            ],
            "fatigue": [
                "Reduce workload intensity for next 3-5 days",
                "Reinforce recovery breaks",
                "Encourage consistent sleep schedule",
            ],
            "workload_strain": [
                "Rebalance workload across the team",
                "Delay low-priority tasks",
                "Limit overtime this week",
            ],
            "morale_decline": [
                "Increase team recognition this week",
                "Clarify priorities and support",
                "Add one team connection touchpoint",
            ],
        }
        self.superadmin_setting_titles = {
            "privacy_policy": "Privacy Policy",
            "terms_and_conditions": "Terms & Conditions",
            "about_us": "About Us",
        }

    async def get_home_dashboard(self, user: User) -> dict[str, Any]:
        """Return the full home dashboard payload."""
        latest_score, previous_score = await self._get_latest_and_previous_scores(
            user.id
        )
        if latest_score is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("No assessment results found for this user."),
            )

        dimension_breakdown = await self.get_dimension_breakdown(user.id, latest_score)
        weakest_dimensions = self.recommendation_service.get_weakest_dimensions(
            latest_score.dimension_scores
        )
        burnout_payload = await self.burnout_service.get_dashboard_payload(user.id)

        return {
            "user_summary": await self.get_user_summary(user),
            "overall_performance": await self.get_overall_performance(
                user.id,
                latest_score,
                previous_score,
            ),
            "dimension_breakdown": dimension_breakdown,
            "radar_chart_data": await self.get_radar_chart_data(user.id, latest_score),
            "last_7_days_progress": await self.get_last_7_days_progress(user.id),
            "personalized_improvement_plan": await self.get_personalized_improvement_plan(
                user.id,
                weakest_dimensions,
            ),
            "leader_action_plan": await self.get_leader_action_plan(
                user.id,
                weakest_dimensions,
            ),
            "behavior_streaks": await self.get_behavior_streaks(user.id),
            "daily_checkin_status": await self.get_daily_checkin_status(user.id),
            "next_checkin_type": (await self.get_checkin_status(user.id))[
                "next_checkin_type"
            ],
            "trend_insight": await self.get_trend_insight(user.id),
            "dashboard_indicators": burnout_payload["dashboard_indicators"],
            "burnout_alert": burnout_payload["burnout_alert"],
            "last_updated_at": latest_score.created_at.isoformat(),
            "live_sync_status": await self.get_live_sync_status(user.id),
        }

    async def get_user_summary(self, user: User) -> dict[str, Any]:
        """Return the dashboard user summary."""
        return {
            "name": user.name,
            "greeting_message": self._get_greeting_message(),
            "profile_image": None,
        }

    async def get_overall_performance(
        self,
        user_id: Any,
        latest_score: Score | None = None,
        previous_score: Score | None = None,
    ) -> dict[str, Any]:
        """Return the overall performance card."""
        if latest_score is None:
            latest_score, previous_score = await self._get_latest_and_previous_scores(
                user_id
            )

        if latest_score is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("No assessment results found for this user."),
            )

        percentage_change = self._calculate_percentage_change(
            latest_score.overall_score,
            previous_score.overall_score if previous_score else None,
        )
        return {
            "overall_score": latest_score.overall_score,
            "score_label": self._derive_score_label(latest_score.overall_score),
            "percentage_change": percentage_change,
            "summary_text": self._build_overall_summary(
                latest_score.dimension_scores,
                latest_score.condition,
            ),
        }

    async def get_dimension_breakdown(
        self,
        user_id: Any,
        latest_score: Score | None = None,
    ) -> list[dict[str, Any]]:
        """Return the five-dimension dashboard breakdown."""
        if latest_score is None:
            latest_score = await self.score_repository.get_latest_by_user_id(user_id)
        if latest_score is None:
            return []

        cards: list[dict[str, Any]] = []
        for key, score in latest_score.dimension_scores.model_dump().items():
            condition = self._classify_score(score)
            cards.append(
                {
                    "key": key,
                    "label": self.dimension_labels[key],
                    "score": score,
                    "condition": condition,
                    "description": self._get_dimension_description(key, score),
                    "status_tag": self._get_status_tag(condition),
                }
            )
        return cards

    async def get_radar_chart_data(
        self,
        user_id: Any,
        latest_score: Score | None = None,
    ) -> list[dict[str, Any]]:
        """Return radar chart points from the latest score."""
        if latest_score is None:
            latest_score = await self.score_repository.get_latest_by_user_id(user_id)
        if latest_score is None:
            return []

        return [
            {
                "key": key,
                "label": self.dimension_labels[key],
                "score": value,
            }
            for key, value in latest_score.dimension_scores.model_dump().items()
        ]

    async def get_last_7_days_progress(self, user_id: Any) -> list[dict[str, Any]]:
        """Return chart-ready progress points for the last seven days."""
        scores = await self.score_repository.list_by_user_id(user_id)
        score_by_day: dict[date, float] = {}
        for score in scores:
            score_day = score.created_at.date()
            if score_day not in score_by_day:
                score_by_day[score_day] = score.overall_score

        today = datetime.utcnow().date()
        progress: list[dict[str, Any]] = []
        for offset in range(6, -1, -1):
            current_day = today - timedelta(days=offset)
            progress.append(
                {
                    "day_label": current_day.strftime("%a").upper(),
                    "score_value": score_by_day.get(current_day),
                }
            )
        return progress

    async def get_personalized_improvement_plan(
        self,
        user_id: Any,
        weakest_dimensions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return personalized recommendations based on weakest dimensions."""
        latest_score = await self.score_repository.get_latest_by_user_id(user_id)
        if latest_score is None:
            return []
        selected_dimensions = (
            weakest_dimensions
            or self.recommendation_service.get_weakest_dimensions(
                latest_score.dimension_scores
            )
        )
        return await self.recommendation_service.get_personalized_improvement_plan(
            selected_dimensions
        )

    async def get_leader_action_plan(
        self,
        user_id: Any,
        weakest_dimensions: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return leader action recommendations based on weakest dimensions."""
        latest_score = await self.score_repository.get_latest_by_user_id(user_id)
        if latest_score is None:
            return []
        selected_dimensions = (
            weakest_dimensions
            or self.recommendation_service.get_weakest_dimensions(
                latest_score.dimension_scores
            )
        )
        return await self.recommendation_service.get_leader_action_plan(
            selected_dimensions
        )

    async def get_behavior_streaks(self, user_id: Any) -> list[dict[str, Any]]:
        """Return all behavior streak cards."""
        return await self.streak_service.get_behavior_streaks(user_id)

    async def get_daily_checkin_status(self, user_id: Any) -> dict[str, Any]:
        """Return whether the user should still complete a daily check-in."""
        checkins = await self.daily_checkin_repository.list_by_user_id(user_id)
        latest_checkin_date = checkins[0].submitted_at.date() if checkins else None
        completed_today = latest_checkin_date == datetime.utcnow().date()
        return {
            "should_show_daily_checkin": not completed_today,
            "last_checkin_date": latest_checkin_date,
            "daily_checkin_completed_today": completed_today,
        }

    async def get_checkin_status(self, user_id: Any) -> dict[str, Any]:
        """Return the next required check-in type for the user based on sequence.

        Priority: Daily -> Weekly (if eligible) -> Monthly (if eligible).
        """
        # 1. Check Daily completion for today
        daily_status = await self.get_daily_checkin_status(user_id)
        if daily_status["should_show_daily_checkin"]:
            return {"next_checkin_type": "daily"}

        # 2. Check Weekly eligibility and completion
        current_daily_streak = await self.streak_service.get_current_streak(user_id)
        existing_weekly = await self.weekly_checkin_repository.get_for_current_week(
            user_id,
            datetime.utcnow(),
        )
        if current_daily_streak >= 7 and existing_weekly is None:
            return {"next_checkin_type": "weekly"}

        # 3. Check Monthly eligibility and completion
        daily_checkins = await self.daily_checkin_repository.list_by_user_id(user_id)
        completed_daily_days = len(
            {checkin.submitted_at.date() for checkin in daily_checkins}
        )
        existing_monthly = await self.monthly_checkin_repository.get_for_current_month(
            user_id,
            datetime.utcnow(),
        )
        if completed_daily_days >= 30 and existing_monthly is None:
            return {"next_checkin_type": "monthly"}

        return {"next_checkin_type": "none"}

    async def get_trend_insight(self, user_id: Any) -> str:
        """Return a short trend summary derived from recent progress."""
        progress = await self.get_last_7_days_progress(user_id)
        trend_points = [
            point["score_value"]
            for point in progress
            if point.get("score_value") is not None
        ]
        if len(trend_points) < 2:
            return "Not enough progress data yet to establish a clear trend."
        if trend_points[-1] > trend_points[0]:
            return "Recent scores suggest your performance trend is improving."
        if trend_points[-1] < trend_points[0]:
            return "Recent scores suggest a mild decline in consistency."
        return "Recent scores are holding steady without a major shift."

    async def get_live_sync_status(self, user_id: Any) -> str:
        """Return a frontend-friendly sync status for dashboard freshness."""
        daily_status = await self.get_daily_checkin_status(user_id)
        if daily_status["daily_checkin_completed_today"]:
            return "live"
        if daily_status["last_checkin_date"] is not None:
            return "stale"
        return "no_recent_checkin"

    async def get_team_dashboard(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return aggregated team/leader dashboard data for the user's org scope."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        range_days = self._resolve_range_days(range_key, start_date, end_date)
        trend_end_date = end_date or datetime.utcnow().date()

        member_profiles = await self.profile_repository.list_by_scope(
            organization_name,
            scope_department,
            scope_team,
        )
        # Allow empty member profiles to return a default empty response instead of 404
        # if not member_profiles:
        #     raise HTTPException(
        #         status_code=status.HTTP_404_NOT_FOUND,
        #         detail=error_response("No team members found for the selected scope."),
        #     )


        member_contexts: list[dict[str, Any]] = []
        latest_scores: list[Score] = []
        burnout_rows: list[dict[str, Any]] = []
        recovery_series: dict[date, list[float]] = {}
        stress_distribution = {
            "low": 0,
            "guarded": 0,
            "moderate": 0,
            "elevated": 0,
        }

        for member in member_profiles:
            member_scores = await self.score_repository.list_by_user_id(member.user_id)
            latest_score = member_scores[0] if member_scores else None
            if latest_score is not None:
                latest_scores.append(latest_score)
            member_daily = await self.daily_checkin_repository.list_by_user_id(
                member.user_id
            )
            member_weekly = await self.weekly_checkin_repository.list_by_user_id(
                member.user_id
            )
            member_monthly = await self.monthly_checkin_repository.list_by_user_id(
                member.user_id
            )
            burnout_payload = self.burnout_service.build_payload_from_checkins(
                member_daily,
                member_weekly,
                member_monthly,
            )
            metrics = burnout_payload["metrics"]
            member_contexts.append(
                {
                    "profile": member,
                    "scores": member_scores,
                    "daily": member_daily,
                    "weekly": member_weekly,
                    "monthly": member_monthly,
                    "metrics": metrics,
                }
            )
            burnout_rows.append(
                {
                    "user_id": str(member.user_id),
                    "name": member.name,
                    "burnout_level": burnout_payload["burnout_alert"]["level"],
                    "signals_in_risk": burnout_payload["burnout_alert"][
                        "signals_in_risk"
                    ],
                    "is_elevated": burnout_payload["burnout_alert"]["is_active"],
                    "stress_value": metrics["stress"]["value"],
                    "leadership_climate": metrics["leadership_climate"]["value"],
                }
            )

            stress_bucket = self._classify_team_stress(metrics["stress"]["value"])
            stress_distribution[stress_bucket] += 1

            recent_daily_for_trend = [
                checkin
                for checkin in member_daily
                if checkin.submitted_at.date()
                >= datetime.utcnow().date() - timedelta(days=13)
            ]
            for checkin in recent_daily_for_trend:
                recovery_value = self.burnout_service._extract_numeric(
                    daily_checkin=checkin,
                    question_id="dc_6",
                )
                if recovery_value is None:
                    continue
                recovery_series.setdefault(checkin.submitted_at.date(), []).append(
                    recovery_value
                )

        average_ops = (
            round(mean(score.overall_score for score in latest_scores), 2)
            if latest_scores
            else None
        )
        average_driver_scores = self._average_driver_scores(latest_scores)
        average_condition = (
            self._derive_score_label(average_ops)
            if average_ops is not None
            else "Not Enough Data"
        )
        elevated_count = sum(1 for row in burnout_rows if row["is_elevated"])
        moderate_or_higher = sum(
            1 for row in burnout_rows if row["signals_in_risk"] >= 2
        )
        climate_scores = [
            row["leadership_climate"]
            for row in burnout_rows
            if row["leadership_climate"] is not None
        ]
        average_leadership_climate = (
            round(mean(climate_scores), 2) if climate_scores else None
        )

        recovery_trend = [
            {
                "date": trend_date.isoformat(),
                "average_recovery_score": round(mean(values), 2),
            }
            for trend_date, values in sorted(recovery_series.items())
        ]
        recent_actions = await self.action_log_repository.list_by_scope(
            organization_name,
            department=scope_department,
            team=scope_team,
            limit=10,
        )
        current_window = self._build_team_window_snapshot(
            member_contexts, datetime.utcnow().date()
        )
        previous_window = self._build_team_window_snapshot(
            member_contexts,
            datetime.utcnow().date() - timedelta(days=14),
        )
        top_risk_signal = self._resolve_top_risk_signal(current_window, previous_window)
        progress_snapshot = self._build_progress_snapshot(
            member_contexts,
            recent_actions,
            top_risk_signal,
        )
        leader_nudges = self._build_leader_nudges(
            recent_actions,
            top_risk_signal,
            progress_snapshot,
        )
        ops_trend = self._build_team_ops_trend(
            member_contexts,
            days=range_days,
            end_date=trend_end_date,
        )
        alert_summary = self._build_leader_alert_summary(
            current_window,
            top_risk_signal,
            burnout_rows,
        )
        impact_cards = self._build_impact_cards(progress_snapshot)

        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "selected_range": range_key,
            "range_days": range_days,
            "available_ranges": ["7d", "30d", "90d", "custom"],
            "team_summary": {
                "member_count": len(member_profiles),
                "scored_member_count": len(latest_scores),
                "average_ops": average_ops,
                "average_condition": average_condition,
            },
            "group_burnout": {
                "elevated_members": elevated_count,
                "moderate_or_higher_members": moderate_or_higher,
                "average_leadership_climate": average_leadership_climate,
            },
            "driver_breakdown": [
                {
                    "key": key,
                    "label": self.dimension_labels[key],
                    "average_score": score,
                    "condition": self._classify_score(score),
                }
                for key, score in average_driver_scores.items()
            ],
            "recovery_trend": recovery_trend,
            "stress_distribution": stress_distribution,
            "member_snapshots": burnout_rows,
            "top_risk_signal": top_risk_signal,
            "recent_actions": [
                self._serialize_action_log(item) for item in recent_actions
            ],
            "progress_snapshot": progress_snapshot,
            "impact_snapshot_cards": impact_cards,
            "leader_nudges": leader_nudges,
            "ops_trend": ops_trend,
            "alert_summary": alert_summary,
        }

    async def list_leader_members(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        query: str | None = None,
        risk_filter: str = "all",
        sort_by: str = "performance",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return paginated leader team member rows for the selected scope."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        member_profiles = await self.profile_repository.list_by_scope(
            organization_name,
            scope_department,
            scope_team,
        )
        items: list[dict[str, Any]] = []
        for member in member_profiles:
            latest_score = await self.score_repository.get_latest_by_user_id(
                member.user_id
            )
            daily = await self.daily_checkin_repository.list_by_user_id(member.user_id)
            weekly = await self.weekly_checkin_repository.list_by_user_id(
                member.user_id
            )
            monthly = await self.monthly_checkin_repository.list_by_user_id(
                member.user_id
            )
            burnout_payload = self.burnout_service.build_payload_from_checkins(
                daily,
                weekly,
                monthly,
            )
            risk_level = burnout_payload["burnout_alert"]["level"]
            primary_driver = self._infer_primary_driver_for_member(
                burnout_payload["metrics"],
                risk_level,
            )
            items.append(
                {
                    "user_id": str(member.user_id),
                    "name": member.name,
                    "role": member.role,
                    "department": member.department,
                    "team": member.team,
                    "overall_score": (
                        latest_score.overall_score if latest_score else None
                    ),
                    "condition": latest_score.condition if latest_score else None,
                    "burnout_level": risk_level,
                    "signals_in_risk": burnout_payload["burnout_alert"][
                        "signals_in_risk"
                    ],
                    "primary_driver": primary_driver,
                    "trend_summary": self._member_trend_summary(
                        {
                            "stress_value": burnout_payload["metrics"]["stress"][
                                "value"
                            ],
                            "signals_in_risk": burnout_payload["burnout_alert"][
                                "signals_in_risk"
                            ],
                        },
                        primary_driver,
                    ),
                    "profile_action": {
                        "label": "View Profile",
                        "user_id": str(member.user_id),
                    },
                    "updated_at": (
                        latest_score.created_at.isoformat() if latest_score else None
                    ),
                }
            )

        filtered_items = self._filter_leader_member_items(items, query, risk_filter)
        sorted_items = self._sort_leader_member_items(filtered_items, sort_by)
        start_index = (page - 1) * page_size
        paged_items = sorted_items[start_index : start_index + page_size]

        total_items = len(sorted_items)
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1
        stats = self._build_leader_member_stats(items)
        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "filters": {
                "query": query or "",
                "risk_filter": risk_filter,
                "sort_by": sort_by,
            },
            "summary_cards": stats,
            "items": paged_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    async def list_superadmin_organizations(
        self,
        current_user: User,
        query: str | None = None,
        risk_filter: str = "all",
        sort_by: str = "performance",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return the superadmin organizations page payload."""
        organization_options = await self.meta_service.get_organizations()
        organization_names = [
            option["value"] for option in organization_options.get("organizations", [])
        ]

        items: list[dict[str, Any]] = []
        for company_name in organization_names:
            member_profiles = await self.profile_repository.list_by_scope(company_name)
            if not member_profiles:
                continue

            dashboard = await self.get_team_dashboard(
                current_user,
                company=company_name,
                range_key="30d",
            )
            company_logo_url = next(
                (
                    profile.company_logo_url
                    for profile in member_profiles
                    if profile.company_logo_url is not None
                ),
                None,
            )
            items.append(
                {
                    "company_name": company_name,
                    "company_logo_url": company_logo_url,
                    "risk_level": self._derive_company_risk_badge(dashboard),
                    "primary_driver": self._derive_company_primary_driver(
                        dashboard["top_risk_signal"]
                    ),
                    "trend_summary": dashboard["top_risk_signal"]["summary"],
                    "avg_company_score": dashboard["team_summary"]["average_ops"],
                    "member_count": dashboard["team_summary"]["member_count"],
                    "at_risk_members": dashboard["group_burnout"][
                        "moderate_or_higher_members"
                    ],
                    "view_details_action": {
                        "label": "View Details",
                        "company": company_name,
                    },
                }
            )

        filtered_items = self._filter_superadmin_organization_items(
            items,
            query,
            risk_filter,
        )
        sorted_items = self._sort_superadmin_organization_items(filtered_items, sort_by)
        start_index = (page - 1) * page_size
        paged_items = sorted_items[start_index : start_index + page_size]
        total_items = len(sorted_items)
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1

        return {
            "page_title": "Organization",
            "subtitle": "Last updated: 5 minutes ago",
            "filters": {
                "query": query or "",
                "risk_filter": risk_filter,
                "sort_by": sort_by,
            },
            "summary_cards": self._build_superadmin_organization_stats(items),
            "items": paged_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    async def get_superadmin_company_dashboard(
        self,
        current_user: User,
        company: str,
        query: str | None = None,
        risk_filter: str = "all",
        sort_by: str = "performance",
        page: int = 1,
        page_size: int = 10,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return the company performance dashboard for a selected organization."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        members = await self.list_leader_members(
            current_user,
            company=company,
            team=team,
            query=query,
            risk_filter=risk_filter,
            sort_by=sort_by,
            page=page,
            page_size=page_size,
        )
        organization_profiles = await self.profile_repository.list_by_scope(company)
        available_teams = sorted(
            {profile.team for profile in organization_profiles if profile.team}
        )
        return {
            "page_title": "Company Performance Dashboard",
            "subtitle": "Last updated: 5 minutes ago",
            "company": company,
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "available_ranges": dashboard["available_ranges"],
            "available_teams": available_teams,
            "summary_cards": members["summary_cards"],
            "filters": {
                **members["filters"],
                "team": dashboard["scope"]["team"],
                "range": dashboard["selected_range"],
                "start_date": (
                    start_date.isoformat() if start_date is not None else None
                ),
                "end_date": end_date.isoformat() if end_date is not None else None,
            },
            "members": members,
        }

    async def get_superadmin_company_member_detail(
        self,
        current_user: User,
        company: str,
        member_user_id: str,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return the read-only member detail analysis for a selected company."""
        detail = await self.get_leader_member_detail(
            current_user,
            member_user_id=member_user_id,
            company=company,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        detail["page_title"] = "Member Detail Analysis"
        detail["company"] = company
        detail["read_only"] = True
        detail["leadership_action_log_mode"] = "read_only"
        detail.pop("leadership_action_form", None)
        return detail

    async def list_superadmin_users(
        self,
        query: str | None = None,
        status_filter: str = "all",
        sort_by: str = "company",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return the superadmin user management page payload."""
        organization_options = await self.meta_service.get_organizations()
        organization_names = [
            option["value"] for option in organization_options.get("organizations", [])
        ]

        items: list[dict[str, Any]] = []
        for company_name in organization_names:
            member_profiles = await self.profile_repository.list_by_scope(company_name)
            for profile in member_profiles:
                user = await self.user_repository.get_by_id(str(profile.user_id))
                if user is None or not user.is_active:
                    continue

                daily = await self.daily_checkin_repository.list_by_user_id(
                    profile.user_id
                )
                weekly = await self.weekly_checkin_repository.list_by_user_id(
                    profile.user_id
                )
                monthly = await self.monthly_checkin_repository.list_by_user_id(
                    profile.user_id
                )
                burnout_payload = self.burnout_service.build_payload_from_checkins(
                    daily,
                    weekly,
                    monthly,
                )
                burnout_level = burnout_payload["burnout_alert"]["level"]
                risk_status = (
                    "Risk"
                    if burnout_level in {"Elevated Burnout Risk", "Moderate"}
                    else "Normal"
                )
                items.append(
                    {
                        "user_id": str(user.id),
                        "name": user.name,
                        "email": user.email,
                        "role": profile.role or user.role,
                        "company": profile.company or user.organization_name,
                        "risk_status": risk_status,
                        "profile_image_url": profile.profile_image_url,
                        "actions": {
                            "view": {
                                "label": "View",
                                "endpoint": f"/api/v1/dashboard/superadmin/users/{user.id}",
                            },
                            "edit": {
                                "label": "Edit",
                                "endpoint": f"/api/v1/dashboard/superadmin/users/{user.id}",
                            },
                            "delete": {
                                "label": "Delete",
                                "endpoint": f"/api/v1/dashboard/superadmin/users/{user.id}",
                            },
                        },
                    }
                )

        filtered_items = self._filter_superadmin_user_items(items, query, status_filter)
        sorted_items = self._sort_superadmin_user_items(filtered_items, sort_by)
        start_index = (page - 1) * page_size
        paged_items = sorted_items[start_index : start_index + page_size]
        total_items = len(sorted_items)
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1
        return {
            "page_title": "User Management",
            "subtitle": "Manage your team members and their account permissions.",
            "filters": {
                "query": query or "",
                "status_filter": status_filter,
                "sort_by": sort_by,
            },
            "items": paged_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    async def get_superadmin_user_detail(self, user_id: str) -> dict[str, Any]:
        """Return a superadmin user detail payload for view/edit flows."""
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )

        profile = await self.profile_repository.get_by_user_id(user.id)
        return {
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": (profile.role if profile is not None else user.role),
            "organization_name": (
                profile.company if profile is not None else user.organization_name
            ),
            "department": profile.department if profile is not None else None,
            "team": profile.team if profile is not None else None,
            "employee_id": profile.employee_id if profile is not None else None,
            "contact_number": profile.contact_number if profile is not None else None,
            "profile_image_url": (
                profile.profile_image_url if profile is not None else None
            ),
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        }

    async def update_superadmin_user(
        self,
        user_id: str,
        payload: SuperadminUserUpdate,
    ) -> dict[str, Any]:
        """Update a user from the superadmin user management page."""
        user = await self.user_repository.get_by_id(user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            return await self.get_superadmin_user_detail(user_id)

        profile = await self.profile_repository.get_by_user_id(user.id)
        organization_name = updates.get(
            "organization_name",
            profile.company if profile is not None else user.organization_name,
        )
        role_value = updates.get(
            "role", profile.role if profile is not None else user.role
        )
        self.meta_service.validate_organization_role(organization_name, role_value)

        user_updates = {}
        if "name" in updates:
            user_updates["name"] = updates["name"]
        if "role" in updates:
            user_updates["role"] = updates["role"]
        if "organization_name" in updates:
            user_updates["organization_name"] = updates["organization_name"]
        if user_updates:
            await self.user_repository.update_user(user_id, user_updates)

        if profile is not None:
            profile_updates = {}
            if "name" in updates:
                profile_updates["name"] = updates["name"]
            if "role" in updates:
                profile_updates["role"] = updates["role"]
            if "organization_name" in updates:
                profile_updates["company"] = updates["organization_name"]
            if profile_updates:
                await self.profile_repository.update_by_user_id(
                    user.id, profile_updates
                )

        return await self.get_superadmin_user_detail(user_id)

    async def deactivate_superadmin_user(self, user_id: str) -> dict[str, Any]:
        """Deactivate a user from the superadmin user management page."""
        user = await self.user_repository.deactivate_user(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )
        return {
            "user_id": str(user.id),
            "is_active": user.is_active,
            "status": "deactivated",
        }

    async def get_leader_alerts(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return leader-facing alert detail payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        top_risk = dashboard["top_risk_signal"]
        alert_summary = dashboard["alert_summary"]
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "Risk & Alerts",
            "subtitle": "Wellness intelligence",
            "top_risk_panel": {
                "title": "Top Risk Signal",
                "headline": top_risk["headline"],
                "status": self._risk_panel_status(top_risk, alert_summary),
                "signal_tags": self._build_risk_signal_tags(alert_summary),
                "status_report": self._build_risk_status_report(
                    alert_summary, top_risk
                ),
                "explanation": top_risk["summary"],
                "warning": self._build_risk_warning(alert_summary, dashboard),
                "driver_impact": self._build_risk_driver_impact(top_risk),
            },
            "recommended_actions": self._build_alert_action_cards(top_risk),
            "indicator_cards": self._build_alert_indicator_cards(dashboard),
            "progress_snapshot": self._build_alert_progress_snapshot(dashboard),
            "log_action_modal": self._build_alert_log_action_modal(dashboard),
            "action_log": {
                "items": dashboard["recent_actions"],
                "view_full_history": True,
            },
            "leader_nudges": dashboard["leader_nudges"],
            "raw_alert_summary": alert_summary,
        }

    async def get_superadmin_alerts(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return the superadmin risk and alerts page payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        organization_name = dashboard["scope"]["organization_name"]
        organization_profiles = await self.profile_repository.list_by_scope(
            organization_name
        )
        team_aggregates = await self._build_superadmin_team_alert_rows(
            current_user,
            organization_name,
            organization_profiles,
            range_key,
        )
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "Risk & Alerts",
            "summary_cards": self._build_superadmin_alert_summary_cards(
                dashboard,
                team_aggregates,
            ),
            "top_risk_clusters": self._build_superadmin_top_risk_clusters(
                team_aggregates
            ),
            "escalation_alerts": self._build_superadmin_escalation_alerts(
                team_aggregates
            ),
            "risk_distribution": self._build_superadmin_alert_risk_distribution(
                team_aggregates
            ),
            "team_risk_overview": team_aggregates,
        }

    async def get_superadmin_audit_logs(
        self,
        current_user: User,
        company: str | None = None,
        query: str | None = None,
        time_filter: str = "today",
        user_filter: str = "all",
        status_filter: str = "all",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return the superadmin audit logs page payload."""
        organization_name = company or current_user.organization_name
        if organization_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response("Company is required for audit logs."),
            )

        raw_logs = await self.action_log_repository.list_by_scope(
            organization_name,
            limit=300,
        )
        member_profiles = await self.profile_repository.list_by_scope(organization_name)
        member_contexts = await self._build_member_contexts(member_profiles)
        rows = [
            await self._build_superadmin_audit_row(
                log, member_contexts, organization_name
            )
            for log in raw_logs
        ]
        filtered_rows = self._filter_superadmin_audit_rows(
            rows,
            query=query,
            time_filter=time_filter,
            user_filter=user_filter,
            status_filter=status_filter,
        )
        total_items = len(filtered_rows)
        start_index = (page - 1) * page_size
        paged_items = filtered_rows[start_index : start_index + page_size]
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1

        return {
            "page_title": "Audit & Logs",
            "summary_cards": self._build_superadmin_audit_summary_cards(filtered_rows),
            "filters": {
                "query": query or "",
                "time_filter": time_filter,
                "user_filter": user_filter,
                "status_filter": status_filter,
            },
            "items": paged_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    async def get_superadmin_audit_log_detail(
        self,
        current_user: User,
        action_log_id: str,
        company: str | None = None,
    ) -> dict[str, Any]:
        """Return the superadmin audit action detail payload."""
        organization_name = company or current_user.organization_name
        action_log = await self.action_log_repository.get_by_id(action_log_id)
        if action_log is None or action_log.organization_name != organization_name:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Audit log not found."),
            )

        member_profiles = await self.profile_repository.list_by_scope(
            action_log.organization_name
        )
        member_contexts = await self._build_member_contexts(member_profiles)
        history_item = self._build_action_history_item(
            action_log,
            member_contexts,
            action_log.team,
            action_log.department,
        )
        performer = await self.user_repository.get_by_id(str(action_log.leader_user_id))
        performer_profile = (
            await self.profile_repository.get_by_user_id(performer.id)
            if performer is not None
            else None
        )
        detail_status = self._audit_status_from_outcome(history_item["outcome"])
        system_classification = self._build_superadmin_audit_classification(action_log)

        return {
            "id": str(action_log.id),
            "primary_action": action_log.action,
            "performed_by": {
                "name": performer.name if performer is not None else "System",
                "role": (
                    performer_profile.role
                    if performer_profile is not None
                    else performer.role if performer is not None else "System"
                ),
            },
            "target_entity": {
                "organization_name": action_log.organization_name,
                "team": action_log.team,
                "department": action_log.department,
            },
            "date_time": action_log.created_at.isoformat(),
            "status": detail_status,
            "system_classification": system_classification,
            "narrative_summary": action_log.note or history_item["note"],
        }

    async def get_leader_member_detail(
        self,
        current_user: User,
        member_user_id: str,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return the leader member detail analysis payload."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        member_profiles = await self.profile_repository.list_by_scope(
            organization_name,
            scope_department,
            scope_team,
        )
        member_profile = next(
            (
                profile
                for profile in member_profiles
                if str(profile.user_id) == member_user_id
            ),
            None,
        )
        if member_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Member not found for the selected scope."),
            )

        member_scores = await self.score_repository.list_by_user_id(
            member_profile.user_id
        )
        latest_score = member_scores[0] if member_scores else None
        daily = await self.daily_checkin_repository.list_by_user_id(
            member_profile.user_id
        )
        weekly = await self.weekly_checkin_repository.list_by_user_id(
            member_profile.user_id
        )
        monthly = await self.monthly_checkin_repository.list_by_user_id(
            member_profile.user_id
        )
        burnout_payload = self.burnout_service.build_payload_from_checkins(
            daily,
            weekly,
            monthly,
        )
        range_days = self._resolve_range_days(range_key, start_date, end_date)
        primary_risk_signal = self._build_member_primary_risk_signal(
            latest_score,
            burnout_payload,
        )
        scope_actions = await self.action_log_repository.list_by_scope(
            organization_name,
            department=scope_department,
            team=scope_team,
            limit=5,
        )

        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "selected_range": range_key,
            "member_summary": {
                "user_id": str(member_profile.user_id),
                "name": member_profile.name,
                "role": member_profile.role,
                "department": member_profile.department,
                "team": member_profile.team,
                "company": member_profile.company,
                "profile_image_url": member_profile.profile_image_url,
                "current_ops_score": (
                    latest_score.overall_score if latest_score else None
                ),
                "current_condition": latest_score.condition if latest_score else None,
                "current_status_label": (
                    latest_score.condition if latest_score else "No Score"
                ),
                "updated_at": (
                    latest_score.created_at.isoformat() if latest_score else None
                ),
            },
            "primary_risk_signal": primary_risk_signal,
            "core_wellness_drivers": self._build_member_driver_breakdown(latest_score),
            "leadership_action_form": {
                "recommended_actions": primary_risk_signal["recommended_actions"],
                "custom_action_placeholder": "Enter custom leadership action...",
                "notes_placeholder": "Context or specific team members...",
            },
            "indicator_cards": self._build_member_indicator_cards(
                burnout_payload["dashboard_indicators"]
            ),
            "ops_score_trend": self._build_member_ops_trend(
                member_scores,
                range_days,
                start_date=start_date,
                end_date=end_date,
            ),
            "signals_14_day": self._build_member_signal_panel(
                burnout_payload["metrics"]
            ),
            "leadership_action_log": [
                self._serialize_action_log(item) for item in scope_actions
            ],
        }

    async def get_leader_burnout_recommendations(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
    ) -> dict[str, Any]:
        """Return the leader burnout recommendations page payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
        )
        top_risk = dashboard["top_risk_signal"]
        sections = self._build_burnout_recommendation_sections(top_risk["key"])
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "Burnout Recommendations",
            "priority_focus": {
                "title": "Priority Focus",
                "summary": self._build_priority_focus_summary(top_risk),
                "risk_key": top_risk["key"],
                "risk_label": top_risk["label"],
                "trend": top_risk["trend"],
            },
            "sections": sections,
            "footnote": (
                "These recommendations are guidance to support team wellbeing. "
                "Actions should be applied based on context and leadership judgment."
            ),
        }

    async def get_leader_ai_insights(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
        dashboard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the leader AI insights page payload with OpenAI-generated narrative."""
        if dashboard is None:
            dashboard = await self.get_team_dashboard(
                current_user,
                company=company,
                department=department,
                team=team,
                range_key=range_key,
                start_date=start_date,
                end_date=end_date,
            )
        top_risk = dashboard["top_risk_signal"]
        team_context = self.ai_service._build_leader_team_context(dashboard)
        recovery_score = next(
            (
                item["average_score"]
                for item in dashboard["driver_breakdown"]
                if item["key"] == "RC"
            ),
            None,
        )

        # Run all 4 generative calls (each falls back deterministically if OpenAI is unavailable)
        (
            executive_analysis,
            insight_cards,
            behavioral_patterns,
            predictive_forecast,
        ) = await asyncio.gather(
            self.ai_service.generate_leader_executive_analysis(
                team_context=team_context,
                top_risk_key=top_risk["key"],
                top_risk_trend=top_risk["trend"],
                average_ops=dashboard["team_summary"]["average_ops"],
            ),
            self.ai_service.generate_leader_insight_card_summaries(
                team_context=team_context,
                top_risk_key=top_risk["key"],
                recovery_score=recovery_score,
            ),
            self.ai_service.generate_leader_behavioral_patterns(
                team_context=team_context,
                top_risk_key=top_risk["key"],
            ),
            self.ai_service.generate_leader_predictive_forecast(
                team_context=team_context,
                top_risk_key=top_risk["key"],
                top_risk_trend=top_risk["trend"],
                is_active=top_risk["is_active"],
            ),
        )

        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "AI Insights",
            "subtitle": "Smart analysis based on recent data and trends",
            "executive_analysis": executive_analysis,
            "insight_cards": insight_cards,
            "behavioral_patterns": behavioral_patterns,
            "correlations": self._build_leader_correlations(dashboard),
            "supporting_trends": self._build_leader_supporting_trends(dashboard),
            "predictive_forecast": predictive_forecast,
            "risk_signals_overview": self._build_leader_risk_signals_overview(
                dashboard
            ),
        }

    async def get_superadmin_ai_insights(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
        dashboard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the superadmin AI insights payload shaped for organization-wide analysis."""
        if dashboard is None:
            dashboard = await self.get_team_dashboard(
                current_user,
                company=company,
                department=department,
                team=team,
                range_key=range_key,
                start_date=start_date,
                end_date=end_date,
            )
        leader_payload = await self.get_leader_ai_insights(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
            dashboard=dashboard,
        )
        organization_profiles = await self.profile_repository.list_by_scope(
            dashboard["scope"]["organization_name"]
        )
        team_count = len(
            {profile.team for profile in organization_profiles if profile.team}
        )
        employee_count = len(organization_profiles)

        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "AI Insights",
            "subtitle": "Smart analysis based on recent data and trends",
            "executive_summary": {
                "eyebrow": (
                    f"Executive Summary · Based on data from {team_count or 1} teams and "
                    f"{employee_count or dashboard['team_summary']['member_count']} employees"
                ),
                "headline": leader_payload["executive_analysis"]["headline"],
                "summary": leader_payload["executive_analysis"]["summary"],
            },
            "signal_cards": leader_payload["insight_cards"],
            "predictive_model": self._build_superadmin_predictive_model(
                leader_payload["predictive_forecast"],
                dashboard,
            ),
            "cross_team_insights": self._build_superadmin_cross_team_insights(
                organization_profiles,
                dashboard,
            ),
            "organization_risk_signals": self._build_superadmin_org_risk_signals(
                dashboard,
            ),
            "cross_organizational_behavior_patterns": self._build_superadmin_behavior_patterns(
                leader_payload,
                dashboard,
            ),
            "correlations": leader_payload["correlations"],
            "supporting_trends": leader_payload["supporting_trends"],
        }

    async def get_leader_report(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return the leader reports page payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        insights = await self.get_leader_ai_insights(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
            dashboard=dashboard,
        )
        members = await self.list_leader_members(
            current_user,
            company=company,
            department=department,
            team=team,
            page=page,
            page_size=page_size,
        )
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "Reports",
            "subtitle": "Analyze and export team performance insights through our sanctuary of data intelligence.",
            "summary_cards": self._build_leader_report_summary_cards(dashboard),
            "performance_trends": self._build_leader_report_performance_trends(
                dashboard
            ),
            "driver_analysis": self._build_leader_report_driver_analysis(dashboard),
            "risk_distribution": self._build_leader_report_risk_distribution(dashboard),
            "auto_generated_insights": self._build_leader_report_auto_insights(
                insights, dashboard
            ),
            "members": members,
            "export": {
                "enabled": True,
                "label": "Export Data",
            },
        }

    async def get_superadmin_report(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return the superadmin reports page payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        insights = await self.get_superadmin_ai_insights(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
            dashboard=dashboard,
        )
        members = await self.list_leader_members(
            current_user,
            company=company,
            department=department,
            team=team,
            page=page,
            page_size=page_size,
        )

        scoped_members = []
        for item in members["items"]:
            scoped_item = dict(item)
            scoped_item["profile_action"] = {
                "label": "View Profile",
                "endpoint": (
                    f"/api/v1/dashboard/superadmin/organizations/"
                    f"{dashboard['scope']['organization_name']}/members/{item['user_id']}"
                ),
                "user_id": item["user_id"],
                "company": dashboard["scope"]["organization_name"],
            }
            scoped_members.append(scoped_item)

        members["items"] = scoped_members
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "Reports",
            "subtitle": "Analyze and export company’s team performance insights through our sanctuary of data intelligence.",
            "summary_cards": self._build_leader_report_summary_cards(dashboard),
            "performance_trends": self._build_leader_report_performance_trends(
                dashboard
            ),
            "driver_analysis": self._build_leader_report_driver_analysis(dashboard),
            "risk_distribution": self._build_leader_report_risk_distribution(dashboard),
            "auto_generated_insights": self._build_superadmin_report_auto_insights(
                insights
            ),
            "members": members,
            "export": {
                "enabled": True,
                "label": "Export Data",
            },
        }

    async def get_leader_burnout_details(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
    ) -> dict[str, Any]:
        """Return the leader burnout risk details page payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
        )
        signal_breakdown = self._build_signal_breakdown(dashboard)
        trend_visualization = self._build_burnout_trend_visualization(dashboard)
        affected_members = self._build_affected_members_rows(dashboard)
        team_context = self._build_team_context(dashboard, affected_members)
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "page_title": "Burnout Risk Details",
            "subtitle": "Real-time analysis based on inputs",
            "summary_cards": {
                "risk_level": (
                    dashboard["alert_summary"]["headline"]
                    if dashboard["alert_summary"]["is_active"]
                    else "Team Risk Status"
                ),
                "risk_label": dashboard["top_risk_signal"]["label"],
                "risk_status": dashboard["group_burnout"]["elevated_members"] > 0
                and "Elevated"
                or "Watch",
                "signals_triggered": len(
                    dashboard["alert_summary"]["triggered_signals"]
                ),
                "total_signals": 6,
                "trend_7d": dashboard["top_risk_signal"]["trend"],
            },
            "signal_breakdown": signal_breakdown,
            "trend_visualization": trend_visualization,
            "affected_members": affected_members,
            "key_insight": self._build_burnout_key_insight(dashboard),
            "team_context": team_context,
        }

    async def get_leader_ops_trend(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return dedicated leader OPS trend payload."""
        dashboard = await self.get_team_dashboard(
            current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "scope": dashboard["scope"],
            "selected_range": dashboard["selected_range"],
            "range_days": dashboard["range_days"],
            "ops_trend": dashboard["ops_trend"],
        }

    async def get_leader_settings(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
    ) -> dict[str, Any]:
        """Return the leader settings page payload."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        profiles = await self.profile_repository.list_by_scope(
            organization_name,
            scope_department,
            scope_team,
        )
        departments = sorted({profile.department for profile in profiles})
        teams = sorted({profile.team for profile in profiles if profile.team})
        roles = sorted({profile.role for profile in profiles if profile.role})
        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "page_title": "Settings",
            "profile_information": {
                "title": "Profile Information",
                "subtitle": "Update your photo and personal details.",
                "fields": {
                    "name": profile.name if profile is not None else current_user.name,
                    "email": current_user.email,
                    "role": profile.role if profile is not None else current_user.role,
                    "contact_number": (
                        profile.contact_number if profile is not None else None
                    ),
                    "employee_id": profile.employee_id if profile is not None else None,
                    "profile_image_url": (
                        profile.profile_image_url if profile is not None else None
                    ),
                },
                "save_endpoint": "/api/v1/dashboard/leader/settings/profile",
            },
            "company_information": {
                "title": "Company Information",
                "subtitle": "Update your company details",
                "fields": {
                    "company_name": (
                        profile.company if profile is not None else organization_name
                    ),
                    "company_address": (
                        profile.company_address if profile is not None else None
                    ),
                    "company_logo_url": (
                        profile.company_logo_url if profile is not None else None
                    ),
                },
                "save_endpoint": "/api/v1/dashboard/leader/settings/company",
            },
            "scope_configuration": {
                "title": "Set Team, Department, and Role",
                "subtitle": "Manage your primary organizational scope.",
                "selected": {
                    "team": profile.team if profile is not None else scope_team,
                    "department": (
                        profile.department if profile is not None else scope_department
                    ),
                    "role": profile.role if profile is not None else current_user.role,
                },
                "options": {
                    "teams": teams,
                    "departments": departments,
                    "roles": roles,
                },
                "save_endpoint": "/api/v1/dashboard/leader/settings/scope",
            },
            "password_settings": {
                "title": "Password settings",
                "subtitle": "Keep your account secure with a strong password",
                "password_label": "Password",
                "last_changed_hint": "Last changed recently",
                "update_endpoint": "/api/v1/users/me/change-password",
            },
        }

    async def get_superadmin_settings_menu(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
    ) -> dict[str, Any]:
        """Return the superadmin settings menu page payload."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        scope_configuration = await self.get_superadmin_settings_scope(
            current_user,
            company=company,
            department=department,
            team=team,
        )
        return {
            "page_title": "Settings",
            "account_summary": {
                "name": current_user.name,
                "email": current_user.email,
                "profile_image_url": (
                    profile.profile_image_url if profile is not None else None
                ),
            },
            "menu_items": [
                {
                    "key": "admin_profile",
                    "label": "Admin Profile",
                    "endpoint": "/api/v1/dashboard/superadmin/settings/profile",
                },
                {
                    "key": "change_password",
                    "label": "Change Password",
                    "endpoint": "/api/v1/dashboard/superadmin/settings/change-password",
                },
                {
                    "key": "privacy_policy",
                    "label": "Privacy Policy",
                    "endpoint": "/api/v1/dashboard/superadmin/settings/privacy-policy",
                },
                {
                    "key": "terms_and_conditions",
                    "label": "Terms & Conditions",
                    "endpoint": "/api/v1/dashboard/superadmin/settings/terms-and-conditions",
                },
                {
                    "key": "about_us",
                    "label": "About Us",
                    "endpoint": "/api/v1/dashboard/superadmin/settings/about-us",
                },
            ],
            "scope": scope_configuration["scope"],
            "scope_configuration": {
                "title": scope_configuration["title"],
                "subtitle": scope_configuration["subtitle"],
                "selected": scope_configuration["selected"],
                "options": scope_configuration["options"],
                "save_endpoint": scope_configuration["save_endpoint"],
            },
            "available_ranges": scope_configuration["available_ranges"],
            "notification_action": scope_configuration["notification_action"],
        }

    async def get_superadmin_settings_profile(
        self, current_user: User
    ) -> dict[str, Any]:
        """Return the superadmin profile settings page payload."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        return {
            "page_title": "Profile",
            "hero": {
                "name": current_user.name,
                "subtitle": "Super Admin",
                "profile_image_url": (
                    profile.profile_image_url if profile is not None else None
                ),
            },
            "fields": {
                "user_name": current_user.name,
                "email": current_user.email,
                "contact_number": (
                    profile.contact_number if profile is not None else None
                ),
                "profile_image_url": (
                    profile.profile_image_url if profile is not None else None
                ),
            },
            "save_endpoint": "/api/v1/dashboard/superadmin/settings/profile",
        }

    async def get_superadmin_settings_company(
        self, current_user: User
    ) -> dict[str, Any]:
        """Return the superadmin company settings page payload."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        organization_name = (
            profile.company
            if profile is not None and profile.company
            else current_user.organization_name
        )
        return {
            "page_title": "Company Information",
            "title": "Company Information",
            "subtitle": "Update your company details.",
            "fields": {
                "company_name": organization_name,
                "company_address": (
                    profile.company_address if profile is not None else None
                ),
                "company_logo_url": (
                    profile.company_logo_url if profile is not None else None
                ),
            },
            "save_endpoint": "/api/v1/dashboard/superadmin/settings/company",
        }

    async def get_superadmin_settings_scope(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
    ) -> dict[str, Any]:
        """Return the superadmin scope settings page payload."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        departments = await self.meta_service.get_departments(organization_name)
        teams = await self.meta_service.get_teams(
            organization_name,
            scope_department,
        )
        roles = await self.meta_service.get_roles(organization_name)
        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "page_title": "Set Team, Department, and Role",
            "title": "Set Team, Department, and Role",
            "subtitle": "Manage your primary organizational scope.",
            "selected": {
                "team": scope_team,
                "department": scope_department,
                "role": profile.role if profile is not None else current_user.role,
            },
            "options": {
                "teams": [item["value"] for item in teams["teams"]],
                "departments": [item["value"] for item in departments["departments"]],
                "roles": [item["value"] for item in roles["roles"]],
            },
            "available_ranges": ["7d", "30d", "90d", "custom"],
            "notification_action": {
                "label": "Risk & Alerts",
                "path": "/risk-alerts",
            },
            "save_endpoint": "/api/v1/dashboard/superadmin/settings/scope",
        }

    async def get_superadmin_change_password_settings(
        self,
        current_user: User,
    ) -> dict[str, Any]:
        """Return the superadmin change password page payload."""
        return {
            "page_title": "Change Password",
            "email": current_user.email,
            "fields": [
                {"key": "current_password", "label": "Current Password"},
                {"key": "new_password", "label": "New Password"},
                {
                    "key": "confirm_password",
                    "label": "Confirm New Password",
                },
            ],
            "submit_endpoint": "/api/v1/users/me/change-password",
            "forgot_password_endpoint": "/api/v1/dashboard/superadmin/settings/forgot-password",
        }

    async def get_superadmin_forgot_password_settings(self) -> dict[str, Any]:
        """Return the superadmin forgot password page payload."""
        return {
            "page_title": "Forgot Password",
            "subtitle": (
                "Enter your email address to get a verification code for resetting your password."
            ),
            "submit_endpoint": "/api/v1/auth/superadmin-forgot-password",
            "verify_page_endpoint": "/api/v1/dashboard/superadmin/settings/verify-reset-code",
        }

    async def get_superadmin_verify_reset_code_settings(self) -> dict[str, Any]:
        """Return the superadmin reset code verification page payload."""
        return {
            "page_title": "Verify Code",
            "subtitle": "Enter the reset code sent to your email address.",
            "verify_endpoint": "/api/v1/auth/superadmin-verify-reset-code",
            "resend_endpoint": "/api/v1/auth/superadmin-resend-reset-code",
            "reset_password_endpoint": "/api/v1/auth/superadmin-reset-password",
        }

    async def get_superadmin_legal_content(self, key: str) -> dict[str, Any]:
        """Return an editable superadmin legal/info content page payload."""
        title = self.superadmin_setting_titles[key]
        existing = await self.app_setting_repository.get_by_key(key)
        if existing is None:
            defaults = await self._get_default_superadmin_legal_content()
            content = defaults[key]
            image_url = None
        else:
            content = existing.content
            image_url = existing.image_url
            title = existing.title or title

        slug = key.replace("_", "-")
        return {
            "page_title": title,
            "content_key": key,
            "content": content,
            "image_url": image_url,
            "save_endpoint": f"/api/v1/dashboard/superadmin/settings/{slug}",
        }

    async def save_superadmin_legal_content(
        self,
        current_user: User,
        key: str,
        payload: SuperadminLegalContentUpdate,
    ) -> dict[str, Any]:
        """Persist editable superadmin legal/info content."""
        title = payload.title or self.superadmin_setting_titles[key]
        setting = await self.app_setting_repository.upsert(
            key=key,
            title=title,
            content=payload.content,
            image_url=payload.image_url,
            updated_by_user_id=current_user.id,
        )
        return {
            "page_title": setting.title,
            "content_key": setting.key,
            "content": setting.content,
            "image_url": setting.image_url,
            "updated_at": setting.updated_at.isoformat(),
        }

    async def get_faqs(self) -> list[dict[str, Any]]:
        """Fetch all FAQs for superadmin management."""
        faqs = await self.faq_repository.get_all()
        return [
            {
                "id": str(f.id),
                "question": f.question,
                "answer": f.answer,
                "order": f.order,
                "updated_at": f.updated_at.isoformat(),
            }
            for f in faqs
        ]

    async def create_faq(self, payload: SuperadminFAQCreate) -> dict[str, Any]:
        """Create a new FAQ entry."""
        faq = await self.faq_repository.create(
            question=payload.question, answer=payload.answer, order=payload.order
        )
        return {
            "id": str(faq.id),
            "question": faq.question,
            "answer": faq.answer,
            "order": faq.order,
        }

    async def update_faq(
        self, faq_id: str, payload: SuperadminFAQUpdate
    ) -> dict[str, Any]:
        """Update an existing FAQ entry."""
        update_data = payload.model_dump(exclude_unset=True)
        faq = await self.faq_repository.update(faq_id, update_data)
        if not faq:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("FAQ not found."),
            )
        return {
            "id": str(faq.id),
            "question": faq.question,
            "answer": faq.answer,
            "order": faq.order,
        }

    async def delete_faq(self, faq_id: str) -> dict[str, bool]:
        """Delete an FAQ entry."""
        success = await self.faq_repository.delete(faq_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("FAQ not found."),
            )
        return {"success": True}

    async def update_leader_settings_profile(
        self,
        current_user: User,
        payload: LeaderSettingsProfileUpdate,
    ) -> dict[str, Any]:
        """Update profile information fields for the leader settings page."""
        update_payload = payload.model_dump(exclude_unset=True)
        if not update_payload:
            return await self.get_leader_settings(current_user)

        profile = await self.profile_repository.get_by_user_id(current_user.id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        profile_updates = {
            key: value
            for key, value in update_payload.items()
            if key
            in {"name", "role", "contact_number", "employee_id", "profile_image_url"}
        }
        if "role" in profile_updates:
            self.meta_service.validate_organization_role(
                profile.company, profile_updates["role"]
            )
        updated_profile = await self.profile_repository.update_by_user_id(
            current_user.id,
            profile_updates,
        )
        if updated_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        user_updates = {}
        if "name" in profile_updates:
            user_updates["name"] = profile_updates["name"]
        if "email" in update_payload and update_payload["email"] != current_user.email:
            existing_user = await self.user_repository.get_by_email(
                update_payload["email"]
            )
            if existing_user is not None and str(existing_user.id) != str(
                current_user.id
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_response(
                        "An account with this email already exists.",
                        {"email": "Email is already registered."},
                    ),
                )
            user_updates["email"] = update_payload["email"]
        if "role" in profile_updates:
            user_updates["role"] = profile_updates["role"]
        if user_updates:
            current_user = await self.user_repository.update_user(
                str(current_user.id), user_updates
            )

        return {
            "profile_information": {
                "name": updated_profile.name,
                "email": current_user.email,
                "role": updated_profile.role,
                "contact_number": updated_profile.contact_number,
                "employee_id": updated_profile.employee_id,
                "profile_image_url": updated_profile.profile_image_url,
            }
        }

    async def update_leader_settings_company(
        self,
        current_user: User,
        payload: LeaderSettingsCompanyUpdate,
    ) -> dict[str, Any]:
        """Update company information fields for the leader settings page."""
        update_payload = payload.model_dump(exclude_unset=True)
        if not update_payload:
            return await self.get_leader_settings(current_user)

        profile = await self.profile_repository.get_by_user_id(current_user.id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        profile_updates = {}
        if "company_name" in update_payload:
            profile_updates["company"] = update_payload["company_name"]
        if "company_address" in update_payload:
            profile_updates["company_address"] = update_payload["company_address"]
        if "company_logo_url" in update_payload:
            profile_updates["company_logo_url"] = update_payload["company_logo_url"]
        updated_profile = await self.profile_repository.update_by_user_id(
            current_user.id,
            profile_updates,
        )
        if updated_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )
        if "company" in profile_updates:
            await self.user_repository.update_user(
                str(current_user.id),
                {"organization_name": profile_updates["company"]},
            )
        return {
            "company_information": {
                "company_name": updated_profile.company,
                "company_address": updated_profile.company_address,
                "company_logo_url": updated_profile.company_logo_url,
            }
        }

    async def update_leader_settings_scope(
        self,
        current_user: User,
        payload: LeaderSettingsScopeUpdate,
    ) -> dict[str, Any]:
        """Update department, team, and role for the leader settings page."""
        update_payload = payload.model_dump(exclude_unset=True)
        if not update_payload:
            return await self.get_leader_settings(current_user)

        profile = await self.profile_repository.get_by_user_id(current_user.id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        organization_name = profile.company
        department_value = update_payload.get("department", profile.department)
        team_value = update_payload.get("team", profile.team)
        role_value = update_payload.get("role", profile.role)
        self.meta_service.validate_organization_role(organization_name, role_value)
        self.meta_service.validate_department(organization_name, department_value)
        self.meta_service.validate_team(organization_name, department_value, team_value)

        updated_profile = await self.profile_repository.update_by_user_id(
            current_user.id,
            update_payload,
        )
        if updated_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )
        if "role" in update_payload:
            await self.user_repository.update_user(
                str(current_user.id),
                {"role": update_payload["role"]},
            )
        return {
            "scope_configuration": {
                "team": updated_profile.team,
                "department": updated_profile.department,
                "role": updated_profile.role,
            }
        }

    async def create_team_action_log(
        self,
        current_user: User,
        payload: TeamActionLogCreate,
        company: str | None = None,
    ) -> dict[str, Any]:
        """Persist an action taken by a leader for the selected scope."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                payload.department,
                payload.team,
            )
        )
        action_log = await self.action_log_repository.create(
            LeaderActionLog(
                leader_user_id=current_user.id,
                organization_name=organization_name,
                department=scope_department,
                team=scope_team,
                risk_key=payload.risk_key,
                action=payload.action.strip(),
                note=payload.note.strip() if payload.note else None,
                selected_from_recommended=payload.selected_from_recommended,
            )
        )
        return self._serialize_action_log(action_log)

    async def list_team_action_logs(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Return recent leader actions for the selected scope."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        logs = await self.action_log_repository.list_by_scope(
            organization_name,
            department=scope_department,
            team=scope_team,
            limit=limit,
        )
        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "items": [self._serialize_action_log(item) for item in logs],
        }

    async def get_leader_action_history(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        outcome: str = "all",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return screenshot-ready action history timeline payload."""
        organization_name, scope_department, scope_team = (
            await self._resolve_team_scope(
                current_user,
                company,
                department,
                team,
            )
        )
        member_profiles = await self.profile_repository.list_by_scope(
            organization_name,
            scope_department,
            scope_team,
        )
        member_contexts: list[dict[str, Any]] = []
        for member in member_profiles:
            member_contexts.append(
                {
                    "profile": member,
                    "scores": await self.score_repository.list_by_user_id(
                        member.user_id
                    ),
                    "daily": await self.daily_checkin_repository.list_by_user_id(
                        member.user_id
                    ),
                    "weekly": await self.weekly_checkin_repository.list_by_user_id(
                        member.user_id
                    ),
                    "monthly": await self.monthly_checkin_repository.list_by_user_id(
                        member.user_id
                    ),
                }
            )

        raw_logs = await self.action_log_repository.list_by_scope(
            organization_name,
            department=scope_department,
            team=scope_team,
            limit=200,
        )
        range_days = self._resolve_range_days(range_key)
        cutoff = date.today() - timedelta(days=max(range_days - 1, 0))
        scoped_logs = [log for log in raw_logs if log.created_at.date() >= cutoff]

        history_items = [
            self._build_action_history_item(
                log, member_contexts, scope_team, scope_department
            )
            for log in scoped_logs
        ]
        filtered_items = self._filter_action_history_items(history_items, outcome)
        total_items = len(filtered_items)
        start_index = (page - 1) * page_size
        paged_items = filtered_items[start_index : start_index + page_size]
        total_pages = max(1, ceil(total_items / page_size)) if total_items else 1

        latest_window = self._build_team_window_snapshot(member_contexts, date.today())
        baseline_anchor = max(
            cutoff - timedelta(days=1), date.today() - timedelta(days=90)
        )
        baseline_window = self._build_team_window_snapshot(
            member_contexts, baseline_anchor
        )
        latest_top_risk = self._resolve_top_risk_signal(latest_window, baseline_window)
        baseline_top_risk = self._resolve_top_risk_signal(baseline_window, None)

        return {
            "scope": {
                "organization_name": organization_name,
                "department": scope_department,
                "team": scope_team,
            },
            "selected_range": range_key,
            "page_title": "Action History",
            "subtitle": "Track actions taken and their impact on team performance",
            "filters": {
                "team": scope_team,
                "range": range_key,
                "outcome": outcome,
                "available_outcomes": ["all", "improved", "no_change", "worsened"],
            },
            "summary_bar": {
                "total_actions": total_items,
                "burnout_risk_change": {
                    "before": baseline_top_risk["label"],
                    "after": latest_top_risk["label"],
                },
                "next_assessment_in_days": 4,
            },
            "items": paged_items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        }

    async def get_superadmin_action_history(
        self,
        current_user: User,
        company: str | None = None,
        department: str | None = None,
        team: str | None = None,
        range_key: str = "30d",
        outcome: str = "all",
        page: int = 1,
        page_size: int = 10,
    ) -> dict[str, Any]:
        """Return action history for a superadmin-selected scope."""
        return await self.get_leader_action_history(
            current_user=current_user,
            company=company,
            department=department,
            team=team,
            range_key=range_key,
            outcome=outcome,
            page=page,
            page_size=page_size,
        )

    async def _get_latest_and_previous_scores(
        self,
        user_id: Any,
    ) -> tuple[Score | None, Score | None]:
        """Return the latest and previous scores for a user."""
        scores = await self.score_repository.list_by_user_id(user_id)
        latest_score = scores[0] if scores else None
        previous_score = scores[1] if len(scores) > 1 else None
        return latest_score, previous_score

    def _get_greeting_message(self) -> str:
        """Return a greeting based on local server time."""
        current_hour = datetime.now().hour
        if 5 <= current_hour <= 11:
            return "Good Morning"
        if 12 <= current_hour <= 16:
            return "Good Afternoon"
        if 17 <= current_hour <= 21:
            return "Good Evening"
        return "Good Night"

    def _calculate_percentage_change(
        self,
        current_score: float,
        previous_score: float | None,
    ) -> float:
        """Calculate percentage change from the previous overall score."""
        if previous_score in (None, 0):
            return 0.0
        return round(((current_score - previous_score) / previous_score) * 100, 2)

    def _derive_score_label(self, overall_score: float) -> str:
        """Return a frontend-friendly overall score label."""
        if overall_score >= 85:
            return "Optimal"
        if overall_score >= 70:
            return "Stable"
        if overall_score >= 55:
            return "Strained"
        if overall_score >= 40:
            return "High Risk"
        return "Critical"

    def _classify_score(self, score: float) -> str:
        """Return the standard score condition for a single value."""
        if score >= 85:
            return "Optimal"
        if score >= 70:
            return "Stable"
        if score >= 55:
            return "Strained"
        if score >= 40:
            return "High Risk"
        return "Critical"

    def _get_status_tag(self, condition: str) -> str:
        """Return a frontend-friendly status tag for a condition."""
        tag_map = {
            "Optimal": "success",
            "Stable": "steady",
            "Strained": "warning",
            "High Risk": "critical",
            "Critical": "critical",
        }
        return tag_map[condition]

    def _build_overall_summary(
        self,
        dimension_scores: DimensionScore,
        condition: str,
    ) -> str:
        """Build a short summary line for the performance card."""
        weakest_dimension = min(
            dimension_scores.model_dump().items(),
            key=lambda item: item[1],
        )[0]
        dimension_name = self.dimension_labels[weakest_dimension].lower()
        return (
            f"Your performance is {condition.lower()}. "
            f"Improving {dimension_name} will raise your overall score."
        )

    def _get_dimension_description(self, key: str, score: float) -> str:
        """Return a static dimension description based on score range."""
        band = self._classify_score(score)
        descriptions = {
            "PC": {
                "Optimal": "Your physical routines are strongly supporting energy, stamina, and performance.",
                "Stable": "Your physical routines are supporting dependable daily performance.",
                "Strained": "Your physical habits are inconsistent and may be limiting sustainable performance.",
                "High Risk": "Your physical patterns suggest energy and health routines need immediate support.",
                "Critical": "Your physical condition appears significantly strained and needs urgent attention.",
            },
            "MR": {
                "Optimal": "Your focus, resilience, and stress recovery patterns are performing at a high level.",
                "Stable": "You are managing pressure reasonably well with room to strengthen resilience.",
                "Strained": "Stress and concentration patterns may be limiting consistent performance.",
                "High Risk": "Your mental resilience patterns suggest stress is noticeably impacting daily output.",
                "Critical": "Stress and mental fatigue appear severe enough to disrupt daily functioning.",
            },
            "MC": {
                "Optimal": "Connection, recognition, and support in your environment are strongly reinforcing performance.",
                "Stable": "Connection and support within your environment remain stable.",
                "Strained": "Team connection and support appear inconsistent across your environment.",
                "High Risk": "You may be experiencing low connection, support, or recognition.",
                "Critical": "Environmental support appears severely limited and may be undermining performance.",
            },
            "PA": {
                "Optimal": "Your daily work appears highly aligned with priorities, meaning, and direction.",
                "Stable": "You have a mostly clear sense of purpose and manageable direction.",
                "Strained": "Connection to long-term goals is fluctuating.",
                "High Risk": "Your workload or direction may feel disconnected from meaningful priorities.",
                "Critical": "Purpose and direction appear deeply misaligned with current demands.",
            },
            "RC": {
                "Optimal": "Your recovery habits are strongly supporting sustainable energy and resilience.",
                "Stable": "Your recovery patterns are mostly steady with some room to improve rest quality.",
                "Strained": "Your recovery routines are inconsistent and may be affecting performance.",
                "High Risk": "Your recovery patterns suggest sleep or rest issues are affecting performance.",
                "Critical": "Recovery appears severely compromised and is likely dragging down performance.",
            },
        }
        return descriptions[key][band]

    def _average_driver_scores(self, scores: list[Score]) -> dict[str, float]:
        """Return average team driver scores from latest member snapshots."""
        if not scores:
            return {key: 0.0 for key in self.dimension_labels}

        return {
            key: round(
                mean(getattr(score.dimension_scores, key) for score in scores),
                2,
            )
            for key in self.dimension_labels
        }

    def _classify_team_stress(self, stress_value: float | None) -> str:
        """Bucket a user's stress signal for team distribution views."""
        if stress_value is None:
            return "low"
        if stress_value >= 75:
            return "elevated"
        if stress_value >= 50:
            return "moderate"
        if stress_value >= 25:
            return "guarded"
        return "low"

    async def _resolve_team_scope(
        self,
        current_user: User,
        company: str | None,
        department: str | None,
        team: str | None,
    ) -> tuple[str, str | None, str | None]:
        """Resolve team analytics scope from the user's profile and query overrides."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        profile_company = (
            profile.company if profile is not None else current_user.organization_name
        )
        organization_name = company or profile_company

        # If a different company is selected explicitly, do not inherit the current
        # user's saved department/team because those values may not exist inside
        # the selected organization and would incorrectly filter out all members.
        use_profile_scope = profile is not None and (
            company is None or company == profile_company
        )
        scope_department = (
            department
            if department is not None
            else (profile.department if use_profile_scope else None)
        )
        scope_team = (
            team if team is not None else (profile.team if use_profile_scope else None)
        )

        if organization_name is None and user_has_superadmin_access(current_user):
            organization_options = await self.meta_service.get_organizations()
            for option in organization_options.get("organizations", []):
                candidate_company = option["value"]
                candidate_profiles = await self.profile_repository.list_by_scope(
                    candidate_company
                )
                if candidate_profiles:
                    organization_name = candidate_company
                    break

        if organization_name is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Organization profile is required before team analytics can be viewed."
                ),
            )
        return organization_name, scope_department, scope_team

    def _build_team_window_snapshot(
        self,
        member_contexts: list[dict[str, Any]],
        anchor_date: date,
    ) -> dict[str, Any]:
        """Return team metrics anchored to a specific date."""
        signal_values: dict[str, list[float]] = {
            "sleep": [],
            "energy": [],
            "stress": [],
            "recovery": [],
            "workload": [],
            "motivation": [],
            "leadership_climate": [],
        }
        signal_counts = {key: 0 for key in signal_values}
        dimension_values = {key: [] for key in self.dimension_labels}
        burnout_signal_counts: list[int] = []

        for context in member_contexts:
            metrics = self.burnout_service._build_metrics(
                [
                    item
                    for item in context["daily"]
                    if item.submitted_at.date() <= anchor_date
                ],
                [
                    item
                    for item in context["weekly"]
                    if item.submitted_at.date() <= anchor_date
                ],
                [
                    item
                    for item in context["monthly"]
                    if item.submitted_at.date() <= anchor_date
                ],
                reference_date=anchor_date,
            )
            signal_risk_count = 0
            for key, metric in metrics.items():
                if metric["value"] is not None:
                    signal_values[key].append(metric["value"])
                if key != "leadership_climate" and metric["in_risk"]:
                    signal_counts[key] += 1
                    signal_risk_count += 1
            burnout_signal_counts.append(signal_risk_count)

            score = self._get_latest_score_before(context["scores"], anchor_date)
            if score is None:
                continue
            for key in self.dimension_labels:
                dimension_values[key].append(getattr(score.dimension_scores, key))

        return {
            "member_count": len(member_contexts),
            "metric_averages": {
                key: round(mean(values), 2) if values else None
                for key, values in signal_values.items()
            },
            "risk_counts": signal_counts,
            "dimension_averages": {
                key: round(mean(values), 2) if values else None
                for key, values in dimension_values.items()
            },
            "average_burnout_signal_count": (
                round(mean(burnout_signal_counts), 2) if burnout_signal_counts else 0.0
            ),
        }

    def _resolve_top_risk_signal(
        self,
        current_window: dict[str, Any],
        previous_window: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the single highest-priority team risk signal."""
        member_count = max(current_window["member_count"], 1)
        threshold_count = max(1, ceil(member_count * 0.3))
        metrics = current_window["metric_averages"]
        counts = current_window["risk_counts"]
        dimension_averages = current_window["dimension_averages"]
        previous_dimensions = (
            previous_window["dimension_averages"] if previous_window is not None else {}
        )
        morale_delta = None
        if (
            dimension_averages.get("MC") is not None
            and previous_dimensions.get("MC") is not None
        ):
            morale_delta = round(
                dimension_averages["MC"] - previous_dimensions["MC"],
                2,
            )

        candidates = {
            "recovery_deficit": {
                "triggered": (
                    (metrics["recovery"] is not None and metrics["recovery"] < 50.0)
                    or (metrics["sleep"] is not None and metrics["sleep"] < 6.0)
                    or counts["recovery"] >= threshold_count
                ),
                "headline": "Recovery deficit detected (early burnout risk)",
                "summary": "Recovery capacity and sleep patterns are dragging down team readiness.",
                "status": "critical",
                "metric": metrics["recovery"],
                "affected_members": max(counts["recovery"], counts["sleep"]),
            },
            "high_stress": {
                "triggered": (
                    (metrics["stress"] is not None and metrics["stress"] > 60.0)
                    or counts["stress"] >= threshold_count
                ),
                "headline": "Stress levels trending high across team",
                "summary": "Stress severity is elevated across recent team check-ins.",
                "status": "critical",
                "metric": metrics["stress"],
                "affected_members": counts["stress"],
            },
            "fatigue": {
                "triggered": (
                    (metrics["energy"] is not None and metrics["energy"] < 50.0)
                    or (metrics["sleep"] is not None and metrics["sleep"] < 6.0)
                    or counts["energy"] >= threshold_count
                ),
                "headline": "Fatigue increasing due to low sleep patterns",
                "summary": "Sleep, energy, and recovery signals point to mounting fatigue risk.",
                "status": "warning",
                "metric": metrics["energy"],
                "affected_members": max(
                    counts["energy"], counts["sleep"], counts["recovery"]
                ),
            },
            "workload_strain": {
                "triggered": (
                    (metrics["workload"] is not None and metrics["workload"] < 50.0)
                    or counts["workload"] >= threshold_count
                ),
                "headline": "Workload strain is limiting team performance",
                "summary": "Recent workload signals show pressure is staying too high for the team.",
                "status": "warning",
                "metric": metrics["workload"],
                "affected_members": counts["workload"],
            },
            "morale_decline": {
                "triggered": (
                    (
                        dimension_averages["MC"] is not None
                        and dimension_averages["MC"] < 70.0
                    )
                    or (morale_delta is not None and morale_delta <= -5.0)
                    or (
                        metrics["motivation"] is not None
                        and metrics["motivation"] < 50.0
                    )
                ),
                "headline": "Morale declining over the past 14 days",
                "summary": "Connection, motivation, or recognition patterns are slipping.",
                "status": "warning",
                "metric": dimension_averages["MC"],
                "affected_members": counts["motivation"],
            },
        }

        previous_key = None
        if previous_window is not None:
            previous_signal = self._resolve_top_risk_signal(previous_window, None)
            previous_key = (
                previous_signal["key"] if previous_signal["is_active"] else None
            )

        for key in self.top_risk_priority:
            candidate = candidates[key]
            if candidate["triggered"]:
                return {
                    "key": key,
                    "label": self._humanize_risk_key(key),
                    "headline": candidate["headline"],
                    "summary": candidate["summary"],
                    "status": candidate["status"],
                    "metric_value": candidate["metric"],
                    "affected_members": candidate["affected_members"],
                    "recommended_actions": self.top_risk_actions[key],
                    "trend": self._derive_risk_trend(key, previous_key),
                    "is_active": True,
                }

        return {
            "key": "none",
            "label": "No Immediate Risk",
            "headline": "No immediate team risk signal detected",
            "summary": "Recent team data does not show a dominant high-priority risk signal.",
            "status": "steady",
            "metric_value": None,
            "affected_members": 0,
            "recommended_actions": [
                "Review team progress this week",
                "Reinforce current healthy routines",
            ],
            "trend": "Stable",
            "is_active": False,
        }

    def _build_progress_snapshot(
        self,
        member_contexts: list[dict[str, Any]],
        recent_actions: list[LeaderActionLog],
        current_top_risk: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a before-versus-after view for the latest action window."""
        latest_action = recent_actions[0] if recent_actions else None
        if latest_action is not None:
            window_days = min(
                max((date.today() - latest_action.created_at.date()).days, 14), 30
            )
            before_anchor = latest_action.created_at.date() - timedelta(days=1)
        else:
            window_days = 14
            before_anchor = date.today() - timedelta(days=window_days)

        before_window = self._build_team_window_snapshot(member_contexts, before_anchor)
        current_window = self._build_team_window_snapshot(member_contexts, date.today())
        before_top_risk = self._resolve_top_risk_signal(before_window, None)

        domain_changes = []
        for key, label in self.dimension_labels.items():
            before_value = before_window["dimension_averages"].get(key)
            after_value = current_window["dimension_averages"].get(key)
            delta = None
            if before_value is not None and after_value is not None:
                delta = round(after_value - before_value, 2)
            domain_changes.append({"key": key, "label": label, "delta": delta})

        burnout_before = before_window["average_burnout_signal_count"]
        burnout_after = current_window["average_burnout_signal_count"]
        burnout_delta = round(burnout_after - burnout_before, 2)

        return {
            "comparison_window_days": window_days,
            "reference_action": self._serialize_action_log(latest_action),
            "top_risk_change": {
                "before": before_top_risk["label"],
                "after": current_top_risk["label"],
                "status": self._describe_top_risk_change(
                    before_top_risk, current_top_risk
                ),
            },
            "domain_score_changes": domain_changes,
            "burnout_level_trend": {
                "before": burnout_before,
                "after": burnout_after,
                "delta": burnout_delta,
                "status": self._describe_burnout_change(burnout_delta),
            },
        }

    def _build_leader_nudges(
        self,
        recent_actions: list[LeaderActionLog],
        top_risk_signal: dict[str, Any],
        progress_snapshot: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Return at most three lightweight leader nudges."""
        nudges: list[dict[str, str]] = []
        if top_risk_signal["is_active"] and top_risk_signal["trend"] == "New":
            nudges.append(
                {
                    "key": "new_risk_signal",
                    "message": "New burnout risk detected-review your dashboard",
                    "status": "warning",
                }
            )

        latest_action = recent_actions[0] if recent_actions else None
        if (
            latest_action is None
            or latest_action.created_at.date() <= date.today() - timedelta(days=7)
        ):
            nudges.append(
                {
                    "key": "no_action_logged",
                    "message": "No action logged this week",
                    "status": "warning",
                }
            )

        if date.today().weekday() == 0:
            nudges.append(
                {
                    "key": "weekly_review",
                    "message": "Check your team's progress",
                    "status": "steady",
                }
            )

        if (
            progress_snapshot["burnout_level_trend"]["status"] == "Worsening"
            and len(nudges) < 3
        ):
            nudges.append(
                {
                    "key": "follow_up",
                    "message": "Top risk is worsening-review your last action",
                    "status": "critical",
                }
            )
        return nudges[:3]

    def _resolve_range_days(
        self,
        range_key: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the day window for a leader dashboard range."""
        normalized = range_key.lower()
        if normalized == "7d":
            return 7
        if normalized == "90d":
            return 90
        if normalized == "custom" and start_date is not None and end_date is not None:
            return max((end_date - start_date).days + 1, 1)
        return 30

    def _build_team_ops_trend(
        self,
        member_contexts: list[dict[str, Any]],
        days: int,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Return chart-ready team OPS trend for the selected window."""
        start_date = end_date - timedelta(days=max(days - 1, 0))
        points: list[dict[str, Any]] = []
        current_day = start_date
        while current_day <= end_date:
            day_scores: list[float] = []
            for context in member_contexts:
                score = self._get_latest_score_before(context["scores"], current_day)
                if score is not None:
                    day_scores.append(score.overall_score)
            points.append(
                {
                    "date": current_day.isoformat(),
                    "day_label": current_day.strftime("%b %d"),
                    "average_ops": round(mean(day_scores), 2) if day_scores else None,
                }
            )
            current_day += timedelta(days=1)
        return points

    def _build_leader_alert_summary(
        self,
        current_window: dict[str, Any],
        top_risk_signal: dict[str, Any],
        burnout_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a screenshot-friendly alert summary block."""
        elevated_members = sum(1 for row in burnout_rows if row["is_elevated"])
        member_count = max(current_window["member_count"], 1)
        triggered_signals: list[dict[str, Any]] = []
        for key in self.top_risk_priority:
            count = current_window["risk_counts"].get(
                {
                    "recovery_deficit": "recovery",
                    "high_stress": "stress",
                    "fatigue": "energy",
                    "workload_strain": "workload",
                    "morale_decline": "motivation",
                }[key],
                0,
            )
            if count > 0:
                triggered_signals.append(
                    {
                        "key": key,
                        "label": self._humanize_risk_key(key),
                        "affected_members": count,
                        "affected_percentage": round((count / member_count) * 100, 1),
                    }
                )

        return {
            "is_active": elevated_members > 0 or top_risk_signal["is_active"],
            "headline": (
                "Active Burnout Alert" if elevated_members > 0 else "Team Risk Status"
            ),
            "risk_level_description": top_risk_signal["summary"],
            "worsening": top_risk_signal["trend"] == "Worsening",
            "triggered_signals": triggered_signals,
            "elevated_members": elevated_members,
            "member_count": current_window["member_count"],
            "recommended_actions": top_risk_signal["recommended_actions"],
        }

    def _build_impact_cards(
        self, progress_snapshot: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Return compact impact snapshot cards for the leader dashboard."""
        cards: list[dict[str, Any]] = []
        cards.append(
            {
                "key": "top_risk_change",
                "label": "Top Risk Trend",
                "value": progress_snapshot["top_risk_change"]["status"],
            }
        )
        sleep_delta = self._find_domain_delta(
            progress_snapshot["domain_score_changes"], "RC"
        )
        cards.append(
            {
                "key": "recovery_change",
                "label": "Recovery Capacity",
                "value": self._format_delta(sleep_delta),
            }
        )
        cards.append(
            {
                "key": "burnout_trend",
                "label": "Burnout Risk",
                "value": progress_snapshot["burnout_level_trend"]["status"],
            }
        )
        return cards

    def _find_domain_delta(
        self,
        domain_changes: list[dict[str, Any]],
        key: str,
    ) -> float | None:
        """Return a domain delta from the progress snapshot list."""
        for item in domain_changes:
            if item["key"] == key:
                return item["delta"]
        return None

    def _format_delta(self, delta: float | None) -> str:
        """Return a compact signed delta string."""
        if delta is None:
            return "No data"
        prefix = "+" if delta > 0 else ""
        return f"{prefix}{delta}%"

    def _build_priority_focus_summary(self, top_risk_signal: dict[str, Any]) -> str:
        """Return the hero summary copy for the burnout recommendations page."""
        summaries = {
            "recovery_deficit": (
                "The team is showing signs of reduced recovery and increased stress. "
                "Supporting recovery behaviors should be the immediate priority."
            ),
            "high_stress": (
                "Stress levels are elevated across the team. Reducing pressure and increasing "
                "support should be the immediate priority."
            ),
            "fatigue": (
                "The team is showing mounting fatigue linked to sleep and energy patterns. "
                "Short-term recovery support should be the immediate priority."
            ),
            "workload_strain": (
                "Workload strain is limiting team performance. Rebalancing pressure and clearing "
                "nonessential tasks should be the immediate priority."
            ),
            "morale_decline": (
                "Team morale and connection are slipping. Recognition, clarity, and supportive "
                "check-ins should be the immediate priority."
            ),
            "none": (
                "No dominant burnout risk is active right now. Maintain healthy routines and "
                "monitor team signals closely."
            ),
        }
        return summaries.get(top_risk_signal["key"], top_risk_signal["summary"])

    def _build_burnout_recommendation_sections(
        self,
        risk_key: str,
    ) -> list[dict[str, Any]]:
        """Return screenshot-ready recommendation sections for the top burnout risk."""
        recommendation_library = {
            "recovery_deficit": [
                {
                    "key": "recovery_support",
                    "title": "Recovery Support",
                    "items": [
                        "Encourage consistent sleep routines",
                        "Promote short breaks during the day",
                        "Suggest limiting after-hours work activity",
                    ],
                },
                {
                    "key": "team_check_in",
                    "title": "Team Check-In",
                    "items": [
                        "Have a quick 1:1 conversation",
                        "Ask about stress and workload experience",
                        "Offer support and listen actively",
                    ],
                },
                {
                    "key": "wellness_practices",
                    "title": "Wellness Practices",
                    "items": [
                        "Encourage breathing exercises",
                        "Suggest reflection or journaling",
                        "Promote short mental reset breaks",
                    ],
                },
                {
                    "key": "if_risk_persists",
                    "title": "If Risk Persists",
                    "items": [
                        "Encourage seeking additional support",
                        "Recommend using available wellness resources",
                    ],
                },
            ],
            "high_stress": [
                {
                    "key": "pressure_reduction",
                    "title": "Pressure Reduction",
                    "items": [
                        "Reduce nonessential deadlines this week",
                        "Pause low-value work where possible",
                        "Create a clearer short-term priority list",
                    ],
                },
                {
                    "key": "team_check_in",
                    "title": "Team Check-In",
                    "items": [
                        "Run quick 1:1 conversations",
                        "Ask about workload and stress triggers",
                        "Clarify where support is immediately needed",
                    ],
                },
                {
                    "key": "wellness_practices",
                    "title": "Wellness Practices",
                    "items": [
                        "Promote brief decompression breaks",
                        "Encourage breathing or reset exercises",
                        "Normalize asking for help early",
                    ],
                },
                {
                    "key": "if_risk_persists",
                    "title": "If Risk Persists",
                    "items": [
                        "Escalate repeated stress issues to leadership or HR",
                        "Review workload allocation across the team",
                    ],
                },
            ],
            "fatigue": [
                {
                    "key": "recovery_support",
                    "title": "Recovery Support",
                    "items": [
                        "Encourage earlier evening shutdown",
                        "Promote shorter work blocks with breaks",
                        "Reinforce consistent sleep timing",
                    ],
                },
                {
                    "key": "team_check_in",
                    "title": "Team Check-In",
                    "items": [
                        "Check for signs of overload or exhaustion",
                        "Ask whether workload is limiting recovery",
                        "Offer temporary workload flexibility",
                    ],
                },
                {
                    "key": "wellness_practices",
                    "title": "Wellness Practices",
                    "items": [
                        "Suggest short recovery walks",
                        "Encourage midday hydration and meal consistency",
                        "Promote low-friction sleep-support habits",
                    ],
                },
                {
                    "key": "if_risk_persists",
                    "title": "If Risk Persists",
                    "items": [
                        "Review after-hours work expectations",
                        "Reduce workload intensity for several days",
                    ],
                },
            ],
            "workload_strain": [
                {
                    "key": "workload_control",
                    "title": "Workload Control",
                    "items": [
                        "Rebalance workload across the team",
                        "Delay low-priority tasks",
                        "Set a hard stop for nonessential work",
                    ],
                },
                {
                    "key": "team_check_in",
                    "title": "Team Check-In",
                    "items": [
                        "Identify the most overloaded team members",
                        "Clarify top priorities for the week",
                        "Remove avoidable task switching",
                    ],
                },
                {
                    "key": "wellness_practices",
                    "title": "Wellness Practices",
                    "items": [
                        "Encourage recovery breaks during heavy days",
                        "Promote focus blocks over multitasking",
                        "Protect one uninterrupted work block",
                    ],
                },
                {
                    "key": "if_risk_persists",
                    "title": "If Risk Persists",
                    "items": [
                        "Escalate resource constraints to higher leadership",
                        "Reduce active commitments for the team",
                    ],
                },
            ],
            "morale_decline": [
                {
                    "key": "recognition_support",
                    "title": "Recognition Support",
                    "items": [
                        "Increase visible recognition this week",
                        "Acknowledge specific wins publicly",
                        "Reinforce what the team is doing well",
                    ],
                },
                {
                    "key": "team_check_in",
                    "title": "Team Check-In",
                    "items": [
                        "Create a quick connection touchpoint",
                        "Ask whether expectations feel clear",
                        "Listen for signs of disengagement",
                    ],
                },
                {
                    "key": "wellness_practices",
                    "title": "Wellness Practices",
                    "items": [
                        "Promote team reflection moments",
                        "Encourage peer support and collaboration",
                        "Reinforce meaningful work alignment",
                    ],
                },
                {
                    "key": "if_risk_persists",
                    "title": "If Risk Persists",
                    "items": [
                        "Review leadership support patterns",
                        "Escalate persistent disengagement themes",
                    ],
                },
            ],
            "none": [
                {
                    "key": "maintain",
                    "title": "Maintain Healthy Routines",
                    "items": [
                        "Keep recovery habits visible across the team",
                        "Review risk signals weekly",
                        "Reinforce current healthy behaviors",
                    ],
                }
            ],
        }
        return recommendation_library.get(risk_key, recommendation_library["none"])

    def _build_signal_breakdown(
        self, dashboard: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Return screenshot-ready signal breakdown rows."""
        member_count = max(dashboard["team_summary"]["member_count"], 1)
        labels = {
            "recovery_deficit": "Recovery",
            "high_stress": "Stress",
            "fatigue": "Energy",
            "workload_strain": "Workload",
            "morale_decline": "Motivation",
        }
        rows: list[dict[str, Any]] = []
        for item in dashboard["alert_summary"]["triggered_signals"]:
            rows.append(
                {
                    "key": item["key"],
                    "label": labels.get(item["key"], item["label"]),
                    "status": self._signal_status_label(
                        item["key"], item["affected_percentage"]
                    ),
                    "affected_members": item["affected_members"],
                    "affected_percentage": item["affected_percentage"],
                }
            )

        present_keys = {row["key"] for row in rows}
        defaults = [
            ("sleep", "Sleep", "Below optimal"),
            ("recovery_deficit", "Recovery", "Poor"),
            ("workload_strain", "Workload", "Moderate strain"),
            ("morale_decline", "Motivation", "Declining"),
        ]
        for key, label, status in defaults:
            if key not in present_keys:
                rows.append(
                    {
                        "key": key,
                        "label": label,
                        "status": status,
                        "affected_members": 0,
                        "affected_percentage": 0.0,
                    }
                )
        order = [
            "sleep",
            "high_stress",
            "fatigue",
            "recovery_deficit",
            "workload_strain",
            "morale_decline",
        ]
        sort_index = {key: index for index, key in enumerate(order)}
        return sorted(rows, key=lambda item: sort_index.get(item["key"], 99))

    def _signal_status_label(self, risk_key: str, percentage: float) -> str:
        """Return a UI-friendly signal status label."""
        if risk_key == "high_stress":
            return "High"
        if risk_key == "fatigue":
            return "Low"
        if risk_key == "recovery_deficit":
            return "Poor"
        if risk_key == "workload_strain":
            return "Moderate strain"
        if risk_key == "morale_decline":
            return "Declining"
        if percentage >= 50:
            return "High"
        if percentage >= 25:
            return "Watch"
        return "Below optimal"

    def _build_burnout_trend_visualization(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return simplified 14-day chart series for stress, recovery, and energy."""
        ops_trend = dashboard["ops_trend"][-14:]
        return {
            "window_days": 14,
            "series": [
                {
                    "key": "stress",
                    "label": "Stress",
                    "points": [
                        {
                            "date": point["date"],
                            "value": self._stress_proxy_from_ops(point["average_ops"]),
                        }
                        for point in ops_trend
                    ],
                },
                {
                    "key": "recovery",
                    "label": "Recovery",
                    "points": [
                        {
                            "date": point["date"],
                            "value": self._recovery_proxy_from_ops(
                                point["average_ops"]
                            ),
                        }
                        for point in ops_trend
                    ],
                },
                {
                    "key": "energy",
                    "label": "Energy",
                    "points": [
                        {"date": point["date"], "value": point["average_ops"]}
                        for point in ops_trend
                    ],
                },
            ],
        }

    def _stress_proxy_from_ops(self, average_ops: float | None) -> float | None:
        """Approximate stress trend from team OPS for charting fallback."""
        if average_ops is None:
            return None
        return round(max(0.0, 100.0 - average_ops), 2)

    def _recovery_proxy_from_ops(self, average_ops: float | None) -> float | None:
        """Approximate recovery trend from team OPS for charting fallback."""
        return average_ops

    def _build_affected_members_rows(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return affected member table rows."""
        rows: list[dict[str, Any]] = []
        for item in dashboard["member_snapshots"]:
            primary_driver = self._primary_driver_from_snapshot(item)
            rows.append(
                {
                    "user_id": item["user_id"],
                    "name": item["name"],
                    "team": dashboard["scope"]["team"],
                    "risk_level": item["burnout_level"],
                    "primary_driver": primary_driver,
                    "trend_summary": self._member_trend_summary(item, primary_driver),
                    "action_label": "View Profile",
                }
            )
        rows.sort(
            key=lambda item: 0 if item["risk_level"] == "Elevated Burnout Risk" else 1
        )
        return rows[:10]

    def _primary_driver_from_snapshot(self, snapshot: dict[str, Any]) -> str:
        """Infer a primary driver label from a member burnout snapshot."""
        stress_value = snapshot.get("stress_value")
        if stress_value is not None and stress_value > 60:
            return "Stress"
        if snapshot.get("signals_in_risk", 0) >= 4:
            return "Recovery"
        return "Energy"

    def _member_trend_summary(
        self, snapshot: dict[str, Any], primary_driver: str
    ) -> str:
        """Return a short member trend summary."""
        if primary_driver == "Stress":
            return "High stress trend and worsening focus scores."
        if primary_driver == "Recovery":
            return "Low recovery and rising stress over the last 7 days."
        return "Declining energy and reduced sleep consistency."

    def _build_burnout_key_insight(self, dashboard: dict[str, Any]) -> str:
        """Return a short narrative insight for the burnout details page."""
        if dashboard["top_risk_signal"]["key"] == "recovery_deficit":
            return (
                "Recovery decline and rising stress are the primary drivers of current burnout risk. "
                "Physiological data suggests insufficient restorative periods between high-intensity work blocks."
            )
        if dashboard["top_risk_signal"]["key"] == "high_stress":
            return (
                "Stress escalation is the primary driver of current burnout risk. "
                "Recent team signals suggest pressure is outpacing recovery capacity."
            )
        return dashboard["top_risk_signal"]["summary"]

    def _build_team_context(
        self,
        dashboard: dict[str, Any],
        affected_members: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return compact team context stats."""
        member_count = max(dashboard["team_summary"]["member_count"], 1)
        affected_ratio = round((len(affected_members) / member_count) * 100, 1)
        return {
            "team_affected_percentage": affected_ratio,
            "most_impacted_driver": dashboard["top_risk_signal"]["label"],
            "delta_vs_last_window": (
                "+12% vs LW"
                if dashboard["top_risk_signal"]["trend"] == "Worsening"
                else "Stable vs LW"
            ),
        }

    def _infer_primary_driver_for_member(
        self,
        metrics: dict[str, dict[str, Any]],
        risk_level: str,
    ) -> str:
        """Infer the primary member driver from available burnout metrics."""
        if metrics["stress"]["in_risk"]:
            return "Stress"
        if metrics["recovery"]["in_risk"] or risk_level == "Elevated Burnout Risk":
            return "Recovery"
        if metrics["energy"]["in_risk"]:
            return "Energy"
        if metrics["workload"]["in_risk"]:
            return "Workload"
        if metrics["motivation"]["in_risk"]:
            return "Motivation"
        return "Recovery"

    def _filter_leader_member_items(
        self,
        items: list[dict[str, Any]],
        query: str | None,
        risk_filter: str,
    ) -> list[dict[str, Any]]:
        """Apply search and risk filters to leader member rows."""
        filtered = items
        normalized_query = (query or "").strip().lower()
        if normalized_query:
            filtered = [
                item
                for item in filtered
                if normalized_query in item["name"].lower()
                or normalized_query in item["role"].lower()
                or normalized_query in item["team"].lower()
                or normalized_query in item["user_id"].lower()
            ]

        normalized_filter = risk_filter.lower()
        if normalized_filter == "high":
            filtered = [
                item
                for item in filtered
                if item["burnout_level"] == "Elevated Burnout Risk"
            ]
        elif normalized_filter == "risk":
            filtered = [
                item
                for item in filtered
                if item["burnout_level"] in {"Elevated Burnout Risk", "Moderate"}
            ]
        return filtered

    def _sort_leader_member_items(
        self,
        items: list[dict[str, Any]],
        sort_by: str,
    ) -> list[dict[str, Any]]:
        """Sort leader member rows for the team members page."""
        normalized = sort_by.lower()
        if normalized == "name":
            return sorted(items, key=lambda item: item["name"].lower())
        if normalized == "risk":
            order = {
                "Elevated Burnout Risk": 0,
                "Moderate": 1,
                "Guarded": 2,
                "Low": 3,
            }
            return sorted(
                items,
                key=lambda item: (
                    order.get(item["burnout_level"], 99),
                    -(item["signals_in_risk"] or 0),
                ),
            )
        return sorted(
            items,
            key=lambda item: (
                -(item["overall_score"] or 0.0),
                item["name"].lower(),
            ),
        )

    def _filter_superadmin_organization_items(
        self,
        items: list[dict[str, Any]],
        query: str | None,
        risk_filter: str,
    ) -> list[dict[str, Any]]:
        """Apply organization search and risk filters."""
        filtered = items
        normalized_query = (query or "").strip().lower()
        if normalized_query:
            filtered = [
                item
                for item in filtered
                if normalized_query in item["company_name"].lower()
            ]

        normalized_filter = risk_filter.lower()
        if normalized_filter == "high":
            filtered = [item for item in filtered if item["risk_level"] == "Elevated"]
        elif normalized_filter == "risk":
            filtered = [
                item for item in filtered if item["risk_level"] in {"Elevated", "Watch"}
            ]
        return filtered

    def _sort_superadmin_organization_items(
        self,
        items: list[dict[str, Any]],
        sort_by: str,
    ) -> list[dict[str, Any]]:
        """Sort organization rows for the superadmin organizations page."""
        normalized = sort_by.lower()
        if normalized == "name":
            return sorted(items, key=lambda item: item["company_name"].lower())
        if normalized == "risk":
            order = {
                "Elevated": 0,
                "Watch": 1,
                "Stable": 2,
            }
            return sorted(
                items,
                key=lambda item: (
                    order.get(item["risk_level"], 99),
                    -(item["at_risk_members"] or 0),
                ),
            )
        return sorted(
            items,
            key=lambda item: (
                -(item["avg_company_score"] or 0.0),
                item["company_name"].lower(),
            ),
        )

    def _build_superadmin_organization_stats(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return summary cards for the superadmin organizations page."""
        high_performing_companies = sum(
            1 for item in items if (item["avg_company_score"] or 0) >= 85
        )
        at_risk_companies = sum(
            1 for item in items if item["risk_level"] in {"Elevated", "Watch"}
        )
        average_values = [
            item["avg_company_score"]
            for item in items
            if item["avg_company_score"] is not None
        ]
        average_company_score = (
            round(mean(average_values), 2) if average_values else None
        )

        return [
            {
                "key": "companies_high_performing",
                "label": "Company Performs High",
                "value": high_performing_companies,
            },
            {
                "key": "companies_at_risk",
                "label": "Company At-Risk",
                "value": at_risk_companies,
            },
            {
                "key": "avg_company_score",
                "label": "Avg. Company Score",
                "value": average_company_score,
            },
        ]

    def _build_superadmin_predictive_model(
        self,
        predictive_forecast: dict[str, Any],
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the predictive model panel for superadmin AI insights."""
        affected_teams = len(
            {
                snapshot["user_id"]
                for snapshot in dashboard["member_snapshots"]
                if snapshot["is_elevated"]
            }
        )
        return {
            "title": "Burnout risk increasing across teams",
            "label": predictive_forecast.get(
                "label", predictive_forecast.get("forecast")
            ),
            "confidence_label": predictive_forecast.get("confidence_label"),
            "confidence_value": predictive_forecast.get(
                "confidence_value",
                predictive_forecast.get("confidence_score"),
            ),
            "critical_alert": {
                "title": "Critical Alert",
                "summary": predictive_forecast.get(
                    "supporting_note",
                    predictive_forecast.get("summary"),
                ),
                "affected_scope": f"{max(affected_teams, 1)} teams affected",
            },
            "org_opportunity": {
                "title": "Org Opportunity",
                "summary": (
                    "If recovery improves this cycle, organization-wide readiness could recover "
                    "measurably before the next reporting window."
                ),
                "confidence_label": "82% Confidence",
            },
            "footnote": "Read-only predictive model for executive planning",
        }

    def _build_superadmin_cross_team_insights(
        self,
        organization_profiles: list[Any],
        dashboard: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Return org-wide cross-team insight tiles."""
        departments = [
            profile.department
            for profile in organization_profiles
            if profile.department
        ]
        teams = [profile.team for profile in organization_profiles if profile.team]
        top_risk = dashboard["top_risk_signal"]["label"]
        return [
            {
                "key": "stress_levels",
                "label": "Stress Levels",
                "summary": (
                    f"Highest observed in {sorted(set(departments))[0]}"
                    if departments
                    else f"Highest observed in {top_risk}"
                ),
            },
            {
                "key": "recovery_rate",
                "label": "Recovery Rate",
                "summary": (
                    f"Lowest in {sorted(set(teams))[0]}"
                    if teams
                    else "Lowest in the currently selected scope"
                ),
            },
            {
                "key": "engagement_score",
                "label": "Engagement Score",
                "summary": self._build_superadmin_engagement_summary(dashboard),
            },
        ]

    def _build_superadmin_org_risk_signals(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return organization risk signal rows for superadmin AI insights."""
        stress_population = self._percentage_of_population(
            dashboard["group_burnout"]["moderate_or_higher_members"],
            dashboard["team_summary"]["member_count"],
        )
        elevated_population = self._percentage_of_population(
            dashboard["group_burnout"]["elevated_members"],
            dashboard["team_summary"]["member_count"],
        )
        return [
            {
                "category": "Cognitive Fatigue",
                "current_status": (
                    "High Risk" if elevated_population >= 30 else "Moderate"
                ),
                "affected_population": f"{stress_population}% of org",
                "trend": dashboard["top_risk_signal"]["trend"],
            },
            {
                "category": "Burnout Vulnerability",
                "current_status": (
                    "Moderate" if dashboard["alert_summary"]["is_active"] else "Low"
                ),
                "affected_population": f"{elevated_population}% of org",
                "trend": (
                    "Stable"
                    if not dashboard["alert_summary"]["is_active"]
                    else "Elevated"
                ),
            },
            {
                "category": "Attrition Risk",
                "current_status": "Low" if stress_population < 30 else "Moderate",
                "affected_population": f"{max(stress_population - 12, 0)}% of org",
                "trend": "-2%" if stress_population < 30 else "+4%",
            },
        ]

    def _build_superadmin_behavior_patterns(
        self,
        leader_payload: dict[str, Any],
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return cross-organizational behavioral pattern cards."""
        patterns = leader_payload["behavioral_patterns"]
        correlations = leader_payload["correlations"]
        first_pattern = (
            patterns[0]
            if patterns
            else {
                "title": "Low sleep is linked to high stress days",
                "summary": "Observed across multiple teams.",
            }
        )
        second_pattern = (
            patterns[1]
            if len(patterns) > 1
            else {
                "title": "Better energy on days with physical activity",
                "summary": "Observed as an organization-wide pattern.",
            }
        )
        return [
            {
                "key": "cause_effect",
                "eyebrow": "Cause & Effect",
                "title": first_pattern["title"],
                "summary": first_pattern["summary"],
                "badge": f"Observed across {max(dashboard['group_burnout']['moderate_or_higher_members'], 1)} teams",
            },
            {
                "key": "energy_correlation",
                "eyebrow": "Energy Correlation",
                "title": second_pattern["title"],
                "summary": second_pattern["summary"],
                "badge": (
                    (
                        correlations[0].get("impact")
                        or correlations[0].get("value")
                        or "Org-wide pattern"
                    )
                    if correlations
                    else "Org-wide pattern"
                ),
            },
        ]

    def _build_superadmin_report_auto_insights(
        self,
        insights: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the auto-generated insights block for the superadmin reports page."""
        signal_cards = insights.get("signal_cards", [])
        highlights = [
            {
                "title": card["title"],
                "summary": card["summary"],
            }
            for card in signal_cards[:2]
        ]
        return {
            "title": "Auto-Generated Insights",
            "highlights": highlights,
            "view_full_insight_analysis": True,
        }

    async def _build_superadmin_team_alert_rows(
        self,
        current_user: User,
        company: str,
        organization_profiles: list[Any],
        range_key: str,
    ) -> list[dict[str, Any]]:
        """Return team-level alert rows for the superadmin alerts page."""
        team_names = sorted(
            {profile.team for profile in organization_profiles if profile.team}
        )
        rows: list[dict[str, Any]] = []
        for team_name in team_names:
            team_dashboard = await self.get_team_dashboard(
                current_user,
                company=company,
                team=team_name,
                range_key=range_key,
            )
            top_risk = team_dashboard["top_risk_signal"]
            elevated = team_dashboard["group_burnout"]["elevated_members"]
            total_members = max(team_dashboard["team_summary"]["member_count"], 1)
            rows.append(
                {
                    "team_name": team_name,
                    "team_code": self._build_team_code(team_name),
                    "risk_status": self._derive_team_risk_status(team_dashboard),
                    "top_issue": self._humanize_risk_key(top_risk["key"]),
                    "trend": top_risk["trend"],
                    "affected_percentage": round((elevated / total_members) * 100),
                    "primary_driver": self._derive_company_primary_driver(top_risk),
                    "summary": top_risk["summary"],
                    "company": company,
                    "action": {
                        "label": "View Details",
                        "endpoint": (
                            f"/api/v1/dashboard/superadmin/burnout-details"
                            f"?company={company}&team={team_name}&range={range_key}"
                        ),
                    },
                }
            )
        return rows

    async def _build_member_contexts(
        self,
        member_profiles: list[Any],
    ) -> list[dict[str, Any]]:
        """Build reusable member contexts for aggregate calculations."""
        member_contexts: list[dict[str, Any]] = []
        for member in member_profiles:
            member_contexts.append(
                {
                    "profile": member,
                    "scores": await self.score_repository.list_by_user_id(
                        member.user_id
                    ),
                    "daily": await self.daily_checkin_repository.list_by_user_id(
                        member.user_id
                    ),
                    "weekly": await self.weekly_checkin_repository.list_by_user_id(
                        member.user_id
                    ),
                    "monthly": await self.monthly_checkin_repository.list_by_user_id(
                        member.user_id
                    ),
                }
            )
        return member_contexts

    async def _build_superadmin_audit_row(
        self,
        action_log: LeaderActionLog,
        member_contexts: list[dict[str, Any]],
        organization_name: str,
    ) -> dict[str, Any]:
        """Return a row for the superadmin audit log table."""
        history_item = self._build_action_history_item(
            action_log,
            member_contexts,
            action_log.team,
            action_log.department,
        )
        performer = await self.user_repository.get_by_id(str(action_log.leader_user_id))
        performer_name = performer.name if performer is not None else "System"
        performer_email = performer.email if performer is not None else None
        status = self._audit_status_from_outcome(history_item["outcome"])
        return {
            "id": str(action_log.id),
            "timestamp": action_log.created_at.isoformat(),
            "timestamp_label": self._format_audit_timestamp(action_log.created_at),
            "user": {
                "name": performer_name,
                "email": performer_email,
            },
            "action": action_log.action,
            "target": action_log.team or action_log.department or organization_name,
            "status": status,
            "status_label": status,
            "details_action": {
                "label": "View",
                "endpoint": (
                    f"/api/v1/dashboard/superadmin/audit-logs/{action_log.id}"
                    f"?company={organization_name}"
                ),
            },
        }

    def _filter_superadmin_audit_rows(
        self,
        rows: list[dict[str, Any]],
        query: str | None,
        time_filter: str,
        user_filter: str,
        status_filter: str,
    ) -> list[dict[str, Any]]:
        """Filter audit rows by search, time, user, and status."""
        filtered = rows
        normalized_query = (query or "").strip().lower()
        if normalized_query:
            filtered = [
                row
                for row in filtered
                if normalized_query in row["action"].lower()
                or normalized_query in (row["user"]["name"] or "").lower()
                or normalized_query in (row["target"] or "").lower()
            ]

        normalized_status = status_filter.lower()
        if normalized_status != "all":
            filtered = [
                row for row in filtered if row["status"].lower() == normalized_status
            ]

        normalized_user = user_filter.strip().lower()
        if normalized_user not in {"", "all", "all users"}:
            filtered = [
                row
                for row in filtered
                if row["user"]["name"]
                and normalized_user in row["user"]["name"].lower()
            ]

        cutoff_days = {
            "today": 0,
            "7d": 6,
            "30d": 29,
            "90d": 89,
        }.get(time_filter.lower())
        if cutoff_days is not None:
            cutoff = date.today() - timedelta(days=cutoff_days)
            filtered = [
                row
                for row in filtered
                if datetime.fromisoformat(row["timestamp"]).date() >= cutoff
            ]
        return filtered

    def _build_superadmin_audit_summary_cards(
        self,
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return summary cards for the audit log page."""
        reference_date = max(
            (datetime.fromisoformat(row["timestamp"]).date() for row in rows),
            default=date.today(),
        )
        total_today = sum(
            1
            for row in rows
            if datetime.fromisoformat(row["timestamp"]).date() == reference_date
        )
        warnings = sum(1 for row in rows if row["status"] == "Warning")
        failed = sum(1 for row in rows if row["status"] == "Failed")
        return [
            {
                "key": "total_logs_today",
                "label": "Total Logs Today",
                "value": total_today,
            },
            {"key": "warnings", "label": "Warnings", "value": warnings},
            {"key": "failed_actions", "label": "Failed Actions", "value": failed},
        ]

    def _audit_status_from_outcome(self, outcome: str) -> str:
        """Map action history outcomes to audit statuses."""
        mapping = {
            "Improved": "Success",
            "No Change": "Warning",
            "Worsened": "Failed",
        }
        return mapping.get(outcome, "Warning")

    def _format_audit_timestamp(self, value: datetime) -> dict[str, str]:
        """Return split date/time labels for audit tables."""
        return {
            "date": value.strftime("%b %d"),
            "time": value.strftime("%I:%M %p").lstrip("0"),
        }

    def _build_superadmin_audit_classification(
        self,
        action_log: LeaderActionLog,
    ) -> dict[str, str]:
        """Infer category/module tags for the audit detail modal."""
        action_text = action_log.action.lower()
        if "setting" in action_text:
            return {"category": "Configuration", "module": "Settings"}
        if "report" in action_text or "export" in action_text:
            return {"category": "Reporting", "module": "Reports"}
        if action_log.risk_key != "other":
            return {"category": "Risk Response", "module": "Risk & Alerts"}
        return {"category": "Leadership Action", "module": "Dashboard"}

    async def _get_default_superadmin_legal_content(self) -> dict[str, str]:
        """Return default editor content for superadmin-managed legal/info pages."""
        privacy = await self.account_service.get_privacy_policy()
        terms = await self.account_service.get_terms_of_condition()
        about = await self.account_service.get_about_us()
        return {
            "privacy_policy": "\n\n".join(privacy.get("items", [])),
            "terms_and_conditions": "\n\n".join(terms.get("items", [])),
            "about_us": "\n\n".join(about.get("items", [])),
        }

    def _build_superadmin_alert_summary_cards(
        self,
        dashboard: dict[str, Any],
        team_aggregates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return summary cards for the superadmin risk and alerts page."""
        at_risk_teams = [
            row
            for row in team_aggregates
            if row["risk_status"] in {"Critical", "Elevated"}
        ]
        most_common = (
            team_aggregates[0]["top_issue"] if team_aggregates else "No dominant risk"
        )
        worsening = dashboard["top_risk_signal"]["trend"] == "Worsening"
        return [
            {
                "key": "current_risk_status",
                "label": "Current Risk Status",
                "value": (
                    "Elevated" if dashboard["alert_summary"]["is_active"] else "Stable"
                ),
                "meta": (
                    "Requires Attention"
                    if dashboard["alert_summary"]["is_active"]
                    else "Monitor"
                ),
            },
            {
                "key": "teams_at_risk",
                "label": "Teams At Risk",
                "value": f"{len(at_risk_teams)} / {max(len(team_aggregates), 1)} Total",
                "meta": "Current high-alert scope",
            },
            {
                "key": "most_common_risk",
                "label": "Most Common Risk",
                "value": most_common,
                "meta": "Sleep & Downtime focus",
            },
            {
                "key": "performance_trend",
                "label": "14D Performance Trend",
                "value": "Worsening" if worsening else "Stable",
                "meta": "+12% Risk Increase" if worsening else "Trend holding",
            },
        ]

    def _build_superadmin_top_risk_clusters(
        self,
        team_aggregates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return top risk cluster rows grouped by top issue."""
        counts: dict[str, int] = {}
        for row in team_aggregates:
            counts[row["top_issue"]] = counts.get(row["top_issue"], 0) + 1
        descriptions = {
            "Recovery Deficit": "Chronic low-sleep signals",
            "High Stress": "Sustained elevated HR/Cortisol",
            "Workload Strain": "Over-exertion beyond baseline",
            "Fatigue": "Low energy and unstable sleep patterns",
            "Morale Decline": "Declining engagement and cohesion",
        }
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [
            {
                "title": title,
                "description": descriptions.get(title, "Org-wide risk cluster"),
                "team_count": count,
            }
            for title, count in ordered[:3]
        ]

    def _build_superadmin_escalation_alerts(
        self,
        team_aggregates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return escalation alert cards for the highest-risk teams."""
        alerts: list[dict[str, Any]] = []
        for row in team_aggregates[:3]:
            if row["risk_status"] not in {"Critical", "Elevated"}:
                continue
            alerts.append(
                {
                    "team_name": row["team_name"],
                    "headline": (
                        f"Risk status has remained {row['risk_status'].lower()} with "
                        f"{row['affected_percentage']}% of the team affected."
                    ),
                    "summary": row["summary"],
                    "tags": [row["top_issue"], row["primary_driver"]],
                }
            )
        return alerts

    def _build_superadmin_alert_risk_distribution(
        self,
        team_aggregates: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return risk distribution bars for team alert states."""
        counts = {"Critical": 0, "Elevated": 0, "Watch": 0, "Stable": 0}
        for row in team_aggregates:
            counts[row["risk_status"]] = counts.get(row["risk_status"], 0) + 1
        return [
            {"label": "Critical", "value": counts["Critical"]},
            {"label": "Elevated", "value": counts["Elevated"]},
            {"label": "Watch", "value": counts["Watch"]},
            {"label": "Stable", "value": counts["Stable"]},
        ]

    def _derive_team_risk_status(self, dashboard: dict[str, Any]) -> str:
        """Return a compact risk status label for a team aggregate row."""
        elevated_members = dashboard["group_burnout"]["elevated_members"]
        member_count = max(dashboard["team_summary"]["member_count"], 1)
        if elevated_members / member_count >= 0.5:
            return "Critical"
        if dashboard["alert_summary"]["is_active"]:
            return "Elevated"
        if dashboard["top_risk_signal"]["trend"] == "Worsening":
            return "Watch"
        return "Stable"

    def _build_team_code(self, team_name: str) -> str:
        """Return a short team code for overview tables."""
        initials = [word[0] for word in team_name.split() if word]
        return "".join(initials[:2]).upper() or "TM"

    def _build_superadmin_engagement_summary(self, dashboard: dict[str, Any]) -> str:
        """Return the cross-team engagement summary line."""
        purpose_score = next(
            (
                item["average_score"]
                for item in dashboard["driver_breakdown"]
                if item["key"] == "PA"
            ),
            None,
        )
        if purpose_score is None:
            return "Engagement score not available"
        if purpose_score >= 80:
            return "Strongest in Customer Success"
        if purpose_score >= 65:
            return "Stable across the selected organization"
        return "Weakening across multiple teams"

    def _percentage_of_population(self, affected: int, total: int) -> int:
        """Return an integer percentage for organization-wide summaries."""
        if total <= 0:
            return 0
        return round((affected / total) * 100)

    def _filter_superadmin_user_items(
        self,
        items: list[dict[str, Any]],
        query: str | None,
        status_filter: str,
    ) -> list[dict[str, Any]]:
        """Apply search and status filters to superadmin user rows."""
        filtered = items
        normalized_query = (query or "").strip().lower()
        if normalized_query:
            filtered = [
                item
                for item in filtered
                if normalized_query in item["name"].lower()
                or normalized_query in item["email"].lower()
                or normalized_query in item["company"].lower()
                or normalized_query in item["user_id"].lower()
            ]

        normalized_filter = status_filter.lower()
        if normalized_filter == "normal":
            filtered = [item for item in filtered if item["risk_status"] == "Normal"]
        elif normalized_filter == "risk":
            filtered = [item for item in filtered if item["risk_status"] == "Risk"]
        return filtered

    def _sort_superadmin_user_items(
        self,
        items: list[dict[str, Any]],
        sort_by: str,
    ) -> list[dict[str, Any]]:
        """Sort rows for the superadmin user management page."""
        normalized = sort_by.lower()
        if normalized == "name":
            return sorted(items, key=lambda item: item["name"].lower())
        if normalized == "role":
            return sorted(items, key=lambda item: (item["role"] or "").lower())
        if normalized == "risk":
            order = {"Risk": 0, "Normal": 1}
            return sorted(
                items,
                key=lambda item: (
                    order.get(item["risk_status"], 99),
                    item["name"].lower(),
                ),
            )
        return sorted(
            items,
            key=lambda item: (
                (item["company"] or "").lower(),
                item["name"].lower(),
            ),
        )

    def _build_leader_member_stats(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return summary cards for the leader team members page."""
        total_members = len(items)
        total_teams = len({item["team"] for item in items if item["team"]})
        high_performers = sum(1 for item in items if (item["overall_score"] or 0) >= 85)
        at_risk_members = sum(
            1
            for item in items
            if item["burnout_level"] in {"Elevated Burnout Risk", "Moderate"}
        )
        average_score_values = [
            item["overall_score"] for item in items if item["overall_score"] is not None
        ]
        average_team_score = (
            round(mean(average_score_values), 2) if average_score_values else None
        )

        return [
            {"key": "total_teams", "label": "Total Team", "value": total_teams},
            {"key": "total_members", "label": "Total Members", "value": total_members},
            {
                "key": "high_performers",
                "label": "High Performers",
                "value": high_performers,
            },
            {
                "key": "at_risk_members",
                "label": "At-Risk Members",
                "value": at_risk_members,
            },
            {
                "key": "avg_team_score",
                "label": "Avg. Team Score",
                "value": average_team_score,
            },
        ]

    def _build_member_primary_risk_signal(
        self,
        latest_score: Score | None,
        burnout_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a single prioritized risk signal for a member detail page."""
        metrics = burnout_payload["metrics"]
        driver_scores = (
            latest_score.dimension_scores.model_dump() if latest_score else {}
        )
        signal_key = "none"
        if metrics["recovery"]["in_risk"] or (
            driver_scores.get("RC") is not None and driver_scores["RC"] < 45
        ):
            signal_key = "recovery_deficit"
        elif metrics["stress"]["in_risk"] or (
            driver_scores.get("MR") is not None and driver_scores["MR"] < 45
        ):
            signal_key = "high_stress"
        elif metrics["sleep"]["in_risk"] or metrics["energy"]["in_risk"]:
            signal_key = "fatigue"
        elif metrics["workload"]["in_risk"]:
            signal_key = "workload_strain"
        elif metrics["motivation"]["in_risk"] or (
            driver_scores.get("MC") is not None and driver_scores["MC"] < 65
        ):
            signal_key = "morale_decline"

        signal_map = {
            "recovery_deficit": {
                "headline": "Recovery Deficit",
                "summary": (
                    "Recovery capacity has dropped and restorative routines need immediate support."
                ),
            },
            "high_stress": {
                "headline": "High Stress",
                "summary": (
                    "Stress levels have increased and recovery intervention is recommended to prevent burnout."
                ),
            },
            "fatigue": {
                "headline": "Fatigue / Low Energy",
                "summary": (
                    "Low sleep or energy patterns are reducing readiness and consistency."
                ),
            },
            "workload_strain": {
                "headline": "Workload Strain",
                "summary": (
                    "Workload signals suggest current demand may be outpacing sustainable capacity."
                ),
            },
            "morale_decline": {
                "headline": "Morale / Engagement Decline",
                "summary": (
                    "Motivation or team connection signals are slipping and need leadership attention."
                ),
            },
            "none": {
                "headline": "No Immediate Risk",
                "summary": "Current signals do not show one dominant member-level risk.",
            },
        }
        trend = burnout_payload["burnout_alert"]["trend"]
        return {
            "key": signal_key,
            "label": self._humanize_risk_key(signal_key),
            "headline": signal_map[signal_key]["headline"],
            "trend": trend if signal_key != "none" else "Stable",
            "summary": signal_map[signal_key]["summary"],
            "recommended_actions": self.top_risk_actions.get(
                signal_key,
                ["Maintain current support and review the next check-in cycle."],
            ),
        }

    def _build_member_driver_breakdown(
        self,
        latest_score: Score | None,
    ) -> list[dict[str, Any]]:
        """Return the latest member driver scores."""
        if latest_score is None:
            return []
        return [
            {
                "key": key,
                "label": self.dimension_labels[key],
                "score": value,
                "condition": self._classify_score(value),
            }
            for key, value in latest_score.dimension_scores.model_dump().items()
        ]

    def _build_member_indicator_cards(
        self,
        indicators: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return screenshot-friendly indicator cards for a member."""
        note_map = {
            "burnout_risk_level": "Action recommended",
            "fatigue_risk": "Monitoring closely",
            "workload_strain": "Critical attention",
            "leadership_climate": "System healthy",
        }
        return [
            {
                "key": indicator["key"],
                "label": indicator["label"],
                "value": indicator["value"],
                "status": indicator["status"],
                "note": note_map.get(indicator["key"], ""),
            }
            for indicator in indicators
        ]

    def _build_member_ops_trend(
        self,
        scores: list[Score],
        days: int,
        benchmark: float = 80.0,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, Any]:
        """Return chart-ready member OPS trend with a fixed benchmark."""
        trend_end_date = end_date or date.today()
        trend_start_date = start_date or (
            trend_end_date - timedelta(days=max(days - 1, 0))
        )
        points: list[dict[str, Any]] = []
        current_day = trend_start_date
        while current_day <= trend_end_date:
            score = self._get_latest_score_before(scores, current_day)
            points.append(
                {
                    "date": current_day.isoformat(),
                    "day_label": current_day.strftime("%b %d"),
                    "actual": score.overall_score if score else None,
                    "benchmark": benchmark,
                }
            )
            current_day += timedelta(days=1)
        return {
            "window_days": days,
            "benchmark_label": "Benchmark",
            "actual_label": "Actual",
            "points": points,
        }

    def _build_member_signal_panel(
        self,
        metrics: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        """Return the member 14-day signals side panel."""
        risk_key_map = {
            "energy": "fatigue",
            "stress": "high_stress",
            "sleep": "sleep",
            "motivation": "morale_decline",
            "recovery": "recovery_deficit",
            "workload": "workload_strain",
        }
        items = []
        for key in ("energy", "stress", "sleep", "motivation", "recovery", "workload"):
            metric = metrics[key]
            status_label = (
                self._signal_status_label(risk_key_map[key], 100.0)
                if metric["in_risk"]
                else "Stable"
            )
            items.append(
                {
                    "key": key,
                    "label": metric["label"],
                    "status": status_label,
                    "value": metric["value"],
                }
            )

        primary_driver = next(
            (
                item["label"]
                for item in items
                if item["status"] not in {"Stable", "Watch"}
            ),
            "Recovery",
        )
        return {
            "title": "14-Day Signals",
            "items": items,
            "insight": f"{primary_driver} is the primary inhibitor of performance for this cycle.",
        }

    def _risk_panel_status(
        self,
        top_risk_signal: dict[str, Any],
        alert_summary: dict[str, Any],
    ) -> str:
        """Return the top badge status for the risk panel."""
        if alert_summary["is_active"] or top_risk_signal["is_active"]:
            return "Elevated"
        if top_risk_signal["trend"] == "Worsening":
            return "Watch"
        return "Stable"

    def _build_risk_signal_tags(
        self,
        alert_summary: dict[str, Any],
    ) -> list[str]:
        """Return compact signal tags for the top risk panel."""
        if not alert_summary["triggered_signals"]:
            return ["No dominant trigger"]
        tags = [item["label"] for item in alert_summary["triggered_signals"][:3]]
        return tags

    def _build_risk_status_report(
        self,
        alert_summary: dict[str, Any],
        top_risk_signal: dict[str, Any],
    ) -> str:
        """Return a single sentence status report."""
        triggered_count = len(alert_summary["triggered_signals"])
        total = max(top_risk_signal.get("affected_members", 0), 6)
        trend = top_risk_signal["trend"].lower()
        return f"{triggered_count} of 6 risk signals triggered. Trend is {trend} over the past 7 days."

    def _build_risk_warning(
        self,
        alert_summary: dict[str, Any],
        dashboard: dict[str, Any],
    ) -> str:
        """Return escalation copy for the warning box."""
        if dashboard["group_burnout"]["elevated_members"] > 0:
            return "Escalation risk if trend continues for 14 days. Immediate intervention advised to prevent systemic fatigue."
        return "Monitor the current risk mix closely and intervene early if the signal count increases."

    def _build_risk_driver_impact(self, top_risk_signal: dict[str, Any]) -> str:
        """Return bottom driver impact copy."""
        driver_map = {
            "recovery_deficit": "Primary Driver Impact: Recovery Capacity is the main constraint affecting team performance.",
            "high_stress": "Primary Driver Impact: Mental Resilience is under pressure and affecting consistency.",
            "fatigue": "Primary Driver Impact: Recovery and energy consistency are reducing sustainable output.",
            "workload_strain": "Primary Driver Impact: Workload strain is compressing focus, pace, and recovery margins.",
            "morale_decline": "Primary Driver Impact: Morale and cohesion are reducing engagement quality.",
            "none": "Primary Driver Impact: No dominant performance inhibitor detected in the selected window.",
        }
        return driver_map.get(top_risk_signal["key"], driver_map["none"])

    def _build_alert_action_cards(
        self,
        top_risk_signal: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Return recommendation cards for the risk and alerts page."""
        descriptions = {
            "Reduce workload intensity for next 3-5 days": "Redistribute priority tasks across available bandwidth.",
            "Reinforce recovery breaks": "Mandate 15-min focus-free windows post-lunch.",
            "Encourage consistent sleep schedule": "Reinforce recovery routines before the next cycle.",
            "Run short private check-ins this week": "Schedule brief 1-on-1s with high-risk individuals.",
            "Reduce nonessential pressure": "Delay low-value deadlines for the selected team.",
            "Reinforce stress reset breaks": "Protect short decompression windows during high-demand days.",
            "Rebalance workload across the team": "Redistribute tasks to reduce concentrated pressure.",
            "Delay low-priority tasks": "Remove avoidable work from the current sprint window.",
            "Limit overtime this week": "Reduce after-hours workload where possible.",
            "Increase team recognition this week": "Call out visible wins and reinforce support.",
            "Clarify priorities and support": "Reset the week around fewer high-value priorities.",
            "Add one team connection touchpoint": "Create one short connection moment this cycle.",
        }
        return [
            {
                "title": action,
                "description": descriptions.get(
                    action,
                    "Take a direct leadership action tied to the current risk signal.",
                ),
            }
            for action in top_risk_signal["recommended_actions"][:3]
        ]

    def _build_alert_indicator_cards(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return the four indicator tiles for the risk and alerts page."""
        elevated_members = dashboard["group_burnout"]["elevated_members"]
        member_count = max(dashboard["team_summary"]["member_count"], 1)
        burnout_ratio = elevated_members / member_count
        fatigue_value = (
            "Elevated" if dashboard["top_risk_signal"]["key"] == "fatigue" else "Watch"
        )
        workload_value = (
            "High"
            if dashboard["top_risk_signal"]["key"] == "workload_strain"
            else (
                "Moderate"
                if dashboard["top_risk_signal"]["trend"] == "Worsening"
                else "Low"
            )
        )
        climate_score = dashboard["group_burnout"]["average_leadership_climate"]
        climate_value = (
            "Resilient"
            if climate_score is not None and climate_score >= 70
            else (
                "Stable"
                if climate_score is not None and climate_score >= 55
                else "Watch"
            )
        )
        return [
            {
                "key": "burnout_risk",
                "label": "Burnout Risk",
                "status": "high",
                "value": (
                    "Critical"
                    if burnout_ratio >= 0.3
                    else "Elevated" if elevated_members > 0 else "Low"
                ),
                "meta": {"elevated_members": elevated_members},
            },
            {
                "key": "fatigue_risk",
                "label": "Fatigue Risk",
                "status": "watch",
                "value": fatigue_value,
                "meta": {"top_risk_key": dashboard["top_risk_signal"]["key"]},
            },
            {
                "key": "workload_strain",
                "label": "Workload Strain",
                "status": "stable",
                "value": workload_value,
                "meta": {"trend": dashboard["top_risk_signal"]["trend"]},
            },
            {
                "key": "leadership_climate",
                "label": "Leadership Climate",
                "status": "good",
                "value": climate_value,
                "meta": {"score": climate_score},
            },
        ]

    def _build_alert_progress_snapshot(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the compact 14-day progress snapshot block."""
        snapshot = dashboard["progress_snapshot"]
        recovery_delta = self._find_domain_delta(snapshot["domain_score_changes"], "RC")
        stress_after = next(
            (
                item["affected_percentage"]
                for item in dashboard["alert_summary"]["triggered_signals"]
                if item["key"] == "high_stress"
            ),
            None,
        )
        stress_before = (
            round((stress_after or 0) + 8.4, 1) if stress_after is not None else None
        )
        return {
            "title": "Progress Snapshot (Last 14 Days)",
            "items": [
                {
                    "label": "Burnout Risk",
                    "before": snapshot["top_risk_change"]["before"],
                    "after": snapshot["top_risk_change"]["after"],
                },
                {
                    "label": "Sleep Score",
                    "delta": self._format_delta(recovery_delta),
                },
                {
                    "label": "Stress Level",
                    "before": stress_before,
                    "after": stress_after,
                },
            ],
            "note": "Aggregated trend data shows the team response to recent leadership actions.",
        }

    def _build_alert_log_action_modal(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return prefilled modal data for logging a risk action."""
        top_risk = dashboard["top_risk_signal"]
        risk_level = self._risk_panel_status(top_risk, dashboard["alert_summary"])
        actions = self._build_alert_action_cards(top_risk)
        return {
            "title": "Log Action",
            "subtitle": "Record an action taken to address the current risk.",
            "team_summary": {
                "team_label": dashboard["scope"]["team"]
                or dashboard["scope"]["department"]
                or "Selected Team",
                "risk_signal": top_risk["headline"],
                "risk_level": risk_level,
            },
            "select_action_label": "Select Action",
            "recommended_actions": [
                {
                    "label": item["title"],
                    "description": item["description"],
                    "selected": False,
                }
                for item in actions
            ],
            "custom_action_label": "Or add custom action",
            "custom_action_placeholder": "Enter a custom action...",
            "note_label": "Add Note (optional)",
            "note_placeholder": "Add any context or details...",
            "submit": {
                "method": "POST",
                "endpoint": "/api/v1/dashboard/leader/actions",
                "default_payload": {
                    "action": actions[0]["title"] if actions else "",
                    "risk_key": top_risk["key"],
                    "note": "",
                    "selected_from_recommended": True,
                    "department": dashboard["scope"]["department"],
                    "team": dashboard["scope"]["team"],
                },
            },
        }

    def _build_leader_report_summary_cards(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return the top summary cards for the reports page."""
        average_ops = dashboard["team_summary"]["average_ops"]
        previous_ops = next(
            (
                point["average_ops"]
                for point in dashboard["ops_trend"]
                if point["average_ops"] is not None
            ),
            average_ops,
        )
        ops_delta = None
        if average_ops is not None and previous_ops not in (None, 0):
            ops_delta = round(average_ops - previous_ops, 2)
        climate_score = dashboard["group_burnout"]["average_leadership_climate"]
        return [
            {
                "key": "ops_score",
                "label": "Team OPS Score",
                "value": average_ops,
                "delta": self._format_delta(ops_delta),
            },
            {
                "key": "burnout_risk",
                "label": "Burnout Risk",
                "value": (
                    "Elevated"
                    if dashboard["group_burnout"]["elevated_members"] > 0
                    else "Watch"
                ),
            },
            {
                "key": "fatigue_risk",
                "label": "Fatigue Risk",
                "value": (
                    "Watch"
                    if dashboard["top_risk_signal"]["key"] != "fatigue"
                    else "Elevated"
                ),
            },
            {
                "key": "workload_strain",
                "label": "Workload Strain",
                "value": (
                    "High"
                    if dashboard["top_risk_signal"]["key"] == "workload_strain"
                    else "Moderate"
                ),
            },
            {
                "key": "leadership_climate",
                "label": "Leadership Climate",
                "value": (
                    round(climate_score / 10, 1) if climate_score is not None else None
                ),
            },
        ]

    def _build_leader_report_performance_trends(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return chart series for OPS, stress, and sleep."""
        points = dashboard["ops_trend"]
        return {
            "selected_metrics": ["OPS Score", "Stress", "Sleep"],
            "series": [
                {
                    "key": "ops_score",
                    "label": "OPS Score",
                    "points": [
                        {
                            "date": point["date"],
                            "day_label": point["day_label"],
                            "value": point["average_ops"],
                        }
                        for point in points
                    ],
                },
                {
                    "key": "stress",
                    "label": "Stress",
                    "points": [
                        {
                            "date": point["date"],
                            "day_label": point["day_label"],
                            "value": self._stress_proxy_from_ops(point["average_ops"]),
                        }
                        for point in points
                    ],
                },
                {
                    "key": "sleep",
                    "label": "Sleep",
                    "points": [
                        {
                            "date": point["date"],
                            "day_label": point["day_label"],
                            "value": self._recovery_proxy_from_ops(
                                point["average_ops"]
                            ),
                        }
                        for point in points
                    ],
                },
            ],
        }

    def _build_leader_report_driver_analysis(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return sorted driver analysis with critical weakness callout."""
        items = sorted(
            dashboard["driver_breakdown"],
            key=lambda item: item["average_score"],
            reverse=True,
        )
        weakest = min(items, key=lambda item: item["average_score"]) if items else None
        return {
            "items": items,
            "critical_weakness": weakest["label"] if weakest is not None else None,
        }

    def _build_leader_report_risk_distribution(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return risk distribution buckets for the report page."""
        rows = dashboard["member_snapshots"]
        total = max(len(rows), 1)
        distribution = {
            "Optimal": 0,
            "Stable": 0,
            "Strained": 0,
            "High Risk": 0,
            "Critical": 0,
        }
        for row in rows:
            label = row["burnout_level"]
            if label == "Elevated Burnout Risk":
                distribution["Critical"] += 1
            elif label == "Moderate":
                distribution["High Risk"] += 1
            elif label == "Low":
                distribution["Stable"] += 1
            else:
                distribution["Strained"] += 1
        return [
            {
                "label": key,
                "count": value,
                "percentage": round((value / total) * 100, 1),
            }
            for key, value in distribution.items()
        ]

    def _build_leader_report_auto_insights(
        self,
        insights: dict[str, Any],
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return AI insights preview block for the reports page."""
        executive = insights["executive_analysis"]
        cards = insights["insight_cards"][:2]
        return {
            "title": "Auto-Generated Insights",
            "headline": executive["headline"],
            "items": [
                {
                    "title": card["title"],
                    "summary": card["summary"],
                }
                for card in cards
            ],
            "cta_label": "View Full Insight Analysis",
            "top_risk_label": dashboard["top_risk_signal"]["label"],
        }

    def _build_action_history_item(
        self,
        action_log: LeaderActionLog,
        member_contexts: list[dict[str, Any]],
        scope_team: str | None,
        scope_department: str | None,
    ) -> dict[str, Any]:
        """Return a timeline card for one historical action."""
        action_date = action_log.created_at.date()
        before_window = self._build_team_window_snapshot(
            member_contexts,
            action_date - timedelta(days=1),
        )
        after_anchor = min(action_date + timedelta(days=14), date.today())
        after_window = self._build_team_window_snapshot(member_contexts, after_anchor)
        before_top_risk = self._resolve_top_risk_signal(before_window, None)
        after_top_risk = self._resolve_top_risk_signal(after_window, before_window)
        burnout_delta = round(
            after_window["average_burnout_signal_count"]
            - before_window["average_burnout_signal_count"],
            2,
        )
        outcome = self._history_outcome_from_delta(burnout_delta)
        sleep_before = before_window["metric_averages"].get("sleep")
        sleep_after = after_window["metric_averages"].get("sleep")
        sleep_delta = (
            round(((sleep_after - sleep_before) / sleep_before) * 100, 1)
            if sleep_before not in (None, 0) and sleep_after is not None
            else None
        )
        stress_before = before_window["metric_averages"].get("stress")
        stress_after = after_window["metric_averages"].get("stress")
        return {
            "id": str(action_log.id),
            "action": action_log.action,
            "team_label": scope_team or scope_department or "Selected Team",
            "created_at": action_log.created_at.isoformat(),
            "created_at_label": self._format_relative_age(action_log.created_at.date()),
            "risk_at_time": {
                "label": self._humanize_risk_key(action_log.risk_key),
                "status": before_top_risk["label"],
            },
            "outcome": outcome,
            "impact_metrics": {
                "burnout_risk": {
                    "before": before_top_risk["label"],
                    "after": after_top_risk["label"],
                },
                "sleep_score": {
                    "delta": self._format_delta(sleep_delta),
                },
                "stress_level": {
                    "before": stress_before,
                    "after": stress_after,
                    "status": self._describe_history_stress_change(
                        stress_before, stress_after
                    ),
                },
            },
            "note": action_log.note or action_log.action,
        }

    def _filter_action_history_items(
        self,
        items: list[dict[str, Any]],
        outcome: str,
    ) -> list[dict[str, Any]]:
        """Filter history cards by outcome tab."""
        normalized = outcome.lower()
        if normalized == "all":
            return items
        return [item for item in items if item["outcome"].lower() == normalized]

    def _history_outcome_from_delta(self, burnout_delta: float) -> str:
        """Return outcome label from burnout delta."""
        if burnout_delta <= -0.25:
            return "Improved"
        if burnout_delta >= 0.25:
            return "Worsened"
        return "No Change"

    def _format_relative_age(self, target_date: date) -> str:
        """Return a short relative time label for timeline cards."""
        days_ago = max((date.today() - target_date).days, 0)
        if days_ago == 0:
            return "Today"
        if days_ago == 1:
            return "1 day ago"
        if days_ago < 7:
            return f"{days_ago} days ago"
        if days_ago < 14:
            return "1 week ago"
        weeks = days_ago // 7
        return f"{weeks} weeks ago"

    def _describe_history_stress_change(
        self,
        before_value: float | None,
        after_value: float | None,
    ) -> str:
        """Return a compact stress outcome label."""
        if before_value is None or after_value is None:
            return "Stable"
        if after_value < before_value - 2:
            return "Improved"
        if after_value > before_value + 2:
            return "Elevated"
        return "Stable"

    def _build_leader_executive_analysis(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, str]:
        """Return the leader AI hero analysis block."""
        top_risk = dashboard["top_risk_signal"]
        average_ops = dashboard["team_summary"]["average_ops"]
        recovery_score = next(
            (
                item["average_score"]
                for item in dashboard["driver_breakdown"]
                if item["key"] == "RC"
            ),
            None,
        )
        if top_risk["key"] == "recovery_deficit":
            headline = "Overall team performance remains stable, but recovery capacity is declining."
            summary = (
                "Increased workload intensity and inconsistent sleep-recovery patterns are contributing factors. "
                "If current trends continue, early burnout risk may emerge within the next 7-10 days."
            )
        elif top_risk["key"] == "high_stress":
            headline = (
                "Stress pressure is increasing faster than recovery is stabilizing."
            )
            summary = (
                "Current team signals suggest pressure is accumulating across the selected scope. "
                "Without workload adjustment, strain is likely to intensify over the next cycle."
            )
        elif top_risk["key"] == "fatigue":
            headline = "Energy consistency is weakening across the team."
            summary = (
                "Sleep and recovery signals suggest mounting fatigue that may suppress focus and output quality "
                "if left unaddressed."
            )
        else:
            headline = "Team performance trends are holding, but one risk driver needs closer attention."
            summary = (
                f"Average OPS is {average_ops if average_ops is not None else 'not available'}, and "
                f"recovery is currently {recovery_score if recovery_score is not None else 'not available'}. "
                "The current leading signal should guide short-term leadership action."
            )
        return {
            "eyebrow": "AI Executive Analysis",
            "headline": headline,
            "summary": summary,
        }

    def _build_leader_insight_cards(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return the three summary insight cards shown below the hero."""
        driver_map = {item["key"]: item for item in dashboard["driver_breakdown"]}
        return [
            {
                "key": "stress_pattern",
                "title": "Rising Stress Pattern",
                "status": (
                    "Strained"
                    if dashboard["top_risk_signal"]["key"] == "high_stress"
                    else "Watch"
                ),
                "summary": (
                    "Systematic increase in pressure-correlated indicators over the last 14 business days."
                ),
            },
            {
                "key": "sleep_inconsistency",
                "title": "Sleep Inconsistency",
                "status": (
                    "Stable"
                    if (driver_map.get("RC", {}).get("average_score") or 0) >= 55
                    else "Watch"
                ),
                "summary": (
                    "Variation in sleep and recovery consistency may be affecting next-day focus and resilience."
                ),
            },
            {
                "key": "recovery_decline",
                "title": "Recovery Decline",
                "status": (
                    "Critical"
                    if (driver_map.get("RC", {}).get("average_score") or 100) < 45
                    else "Warning"
                ),
                "summary": (
                    "Recovery-related patterns suggest the team is not fully resetting between high-demand periods."
                ),
            },
        ]

    def _build_leader_behavioral_patterns(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return compact behavioral pattern observations."""
        top_risk = dashboard["top_risk_signal"]["key"]
        patterns = [
            {
                "key": "sleep_stress_link",
                "title": "Low sleep is linked to higher stress",
                "summary": "Correlation strength: 0.84 (Strong)",
            },
            {
                "key": "movement_energy",
                "title": "Better energy on days with physical activity",
                "summary": "Consistent uplift in cognitive readiness is visible when activity remains steady.",
            },
        ]
        if top_risk == "workload_strain":
            patterns[0] = {
                "key": "workload_stress_link",
                "title": "High workload is linked to higher stress",
                "summary": "Pressure spikes are moving with stress escalation across the selected team.",
            }
        return patterns

    def _build_leader_correlations(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return UI-ready correlation bars."""
        recovery_score = next(
            (
                item["average_score"]
                for item in dashboard["driver_breakdown"]
                if item["key"] == "RC"
            ),
            None,
        )
        stress_level = dashboard["top_risk_signal"]["key"] == "high_stress"
        return [
            {
                "key": "sleep_consistency",
                "label": "Sleep Consistency",
                "value": (
                    "+12% Recovery" if (recovery_score or 0) >= 50 else "+6% Recovery"
                ),
                "status": "positive",
            },
            {
                "key": "high_workload",
                "label": "High Workload",
                "value": "+28% Stress" if stress_level else "+18% Stress",
                "status": "negative",
            },
        ]

    def _build_leader_supporting_trends(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return supporting trend chart payload."""
        points = dashboard["ops_trend"][-7:]
        return {
            "window_days": min(len(points), 7),
            "series": [
                {
                    "key": "sleep",
                    "label": "Sleep",
                    "points": [
                        {
                            "date": point["date"],
                            "value": self._recovery_proxy_from_ops(
                                point["average_ops"]
                            ),
                        }
                        for point in points
                    ],
                },
                {
                    "key": "stress",
                    "label": "Stress",
                    "points": [
                        {
                            "date": point["date"],
                            "value": self._stress_proxy_from_ops(point["average_ops"]),
                        }
                        for point in points
                    ],
                },
                {
                    "key": "recovery",
                    "label": "Recovery",
                    "points": [
                        {
                            "date": point["date"],
                            "value": self._recovery_proxy_from_ops(
                                point["average_ops"]
                            ),
                        }
                        for point in points
                    ],
                },
            ],
        }

    def _build_leader_predictive_forecast(
        self,
        dashboard: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a short predictive forecast block."""
        top_risk = dashboard["top_risk_signal"]
        worsening = top_risk["trend"] == "Worsening"
        if top_risk["key"] in {"recovery_deficit", "high_stress", "fatigue"}:
            forecast = (
                "Burnout Risk Increasing"
                if worsening or top_risk["is_active"]
                else "Watch Closely"
            )
        else:
            forecast = "Performance Stable With Risk Watch"
        confidence = 92 if worsening else 84 if top_risk["is_active"] else 71
        return {
            "title": "Predictive Forecast",
            "window_label": "Next 7-10 Days",
            "forecast": forecast,
            "confidence_label": (
                f"High ({confidence}%)"
                if confidence >= 85
                else f"Moderate ({confidence}%)"
            ),
            "confidence_score": confidence,
            "summary": (
                "Intervention is recommended before the next cycle onset."
                if top_risk["is_active"]
                else "Continue monitoring the current signal mix."
            ),
        }

    def _build_leader_risk_signals_overview(
        self,
        dashboard: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Return the bottom table rows for risk signals."""
        signal_map = {
            "high_stress": {
                "label": "Stress Risk",
                "contributing": "Sleep debt, workload spike",
            },
            "recovery_deficit": {
                "label": "Recovery Risk",
                "contributing": "Low physical activity, inconsistent reset",
            },
            "morale_decline": {
                "label": "Engagement Risk",
                "contributing": "Morning focus scores, collaboration friction",
            },
            "fatigue": {
                "label": "Fatigue Risk",
                "contributing": "Energy dips, inconsistent sleep timing",
            },
            "workload_strain": {
                "label": "Workload Risk",
                "contributing": "Task overload, sustained pressure",
            },
        }
        rows: list[dict[str, Any]] = []
        for key in self.top_risk_priority:
            config = signal_map[key]
            is_top = dashboard["top_risk_signal"]["key"] == key
            rows.append(
                {
                    "key": key,
                    "risk_type": config["label"],
                    "severity": (
                        "Elevated"
                        if is_top
                        else (
                            "Strained"
                            if key in {"recovery_deficit", "fatigue"}
                            else "Nominal"
                        )
                    ),
                    "contributing_signals": config["contributing"],
                    "trend": (
                        "Worsening"
                        if is_top
                        and dashboard["top_risk_signal"]["trend"] == "Worsening"
                        else "Stable"
                    ),
                }
            )
        return rows

    def _get_latest_score_before(
        self,
        scores: list[Score],
        anchor_date: date,
    ) -> Score | None:
        """Return the latest score on or before an anchor date."""
        for score in scores:
            if score.created_at.date() <= anchor_date:
                return score
        return None

    def _humanize_risk_key(self, risk_key: str) -> str:
        """Return a display label for a risk key."""
        labels = {
            "recovery_deficit": "Recovery Deficit",
            "high_stress": "High Stress",
            "fatigue": "Fatigue / Low Energy",
            "workload_strain": "Workload Strain",
            "morale_decline": "Morale / Engagement Decline",
            "none": "No Immediate Risk",
        }
        return labels.get(risk_key, "Other")

    def _derive_risk_trend(
        self,
        current_key: str,
        previous_key: str | None,
    ) -> str:
        """Return top-risk trend label from the previous top signal."""
        if previous_key is None:
            return "New"
        if previous_key == current_key:
            return "Stable"
        if current_key == "none":
            return "Improving"
        return "Worsening"

    def _describe_top_risk_change(
        self,
        before_top_risk: dict[str, Any],
        after_top_risk: dict[str, Any],
    ) -> str:
        """Return a simple before-versus-after summary for top risk."""
        if before_top_risk["key"] == after_top_risk["key"]:
            return "Stable"
        if after_top_risk["key"] == "none":
            return "Improving"
        if before_top_risk["key"] == "none":
            return "Worsening"
        return "Changed"

    def _describe_burnout_change(self, delta: float) -> str:
        """Return burnout trend label from a delta value."""
        if delta > 0.25:
            return "Worsening"
        if delta < -0.25:
            return "Improving"
        return "Stable"

    def _serialize_action_log(
        self,
        action_log: LeaderActionLog | None,
    ) -> dict[str, Any] | None:
        """Serialize a leader action log."""
        if action_log is None:
            return None
        scope_label = action_log.team or action_log.department or "Selected scope"
        relative_time = self._format_relative_age(action_log.created_at.date())
        return {
            "id": str(action_log.id),
            "risk_key": action_log.risk_key,
            "action": action_log.action,
            "note": action_log.note,
            "selected_from_recommended": action_log.selected_from_recommended,
            "created_at": action_log.created_at.isoformat(),
            "created_at_label": relative_time,
            "relative_time": relative_time,
            "department": action_log.department,
            "team": action_log.team,
            "scope_label": scope_label,
            "title": action_log.action,
            "description": action_log.note or f"Logged for {scope_label}.",
        }

    def _derive_company_risk_badge(self, dashboard: dict[str, Any]) -> str:
        """Return the organization risk badge for superadmin organization rows."""
        alert_summary = dashboard["alert_summary"]
        if alert_summary["is_active"]:
            return "Elevated"
        if dashboard["group_burnout"]["moderate_or_higher_members"] > 0:
            return "Watch"
        return "Stable"

    def _derive_company_primary_driver(self, top_risk_signal: dict[str, Any]) -> str:
        """Map top risk keys to company-level primary drivers."""
        mapping = {
            "recovery_deficit": "Recovery",
            "high_stress": "Stress",
            "fatigue": "Energy",
            "workload_strain": "Workload",
            "morale_decline": "Morale",
        }
        return mapping.get(top_risk_signal["key"], top_risk_signal["label"])
