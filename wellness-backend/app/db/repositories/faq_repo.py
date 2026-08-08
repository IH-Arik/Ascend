"""Data access helpers for FAQ content."""

from datetime import datetime, timezone
from app.models.faq import FAQ


class FAQRepository:
    """Repository for FAQ document operations."""

    async def get_all(self) -> list[FAQ]:
        """Fetch all FAQs ordered by display order."""
        return await FAQ.find_all().sort(FAQ.order).to_list()

    async def create(self, question: str, answer: str, order: int = 0) -> FAQ:
        """Create a new FAQ entry."""
        faq = FAQ(question=question, answer=answer, order=order)
        await faq.insert()
        return faq

    async def update(self, id: str, data: dict) -> FAQ | None:
        """Update an existing FAQ entry."""
        faq = await FAQ.get(id)
        if faq:
            for key, value in data.items():
                setattr(faq, key, value)
            faq.updated_at = datetime.now(timezone.utc)
            await faq.save()
        return faq

    async def delete(self, id: str) -> bool:
        """Delete an FAQ entry."""
        faq = await FAQ.get(id)
        if faq:
            await faq.delete()
            return True
        return False
