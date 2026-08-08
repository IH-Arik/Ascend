"""Data access helpers for weekly check-in documents."""

from datetime import datetime, timedelta

from beanie import PydanticObjectId

from app.models.assessment import WeeklyCheckIn


class WeeklyCheckInRepository:
    """Repository for weekly check-in document operations."""

    async def create(self, weekly_checkin: WeeklyCheckIn) -> WeeklyCheckIn:
        """Persist a new weekly check-in document."""
        await weekly_checkin.insert()
        return weekly_checkin

    async def list_by_user_id(self, user_id: PydanticObjectId) -> list[WeeklyCheckIn]:
        """List all weekly check-ins for a user."""
        return (
            await WeeklyCheckIn.find(WeeklyCheckIn.user_id == user_id)
            .sort(-WeeklyCheckIn.submitted_at)
            .to_list()
        )

    async def get_for_current_week(
        self,
        user_id: PydanticObjectId,
        now: datetime,
    ) -> WeeklyCheckIn | None:
        """Return the user's weekly check-in for the current week, if present."""
        start_of_week = datetime.combine(
            (now - timedelta(days=now.weekday())).date(),
            datetime.min.time(),
        )
        end_of_week = start_of_week + timedelta(days=7)
        return await WeeklyCheckIn.find_one(
            WeeklyCheckIn.user_id == user_id,
            WeeklyCheckIn.submitted_at >= start_of_week,
            WeeklyCheckIn.submitted_at < end_of_week,
        )

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> int:
        """Delete all weekly check-ins for a user and return the count."""
        checkins = await WeeklyCheckIn.find(WeeklyCheckIn.user_id == user_id).to_list()
        for checkin in checkins:
            await checkin.delete()
        return len(checkins)
