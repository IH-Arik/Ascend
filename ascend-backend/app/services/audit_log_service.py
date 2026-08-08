"""Append-only audit log service (docs/AUDIT_LOG_RULES.md)."""

from __future__ import annotations

from typing import Any

from app.models.audit_log import AuditLog


class AuditLogService:
    """Record audit events. Never update or delete an existing entry."""

    async def record(
        self,
        *,
        event_type: str,
        actor_id: Any,
        actor_role: str,
        target_entity_type: str,
        target_entity_id: str,
        summary_message: str,
        metadata_payload: dict[str, Any] | None = None,
        outcome_status: str = "success",
    ) -> AuditLog:
        """Insert one immutable audit event."""
        record = AuditLog(
            event_type=event_type,
            actor_id=actor_id,
            actor_role=actor_role,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            summary_message=summary_message,
            metadata_payload=metadata_payload or {},
            outcome_status=outcome_status,
        )
        await record.insert()
        return record
