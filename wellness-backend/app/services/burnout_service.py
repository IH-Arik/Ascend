"""Burnout detection and leadership risk indicator service."""

from collections.abc import Iterable
from datetime import date, timedelta
from statistics import mean
from typing import Any

from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.monthly_checkin_repo import MonthlyCheckInRepository
from app.db.repositories.weekly_checkin_repo import WeeklyCheckInRepository
from app.models.assessment import DailyCheckIn, MonthlyCheckIn, WeeklyCheckIn


class BurnoutService:
    """Service for rolling burnout detection and dashboard alert payloads."""

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.daily_repository = DailyCheckInRepository()
        self.weekly_repository = WeeklyCheckInRepository()
        self.monthly_repository = MonthlyCheckInRepository()
        self.action_library = {
            "sleep": [
                "Encourage sleep and recovery time.",
                "Allow lighter duty or workload.",
                "Encourage regular breaks.",
            ],
            "energy": [
                "Reduce nonessential tasks.",
                "Encourage recovery breaks.",
                "Conduct a private check-in.",
            ],
            "stress": [
                "Conduct a private check-in.",
                "Offer support resources.",
                "Encourage stress-management practices.",
            ],
            "recovery": [
                "Encourage sleep and recovery time.",
                "Allow lighter duty or workload.",
                "Reinforce recovery culture.",
            ],
            "workload": [
                "Rebalance workload distribution.",
                "Reduce nonessential tasks.",
                "Temporarily limit overtime.",
            ],
            "motivation": [
                "Improve communication of priorities.",
                "Recognize contributions.",
                "Encourage peer support.",
            ],
        }

    async def get_dashboard_payload(self, user_id: Any) -> dict[str, Any]:
        """Return burnout indicators and alert data for dashboard consumption."""
        daily_checkins = await self.daily_repository.list_by_user_id(user_id)
        weekly_checkins = await self.weekly_repository.list_by_user_id(user_id)
        monthly_checkins = await self.monthly_repository.list_by_user_id(user_id)

        return self.build_payload_from_checkins(
            daily_checkins,
            weekly_checkins,
            monthly_checkins,
        )

    def build_payload_from_checkins(
        self,
        daily_checkins: list[DailyCheckIn],
        weekly_checkins: list[WeeklyCheckIn],
        monthly_checkins: list[MonthlyCheckIn],
    ) -> dict[str, Any]:
        """Return burnout indicators and alert data from preloaded check-ins."""
        metrics = self._build_metrics(daily_checkins, weekly_checkins, monthly_checkins)
        risk_count = sum(
            1
            for key, metric in metrics.items()
            if key != "leadership_climate" and metric["in_risk"]
        )
        history = self._build_daily_risk_history(
            daily_checkins,
            weekly_checkins,
            monthly_checkins,
        )

        return {
            "metrics": metrics,
            "dashboard_indicators": self._build_dashboard_indicators(metrics, risk_count),
            "burnout_alert": self._build_burnout_alert(metrics, risk_count, history),
        }

    # ------------------------------------------------------------------ #
    # Rolling window constants (calendar-based)                          #
    # ------------------------------------------------------------------ #
    DAILY_WINDOW_DAYS: int = 3       # last 3 calendar days
    WEEKLY_WINDOW_DAYS: int = 14     # last 2 calendar weeks
    MONTHLY_WINDOW_DAYS: int = 62    # last ~2 calendar months

    def _apply_date_windows(
        self,
        daily_checkins: list[DailyCheckIn],
        weekly_checkins: list[WeeklyCheckIn],
        monthly_checkins: list[MonthlyCheckIn],
        reference_date: date | None = None,
    ) -> tuple[list[DailyCheckIn], list[WeeklyCheckIn], list[MonthlyCheckIn]]:
        """Filter each check-in list to its respective calendar window.

        Args:
            daily_checkins:  All daily check-ins for the user.
            weekly_checkins: All weekly check-ins for the user.
            monthly_checkins: All monthly check-ins for the user.
            reference_date:  The anchor date for window calculation
                             (defaults to today when not provided).

        Returns:
            A tuple of (recent_daily, recent_weekly, recent_monthly) where
            each list contains only check-ins submitted inside its window.
        """
        anchor = reference_date or date.today()

        daily_cutoff = anchor - timedelta(days=self.DAILY_WINDOW_DAYS - 1)
        weekly_cutoff = anchor - timedelta(days=self.WEEKLY_WINDOW_DAYS - 1)
        monthly_cutoff = anchor - timedelta(days=self.MONTHLY_WINDOW_DAYS - 1)

        recent_daily = [
            c for c in daily_checkins
            if c.submitted_at.date() >= daily_cutoff
        ]
        recent_weekly = [
            c for c in weekly_checkins
            if c.submitted_at.date() >= weekly_cutoff
        ]
        recent_monthly = [
            c for c in monthly_checkins
            if c.submitted_at.date() >= monthly_cutoff
        ]
        return recent_daily, recent_weekly, recent_monthly

    def _build_metrics(
        self,
        daily_checkins: list[DailyCheckIn],
        weekly_checkins: list[WeeklyCheckIn],
        monthly_checkins: list[MonthlyCheckIn],
        reference_date: date | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Return burnout metrics using calendar-bounded rolling windows.

        Each signal is evaluated using only check-ins that fall within the
        client-specified date range:
          - Daily signals  → last 3 calendar days
          - Weekly signals → last 14 calendar days
          - Monthly signals → last 62 calendar days (~2 months)
        """
        recent_daily, recent_weekly, recent_monthly = self._apply_date_windows(
            daily_checkins, weekly_checkins, monthly_checkins, reference_date
        )

        sleep_avg = self._average(
            self._extract_sleep_hours(checkin)
            for checkin in recent_daily
        )
        energy_avg = self._average(
            self._extract_numeric(daily_checkin=checkin, question_id="dc_1")
            for checkin in recent_daily
        )
        stress_raw_avg = self._average(
            self._extract_stress_severity(checkin)
            for checkin in recent_daily
        )
        recovery_avg = self._average(
            self._extract_numeric(daily_checkin=checkin, question_id="dc_6")
            for checkin in recent_daily
        )
        workload_avg = self._average(
            list(
                self._extract_numeric(weekly_checkin=checkin, question_id="wc_8")
                for checkin in recent_weekly
            )
            + list(
                self._extract_numeric(monthly_checkin=checkin, question_id="mc_10")
                for checkin in recent_monthly
            )
        )
        motivation_avg = self._average(
            list(
                self._extract_numeric(daily_checkin=checkin, question_id="dc_4")
                for checkin in recent_daily
            )
            + list(
                self._extract_numeric(monthly_checkin=checkin, question_id="mc_8")
                for checkin in recent_monthly
            )
        )
        leadership_climate_avg = self._average(
            list(
                self._extract_numeric(weekly_checkin=checkin, question_id="wc_9")
                for checkin in recent_weekly
            )
            + list(
                self._extract_numeric(monthly_checkin=checkin, question_id="mc_11")
                for checkin in recent_monthly
            )
            + list(
                self._extract_numeric(monthly_checkin=checkin, question_id="mc_12")
                for checkin in recent_monthly
            )
        )

        return {
            "sleep": self._metric_payload(
                "Sleep",
                sleep_avg,
                sleep_avg is not None and sleep_avg < 6.0,
                "avg < 6 hours over last 3 daily check-ins",
            ),
            "energy": self._metric_payload(
                "Energy",
                energy_avg,
                energy_avg is not None and energy_avg < 50.0,
                "avg score < 50 over last 3 daily check-ins",
            ),
            "stress": self._metric_payload(
                "Stress",
                stress_raw_avg,
                stress_raw_avg is not None and stress_raw_avg > 60.0,
                "avg severity > 60 over last 3 daily check-ins",
            ),
            "recovery": self._metric_payload(
                "Recovery",
                recovery_avg,
                recovery_avg is not None and recovery_avg < 50.0,
                "avg score < 50 over last 3 daily check-ins",
            ),
            "workload": self._metric_payload(
                "Workload",
                workload_avg,
                workload_avg is not None and workload_avg < 50.0,
                "avg score < 50 across recent weekly/monthly check-ins",
            ),
            "motivation": self._metric_payload(
                "Motivation",
                motivation_avg,
                motivation_avg is not None and motivation_avg < 50.0,
                "avg score < 50 across recent daily/monthly check-ins",
            ),
            "leadership_climate": self._metric_payload(
                "Leadership Climate",
                leadership_climate_avg,
                leadership_climate_avg is not None and leadership_climate_avg < 50.0,
                "avg support/recognition score < 50 across recent leadership items",
            ),
        }

    def _build_dashboard_indicators(
        self,
        metrics: dict[str, dict[str, Any]],
        risk_count: int,
    ) -> list[dict[str, Any]]:
        """Return the minimum-launch dashboard indicators."""
        fatigue_risk = sum(
            1 for key in ("sleep", "energy", "recovery") if metrics[key]["in_risk"]
        )
        workload_risk = sum(
            1 for key in ("workload", "stress") if metrics[key]["in_risk"]
        )
        leadership_climate = metrics["leadership_climate"]["value"]

        return [
            {
                "key": "burnout_risk_level",
                "label": "Burnout Risk Level",
                "value": self._burnout_level(risk_count),
                "status": self._status_from_count(risk_count, elevated_at=4),
                "meta": {"signals_in_risk": risk_count, "total_signals": 6},
            },
            {
                "key": "fatigue_risk",
                "label": "Fatigue Risk",
                "value": self._risk_label(fatigue_risk, high_at=3, medium_at=1),
                "status": self._status_from_count(fatigue_risk, elevated_at=3),
                "meta": {"triggered_components": fatigue_risk, "components": 3},
            },
            {
                "key": "workload_strain",
                "label": "Workload Strain",
                "value": self._risk_label(workload_risk, high_at=2, medium_at=1),
                "status": self._status_from_count(workload_risk, elevated_at=2),
                "meta": {"triggered_components": workload_risk, "components": 2},
            },
            {
                "key": "leadership_climate",
                "label": "Leadership Climate",
                "value": self._climate_label(leadership_climate),
                "status": self._status_from_score(leadership_climate),
                "meta": {"score": leadership_climate},
            },
        ]

    def _build_burnout_alert(
        self,
        metrics: dict[str, dict[str, Any]],
        risk_count: int,
        history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return the burnout alert card payload."""
        triggered = [
            {
                "key": key,
                "label": metric["label"],
                "value": metric["value"],
                "threshold": metric["threshold_text"],
            }
            for key, metric in metrics.items()
            if key != "leadership_climate" and metric["in_risk"]
        ]
        trend = self._derive_trend(history)
        consecutive_elevated_days = self._count_consecutive_elevated_days(history)
        alert_active = risk_count >= 4

        actions: list[str] = []
        for item in triggered:
            actions.extend(self.action_library.get(item["key"], []))
        actions = list(dict.fromkeys(actions))

        return {
            "is_active": alert_active,
            "level": "Elevated Burnout Risk" if alert_active else self._burnout_level(risk_count),
            "signals_in_risk": risk_count,
            "total_signals": 6,
            "triggered_signals": triggered,
            "recommended_actions_preview": actions[:5],
            "recommended_actions_all": actions,
            "trend": trend,
            "consecutive_elevated_days": consecutive_elevated_days,
            "escalated": consecutive_elevated_days >= 14,
            "escalation_target": "Higher leadership / HR / command"
            if consecutive_elevated_days >= 14
            else None,
            "history": history[-14:],
        }

    def _build_daily_risk_history(
        self,
        daily_checkins: list[DailyCheckIn],
        weekly_checkins: list[WeeklyCheckIn],
        monthly_checkins: list[MonthlyCheckIn],
    ) -> list[dict[str, Any]]:
        """Return a day-by-day burnout risk history using calendar-anchored rolling windows.

        For each day in history, the rolling window is anchored to that
        specific date — so a day's burnout score reflects only check-ins
        that would have been inside the window on that day, not all prior
        records.
        """
        history: list[dict[str, Any]] = []
        ordered_daily = sorted(daily_checkins, key=lambda item: item.submitted_at)
        ordered_weekly = sorted(weekly_checkins, key=lambda item: item.submitted_at)
        ordered_monthly = sorted(monthly_checkins, key=lambda item: item.submitted_at)

        for current_checkin in ordered_daily:
            current_day = current_checkin.submitted_at.date()
            metrics = self._build_metrics(
                [
                    item
                    for item in daily_checkins
                    if item.submitted_at.date() <= current_day
                ],
                [
                    item
                    for item in ordered_weekly
                    if item.submitted_at.date() <= current_day
                ],
                [
                    item
                    for item in ordered_monthly
                    if item.submitted_at.date() <= current_day
                ],
                reference_date=current_day,
            )
            risk_count = sum(
                1
                for key, metric in metrics.items()
                if key != "leadership_climate" and metric["in_risk"]
            )
            history.append(
                {
                    "date": current_day.isoformat(),
                    "risk_count": risk_count,
                    "level": self._burnout_level(risk_count),
                    "is_elevated": risk_count >= 4,
                }
            )
        return history

    def _extract_sleep_hours(self, checkin: DailyCheckIn) -> float | None:
        """Return representative hours slept from the daily sleep answer."""
        answer = self._find_answer(checkin.answers, "dc_5")
        if answer is None:
            return None
        hour_map = {
            "Less than 4": 3.5,
            "4-5": 4.5,
            "6-7": 6.5,
            "7-8": 7.5,
            "More than 8": 8.5,
        }
        return hour_map.get(answer.answer_text)

    def _extract_stress_severity(self, checkin: DailyCheckIn) -> float | None:
        """Return raw stress severity where higher means worse stress."""
        answer = self._find_answer(checkin.answers, "dc_3")
        if answer is None:
            return None
        stress_map = {
            "Very low": 0.0,
            "Low": 25.0,
            "About average": 50.0,
            "High": 75.0,
            "Very high": 100.0,
        }
        return stress_map.get(answer.answer_text)

    def _extract_numeric(
        self,
        question_id: str,
        daily_checkin: DailyCheckIn | None = None,
        weekly_checkin: WeeklyCheckIn | None = None,
        monthly_checkin: MonthlyCheckIn | None = None,
    ) -> float | None:
        """Return a stored numeric score for a selected answer."""
        checkin = daily_checkin or weekly_checkin or monthly_checkin
        if checkin is None:
            return None
        answer = self._find_answer(checkin.answers, question_id)
        return answer.numeric_value if answer is not None else None

    def _find_answer(
        self,
        answers: Iterable[Any],
        question_id: str,
    ) -> Any | None:
        """Return the first answer matching a question id."""
        return next(
            (answer for answer in answers if str(answer.question_id) == question_id),
            None,
        )

    def _average(self, values: Iterable[float | None]) -> float | None:
        """Return the average of non-null values."""
        cleaned = [value for value in values if value is not None]
        return round(mean(cleaned), 2) if cleaned else None

    def _metric_payload(
        self,
        label: str,
        value: float | None,
        in_risk: bool,
        threshold_text: str,
    ) -> dict[str, Any]:
        """Return a standard metric payload."""
        return {
            "label": label,
            "value": value,
            "in_risk": in_risk,
            "threshold_text": threshold_text,
        }

    def _burnout_level(self, risk_count: int) -> str:
        """Return the burnout risk level from triggered signal count."""
        if risk_count >= 4:
            return "Elevated"
        if risk_count >= 2:
            return "Moderate"
        if risk_count >= 1:
            return "Guarded"
        return "Low"

    def _risk_label(self, count: int, high_at: int, medium_at: int) -> str:
        """Return a generic risk label from a triggered component count."""
        if count >= high_at:
            return "High"
        if count >= medium_at:
            return "Moderate"
        return "Low"

    def _climate_label(self, score: float | None) -> str:
        """Return a climate summary label from a support score."""
        if score is None:
            return "Not Enough Data"
        if score >= 70:
            return "Supportive"
        if score >= 50:
            return "Watch"
        return "Strained"

    def _status_from_count(self, count: int, elevated_at: int) -> str:
        """Return a frontend-friendly status tag from a risk count."""
        if count >= elevated_at:
            return "critical"
        if count >= 1:
            return "warning"
        return "steady"

    def _status_from_score(self, score: float | None) -> str:
        """Return a frontend-friendly status tag from a positive score."""
        if score is None:
            return "steady"
        if score < 50:
            return "critical"
        if score < 70:
            return "warning"
        return "success"

    def _derive_trend(self, history: list[dict[str, Any]]) -> str:
        """Return burnout trend state from recent history."""
        if not history:
            return "New"
        if len(history) == 1:
            return "New"

        latest_count = history[-1]["risk_count"]
        prior_counts = [item["risk_count"] for item in history[-8:-1]]
        if not prior_counts:
            return "New"

        prior_average = mean(prior_counts)
        if latest_count > prior_average + 0.5:
            return "Worsening"
        if latest_count < prior_average - 0.5:
            return "Improving"
        return "Stable"

    def _count_consecutive_elevated_days(self, history: list[dict[str, Any]]) -> int:
        """Return trailing consecutive days with elevated burnout risk."""
        streak = 0
        for item in reversed(history):
            if not item["is_elevated"]:
                break
            streak += 1
        return streak
