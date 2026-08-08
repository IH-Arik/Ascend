"""Data access helpers for score documents."""

from beanie import PydanticObjectId

from app.models.score import Score


class ScoreRepository:
    """Repository for score document operations."""

    async def create(self, score: Score) -> Score:
        """Persist a new score document."""
        await score.insert()
        return score

    async def get_latest_by_user_id(self, user_id: PydanticObjectId) -> Score | None:
        """Fetch the latest score for a user."""
        return (
            await Score.find(Score.user_id == user_id)
            .sort(-Score.created_at)
            .first_or_none()
        )

    async def list_by_user_id(self, user_id: PydanticObjectId) -> list[Score]:
        """List all scores for a user."""
        return await Score.find(Score.user_id == user_id).sort(-Score.created_at).to_list()

    async def list_latest_by_user_ids(
        self,
        user_ids: list[PydanticObjectId],
    ) -> list[Score]:
        """Return the latest score per user for a list of users."""
        latest_scores: list[Score] = []
        for user_id in user_ids:
            score = await self.get_latest_by_user_id(user_id)
            if score is not None:
                latest_scores.append(score)
        return latest_scores

    async def get_by_checkin_id(
        self,
        user_id: PydanticObjectId,
        checkin_id: str,
    ) -> Score | None:
        """Fetch a score by related check-in identifier for a user."""
        try:
            object_id = PydanticObjectId(checkin_id)
        except Exception:
            return None
        return await Score.find_one(
            Score.user_id == user_id,
            Score.checkin_id == object_id,
        )

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> int:
        """Delete all score documents for a user and return the count."""
        scores = await Score.find(Score.user_id == user_id).to_list()
        for score in scores:
            await score.delete()
        return len(scores)
