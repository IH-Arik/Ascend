"""Performance report service."""

from calendar import month_name
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.score_repo import ScoreRepository
from app.models.assessment import DailyCheckIn
from app.models.score import Score


class ReportService:
    """Service for performance report aggregation."""

    def __init__(self) -> None:
        """Initialize repository dependencies and presentation mappings."""
        self.score_repository = ScoreRepository()
        self.daily_checkin_repository = DailyCheckInRepository()
        self.dimension_labels = {
            "PC": "Physical Capacity",
            "MR": "Mental Resilience",
            "MC": "Morale & Cohesion",
            "PA": "Purpose Alignment",
            "RC": "Recovery Capacity",
        }
        self.dimension_colors = {
            "PC": "#4F8EF7",
            "MR": "#A855F7",
            "RC": "#22C55E",
            "PA": "#F97316",
            "MC": "#06B6D4",
        }

    async def get_performance_report(
        self,
        user_id: Any,
        selected_week: str,
        selected_month: int,
        selected_year: int,
    ) -> dict[str, Any]:
        """Return the full performance report payload."""
        scores = await self.score_repository.list_by_user_id(user_id)
        daily_checkins = await self.daily_checkin_repository.list_by_user_id(user_id)

        filtered_scores = self._filter_scores(scores, selected_week, selected_month, selected_year)
        is_fallback_data = False
        if not filtered_scores:
            filtered_scores = self._fallback_scores(scores)
            is_fallback_data = True

        filtered_daily = self._filter_daily_checkins(
            daily_checkins,
            selected_week,
            selected_month,
            selected_year,
        )

        latest_score = filtered_scores[0] if filtered_scores else None

        # Compare against previous calendar month (not just previous item in filtered set)
        prev_month = selected_month - 1 if selected_month > 1 else 12
        prev_year = selected_year if selected_month > 1 else selected_year - 1
        prev_month_scores = self._filter_scores(scores, "all", prev_month, prev_year)
        prev_month_latest = prev_month_scores[0] if prev_month_scores else None

        period_label = self._build_period_label(selected_week, selected_month, selected_year)

        return {
            "filters": self._build_filters(scores, selected_week, selected_month, selected_year),
            "ops_summary": self._build_ops_summary(
                latest_score,
                prev_month_latest,
                selected_month,
                selected_year,
            ),
            "ops_trend": self._build_ops_trend(filtered_scores, selected_month, selected_year),
            "driver_trends": self._build_driver_trends(filtered_scores),
            "behavior_trends": self._build_behavior_trends(filtered_daily),
            "performance_summary": self._build_performance_summary(filtered_scores),
            "is_fallback_data": is_fallback_data,
            "period_label": period_label,
        }

    def _filter_scores(
        self,
        scores: list[Score],
        selected_week: str,
        selected_month: int,
        selected_year: int,
    ) -> list[Score]:
        """Filter score history by selected year, month, and week slot."""
        filtered = [
            score
            for score in scores
            if score.created_at.year == selected_year and score.created_at.month == selected_month
        ]
        if selected_week == "all":
            return filtered

        week_slot = int(selected_week)
        start_day = ((week_slot - 1) * 7) + 1
        end_day = min(start_day + 6, self._days_in_month(selected_year, selected_month))
        return [
            score
            for score in filtered
            if start_day <= score.created_at.day <= end_day
        ]

    def _filter_daily_checkins(
        self,
        checkins: list[DailyCheckIn],
        selected_week: str,
        selected_month: int,
        selected_year: int,
    ) -> list[DailyCheckIn]:
        """Filter daily check-ins by selected year, month, and week slot."""
        filtered = [
            checkin
            for checkin in checkins
            if checkin.submitted_at.year == selected_year
            and checkin.submitted_at.month == selected_month
        ]
        if selected_week == "all":
            return filtered

        week_slot = int(selected_week)
        start_day = ((week_slot - 1) * 7) + 1
        end_day = min(start_day + 6, self._days_in_month(selected_year, selected_month))
        return [
            checkin
            for checkin in filtered
            if start_day <= checkin.submitted_at.day <= end_day
        ]

    def _fallback_scores(self, scores: list[Score]) -> list[Score]:
        """Return a fallback slice of recent scores when the requested period is empty."""
        return scores[:5]

    def _build_filters(
        self,
        scores: list[Score],
        selected_week: str,
        selected_month: int,
        selected_year: int,
    ) -> dict[str, Any]:
        """Build report filter options and selections."""
        available_years = sorted({score.created_at.year for score in scores}, reverse=True)
        if not available_years:
            available_years = [datetime.utcnow().year]

        return {
            "weeks": [
                {"label": "All", "value": "all"},
                {"label": "1 Week", "value": 1},
                {"label": "2 Week", "value": 2},
                {"label": "3 Week", "value": 3},
                {"label": "4 Week", "value": 4},
            ],
            "months": [
                {"label": month_name[index], "value": index}
                for index in range(1, 13)
            ],
            "years": [{"label": str(year), "value": year} for year in available_years],
            "selected_week": selected_week,
            "selected_month": selected_month,
            "selected_year": selected_year,
        }

    def _build_ops_summary(
        self,
        latest_score: Score | None,
        prev_month_score: Score | None,
        selected_month: int,
        selected_year: int,
    ) -> dict[str, Any]:
        """Build the OPS summary card with explicit monthly comparison."""
        prev_month = selected_month - 1 if selected_month > 1 else 12
        prev_month_label = month_name[prev_month]
        comparison_label = f"vs {prev_month_label}"

        if latest_score is None:
            return {
                "overall_score": 0.0,
                "status": "No Data",
                "percentage_change": 0.0,
                "progress_value": 0.0,
                "comparison_label": comparison_label,
            }

        percentage_change = 0.0
        if prev_month_score and prev_month_score.overall_score:
            percentage_change = round(
                ((latest_score.overall_score - prev_month_score.overall_score)
                 / prev_month_score.overall_score) * 100,
                2,
            )

        return {
            "overall_score": latest_score.overall_score,
            "status": self._derive_status(latest_score.overall_score),
            "percentage_change": percentage_change,
            "progress_value": latest_score.overall_score,
            "comparison_label": comparison_label,
        }

    def _build_ops_trend(
        self,
        filtered_scores: list[Score],
        selected_month: int,
        selected_year: int,
    ) -> list[dict[str, Any]]:
        """Build weekly OPS trend bars for the selected month."""
        buckets: list[tuple[str, int, int]] = [
            ("WEEK 1", 1, 7),
            ("WEEK 2", 8, 14),
            ("WEEK 3", 15, 21),
            ("WEEK 4", 22, self._days_in_month(selected_year, selected_month)),
        ]
        trend: list[dict[str, Any]] = []
        for label, start_day, end_day in buckets:
            values = [
                score.overall_score
                for score in filtered_scores
                if start_day <= score.created_at.day <= end_day
            ]
            trend.append(
                {
                    "label": label,
                    "value": round(mean(values), 2) if values else 0.0,
                    "is_current": False,
                }
            )

        latest_value = filtered_scores[0].overall_score if filtered_scores else 0.0
        trend.append({"label": "CURRENT", "value": latest_value, "is_current": True})
        return trend

    def _build_driver_trends(self, filtered_scores: list[Score]) -> list[dict[str, Any]]:
        """Build driver trend cards from the selected scores."""
        if not filtered_scores:
            return []

        latest = filtered_scores[0].dimension_scores.model_dump()
        oldest = filtered_scores[-1].dimension_scores.model_dump()
        trend_cards: list[dict[str, Any]] = []

        for key, label in self.dimension_labels.items():
            score_history = [
                score.dimension_scores.model_dump().get(key, 0.0)
                for score in reversed(filtered_scores[:4])
            ]
            delta = round(latest[key] - oldest[key], 2)
            trend_cards.append(
                {
                    "key": key,
                    "label": label,
                    "current_score": latest[key],
                    "delta": delta,
                    "delta_label": self._format_delta(delta),
                    "color": self.dimension_colors[key],
                    "sparkline": score_history,
                }
            )
        return trend_cards

    def _build_behavior_trends(self, filtered_daily: list[DailyCheckIn]) -> list[dict[str, Any]]:
        """Build behavior trend rows from daily check-ins."""
        recent_checkins = list(reversed(filtered_daily[:7]))
        sleep_bars = [self._extract_behavior_score(checkin, {"dc_5", "dc_6"}) for checkin in recent_checkins]
        stress_bars = [
            100.0 - self._extract_behavior_score(checkin, {"dc_3"})
            for checkin in recent_checkins
        ]
        activity_bars = [self._extract_behavior_score(checkin, {"dc_7"}) for checkin in recent_checkins]

        return [
            {
                "key": "sleep_quality",
                "label": "Sleep Quality",
                "status": self._behavior_status(sleep_bars),
                "bars": self._normalize_bar_series(sleep_bars),
                "color_scale": ["#bfecec", "#93dfde", "#68d1cf", "#3dc2c0", "#16b3b0", "#0ea5a6", "#059597"],
            },
            {
                "key": "stress_levels",
                "label": "Stress Levels",
                "status": self._behavior_status(stress_bars, inverse=True),
                "bars": self._normalize_bar_series(stress_bars),
                "color_scale": ["#f9d0d8", "#f7b4c1", "#f9e78f", "#9de9c3", "#76ddb0", "#9fe1c0", "#c6ecd7"],
            },
            {
                "key": "daily_activity",
                "label": "Daily Activity",
                "status": self._behavior_status(activity_bars),
                "bars": self._normalize_bar_series(activity_bars),
                "color_scale": ["#d3dae5", "#a9b9d0", "#8da2bf", "#6d86aa", "#486992", "#163d73", "#123664"],
            },
        ]

    def _build_performance_summary(self, filtered_scores: list[Score]) -> str:
        """Build the narrative performance summary."""
        if not filtered_scores:
            return "There is not enough performance data yet to build a report summary."

        latest = filtered_scores[0].dimension_scores.model_dump()
        oldest = filtered_scores[-1].dimension_scores.model_dump()
        strongest_key = max(latest.items(), key=lambda item: item[1])[0]
        weakest_delta_key = min(
            latest.keys(),
            key=lambda key: latest[key] - oldest.get(key, latest[key]),
        )
        strongest_label = self.dimension_labels[strongest_key].lower()
        weakest_label = self.dimension_labels[weakest_delta_key].lower()
        return (
            f"Your {strongest_label} is strong, but {weakest_label} has shifted more slowly "
            f"during this period. Improving sleep, recovery, and consistency may help stabilize overall performance."
        )

    def _extract_behavior_score(self, checkin: DailyCheckIn, question_ids: set[str]) -> float:
        """Extract an average numeric value from selected daily check-in answers."""
        values = [
            answer.numeric_value
            for answer in checkin.answers
            if str(answer.question_id) in question_ids
        ]
        return round(mean(values), 2) if values else 0.0

    def _normalize_bar_series(self, values: list[float]) -> list[float]:
        """Normalize a short series to a 0-100 range."""
        normalized = [round(min(max(value, 0.0), 100.0), 2) for value in values]
        while len(normalized) < 7:
            normalized.insert(0, 0.0)
        return normalized[-7:]

    def _behavior_status(self, values: list[float], inverse: bool = False) -> str:
        """Return a frontend-friendly behavior status label."""
        if not values:
            return "No Data"

        avg_value = mean(values)
        if inverse:
            if avg_value <= 40:
                return "Low"
            if avg_value <= 70:
                return "Low-Medium"
            return "High"

        if avg_value >= 80:
            return "High"
        if avg_value >= 50:
            return "Low-Medium"
        return "Low"

    def _derive_status(self, overall_score: float) -> str:
        """Return a report-friendly status label."""
        if overall_score >= 85:
            return "Optimal"
        if overall_score >= 70:
            return "Stable"
        if overall_score >= 55:
            return "Strained"
        if overall_score >= 40:
            return "High Risk"
        return "Critical"

    def _format_delta(self, delta: float) -> str:
        """Format a signed driver delta label in score points (not percentage)."""
        if abs(delta) < 1:
            return "Stable"
        sign = "+" if delta > 0 else ""
        return f"{sign}{delta:.0f} pts"

    def _build_period_label(
        self,
        selected_week: str,
        selected_month: int,
        selected_year: int,
    ) -> str:
        """Return a human-readable label for the selected report period."""
        month_label = month_name[selected_month]
        if selected_week == "all":
            return f"All of {month_label} {selected_year}"
        return f"{month_label} {selected_year} - Week {selected_week}"

    def _days_in_month(self, year: int, month: int) -> int:
        """Return the number of days in a given month."""
        if month == 12:
            return 31
        next_month = date(year + (month // 12), (month % 12) + 1, 1)
        return (next_month - timedelta(days=1)).day

