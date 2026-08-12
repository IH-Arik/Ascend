"""Admin-configurable recommendation trigger threshold service.

`get_active_thresholds` is the single source of truth every recommendation
trigger call site should use - it returns the most recent
`RecommendationThresholdConfig` whose `effective_date` is today or earlier,
or `None` if an Admin has never created one (in which case callers fall
back to the DOCX baseline `HIGH_THRESHOLD`/`MODERATE_THRESHOLD` already
hardcoded in `app/core/recommendation_rules.py`, unchanged from before this
feature existed). Mirrors `ScoringConfigService` exactly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.models.recommendation_threshold_config import RecommendationThresholdConfig
from app.schemas.recommendation_threshold_config import RecommendationThresholdConfigCreate


class RecommendationThresholdConfigService:
    """Read and create admin-configured recommendation trigger threshold versions."""

    async def get_active_config(self) -> RecommendationThresholdConfig | None:
        """Return the currently effective threshold config, if an Admin has set one."""
        today = date.today()
        candidates = await RecommendationThresholdConfig.find(
            RecommendationThresholdConfig.effective_date <= today
        ).to_list()
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.effective_date)

    async def get_active_thresholds(self) -> tuple[float, float] | None:
        """Return (high_threshold, moderate_threshold), or None to use the DOCX baseline default."""
        config = await self.get_active_config()
        if config is None:
            return None
        return config.high_threshold, config.moderate_threshold

    async def create_config(
        self, payload: RecommendationThresholdConfigCreate, created_by: Any
    ) -> dict[str, Any]:
        """Admin creates a new versioned recommendation threshold configuration."""
        record = RecommendationThresholdConfig(
            effective_date=payload.effective_date,
            high_threshold=payload.high_threshold,
            moderate_threshold=payload.moderate_threshold,
            created_by=created_by,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_configs(self) -> dict[str, Any]:
        """Return every threshold config version, newest first."""
        records = await RecommendationThresholdConfig.find().to_list()
        records.sort(key=lambda item: item.effective_date, reverse=True)
        return {"configs": [await self._serialize(r) for r in records]}

    async def _serialize(self, record: RecommendationThresholdConfig) -> dict[str, Any]:
        """Convert a stored config to a transport-safe dict."""
        active = await self.get_active_config()
        return {
            "id": str(record.id),
            "effective_date": record.effective_date.isoformat(),
            "high_threshold": record.high_threshold,
            "moderate_threshold": record.moderate_threshold,
            "is_active": active is not None and active.id == record.id,
            "created_at": record.created_at.isoformat(),
        }
