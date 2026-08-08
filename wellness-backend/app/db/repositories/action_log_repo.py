"""Data access helpers for leader action log documents."""

from beanie import PydanticObjectId

from app.models.action_log import LeaderActionLog


class ActionLogRepository:
    """Repository for leader action log operations."""

    async def get_by_id(self, action_log_id: str) -> LeaderActionLog | None:
        """Fetch a leader action log by identifier."""
        try:
            object_id = PydanticObjectId(action_log_id)
        except Exception:
            return None
        return await LeaderActionLog.get(object_id)

    async def create(self, action_log: LeaderActionLog) -> LeaderActionLog:
        """Persist a new leader action log."""
        await action_log.insert()
        return action_log

    async def list_by_scope(
        self,
        organization_name: str,
        department: str | None = None,
        team: str | None = None,
        limit: int = 10,
    ) -> list[LeaderActionLog]:
        """Return recent action logs for an organization scope."""
        filters = [LeaderActionLog.organization_name == organization_name]
        if department is not None:
            filters.append(LeaderActionLog.department == department)
        if team is not None:
            filters.append(LeaderActionLog.team == team)

        return await (
            LeaderActionLog.find(*filters)
            .sort(-LeaderActionLog.created_at)
            .limit(limit)
            .to_list()
        )

    async def get_latest_by_scope(
        self,
        organization_name: str,
        department: str | None = None,
        team: str | None = None,
    ) -> LeaderActionLog | None:
        """Return the latest action log for an organization scope."""
        logs = await self.list_by_scope(
            organization_name,
            department=department,
            team=team,
            limit=1,
        )
        return logs[0] if logs else None

    async def list_by_leader(
        self,
        leader_user_id: PydanticObjectId,
        limit: int = 10,
    ) -> list[LeaderActionLog]:
        """Return recent logs authored by a leader."""
        return await (
            LeaderActionLog.find(LeaderActionLog.leader_user_id == leader_user_id)
            .sort(-LeaderActionLog.created_at)
            .limit(limit)
            .to_list()
        )
