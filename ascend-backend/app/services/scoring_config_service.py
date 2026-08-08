"""Admin-configurable OPS scoring weights/thresholds service.

`get_active_config` is the single source of truth every scoring call site
should use - it returns the most recent `ScoringConfig` whose
`effective_date` is today or earlier, or `None` if an Admin has never
created one (in which case callers fall back to the DOCX baseline weights
already hardcoded in `app/core/scoring.py`, unchanged from before this
feature existed).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.security import utc_now
from app.models.scoring_config import ScoringConfig
from app.schemas.scoring_config import ScoringConfigCreate

_DEFAULT_THRESHOLDS = {"Ready": 85.0, "Monitor": 70.0, "Caution": 55.0, "Action Needed": 40.0}


class ScoringConfigService:
    """Read and create admin-configured OPS scoring versions."""

    async def get_active_config(self) -> ScoringConfig | None:
        """Return the currently effective scoring config, if an Admin has set one."""
        today = date.today()
        candidates = await ScoringConfig.find(ScoringConfig.effective_date <= today).to_list()
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.effective_date)

    async def get_active_weights(self) -> dict[str, float] | None:
        """Return the active weights dict, or None to use the DOCX baseline default."""
        config = await self.get_active_config()
        return config.as_weights() if config else None

    async def get_active_thresholds(self) -> dict[str, float] | None:
        """Return the active band thresholds, or None to use the DOCX baseline default."""
        config = await self.get_active_config()
        return config.band_thresholds if config else None

    async def create_config(self, payload: ScoringConfigCreate, created_by: Any) -> dict[str, Any]:
        """Admin creates a new versioned scoring configuration."""
        record = ScoringConfig(
            effective_date=payload.effective_date,
            physical_weight=payload.physical_weight,
            sleep_weight=payload.sleep_weight,
            mental_weight=payload.mental_weight,
            nutritional_weight=payload.nutritional_weight,
            spiritual_weight=payload.spiritual_weight,
            band_thresholds=payload.band_thresholds or _DEFAULT_THRESHOLDS,
            created_by=created_by,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_configs(self) -> dict[str, Any]:
        """Return every scoring config version, newest first."""
        records = await ScoringConfig.find().to_list()
        records.sort(key=lambda item: item.effective_date, reverse=True)
        return {"configs": [await self._serialize(r) for r in records]}

    async def _serialize(self, record: ScoringConfig) -> dict[str, Any]:
        """Convert a stored config to a transport-safe dict."""
        active = await self.get_active_config()
        return {
            "id": str(record.id),
            "effective_date": record.effective_date.isoformat(),
            "physical_weight": record.physical_weight,
            "sleep_weight": record.sleep_weight,
            "mental_weight": record.mental_weight,
            "nutritional_weight": record.nutritional_weight,
            "spiritual_weight": record.spiritual_weight,
            "band_thresholds": record.band_thresholds,
            "is_active": active is not None and active.id == record.id,
            "created_at": record.created_at.isoformat(),
        }
