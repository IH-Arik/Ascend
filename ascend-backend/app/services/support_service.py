"""Support pathway listing service ("Talk to your team" / "My Support Team" / "Request support").

`availability_status` is currently a static "Available" label - there is no
staffing/roster module yet to derive real specialist availability from
(tracked separately as the `support_requests` module in TASKS.MD).

`get_pathways_for_user` (the "Talk to your team" listing) scopes to a
pathway that's always-available, opted into during onboarding, or since
enabled from the My Team screen (`app/services/team_service.py`) - these are
two separate opt-in moments that both need to unlock the same pathway there.

`create_request` (the "Request support" screen) is deliberately **not**
scoped the same way: the docx's "My Support Team" requirement gives all 5
pathways a request-support button with no opt-in precondition, and the
"Request support" screen presents all 5 as pickable topics - only the
"message option" is gated by "if enabled". So any of the 5 defined pathways
can receive a request regardless of the user's opt-in/enabled state.

`create_request` also runs the DOCX's "Level 5 - Safety Boundary" keyword
scan (`app/core/safety_boundary.py`) on the message. This is deliberately a
small, deterministic keyword match - no AI/LLM decision-making, per the
DOCX's "Do not let AI or app decide care." A match never blocks the
request; it sets `priority_flag`, skips the (lower-priority) OPSEC block so
a coincidental OPSEC word never stops someone in crisis from submitting,
notifies the assigned provider and all admins immediately, writes an
`AuditLog` entry, and returns a generic, publicly known emergency-resource
notice to the caller. This is an interim conservative safety net, not the
DOCX's still-outstanding "approved safety/emergency language and DWS/
Government routing procedure," which needs to be supplied by the
organization separately.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from app.core.notification_rules import SAFETY_BOUNDARY_PRIORITY_FLAG, scan_for_opsec_terms
from app.core.roles import ADMIN_ROLES
from app.core.safety_boundary import SAFETY_NOTICE, scan_for_safety_boundary_terms
from app.core.security import utc_now
from app.core.support_pathways import get_support_pathway, get_support_pathways
from app.models.onboarding_answer import OnboardingAnswer
from app.models.support_request import SupportRequest
from app.models.team_assignment import STATUS_ENABLED, TeamAssignment
from app.models.user import User
from app.schemas.support import SupportRequestCreate
from app.services.audit_log_service import AuditLogService
from app.services.notification_service import NotificationService

SUPPORT_PATHWAYS_QUESTION_ID = 18
ALLOWED_REQUEST_STATUSES = {"open", "in_progress", "resolved"}


class SupportService:
    """Return the support pathway catalog scoped to a user's opt-ins, and handle requests."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()
        self.audit_log_service = AuditLogService()

    async def get_pathways_for_user(self, user: User) -> dict[str, Any]:
        """Return always-available pathways plus the user's opted-in ones."""
        opted_in = await self.get_opted_in_pathways(user)
        team_enabled = await self._get_team_enabled_pathways(user)
        opted_in = opted_in | team_enabled
        pathways = [
            {
                "key": pathway["key"],
                "label": pathway["label"],
                "description": pathway["description"],
                "availability_status": "Available",
            }
            for pathway in get_support_pathways()
            if pathway["always_available"] or pathway["key"] in opted_in
        ]
        return {"pathways": pathways}

    async def create_request(self, user: User, payload: SupportRequestCreate) -> dict[str, Any]:
        """Create a support request against any of the 5 defined support pathways."""
        matched = get_support_pathway(payload.pathway_key)
        if matched is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown support pathway.",
            )

        message = payload.message.strip() if payload.message else None
        safety_terms = scan_for_safety_boundary_terms(message) if message else []
        if message and not safety_terms:
            blocked_terms = scan_for_opsec_terms(message)
            if blocked_terms:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Request content was blocked by the OPSEC content scan.",
                        "blocked_terms": blocked_terms,
                    },
                )

        record = SupportRequest(
            user_id=user.id,
            pathway_key=matched["key"],
            pathway_label=matched["label"],
            message=message,
            priority_flag=bool(safety_terms),
            safety_flag_terms=safety_terms,
        )
        await record.insert()

        if safety_terms:
            await self._notify_safety_flag(user, matched, record, safety_terms)
        else:
            await self.notification_service.notify(
                user.id,
                family="support_request_updates",
                title=f"Support request sent to {record.pathway_label}",
                body="Your support team will follow up soon.",
                related_entity_type="support_request",
                related_entity_id=str(record.id),
            )
        return self._serialize_request(record)

    async def list_requests(self, user: User) -> dict[str, Any]:
        """Return the user's support requests, most recent first."""
        records = await SupportRequest.find(SupportRequest.user_id == user.id).to_list()
        records.sort(key=lambda item: item.created_at, reverse=True)
        return {"requests": [self._serialize_request(record) for record in records]}

    async def list_assigned_requests(self, user: User) -> dict[str, Any]:
        """Return support requests routed to the calling provider's role (Admin sees all)."""
        if user.role in ADMIN_ROLES:
            records = await SupportRequest.find().to_list()
        else:
            records = await SupportRequest.find(SupportRequest.pathway_key == user.role).to_list()
        records.sort(key=lambda item: item.created_at, reverse=True)

        requester_ids = {record.user_id for record in records}
        requesters = {user_id: await User.get(user_id) for user_id in requester_ids}
        return {
            "requests": [
                self._serialize_request(record, requester=requesters.get(record.user_id))
                for record in records
            ]
        }

    async def update_request_status(
        self, user: User, request_id: str, new_status: str
    ) -> dict[str, Any]:
        """Let the assigned provider (or Admin) update a support request's status."""
        if new_status not in ALLOWED_REQUEST_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unknown status.", "allowed": sorted(ALLOWED_REQUEST_STATUSES)},
            )
        record = await SupportRequest.get(request_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
        if user.role not in ADMIN_ROLES and record.pathway_key != user.role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This request is not routed to your role.",
            )

        record.status = new_status
        record.updated_at = utc_now()
        await record.save()
        await self.notification_service.notify(
            record.user_id,
            family="support_request_updates",
            title=f"Update on your {record.pathway_label} request",
            body=f"Your support request is now {new_status.replace('_', ' ')}.",
            related_entity_type="support_request",
            related_entity_id=str(record.id),
        )
        return self._serialize_request(record)

    async def _notify_safety_flag(
        self,
        user: User,
        pathway: dict[str, Any],
        record: SupportRequest,
        safety_terms: list[str],
    ) -> None:
        """Notify the assigned provider and all admins of a Level 5 safety-boundary flag."""
        await self.audit_log_service.record(
            event_type="safety_boundary_priority_flag",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="support_request",
            target_entity_id=str(record.id),
            summary_message=f"Safety-boundary keyword flag on a {record.pathway_label} support request.",
            metadata_payload={"pathway_key": record.pathway_key, "matched_terms": safety_terms},
        )

        recipients: list[User] = []
        if pathway["role"] is not None:
            provider = await self._find_active_provider(pathway["role"])
            if provider is not None:
                recipients.append(provider)
        admins: list[User] = []
        for admin_role in ADMIN_ROLES:
            admins.extend(await User.find(User.role == admin_role).to_list())
        recipients.extend(admin for admin in admins if admin.is_active)

        for recipient in recipients:
            await self.notification_service.notify(
                recipient.id,
                family=SAFETY_BOUNDARY_PRIORITY_FLAG,
                title=f"Priority: safety-flagged {record.pathway_label} request",
                body=f"A support request from {user.full_name} was flagged for immediate review.",
                related_entity_type="support_request",
                related_entity_id=str(record.id),
                send_email=True,
            )

    async def _find_active_provider(self, role: str) -> User | None:
        """Return the first active user with a given provider role, if any exists."""
        candidates = await User.find(User.role == role).to_list()
        active = [u for u in candidates if u.is_active]
        return active[0] if active else None

    def _serialize_request(
        self, record: SupportRequest, requester: User | None = None
    ) -> dict[str, Any]:
        """Convert a stored support request to a transport-safe dict."""
        data = {
            "id": str(record.id),
            "pathway_key": record.pathway_key,
            "pathway_label": record.pathway_label,
            "message": record.message,
            "status": record.status,
            "priority_flag": record.priority_flag,
            "safety_notice": SAFETY_NOTICE if record.priority_flag else None,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
        if requester is not None:
            data["user_id"] = str(requester.id)
            data["user_name"] = requester.full_name
        return data

    async def get_opted_in_pathways(self, user: User) -> set[str]:
        """Return the pathway keys the user opted into during onboarding."""
        answer = await OnboardingAnswer.find_one(
            OnboardingAnswer.user_id == user.id,
            OnboardingAnswer.question_id == SUPPORT_PATHWAYS_QUESTION_ID,
        )
        if answer is None or not isinstance(answer.follow_up_answer, list):
            return set()
        return set(answer.follow_up_answer)

    async def _get_team_enabled_pathways(self, user: User) -> set[str]:
        """Return pathway keys the user has since enabled from the My Team screen."""
        records = await TeamAssignment.find(TeamAssignment.user_id == user.id).to_list()
        return {record.pathway_key for record in records if record.status == STATUS_ENABLED}
