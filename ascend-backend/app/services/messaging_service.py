"""Direct messaging service (DOCX section 10, Messaging).

`_can_message` is the real roster-based authorization gate, closed
2026-08-10: allowed if either party is Admin/Superadmin (oversight always
reachable), or a real `TeamAssignment` links them (the operator's assigned
SCS/PT-IM, or an opted-in Nutritionist/Mental Performance/Chaplain), or both
parties hold a real provider/admin role (peer coordination between two
specialists/leadership). Replaces the previous placeholder ("any
authenticated, active user can message any other") which is no longer
accurate. Every message body is screened with the same OPSEC keyword scan
used for notifications, per the DOCX's explicit requirement here.

`get_thread` also attaches pathway context (pathway key/label/role title/
assignment status) when the other party's role matches one of the 5 support
pathways - the "Request a message" screen shows the thread as tied to a
specific pathway ("SCS - Strength & ...", "Assigned - active pathway"), so
the thread header needs that context, not just the raw counterparty role.

`send_message` optionally accepts `related_recommendation_id` (the "Assigned
Action"/plan-link a message is a reply about) and writes an `AuditLog` entry
per send, so `get_message_trace` can reconstruct an "Audit & decisions"
panel. Fields that can't be honestly derived from what this backend tracks
are left `null` rather than invented: there is no per-question traceability
on a Recommendation (it's generated from a component score, not a single
check-in question), so `question_id` is always `null`; `opsec_scan` only
reports the server-side result actually performed here, never a claimed
client-side pass this backend has no way to verify.

`send_message` also optionally accepts a file attachment - reuses the same
local-disk Fernet-encrypted `FileStorageService` (namespaced separately from
medical records) and the same malware-scan stub built for medical record
uploads. Attachment access is restricted to the two thread participants,
same as the message content itself.
"""

from __future__ import annotations

from typing import Any

from beanie import PydanticObjectId
from fastapi import HTTPException, UploadFile, status

from app.core.notification_rules import MESSAGE_RECEIVED
from app.core.notification_rules import highest_opsec_severity
from app.core.notification_rules import scan_for_opsec_terms
from app.core.roles import (
    ADMIN_ROLES,
    ROLE_CHAPLAIN,
    ROLE_IDMT,
    ROLE_LEADERSHIP,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_NUTRITIONIST,
    ROLE_PTIM,
    ROLE_SCS,
)
from app.core.support_pathways import get_support_pathways
from app.models.audit_log import AuditLog
from app.models.message import Message, build_thread_key
from app.models.message_thread import MessageThread
from app.models.recommendation import Recommendation
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.schemas.message import (
    MESSAGE_ATTACHMENT_ALLOWED_EXTENSIONS,
    MESSAGE_ATTACHMENT_MAX_BYTES,
    GroupThreadCreateRequest,
    SendMessageRequest,
)
from app.services.audit_log_service import AuditLogService
from app.services.file_storage_service import FileStorageService, scan_file_stub
from app.services.notification_service import NotificationService

import pathlib

PROVIDER_ROLES = (
    ROLE_SCS,
    ROLE_PTIM,
    ROLE_NUTRITIONIST,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_CHAPLAIN,
    ROLE_LEADERSHIP,
    ROLE_IDMT,
    *ADMIN_ROLES,
)

ROLE_SCOPE_DISPLAY = {
    "Airman": "operator",
    "SCS": "scs",
    "PT/IM": "pt/im",
    "Nutritionist": "nutritionist",
    "Mental Performance": "mental performance",
    "Chaplain": "chaplain",
    "Leadership": "leadership",
    "DWS Admin": "admin",
    "DWS Superadmin": "superadmin",
}


