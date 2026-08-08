"""Data access helpers for daily check-in documents."""

from datetime import date, datetime, timedelta

from beanie import PydanticObjectId

from app.models.assessment import DailyCheckIn


class DailyCheckInRepository:
    """Repository for daily check-in document operations."""

    async def create(self, daily_checkin: DailyCheckIn) -> DailyCheckIn:
        """Persist a new daily check-in document."""
        await daily_checkin.insert()
        return daily_checkin

    async def list_by_user_id(self, user_id: PydanticObjectId) -> list[DailyCheckIn]:
        """List all daily check-ins for a user."""
        return (
            await DailyCheckIn.find(DailyCheckIn.user_id == user_id)
            .sort(-DailyCheckIn.submitted_at)
            .to_list()
        )

    async def get_for_date(
        self,
        user_id: PydanticObjectId,
        target_date: date,
    ) -> DailyCheckIn | None:
        """Return the user's daily check-in for a specific date, if present."""
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        return await DailyCheckIn.find_one(
            DailyCheckIn.user_id == user_id,
            DailyCheckIn.submitted_at >= start_of_day,
            DailyCheckIn.submitted_at < end_of_day,
        )

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> int:
        """Delete all daily check-ins for a user and return the count."""
        checkins = await DailyCheckIn.find(DailyCheckIn.user_id == user_id).to_list()
        for checkin in checkins:
            await checkin.delete()
        return len(checkins)
