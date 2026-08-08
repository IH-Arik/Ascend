"""Data access helpers for behavior log documents."""

from datetime import date

from beanie import PydanticObjectId

from app.models.behavior import BehaviorLog, BehaviorType


class BehaviorLogRepository:
    """Repository for behavior log document operations."""

    async def list_by_user_id(
        self,
        user_id: PydanticObjectId,
    ) -> list[BehaviorLog]:
        """Return all behavior logs for a user ordered from newest to oldest."""
        return await (
            BehaviorLog.find(BehaviorLog.user_id == user_id)
            .sort(-BehaviorLog.behavior_date, -BehaviorLog.logged_at)
            .to_list()
        )

    async def upsert_for_period(
        self,
        user_id: PydanticObjectId,
        behavior_date: date,
        source: str,
        behaviors: list[BehaviorType],
    ) -> BehaviorLog:
        """Create or replace a behavior log for a user, date, and source."""
        existing = await BehaviorLog.find_one(
            BehaviorLog.user_id == user_id,
            BehaviorLog.behavior_date == behavior_date,
            BehaviorLog.source == source,
        )
        normalized_behaviors = list(dict.fromkeys(behaviors))
        if existing is None:
            log = BehaviorLog(
                user_id=user_id,
                behavior_date=behavior_date,
                source=source,
                behaviors=normalized_behaviors,
            )
            await log.insert()
            return log

        existing.behaviors = normalized_behaviors
        await existing.save()
        return existing
