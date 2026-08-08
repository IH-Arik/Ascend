"""Monthly review generation service.

Composes real data from check-ins, workouts, OFT, and provider messages into
one summary, matching the "30-day recap" / "In this review" Monthly Review
screen. See app/schemas/monthly_review.py for what is deliberately left out
(provider sign-off/locking, medical records) and why.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.recommendation_rules import COMPONENT_PRIORITY_ORDER
from app.core.roles import ROLE_PTIM, ROLE_SCS
from app.models.checkin_answer import CheckinAnswer
from app.models.message import Message
from app.models.ops_snapshot import OpsSnapshot
from app.models.user import User
from app.services.dashboard_service import DashboardService
from app.services.oft_service import OFTService
from app.services.workout_service import WorkoutService

REVIEW_WINDOW_DAYS = 30
PROVIDER_ROLES = {ROLE_SCS, ROLE_PTIM}
PROVIDER_NOTE_LIMIT = 5


class MonthlyReviewService:
    """Generate the on-demand monthly review payload."""

    def __init__(self) -> None:
        self.dashboard_service = DashboardService()
        self.oft_service = OFTService()
        self.workout_service = WorkoutService()

    async def generate(self, user: User) -> dict[str, Any]:
        """Build the monthly review for the trailing 30-day window."""
        today = date.today()
        period_start = today - timedelta(days=REVIEW_WINDOW_DAYS)
        now = datetime.now(timezone.utc)

        snapshots_60d = await self.dashboard_service.get_recent_snapshots(user, REVIEW_WINDOW_DAYS * 2)
        recent = [s for s in snapshots_60d if s.snapshot_date >= period_start]
        prior = [s for s in snapshots_60d if s.snapshot_date < period_start]

        thirty_day_recap = self.dashboard_service.build_driver_overview(
            user, recent, today, REVIEW_WINDOW_DAYS
        )
        average_ops_score = self._average_ops(recent)
        average_ops_delta = (
            round(average_ops_score - self._average_ops(prior), 2)
            if average_ops_score is not None and self._average_ops(prior) is not None
            else None
        )

        daily_checkins = await self._daily_checkin_recap(user, period_start, today)
        workout_summary = await self.workout_service.get_summary(user, REVIEW_WINDOW_DAYS)
        oft_status = await self.oft_service.get_status_for_user(user)
        provider_notes = await self._recent_provider_notes(user)

        return {
            "review_status": "draft",
            "period_label": today.strftime("%B %Y"),
            "period_start": period_start.isoformat(),
            "period_end": today.isoformat(),
            "generated_at": now.isoformat(),
            "thirty_day_recap": thirty_day_recap,
            "average_ops_score": average_ops_score,
            "average_ops_delta": average_ops_delta,
            "daily_checkins": daily_checkins,
            "workout_summary": workout_summary,
            "oft_status": oft_status,
            "provider_notes": provider_notes,
        }

    def _average_ops(self, snapshots: list[OpsSnapshot]) -> float | None:
        """Return the average OPS score across a set of snapshots."""
        scores = [s.ops_score for s in snapshots if s.ops_score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 2)

    async def _daily_checkin_recap(
        self, user: User, period_start: date, today: date
    ) -> dict[str, Any]:
        """Return daily check-in cadence over the review period."""
        answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id,
            CheckinAnswer.cadence == "daily",
            CheckinAnswer.checkin_date >= period_start,
        ).to_list()
        days_logged = len({a.checkin_date for a in answers})
        days_total = (today - period_start).days
        cadence_percent = round((days_logged / days_total) * 100, 1) if days_total else 0.0
        return {
            "days_logged": days_logged,
            "days_total": days_total,
            "cadence_percent": cadence_percent,
        }

    async def _recent_provider_notes(self, user: User) -> list[dict[str, Any]]:
        """Return recent messages sent to this user by an SCS/PT-IM provider."""
        messages = await Message.find(Message.recipient_id == user.id).to_list()
        provider_messages = [m for m in messages if m.sender_role in PROVIDER_ROLES]
        provider_messages.sort(key=lambda item: item.created_at, reverse=True)
        top = provider_messages[:PROVIDER_NOTE_LIMIT]

        sender_ids = {m.sender_id for m in top}
        senders = {u.id: u for u in await User.find({"_id": {"$in": list(sender_ids)}}).to_list()}

        return [
            {
                "sender_name": senders[m.sender_id].full_name if m.sender_id in senders else None,
                "sender_role": m.sender_role,
                "body": m.body,
                "created_at": m.created_at.isoformat(),
            }
            for m in top
        ]
