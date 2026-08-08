"""Data access helpers for assessment documents."""

from beanie import PydanticObjectId

from app.models.assessment import CheckIn


class AssessmentRepository:
    """Repository for check-in document operations."""

    async def create(self, checkin: CheckIn) -> CheckIn:
        """Persist a new check-in document."""
        await checkin.insert()
        return checkin

    async def get_by_id(self, checkin_id: str) -> CheckIn | None:
        """Fetch a check-in by identifier."""
        try:
            object_id = PydanticObjectId(checkin_id)
        except Exception:
            return None
        return await CheckIn.get(object_id)

    async def list_by_user_id(self, user_id: PydanticObjectId) -> list[CheckIn]:
        """List all check-ins for a user."""
        return await CheckIn.find(CheckIn.user_id == user_id).sort(-CheckIn.submitted_at).to_list()

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> int:
        """Delete all onboarding assessment check-ins for a user and return the count."""
        checkins = await CheckIn.find(CheckIn.user_id == user_id).to_list()
        for checkin in checkins:
            await checkin.delete()
        return len(checkins)
