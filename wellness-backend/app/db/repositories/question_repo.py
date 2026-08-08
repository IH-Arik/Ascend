"""Data access helpers for question documents."""

from app.models.question import Question


class QuestionRepository:
    """Repository for question document operations."""

    async def list_all(self) -> list[Question]:
        """Return all questions ordered by assessment order."""
        return await Question.find_all().sort(Question.order).to_list()

    async def get_by_ids(self, question_ids: list[str]) -> list[Question]:
        """Return questions matching the provided identifiers."""
        return await Question.find({"_id": {"$in": question_ids}}).to_list()
