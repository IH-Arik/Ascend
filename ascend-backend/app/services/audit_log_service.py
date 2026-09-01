"""Append-only audit log service (docs/AUDIT_LOG_RULES.md).

`search`/`get_category_rollup` back the Admin/Superadmin "Audit log" screen
(not DOCX-sourced - a Figma screenshot triggered building a real listing
endpoint where before `AuditLog` was only ever read as an embedded top-10
slice). The category-to-event-type mapping is stated explicitly here, not
hidden, since the screenshot's 6 category names don't correspond 1:1 to
this project's real event-type vocabulary - see the comments on each entry.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.models.audit_log import AuditLog
from app.models.medical_record import MedicalRecordAccessEvent
from app.models.pending_confirmation import PendingConfirmation
from app.models.report_export import ReportExport
from app.models.user import User

# Real, confirmed retention policy (docs/AUDIT_LOG_RULES.md) - exposed as
# metadata only, never auto-deletion: the same doc's own "audit logs should
# be append-only" rule means nothing here actually purges records at 7
# years, this just states the real policy value for admins/compliance to
# see.
AUDIT_LOG_RETENTION_YEARS = 7

# Real event types mapped into the screenshot's 6 named categories. Two
# categories ("Medical-record access", "Downloads") are NOT sourced from
# `AuditLog` at all - they come from the separate `MedicalRecordAccessEvent`
# collection, which already exists specifically for this. "Exports" counts
# real `ReportExport` documents (the actual export-log source of truth),
# not `AuditLog` export-request events, to avoid double-counting a single
# export as both a request event and a completed log entry.
PERMISSION_CHANGE_EVENTS = {
    "role_changed",
    "role_change_requested",
    "role_change_approved",
    "role_change_rejected",
    "role_change_reverted",
    "scope_config_updated",
    "unit_assigned",
    "provider_assigned",
}
# `recommendation_assigned`/`dismissed`/`completed` are new - added to
# `RecommendationService` this pass to close a real, already-documented gap
# (`docs/AUDIT_LOG_RULES.md`: "recommendation assignment or override" was
# never actually being logged).
RECOMMENDATION_CHANGE_EVENTS = {
    "recommendation_assigned",
    "recommendation_dismissed",
    "recommendation_completed",
}
# "Resolved/archived" overlaps Recommendation changes by design (a
# dismissed/completed recommendation is also a resolved one) plus real
# deactivation-approval events - the screenshot's own category names are
# this loosely defined, so the overlap is stated rather than hidden.
RESOLVED_ARCHIVED_EVENTS = {
    "recommendation_dismissed",
    "recommendation_completed",
    "deactivation_approved",
}


class AuditLogService:
    """Record, search, and summarize audit events. Never update or delete an existing entry."""

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

    async def open_event(
        self, actor: User, target_entity_type: str, target_entity_id: str, summary_message: str
    ) -> AuditLog:
        """Log that a user opened/started viewing a real record - the paired start of a
        real, immutable open/close duration pair (see `close_event`).

        Real, added 2026-09-01 - the Nutritionist dashboard's "Access log"
        widget showed a real who/when/what access trail (already backed by
        this same audit log) plus a per-open "Duration" column with no real
        source anywhere. Rather than add an update path to an explicitly
        append-only, immutable model (this service's own docstring, and
        `docs/AUDIT_LOG_RULES.md`, both say never update or delete an
        existing entry), duration is 2 real, separate immutable events -
        this one, and `close_event` below - with the real elapsed time
        computed server-side from their two real timestamps, not trusted
        from the client.
        """
        return await self.record(
            event_type="record_view_opened",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type=target_entity_type,
            target_entity_id=target_entity_id,
            summary_message=summary_message,
        )

    async def close_event(self, actor: User, open_event_id: str) -> AuditLog:
        """Log the real, server-computed duration of a paired `open_event`.

        Only the original opener may close their own open event. A given
        open event may only be closed once (the search for another
        `record_view_closed` referencing the same open id prevents a
        double-close, not by mutating the open event, but by refusing a
        2nd close event).
        """
        open_log = await AuditLog.get(open_event_id)
        if open_log is None or open_log.event_type != "record_view_opened":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Open event not found.")
        if open_log.actor_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only the original opener may close this event."
            )
        already_closed = await AuditLog.find_one(
            {"event_type": "record_view_closed", "metadata_payload.open_event_id": str(open_log.id)}
        )
        if already_closed is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This open event is already closed.")

        duration_seconds = round((datetime.now(timezone.utc) - open_log.created_at).total_seconds())
        return await self.record(
            event_type="record_view_closed",
            actor_id=actor.id,
            actor_role=actor.role,
            target_entity_type=open_log.target_entity_type,
            target_entity_id=open_log.target_entity_id,
            summary_message=open_log.summary_message,
            metadata_payload={"open_event_id": str(open_log.id), "duration_seconds": duration_seconds},
        )
        return record

    async def search_own(
        self, actor: User, event_type: str | None = None, page: int = 1, page_size: int = 50
    ) -> dict[str, Any]:
        """A real 'my own recent actions' log - any staff member's own real audit trail.

        Real, added 2026-09-01 - the Chaplain dashboard's "Records access
        log" widget (Read/Write/Confirmed rows, one per real prior action)
        turned out to already be fully backed - `reflections_viewed`
        (`ReflectionService.list_for_user`), `specialist_note_created`, and
        `support_pathway_toggle`/`support_pathway_witnessed_opt_in` were all
        already being logged for other reasons. The only real gap was that
        `search` was Admin-only - a specialist had no way to see their own
        trail. This is that real, self-scoped view.
        """
        return await self.search(event_type=event_type, page=page, page_size=page_size, actor_id=actor.id)

    async def search(
        self,
        actor_role: str | None = None,
        event_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 50,
        actor_id: Any | None = None,
    ) -> dict[str, Any]:
        """Real filter/search/paginate over `AuditLog` - no fabricated fields.

        `actor_id` added 2026-09-01 - backs a real "my own recent actions"
        view (see `search_own`) distinct from the Admin-only org-wide
        `actor_role` filter above.
        """
        filters = []
        if actor_id is not None:
            filters.append(AuditLog.actor_id == actor_id)
        if actor_role:
            filters.append(AuditLog.actor_role == actor_role)
        if event_type:
            filters.append(AuditLog.event_type == event_type)
        if date_from:
            filters.append(AuditLog.created_at >= date_from)
        if date_to:
            filters.append(AuditLog.created_at <= date_to)

        records = await AuditLog.find(*filters).sort(-AuditLog.created_at).to_list()
        if query:
            needle = query.lower()
            records = [r for r in records if needle in r.summary_message.lower()]

        total = len(records)
        start = (page - 1) * page_size
        page_records = records[start : start + page_size]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "entries": [
                {
                    "id": str(r.id),
                    "event_type": r.event_type,
                    "actor_id": str(r.actor_id) if r.actor_id else None,
                    "actor_role": r.actor_role,
                    "target_entity_type": r.target_entity_type,
                    "target_entity_id": r.target_entity_id,
                    "summary_message": r.summary_message,
                    "metadata_payload": r.metadata_payload,
                    "outcome_status": r.outcome_status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in page_records
            ],
        }

    async def get_category_rollup(self) -> dict[str, Any]:
        """Real 24h/7d/30d counts per category - explicit mapping, no fabricated retention field."""
        now = datetime.now(timezone.utc)
        windows = {"last_24h": now - timedelta(hours=24), "last_7d": now - timedelta(days=7), "last_30d": now - timedelta(days=30)}

        audit_events = await AuditLog.find().to_list()
        medical_events = await MedicalRecordAccessEvent.find().to_list()
        exports = await ReportExport.find().to_list()

        def count_audit(event_types: set[str], since: datetime) -> int:
            return sum(1 for e in audit_events if e.event_type in event_types and e.created_at >= since)

        def count_medical(action: str | None, since: datetime) -> int:
            return sum(
                1
                for e in medical_events
                if e.created_at >= since and (action is None or e.action == action)
            )

        def count_exports(since: datetime) -> int:
            return sum(1 for r in exports if r.created_at >= since)

        categories = {
            "Permission changes": lambda since: count_audit(PERMISSION_CHANGE_EVENTS, since),
            "Recommendation changes": lambda since: count_audit(RECOMMENDATION_CHANGE_EVENTS, since),
            "Resolved/archived": lambda since: count_audit(RESOLVED_ARCHIVED_EVENTS, since),
            "Medical-record access": lambda since: count_medical(None, since),
            "Downloads": lambda since: count_medical("download", since),
            "Exports": lambda since: count_exports(since),
        }

        return {
            "categories": [
                {
                    "category": name,
                    "last_24h": counter(windows["last_24h"]),
                    "last_7d": counter(windows["last_7d"]),
                    "last_30d": counter(windows["last_30d"]),
                }
                for name, counter in categories.items()
            ]
        }

    async def get_stats(self) -> dict[str, Any]:
        """Real 24h/7d totals + destructive-action/record-access snapshot for the Overview stat cards.

        `destructive_action_total_count`/`_pending_review_count` were
        promised by this docstring but never actually implemented until
        2026-08-23 (caught re-checking the Audit log screen's "Destructive
        actions" card against this method - the docstring already said
        "destructive-action... snapshot", the return dict never had one).
        Sourced from `PendingConfirmation`, whose own module docstring
        literally calls it "confirmation queue for destructive admin
        actions" - every action type it tracks (`role_change`,
        `deactivation`, `export`, `idmt_handoff`) counts, not just a
        narrowed subset, since the model's own stated purpose already
        settles the definition.
        """
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        audit_events = await AuditLog.find().to_list()
        count_24h = sum(1 for e in audit_events if e.created_at >= last_24h)
        count_7d = sum(1 for e in audit_events if e.created_at >= last_7d)
        daily_avg_7d = count_7d / 7 if count_7d else 0.0
        percent_vs_7d_avg = (
            round((count_24h - daily_avg_7d) / daily_avg_7d * 100, 1) if daily_avg_7d else None
        )

        medical_events_24h = await MedicalRecordAccessEvent.find(
            MedicalRecordAccessEvent.created_at >= last_24h
        ).to_list()
        record_access_count = len(medical_events_24h)

        confirmations = await PendingConfirmation.find().to_list()
        destructive_action_total_count = len(confirmations)
        destructive_action_pending_review_count = sum(1 for c in confirmations if c.status == "pending")

        return {
            "count_24h": count_24h,
            "count_7d": count_7d,
            "percent_vs_7d_avg": percent_vs_7d_avg,
            "record_access_count_24h": record_access_count,
            "destructive_action_total_count": destructive_action_total_count,
            "destructive_action_pending_review_count": destructive_action_pending_review_count,
            "retention_years": AUDIT_LOG_RETENTION_YEARS,
        }
