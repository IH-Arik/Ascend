"""Provider coverage-hours log service - feeds the PRS/QCP Support Report."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.models.coverage_log import CoverageLog
from app.models.user import User
from app.schemas.coverage_log import CoverageLogCreate


class CoverageService:
    """Log and list provider coverage-hours entries."""

    async def create(self, logged_by: Any, payload: CoverageLogCreate) -> dict[str, Any]:
        """Log a block of coverage hours for a provider."""
        record = CoverageLog(
            provider_id=payload.provider_id,
            role=payload.role,
            hours=payload.hours,
            coverage_date=payload.coverage_date,
            is_weekend_rsd=payload.is_weekend_rsd,
            notes=payload.notes,
            logged_by=logged_by,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_for_provider(self, provider_id: Any, year: int | None = None) -> dict[str, Any]:
        """Return a provider's coverage log, optionally filtered to one calendar year."""
        records = await CoverageLog.find(CoverageLog.provider_id == provider_id).to_list()
        if year:
            records = [r for r in records if r.coverage_date.year == year]
        records.sort(key=lambda item: item.coverage_date, reverse=True)
        return {"entries": [await self._serialize(r) for r in records]}

    async def total_hours_for_provider(self, provider_id: Any, year: int) -> float:
        """Return a provider's total logged coverage hours for one calendar year."""
        records = await CoverageLog.find(CoverageLog.provider_id == provider_id).to_list()
        return sum(r.hours for r in records if r.coverage_date.year == year)

    async def _serialize(self, record: CoverageLog) -> dict[str, Any]:
        """Convert a stored coverage entry to a transport-safe dict."""
        provider = await User.get(record.provider_id)
        return {
            "id": str(record.id),
            "provider_id": str(record.provider_id),
            "provider_name": provider.full_name if provider else None,
            "role": record.role,
            "hours": record.hours,
            "coverage_date": record.coverage_date.isoformat(),
            "is_weekend_rsd": record.is_weekend_rsd,
            "notes": record.notes,
        }
