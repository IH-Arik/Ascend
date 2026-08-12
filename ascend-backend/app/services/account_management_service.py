"""Sign-in history and account deactivation ("Sign-in & activation" screen, DOCX section 14).

DOCX: "Login, password reset, account activation/deactivation, role
assignment, ..., login/activity tracking, access logs..." (Secure Login and
Account Management), and the Admin Panel module lists a "deactivation
queue." Deactivation is user-requested but never self-service: only an
Admin can approve it, matching the DOCX's admin-led account management
model. No record is ever deleted - a rejected or approved request stays in
the collection.

Sign-in history is read from the `AuditLog` entries `AuthService` already
writes on every login attempt (`login_success`/`login_failed`) - real IP
address and User-Agent header captured from the request, nothing else
(no CAC/PIV/EDIPI, no device-model parsing, no IP geolocation - none of
that has a real source in this project).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES
from app.core.security import utc_now
from app.models.audit_log import AuditLog
from app.models.deactivation_request import DeactivationRequest
from app.models.user import User
from app.schemas.account import DeactivationRequestCreate
from app.services.audit_log_service import AuditLogService
from app.services.notification_service import NotificationService

LOGIN_EVENT_TYPES = ("login_success", "login_failed")
RECENT_HISTORY_LIMIT = 5


class AccountManagementService:
    """Sign-in history lookups and the deactivation-request queue."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.notification_service = NotificationService()

    async def get_sign_in_history(self, user: User) -> dict[str, Any]:
        """Return the last sign-in plus recent login/logout audit history."""
        records = await AuditLog.find(
            AuditLog.target_entity_type == "user", AuditLog.target_entity_id == str(user.id)
        ).to_list()
        login_events = [r for r in records if r.event_type in LOGIN_EVENT_TYPES]
        login_events.sort(key=lambda item: item.created_at, reverse=True)
        recent = [self._serialize_event(r) for r in login_events[:RECENT_HISTORY_LIMIT]]

        return {
            "last_sign_in": recent[0] if recent else None,
            "recent_history": recent,
            "activation_date": user.activation_date.isoformat() if user.activation_date else None,
            "deactivation_date": user.deactivation_date.isoformat() if user.deactivation_date else None,
        }

    async def request_deactivation(
        self, user: User, payload: DeactivationRequestCreate
    ) -> dict[str, Any]:
        """Queue a self-initiated deactivation request for Admin approval."""
        existing = await DeactivationRequest.find_one(
            DeactivationRequest.user_id == user.id, DeactivationRequest.status == "pending"
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A deactivation request is already pending for this account.",
            )

        record = DeactivationRequest(user_id=user.id, reason=payload.reason)
        await record.insert()

        await self.audit_log_service.record(
            event_type="deactivation_requested",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="deactivation_request",
            target_entity_id=str(record.id),
            summary_message="User requested account deactivation.",
            metadata_payload={"reason": payload.reason},
        )

        admins: list[User] = []
        for admin_role in ADMIN_ROLES:
            admins.extend(await User.find(User.role == admin_role).to_list())
        for admin in admins:
            if admin.is_active:
                await self.notification_service.notify(
                    admin.id,
                    family="compliance_due_reminders",
                    title="Deactivation request pending review",
                    body=f"{user.full_name or user.email} requested account deactivation.",
                    related_entity_type="deactivation_request",
                    related_entity_id=str(record.id),
                )

        return await self._serialize_request(record)

    async def list_deactivation_requests(self, status_filter: str = "pending") -> dict[str, Any]:
        """Return deactivation requests for Admin review (default: pending only)."""
        if status_filter == "all":
            records = await DeactivationRequest.find().to_list()
        else:
            records = await DeactivationRequest.find(
                DeactivationRequest.status == status_filter
            ).to_list()
        records.sort(key=lambda item: item.requested_at, reverse=True)
        return {"requests": [await self._serialize_request(r) for r in records]}

    async def review_deactivation_request(
        self, admin: User, request_id: str, approve: bool
    ) -> dict[str, Any]:
        """Admin approves or rejects a pending deactivation request."""
        record = await DeactivationRequest.get(request_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
        if record.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This request has already been reviewed.",
            )

        record.status = "approved" if approve else "rejected"
        record.reviewed_at = utc_now()
        record.reviewed_by = admin.id
        await record.save()

        target_user = await User.get(record.user_id)
        if approve and target_user is not None:
            target_user.is_active = False
            target_user.deactivation_date = utc_now()
            target_user.updated_at = utc_now()
            await target_user.save()

        await self.audit_log_service.record(
            event_type="deactivation_approved" if approve else "deactivation_rejected",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="deactivation_request",
            target_entity_id=str(record.id),
            summary_message=f"Deactivation request {'approved' if approve else 'rejected'}.",
            metadata_payload={"target_user_id": str(record.user_id)},
        )

        return await self._serialize_request(record)

    async def _serialize_request(self, record: DeactivationRequest) -> dict[str, Any]:
        """Convert a stored deactivation request to a transport-safe dict."""
        requester = await User.get(record.user_id)
        return {
            "id": str(record.id),
            "user_id": str(record.user_id),
            "user_name": requester.full_name if requester else None,
            "reason": record.reason,
            "status": record.status,
            "requested_at": record.requested_at.isoformat(),
            "reviewed_at": record.reviewed_at.isoformat() if record.reviewed_at else None,
        }

    def _serialize_event(self, record: AuditLog) -> dict[str, Any]:
        """Convert a login AuditLog entry to a transport-safe sign-in event."""
        return {
            "event_type": record.event_type,
            "method": record.metadata_payload.get("method", "password"),
            "outcome": "OK" if record.event_type == "login_success" else "FAIL",
            "ip_address": record.metadata_payload.get("ip_address"),
            "user_agent": record.metadata_payload.get("user_agent"),
            "created_at": record.created_at.isoformat(),
        }