class MessagingService:
    """Send and read direct messages between users."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()
        self.audit_log_service = AuditLogService()
        self.storage = FileStorageService(namespace="message_attachments")

    async def send_message(
        self,
        sender: User,
        payload: SendMessageRequest,
        attachment: UploadFile | None = None,
    ) -> dict[str, Any]:
        """Send a direct message, after an OPSEC content screen."""
        recipient = await User.get(payload.recipient_id)
        if recipient is None or not recipient.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient not found.",
            )
        if str(recipient.id) == str(sender.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot message yourself.",
            )
        if not await self._can_message(sender, recipient):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to message this user.",
            )

        related_recommendation = None
        if payload.related_recommendation_id:
            related_recommendation = await Recommendation.get(payload.related_recommendation_id)
            if related_recommendation is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Related plan link not found.",
                )

        blocked_terms = scan_for_opsec_terms(payload.body)
        if blocked_terms:
            severity = highest_opsec_severity(blocked_terms)
            await self.audit_log_service.record(
                event_type="message_blocked_opsec",
                actor_id=sender.id,
                actor_role=sender.role,
                target_entity_type="user",
                target_entity_id=str(recipient.id),
                summary_message=f"Message to {recipient.email} blocked by OPSEC scan (severity {severity}).",
                metadata_payload={"blocked_terms": blocked_terms, "severity": severity},
                outcome_status="blocked",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Message content was blocked by the OPSEC content scan.",
                    "blocked_terms": blocked_terms,
                    "severity": severity,
                },
            )

        attachment_file_name = None
        attachment_storage_path = None
        attachment_file_size_bytes = None
        if attachment is not None and attachment.filename:
            extension = pathlib.Path(attachment.filename).suffix.lower()
            if extension not in MESSAGE_ATTACHMENT_ALLOWED_EXTENSIONS or not scan_file_stub(
                attachment.filename
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This attachment file type is not allowed.",
                )
            content = await attachment.read()
            if len(content) > MESSAGE_ATTACHMENT_MAX_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Attachment exceeds the {MESSAGE_ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB limit.",
                )
            attachment_file_name = attachment.filename
            attachment_file_size_bytes = len(content)
            attachment_storage_path = self.storage.save_file(str(sender.id), attachment.filename, content)

        record = Message(
            thread_key=build_thread_key(str(sender.id), str(recipient.id)),
            sender_id=sender.id,
            sender_role=sender.role,
            recipient_id=recipient.id,
            body=payload.body.strip(),
            source_type="provider_plan_link" if related_recommendation else "user_initiated",
            related_recommendation_id=related_recommendation.id if related_recommendation else None,
            attachment_file_name=attachment_file_name,
            attachment_storage_path=attachment_storage_path,
            attachment_file_size_bytes=attachment_file_size_bytes,
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="message_sent",
            actor_id=sender.id,
            actor_role=sender.role,
            target_entity_type="message",
            target_entity_id=str(record.id),
            summary_message=f"Message sent in thread {record.thread_key}.",
            metadata_payload={
                "opsec_scan": "passed",
                "attachment_count": 1 if attachment_file_name else 0,
                "role_scope": self._role_scope(sender.role, recipient.role),
            },
        )

        await self.notification_service.notify(
            recipient.id,
            family=MESSAGE_RECEIVED,
            title=f"New message from {sender.full_name or sender.role}",
            body=payload.body.strip()[:140],
            related_entity_type="message_thread",
            related_entity_id=record.thread_key,
        )
        return self._serialize(record)

    async def _can_message(self, sender: User, recipient: User) -> bool:
        """Real roster-based authorization gate - see module docstring for the 3 real conditions."""
        if sender.role in ADMIN_ROLES or recipient.role in ADMIN_ROLES:
            return True
        if sender.role in PROVIDER_ROLES and recipient.role in PROVIDER_ROLES:
            return True
        linked = await TeamAssignment.find_one(
            {
                "$or": [
                    {"user_id": sender.id, "provider_user_id": recipient.id},
                    {"user_id": recipient.id, "provider_user_id": sender.id},
                ],
                "status": {"$ne": "disabled"},
            }
        )
        return linked is not None

    async def get_attachment(self, user: User, message_id: str) -> tuple[bytes, str]:
        """Return a message attachment's decrypted bytes + filename.

        Restricted to the two thread participants - same boundary as the
        message content itself.
        """
        message = await Message.get(message_id)
        if message is None or not message.attachment_storage_path:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found.")
        if user.id not in (message.sender_id, message.recipient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This message is not part of one of your threads.",
            )
        content = self.storage.read_file(message.attachment_storage_path)
        return content, message.attachment_file_name or "attachment"

    async def list_threads(self, user: User) -> dict[str, Any]:
        """Return conversation previews for all of a user's threads."""
        messages = await Message.find(
            {"$or": [{"sender_id": user.id}, {"recipient_id": user.id}]}
        ).to_list()
        if not messages:
            return {"threads": []}

        by_thread: dict[str, list[Message]] = {}
        for message in messages:
            by_thread.setdefault(message.thread_key, []).append(message)

        other_user_ids = set()
        for thread_messages in by_thread.values():
            latest = max(thread_messages, key=lambda item: item.created_at)
            other_id = latest.recipient_id if latest.sender_id == user.id else latest.sender_id
            other_user_ids.add(other_id)
        other_users = {u.id: u for u in await User.find({"_id": {"$in": list(other_user_ids)}}).to_list()}

        previews = []
        for thread_key, thread_messages in by_thread.items():
            latest = max(thread_messages, key=lambda item: item.created_at)
            other_id = latest.recipient_id if latest.sender_id == user.id else latest.sender_id
            other_user = other_users.get(other_id)
            unread_count = sum(
                1 for m in thread_messages if m.recipient_id == user.id and not m.is_read
            )
            previews.append(
                {
                    "thread_key": thread_key,
                    "other_user_id": str(other_id),
                    "other_user_name": other_user.full_name if other_user else None,
                    "other_user_role": other_user.role if other_user else "",
                    "last_message_body": latest.body,
                    "last_message_at": latest.created_at.isoformat(),
                    "unread_count": unread_count,
                }
            )
        previews.sort(key=lambda item: item["last_message_at"], reverse=True)
        return {"threads": previews}

    async def get_thread(self, user: User, other_user_id: str) -> dict[str, Any]:
        """Return a full message thread with one other user, marking it read."""
        thread_key = build_thread_key(str(user.id), other_user_id)
        messages = await Message.find(Message.thread_key == thread_key).to_list()
        messages.sort(key=lambda item: item.created_at)

        unread = [m for m in messages if m.recipient_id == user.id and not m.is_read]
        for message in unread:
            message.is_read = True
            await message.save()

        other_user = await User.get(other_user_id)
        pathway_context = await self._get_pathway_context(user, other_user) if other_user else None

        return {
            "thread_key": thread_key,
            "other_user_id": str(other_user.id) if other_user else other_user_id,
            "other_user_name": other_user.full_name if other_user else None,
            "other_user_role": other_user.role if other_user else "",
            "pathway_context": pathway_context,
            "messages": [self._serialize(m) for m in messages],
        }

    async def scan_preview(self, body: str) -> dict[str, Any]:
        """Preview which OPSEC-blocked terms a message body would trigger, without sending it."""
        blocked_terms = scan_for_opsec_terms(body)
        return {"blocked_terms": blocked_terms, "severity": highest_opsec_severity(blocked_terms)}

    async def get_message_trace(self, user: User, message_id: str) -> dict[str, Any]:
        """Return the "Audit & decisions" trace panel for one message."""
        message = await Message.get(message_id)
        if message is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")
        if user.id not in (message.sender_id, message.recipient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This message is not part of one of your threads.",
            )

        recommendation = (
            await Recommendation.get(message.related_recommendation_id)
            if message.related_recommendation_id
            else None
        )
        recipient = await User.get(message.recipient_id)

        thread_source = {
            "source_type": message.source_type,
            "plan_link_id": str(recommendation.id) if recommendation else None,
            "readiness_driver": recommendation.readiness_component if recommendation else None,
            "route_level": recommendation.route_level if recommendation else None,
            "assigned_to": recipient.full_name if recipient else None,
        }

        # `question_id` is deliberately absent: a Recommendation is generated from
        # a component score, not a single check-in question, so there is no real
        # per-question id to report here without inventing one.

        audit_entry = await AuditLog.find_one(
            AuditLog.target_entity_type == "message", AuditLog.target_entity_id == str(message.id)
        )
        last_send_audit = None
        if audit_entry is not None:
            last_send_audit = {
                "message_id": str(message.id),
                "audit_event_id": str(audit_entry.id),
                "audit_timestamp": audit_entry.created_at.isoformat(),
                "attachment_count": audit_entry.metadata_payload.get("attachment_count", 0),
                "opsec_scan": f"{audit_entry.metadata_payload.get('opsec_scan', 'passed')} (server)",
                "role_scope": audit_entry.metadata_payload.get(
                    "role_scope", self._role_scope(message.sender_role, recipient.role if recipient else "")
                ),
            }

        return {"thread_source": thread_source, "last_send_audit": last_send_audit}

    def _role_scope(self, sender_role: str, recipient_role: str) -> str:
        """Return a "sender · recipient · (allowed)" role-scope string for the audit trace."""
        sender_display = ROLE_SCOPE_DISPLAY.get(sender_role, sender_role.lower())
        recipient_display = ROLE_SCOPE_DISPLAY.get(recipient_role, recipient_role.lower())
        return f"{sender_display} · {recipient_display} · (allowed)"

    async def _get_pathway_context(self, user: User, other_user: User) -> dict[str, Any] | None:
        """Return the support pathway this thread belongs to, if the other party is a provider."""
        pathway = next(
            (p for p in get_support_pathways() if p["role"] == other_user.role), None
        )
        if pathway is None:
            return None
        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == user.id, TeamAssignment.pathway_key == pathway["key"]
        )
        return {
            "pathway_key": pathway["key"],
            "label": pathway["label"],
            "role_title": pathway["role_title"],
            "status": assignment.status if assignment is not None else None,
        }

    async def create_group_thread(self, creator: User, payload: GroupThreadCreateRequest) -> dict[str, Any]:
        """Create a real multi-participant group thread.

        Every pair of participants (not just creator-to-each) must be
        real-authorized to message each other via `_can_message` - a group
        thread can't be used to route around the 1:1 roster gate.
        """
        unique_ids = {creator.id, *(PydanticObjectId(pid) for pid in payload.participant_ids)}
        if len(unique_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A group thread needs at least 2 distinct participants.",
            )
        participants = await User.find({"_id": {"$in": list(unique_ids)}}).to_list()
        if len(participants) != len(unique_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more participants were not found.")

        for a in participants:
            for b in participants:
                if a.id != b.id and not await self._can_message(a, b):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"{a.full_name or a.role} is not authorized to message {b.full_name or b.role}.",
                    )

        thread = MessageThread(participant_ids=list(unique_ids), title=payload.title, created_by=creator.id)
        await thread.insert()
        return await self._serialize_group_thread(thread)

    async def send_group_message(self, sender: User, thread_id: str, body: str) -> dict[str, Any]:
        """Send a message into an existing group thread."""
        thread = await MessageThread.get(thread_id)
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group thread not found.")
        if sender.id not in thread.participant_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not a participant in this thread.")

        blocked_terms = scan_for_opsec_terms(body)
        if blocked_terms:
            severity = highest_opsec_severity(blocked_terms)
            await self.audit_log_service.record(
                event_type="message_blocked_opsec",
                actor_id=sender.id,
                actor_role=sender.role,
                target_entity_type="message_thread",
                target_entity_id=str(thread.id),
                summary_message=f"Group message in thread {thread.id} blocked by OPSEC scan (severity {severity}).",
                metadata_payload={"blocked_terms": blocked_terms, "severity": severity},
                outcome_status="blocked",
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Message content was blocked by the OPSEC content scan.",
                    "blocked_terms": blocked_terms,
                    "severity": severity,
                },
            )

        record = Message(
            thread_id=thread.id,
            sender_id=sender.id,
            sender_role=sender.role,
            body=body.strip(),
        )
        await record.insert()

        await self.audit_log_service.record(
            event_type="message_sent",
            actor_id=sender.id,
            actor_role=sender.role,
            target_entity_type="message",
            target_entity_id=str(record.id),
            summary_message=f"Message sent in group thread {thread.id}.",
            metadata_payload={"opsec_scan": "passed", "thread_id": str(thread.id)},
        )

        for participant_id in thread.participant_ids:
            if participant_id != sender.id:
                await self.notification_service.notify(
                    participant_id,
                    family=MESSAGE_RECEIVED,
                    title=f"New message from {sender.full_name or sender.role}",
                    body=body.strip()[:140],
                    related_entity_type="message_thread",
                    related_entity_id=str(thread.id),
                )
        return self._serialize(record)

    async def list_group_threads(self, user: User) -> dict[str, Any]:
        """Return every real group thread the user is a participant in."""
        threads = await MessageThread.find({"participant_ids": user.id}).to_list()
        threads.sort(key=lambda item: item.created_at, reverse=True)
        return {"threads": [await self._serialize_group_thread(t) for t in threads]}

    async def get_group_thread(self, user: User, thread_id: str) -> dict[str, Any]:
        """Return a full group thread with its messages, if the user is a participant."""
        thread = await MessageThread.get(thread_id)
        if thread is None or user.id not in thread.participant_ids:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group thread not found.")
        messages = await Message.find(Message.thread_id == thread.id).to_list()
        messages.sort(key=lambda item: item.created_at)
        data = await self._serialize_group_thread(thread)
        data["messages"] = [self._serialize(m) for m in messages]
        return data

    async def _serialize_group_thread(self, thread: MessageThread) -> dict[str, Any]:
        """Convert a stored group thread to a transport-safe dict (without messages)."""
        participants = await User.find({"_id": {"$in": thread.participant_ids}}).to_list()
        by_id = {p.id: p for p in participants}
        return {
            "id": str(thread.id),
            "title": thread.title,
            "created_by": str(thread.created_by),
            "created_at": thread.created_at.isoformat(),
            "participants": [
                {
                    "id": str(pid),
                    "name": by_id[pid].full_name if pid in by_id else None,
                    "role": by_id[pid].role if pid in by_id else None,
                }
                for pid in thread.participant_ids
            ],
        }

    def _serialize(self, record: Message) -> dict[str, Any]:
        """Convert a stored message to a transport-safe dict (1:1 or group)."""
        return {
            "id": str(record.id),
            "thread_key": record.thread_key,
            "thread_id": str(record.thread_id) if record.thread_id else None,
            "sender_id": str(record.sender_id),
            "sender_role": record.sender_role,
            "recipient_id": str(record.recipient_id) if record.recipient_id else None,
            "body": record.body,
            "is_read": record.is_read,
            "source_type": record.source_type,
            "related_recommendation_id": (
                str(record.related_recommendation_id) if record.related_recommendation_id else None
            ),
            "attachment": (
                {
                    "file_name": record.attachment_file_name,
                    "file_size_bytes": record.attachment_file_size_bytes,
                }
                if record.attachment_storage_path
                else None
            ),
            "created_at": record.created_at.isoformat(),
        }
