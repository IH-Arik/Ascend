"""Range-of-motion measurement service (net-new, not DOCX-sourced - see model docstring)."""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId

from app.models.reconditioning_event import ReconditioningEvent
from app.models.rom_measurement import RomMeasurement
from app.models.user import User


class RomMeasurementService:
    """Record and list real ROM measurements for an operator."""

    async def add_measurement(
        self, target_user: User, movement: str, value_degrees: float, measured_date, measured_by: Any, note: str | None
    ) -> dict[str, Any]:
        """Record a real ROM measurement and append a real timeline event."""
        record = RomMeasurement(
            user_id=target_user.id,
            movement=movement,
            value_degrees=value_degrees,
            measured_date=measured_date,
            measured_by=measured_by,
            note=note,
        )
        await record.insert()
        await ReconditioningEvent(
            user_id=target_user.id,
            event_type="rom_measurement_added",
            detail=f"{movement}: {value_degrees:g} degrees ({measured_date.isoformat()})",
            recorded_by=measured_by,
        ).insert()
        return self._serialize(record)

    async def list_for_user(self, user_id: Any) -> dict[str, Any]:
        """Real measurements grouped by movement, each sorted by measured_date.

        `user_id` may be a route-supplied string - coerced to a real
        `PydanticObjectId` before querying (same fix as `CoverageService`/
        `ReconditioningService.get_timeline` - see those for the full
        explanation).
        """
        if not isinstance(user_id, PydanticObjectId):
            user_id = PydanticObjectId(user_id)
        records = await RomMeasurement.find(RomMeasurement.user_id == user_id).to_list()
        records.sort(key=lambda r: r.measured_date)

        by_movement: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            by_movement.setdefault(record.movement, []).append(self._serialize(record))

        return {"by_movement": by_movement, "measurements": [self._serialize(r) for r in records]}

    def _serialize(self, record: RomMeasurement) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "movement": record.movement,
            "value_degrees": record.value_degrees,
            "measured_date": record.measured_date.isoformat(),
            "note": record.note,
            "created_at": record.created_at.isoformat(),
        }
