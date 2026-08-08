"""Data access helpers for monthly check-in documents."""

from datetime import datetime

from beanie import PydanticObjectId

from app.models.assessment import MonthlyCheckIn


class MonthlyCheckInRepository:
    """Repository for monthly check-in document operations."""

    async def create(self, monthly_checkin: MonthlyCheckIn) -> MonthlyCheckIn:
        """Persist a new monthly check-in document."""
        await monthly_checkin.insert()
        return monthly_checkin

    async def list_by_user_id(self, user_id: PydanticObjectId) -> list[MonthlyCheckIn]:
        """List all monthly check-ins for a user."""
        return (
            await MonthlyCheckIn.find(MonthlyCheckIn.user_id == user_id)
            .sort(-MonthlyCheckIn.submitted_at)
            .to_list()
        )

    async def get_for_current_month(
        self,
        user_id: PydanticObjectId,
        now: datetime,
    ) -> MonthlyCheckIn | None:
        """Return the user's monthly check-in for the current month, if present."""
        start_of_month = datetime(year=now.year, month=now.month, day=1)
        if now.month == 12:
            next_month = datetime(year=now.year + 1, month=1, day=1)
        else:
            next_month = datetime(year=now.year, month=now.month + 1, day=1)

        return await MonthlyCheckIn.find_one(
            MonthlyCheckIn.user_id == user_id,
            MonthlyCheckIn.submitted_at >= start_of_month,
            MonthlyCheckIn.submitted_at < next_month,
        )

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> int:
        """Delete all monthly check-ins for a user and return the count."""
        checkins = await MonthlyCheckIn.find(MonthlyCheckIn.user_id == user_id).to_list()
        for checkin in checkins:
            await checkin.delete()
        return len(checkins)
