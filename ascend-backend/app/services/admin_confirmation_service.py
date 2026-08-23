"""Second-reviewer confirmation queue service.

Not DOCX-sourced - see `app/models/pending_confirmation.py` for why this
exists. Three action types go through this queue instead of applying
immediately: an admin-level role grant/removal, deactivating a
provider/admin-level account (one that can have a real caseload), and
exporting a "restricted"-sensitivity report. Every other role change,
every Airman deactivation, and every "aggregate"-sensitivity export is
completely unaffected and keeps applying immediately as before.

The two-person rule is enforced in `approve`/`reject`/`revert`: the
reviewer must be a *different* Admin/Superadmin than whoever requested the
action.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, ROLE_LEADERSHIP, ROLE_PTIM, ROLE_SCS, SPECIALIST_ROLES
from app.core.security import utc_now
from app.models.idmt_handoff import IdmtHandoff
from app.models.pending_confirmation import PendingConfirmation
from app.models.report_export import ReportExport
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.services.audit_log_service import AuditLogService

# Not DOCX-sourced (a Figma "System" screen's "Export approval window: 72h"
# claim triggered this) - a pending restricted-export confirmation that
# nobody reviews within this real window auto-expires (see `expire_stale`)
# rather than staying open indefinitely.
EXPORT_APPROVAL_WINDOW_HOURS = 72

# Roles that can hold a real caseload (TeamAssignment.provider_user_id may
# point at them) - deactivating one of these needs a second reviewer.
# Airman (no caseload, uses the existing self-request flow) and IDMT
# (export-only recipient, never assigned) are deliberately excluded.
GATED_DEACTIVATION_ROLES: tuple[str, ...] = (
    ROLE_SCS,
    ROLE_PTIM,
    *SPECIALIST_ROLES,
    ROLE_LEADERSHIP,
    *ADMIN_ROLES,
)

RESTRICTED_REPORT_TYPES: tuple[str, ...] = ("injury",)


class AdminConfirmationService:
    """Request, approve, reject, and revert gated admin actions."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()

    async def request_role_change(
        self, admin: User, target: User, old_role: str, new_role: str
    ) -> PendingConfirmation:
        """Create a pending confirmation for an admin-level role change (not yet applied)."""
        confirmation = PendingConfirmation(
            action_type="role_change",
            requested_by=admin.id,
            target_entity_type="user",
            target_entity_id=str(target.id),
            target_summary=target.full_name or target.email,
            consequence_summary=f"Role change: {old_role} -> {new_role}",
            scope_summary=f"{old_role} - {target.unit_id or 'no unit'}",
            payload={"new_role": new_role},
            snapshot_before={"role": old_role},
        )
        await confirmation.insert()
        await self.audit_log_service.record(
            event_type="role_change_requested",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Requested role change for {target.email}: {old_role} -> {new_role}.",
            metadata_payload={"confirmation_id": str(confirmation.id)},
        )
        return confirmation

    async def request_deactivation(self, admin: User, user_id: str, reason: str | None) -> PendingConfirmation:
        """Create a pending confirmation to deactivate a provider/admin-level account."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        if target.role not in GATED_DEACTIVATION_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "This account type has no caseload and does not use the "
                    "second-reviewer deactivation path. Use the self-deactivation-"
                    "request flow instead."
                ),
            )
        caseload_count = await TeamAssignment.find(
            TeamAssignment.provider_user_id == target.id
        ).count()
        confirmation = PendingConfirmation(
            action_type="deactivation",
            requested_by=admin.id,
            target_entity_type="user",
            target_entity_id=str(target.id),
            target_summary=target.full_name or target.email,
            consequence_summary=f"{caseload_count} caseload{'s' if caseload_count != 1 else ''} reassigned",
            scope_summary=f"{target.role} - {target.unit_id or 'no unit'}",
            payload={"reason": reason},
            snapshot_before={"is_active": target.is_active},
        )
        await confirmation.insert()
        await self.audit_log_service.record(
            event_type="admin_deactivation_requested",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Requested deactivation of {target.email} ({caseload_count} assigned).",
            metadata_payload={"confirmation_id": str(confirmation.id), "caseload_count": caseload_count},
        )
        return confirmation

    async def request_export(
        self,
        admin: User,
        report_type: str,
        date_range: str,
        sensitivity_level: str,
        row_count: int,
        export_format: str = "csv",
        recipient_role: str | None = None,
    ) -> tuple[PendingConfirmation, ReportExport]:
        """Create a pending confirmation + `ReportExport` row for a restricted-sensitivity export.

        `recipient_role` defaults to the requesting admin's own role unless
        a real one is supplied - a recurring `ScheduledExport` passes its
        own admin-configured recipient_role.
        """
        export_log = ReportExport(
            report_type=report_type,
            date_range=date_range,
            generated_by=admin.id,
            recipient_role=recipient_role or admin.role,
            export_format=export_format,
            sensitivity_level=sensitivity_level,
            export_log_status="pending_approval",
            lifecycle_status="in_review",
        )
        await export_log.insert()
        confirmation = PendingConfirmation(
            action_type="export",
            requested_by=admin.id,
            target_entity_type="report_export",
            target_entity_id=str(export_log.id),
            target_summary=f"{report_type} ({date_range})",
            consequence_summary=f"{row_count} records - {sensitivity_level}",
            scope_summary=f"{sensitivity_level} - {recipient_role or admin.role}",
            expires_at=utc_now() + timedelta(hours=EXPORT_APPROVAL_WINDOW_HOURS),
            payload={
                "report_type": report_type,
                "date_range": date_range,
                "row_count": row_count,
                "sensitivity_level": sensitivity_level,
                "export_format": export_format,
            },
        )
        await confirmation.insert()
        await self.audit_log_service.record(
            event_type="export_requested",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="report_export",
            target_entity_id=str(export_log.id),
            summary_message=f"Requested export of {report_type} ({sensitivity_level}, {row_count} records).",
            metadata_payload={"confirmation_id": str(confirmation.id)},
        )
        return confirmation, export_log

    async def list_pending(self, status_filter: str = "pending") -> dict[str, Any]:
        """List confirmations, optionally filtered by status."""
        if status_filter == "all":
            confirmations = await PendingConfirmation.find().to_list()
        else:
            confirmations = await PendingConfirmation.find(
                PendingConfirmation.status == status_filter
            ).to_list()
        confirmations.sort(key=lambda c: c.requested_at, reverse=True)
        return {"confirmations": [self._serialize(c) for c in confirmations]}

    async def approve(self, reviewer: User, confirmation_id: str) -> dict[str, Any]:
        """Approve a pending confirmation and apply the real underlying action."""
        confirmation = await self._get_pending(confirmation_id)
        self._require_different_reviewer(reviewer, confirmation)

        if confirmation.action_type == "role_change":
            target = await User.get(confirmation.target_entity_id)
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found.")
            target.role = confirmation.payload["new_role"]
            target.updated_at = utc_now()
            await target.save()
        elif confirmation.action_type == "deactivation":
            target = await User.get(confirmation.target_entity_id)
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found.")
            target.is_active = False
            target.deactivation_date = utc_now()
            target.updated_at = utc_now()
            await target.save()
            assignments = await TeamAssignment.find(
                TeamAssignment.provider_user_id == target.id
            ).to_list()
            for assignment in assignments:
                assignment.provider_user_id = None
                assignment.updated_at = utc_now()
                await assignment.save()
        elif confirmation.action_type == "export":
            export_log = await ReportExport.get(confirmation.target_entity_id)
            if export_log is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export log not found.")
            export_log.export_log_status = "approved"
            export_log.lifecycle_status = "ready"
            await export_log.save()
        elif confirmation.action_type == "idmt_handoff":
            handoff = await IdmtHandoff.get(confirmation.target_entity_id)
            if handoff is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found.")
            handoff.status = "approved"
            await handoff.save()

        confirmation.status = "approved"
        confirmation.reviewed_by = reviewer.id
        confirmation.reviewed_at = utc_now()
        confirmation.executed_at = utc_now()
        await confirmation.save()

        await self.audit_log_service.record(
            event_type=f"{confirmation.action_type}_approved",
            actor_id=reviewer.id,
            actor_role=reviewer.role,
            target_entity_type=confirmation.target_entity_type,
            target_entity_id=confirmation.target_entity_id,
            summary_message=f"Approved {confirmation.action_type} for {confirmation.target_summary}.",
            metadata_payload={"confirmation_id": str(confirmation.id)},
        )
        return self._serialize(confirmation)

    async def reject(self, reviewer: User, confirmation_id: str, reason: str | None) -> dict[str, Any]:
        """Reject a pending confirmation. No underlying action is applied."""
        confirmation = await self._get_pending(confirmation_id)
        self._require_different_reviewer(reviewer, confirmation)

        confirmation.status = "rejected"
        confirmation.reviewed_by = reviewer.id
        confirmation.reviewed_at = utc_now()
        confirmation.rejection_reason = reason
        await confirmation.save()

        if confirmation.action_type == "export":
            export_log = await ReportExport.get(confirmation.target_entity_id)
            if export_log is not None:
                export_log.export_log_status = "rejected"
                await export_log.save()
        elif confirmation.action_type == "idmt_handoff":
            handoff = await IdmtHandoff.get(confirmation.target_entity_id)
            if handoff is not None:
                handoff.status = "rejected"
                await handoff.save()

        await self.audit_log_service.record(
            event_type=f"{confirmation.action_type}_rejected",
            actor_id=reviewer.id,
            actor_role=reviewer.role,
            target_entity_type=confirmation.target_entity_type,
            target_entity_id=confirmation.target_entity_id,
            summary_message=f"Rejected {confirmation.action_type} for {confirmation.target_summary}.",
            metadata_payload={"confirmation_id": str(confirmation.id), "reason": reason},
        )
        return self._serialize(confirmation)

    async def expire_stale(self) -> int:
        """Real auto-expiry for pending `export` confirmations past their real `expires_at`.

        Not DOCX-sourced (see `EXPORT_APPROVAL_WINDOW_HOURS`). Only
        `action_type == "export"` is ever eligible - `role_change`/
        `deactivation` have no `expires_at` set (`None`) and are never
        matched by this query. Returns the number expired.
        """
        now = utc_now()
        candidates = await PendingConfirmation.find(
            PendingConfirmation.status == "pending", PendingConfirmation.action_type == "export"
        ).to_list()
        stale = [c for c in candidates if c.expires_at is not None and c.expires_at <= now]

        for confirmation in stale:
            confirmation.status = "rejected"
            confirmation.reviewed_at = now
            confirmation.rejection_reason = f"Auto-expired after the {EXPORT_APPROVAL_WINDOW_HOURS}h export approval window."
            await confirmation.save()

            export_log = await ReportExport.get(confirmation.target_entity_id)
            if export_log is not None:
                export_log.export_log_status = "rejected"
                await export_log.save()

            await self.audit_log_service.record(
                event_type="export_rejected",
                actor_id=None,
                actor_role="system",
                target_entity_type=confirmation.target_entity_type,
                target_entity_id=confirmation.target_entity_id,
                summary_message=f"Auto-expired export request for {confirmation.target_summary}.",
                metadata_payload={"confirmation_id": str(confirmation.id), "auto_expired": True},
            )
        return len(stale)

    async def revert(self, reviewer: User, confirmation_id: str) -> dict[str, Any]:
        """Revert an already-approved role_change/deactivation using its stored snapshot."""
        confirmation = await PendingConfirmation.get(confirmation_id)
        if confirmation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Confirmation not found.")
        if confirmation.status != "approved":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved actions can be reverted.")
        if confirmation.action_type in ("export", "idmt_handoff"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{confirmation.action_type.replace('_', ' ').title()}s cannot be reverted once approved.",
            )

        target = await User.get(confirmation.target_entity_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found.")

        if confirmation.action_type == "role_change":
            target.role = confirmation.snapshot_before["role"]
        elif confirmation.action_type == "deactivation":
            target.is_active = confirmation.snapshot_before["is_active"]
            target.deactivation_date = None
        target.updated_at = utc_now()
        await target.save()

        confirmation.reverted_at = utc_now()
        confirmation.reverted_by = reviewer.id
        await confirmation.save()

        await self.audit_log_service.record(
            event_type=f"{confirmation.action_type}_reverted",
            actor_id=reviewer.id,
            actor_role=reviewer.role,
            target_entity_type=confirmation.target_entity_type,
            target_entity_id=confirmation.target_entity_id,
            summary_message=f"Reverted {confirmation.action_type} for {confirmation.target_summary}.",
            metadata_payload={"confirmation_id": str(confirmation.id)},
        )
        return self._serialize(confirmation)

    async def _get_pending(self, confirmation_id: str) -> PendingConfirmation:
        confirmation = await PendingConfirmation.get(confirmation_id)
        if confirmation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Confirmation not found.")
        if confirmation.status != "pending":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Confirmation is no longer pending.")
        return confirmation

    def _require_different_reviewer(self, reviewer: User, confirmation: PendingConfirmation) -> None:
        if reviewer.id == confirmation.requested_by:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A different Admin/Superadmin must review this action (two-person rule).",
            )

    def _serialize(self, confirmation: PendingConfirmation) -> dict[str, Any]:
        return {
            "id": str(confirmation.id),
            "action_type": confirmation.action_type,
            "status": confirmation.status,
            "requested_by": str(confirmation.requested_by),
            "requested_at": confirmation.requested_at,
            "reviewed_by": str(confirmation.reviewed_by) if confirmation.reviewed_by else None,
            "reviewed_at": confirmation.reviewed_at,
            "rejection_reason": confirmation.rejection_reason,
            "target_entity_type": confirmation.target_entity_type,
            "target_entity_id": confirmation.target_entity_id,
            "target_summary": confirmation.target_summary,
            "consequence_summary": confirmation.consequence_summary,
            "scope_summary": confirmation.scope_summary,
            "payload": confirmation.payload,
            "executed_at": confirmation.executed_at,
            "reverted_at": confirmation.reverted_at,
            "reverted_by": str(confirmation.reverted_by) if confirmation.reverted_by else None,
        }
