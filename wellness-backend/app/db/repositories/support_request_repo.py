"""Data access helpers for support request documents."""

from beanie import PydanticObjectId
from app.models.support_request import SupportRequest


class SupportRequestRepository:
    """Repository for support request document operations."""

    async def create(self, user_id: PydanticObjectId, email: str, issue: str) -> SupportRequest:
        """Persist a new support request."""
        request = SupportRequest(user_id=user_id, email=email, issue=issue)
        await request.insert()
        return request

    async def get_by_user_id(self, user_id: PydanticObjectId) -> list[SupportRequest]:
        """Fetch all support requests for a user."""
        return await SupportRequest.find({"user_id": user_id}).to_list()

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> None:
        """Delete all support requests for a user."""
        await SupportRequest.find({"user_id": user_id}).delete()
