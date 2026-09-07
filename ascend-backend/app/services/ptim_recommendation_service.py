"""PT/IM quarterly recommendation service. See `app/models/ptim_recommendation.py`."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.security import utc_now
from app.models.ptim_recommendation import PtimRecommendation
from app.models.user import User
from app.schemas.ptim_recommendation import PtimRecommendationCreateRequest


class PtimRecommendationService:
    """Draft, list, and resolve quarterly PT/IM recommendations."""

    async def create(self, author: User, payload: PtimRecommendationCreateRequest) -> dict[str, Any]:
        """PT/IM drafts a new recommendation for one real fiscal quarter."""
        rec = PtimRecommendation(
            fiscal_year=payload.fiscal_year,
            quarter=payload.quarter,
            title=payload.title,
            body=payload.body,
            subject=payload.subject,
            owners=payload.owners,
            due_date=payload.due_date,
            created_by=author.id,
        )
        await rec.insert()
        return await self._serialize(rec)

    async def list_for_quarter(self, fiscal_year: int, quarter: int) -> dict[str, Any]:
        """Every recommendation drafted for one real fiscal quarter."""
        recs = await PtimRecommendation.find(
            PtimRecommendation.fiscal_year == fiscal_year, PtimRecommendation.quarter == quarter
        ).to_list()
        recs.sort(key=lambda r: r.created_at, reverse=True)
        return {"recommendations": [await self._serialize(r) for r in recs]}

    async def mark_done(self, actor: User, recommendation_id: str) -> dict[str, Any]:
        """PT/IM or SCS marks a recommendation done."""
        rec = await PtimRecommendation.get(recommendation_id)
        if rec is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found.")
        rec.status = "done"
        rec.updated_at = utc_now()
        await rec.save()
        return await self._serialize(rec)

    async def _serialize(self, rec: PtimRecommendation) -> dict[str, Any]:
        author = await User.get(rec.created_by)
        return {
            "id": str(rec.id),
            "fiscal_year": rec.fiscal_year,
            "quarter": rec.quarter,
            "title": rec.title,
            "body": rec.body,
            "subject": rec.subject,
            "owners": rec.owners,
            "due_date": rec.due_date.isoformat() if rec.due_date else None,
            "status": rec.status,
            "created_by_name": author.full_name if author else None,
            "created_at": rec.created_at.isoformat(),
            "updated_at": rec.updated_at.isoformat(),
        }
