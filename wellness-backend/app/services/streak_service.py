"""Behavior streak calculation service."""

from datetime import datetime, date, timedelta

from beanie import PydanticObjectId

from app.db.repositories.behavior_log_repo import BehaviorLogRepository
from app.models.behavior import BehaviorLog, BehaviorType


class StreakService:
    """Service for engagement and behavior streak calculations."""

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.behavior_log_repository = BehaviorLogRepository()

    async def get_behavior_streaks(
        self,
        user_id: PydanticObjectId,
    ) -> list[dict[str, int | str]]:
        """Return all dashboard streak cards for a user."""
        behavior_logs = await self.behavior_log_repository.list_by_user_id(user_id)
        behavior_by_day = self._build_behavior_map(behavior_logs)
        streak_definitions: dict[str, BehaviorType] = {
            "sleep": BehaviorType.INTENTIONAL_SLEEP_ROUTINE,
            "movement": BehaviorType.PHYSICAL_ACTIVITY,
            "recovery": BehaviorType.RECOVERY_PRACTICE,
            "reflection": BehaviorType.GRATITUDE_REFLECTION,
        }

        streaks: list[dict[str, int | str]] = []
        for streak_type, behavior_type in streak_definitions.items():
            current_days = self._calculate_consecutive_days(
                behavior_by_day,
                behavior_type,
            )
            streaks.append(
                {
                    "type": streak_type,
                    "current_days": current_days,
                    "status": self._get_streak_status(current_days),
                }
            )
        return streaks

    async def get_current_streak(self, user_id: PydanticObjectId) -> int:
        """Return the reflection streak for a user."""
        behavior_logs = await self.behavior_log_repository.list_by_user_id(user_id)
        behavior_by_day = self._build_behavior_map(behavior_logs)
        return self._calculate_consecutive_days(
            behavior_by_day,
            BehaviorType.GRATITUDE_REFLECTION,
        )

    async def get_reflection_streak_summary(
        self,
        user_id: PydanticObjectId,
    ) -> dict[str, object]:
        """Return streak count, current week progress, and motivational text."""
        behavior_logs = await self.behavior_log_repository.list_by_user_id(user_id)
        behavior_by_day = self._build_behavior_map(behavior_logs)
        reflection_streak_days = self._calculate_consecutive_days(
            behavior_by_day,
            BehaviorType.GRATITUDE_REFLECTION,
        )
        week_progress = self._build_current_week_progress(behavior_by_day)
        completed_days = sum(1 for item in week_progress if bool(item["completed"]))

        return {
            "reflection_streak_days": reflection_streak_days,
            "week_progress": week_progress,
            "weekly_completed_days": completed_days,
            "motivation_message": self._get_motivation_message(
                reflection_streak_days,
                completed_days,
            ),
        }

    async def update_streak(self, user_id: PydanticObjectId) -> int:
        """Return the recalculated reflection streak for a user."""
        return await self.get_current_streak(user_id)

    async def check_achievements(self, user_id: PydanticObjectId) -> list[str]:
        """Return simple streak-based achievements for a user."""
        current_streak = await self.get_current_streak(user_id)
        achievements: list[str] = []
        if current_streak >= 3:
            achievements.append("3-day reflection streak")
        if current_streak >= 7:
            achievements.append("7-day reflection streak")
        return achievements

    def _calculate_consecutive_days(
        self,
        behavior_by_day: dict[date, set[BehaviorType]],
        behavior_type: BehaviorType,
    ) -> int:
        """Calculate consecutive day streak count from behavior logs."""
        if not behavior_by_day:
            return 0

        today = datetime.utcnow().date()
        current_day = (
            today
            if behavior_type in behavior_by_day.get(today, set())
            else today - timedelta(days=1)
        )
        streak = 0

        while behavior_type in behavior_by_day.get(current_day, set()):
            streak += 1
            current_day -= timedelta(days=1)

        return streak

    def _build_current_week_progress(
        self,
        behavior_by_day: dict[date, set[BehaviorType]],
    ) -> list[dict[str, object]]:
        """Return Monday-to-Sunday reflection completion data for the current week."""
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday())
        day_labels = ["M", "T", "W", "T", "F", "S", "S"]
        progress: list[dict[str, object]] = []

        for offset, label in enumerate(day_labels):
            current_day = week_start + timedelta(days=offset)
            progress.append(
                {
                    "day_label": label,
                    "date": current_day.isoformat(),
                    "completed": BehaviorType.GRATITUDE_REFLECTION
                    in behavior_by_day.get(current_day, set()),
                    "is_today": current_day == today,
                }
            )

        return progress

    def _build_behavior_map(
        self,
        behavior_logs: list[BehaviorLog],
    ) -> dict[date, set[BehaviorType]]:
        """Collapse behavior logs into a per-day set of completed behaviors."""
        behavior_by_day: dict[date, set[BehaviorType]] = {}
        for log in behavior_logs:
            behavior_by_day.setdefault(log.behavior_date, set()).update(log.behaviors)
        return behavior_by_day

    def _get_streak_status(self, current_days: int) -> str:
        """Return a frontend-friendly streak status."""
        if current_days >= 7:
            return "strong"
        if current_days >= 3:
            return "active"
        if current_days >= 1:
            return "building"
        return "idle"

    def _get_motivation_message(
        self,
        reflection_streak_days: int,
        weekly_completed_days: int,
    ) -> str:
        """Return a motivational message based on streak momentum."""
        if reflection_streak_days >= 7:
            return "Outstanding consistency. You are building a strong weekly rhythm."
        if reflection_streak_days >= 4:
            return "You're on a roll! Keep it up to reach your weekly goal."
        if reflection_streak_days >= 2:
            return "Good momentum. A few more check-ins will strengthen your routine."
        if weekly_completed_days >= 1:
            return "Nice start. Keep checking in daily to build your streak."
        return "Start your daily rhythm today and build steady performance habits."
