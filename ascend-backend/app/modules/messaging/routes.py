"""Direct messaging routes (DOCX section 10)."""

import base64
from typing import Any

from fastapi import APIRouter, Depends, File, Form, UploadFile, WebSocket, WebSocketDisconnect, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.core.routing_levels import get_routing_levels
from app.core.security import decode_token
from app.models.message import Message
from app.models.message_thread import MessageThread
from app.models.user import User
from app.schemas.message import (
    GroupThreadCreateRequest,
    GroupThreadSendRequest,
    ScanPreviewRequest,
    SendMessageRequest,
)
from app.services.file_storage_service import guess_content_type
from app.services.messaging_service import MessagingService

router = APIRouter()
messaging_service = MessagingService()


@router.get("/routing-levels", status_code=status.HTTP_200_OK)
async def list_routing_levels(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the DOCX's L0-L5 routing threshold reference table."""
    return success_response("Routing levels loaded successfully.", {"levels": get_routing_levels()})


@router.post("/send", status_code=status.HTTP_201_CREATED)
async def send_message(
    recipient_id: str = Form(...),
    body: str = Form(..., min_length=1, max_length=2000),
    related_recommendation_id: str | None = Form(default=None),
    attachment: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Send a direct message to another user, with an optional file attachment."""
    payload = SendMessageRequest(
        recipient_id=recipient_id, body=body, related_recommendation_id=related_recommendation_id
    )
    data = await messaging_service.send_message(current_user, payload, attachment)
    return success_response("Message sent successfully.", data)


@router.get("/message/{message_id}/attachment")
async def download_message_attachment(
    message_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a message's attachment as base64-encoded JSON (thread participants only)."""
    content, file_name = await messaging_service.get_attachment(current_user, message_id)
    data = {
        "file_name": file_name,
        "content_type": guess_content_type(file_name),
        "file_size_bytes": len(content),
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    return success_response("Attachment loaded successfully.", data)


@router.post("/scan", status_code=status.HTTP_200_OK)
async def scan_message_preview(
    payload: ScanPreviewRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Preview which OPSEC-blocked terms a message would trigger, before sending."""
    data = await messaging_service.scan_preview(payload.body)
    return success_response("Scan preview complete.", data)


@router.get("/threads", status_code=status.HTTP_200_OK)
async def list_threads(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return conversation previews for all of the user's threads."""
    data = await messaging_service.list_threads(current_user)
    return success_response("Threads loaded successfully.", data)


@router.get("/thread/{other_user_id}", status_code=status.HTTP_200_OK)
async def get_thread(
    other_user_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the full message history with one other user."""
    data = await messaging_service.get_thread(current_user, other_user_id)
    return success_response("Thread loaded successfully.", data)


@router.get("/message/{message_id}/trace", status_code=status.HTTP_200_OK)
async def get_message_trace(
    message_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the "Audit & decisions" trace panel for one message."""
    data = await messaging_service.get_message_trace(current_user, message_id)
    return success_response("Message trace loaded successfully.", data)


@router.post("/group-threads", status_code=status.HTTP_201_CREATED)
async def create_group_thread(
    payload: GroupThreadCreateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a real multi-participant group message thread."""
    data = await messaging_service.create_group_thread(current_user, payload)
    return success_response("Group thread created successfully.", data)


@router.post("/group-threads/{thread_id}/send", status_code=status.HTTP_201_CREATED)
async def send_group_message(
    thread_id: str,
    payload: GroupThreadSendRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Send a message into an existing group thread."""
    data = await messaging_service.send_group_message(current_user, thread_id, payload.body)
    return success_response("Message sent successfully.", data)


@router.get("/group-threads", status_code=status.HTTP_200_OK)
async def list_group_threads(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return every real group thread the user is a participant in."""
    data = await messaging_service.list_group_threads(current_user)
    return success_response("Group threads loaded successfully.", data)


@router.get("/group-threads/{thread_id}", status_code=status.HTTP_200_OK)
async def get_group_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a full group thread with its messages."""
    data = await messaging_service.get_group_thread(current_user, thread_id)
    return success_response("Group thread loaded successfully.", data)


@router.websocket("/live")
async def messaging_live(websocket: WebSocket, token: str = "") -> None:
    """Real-time message delivery via a MongoDB change stream (not polling).

    Not DOCX-sourced - reuses the exact real pattern built for the Control
    Plane's Audit-log "Live tail" (`app/modules/admin/routes.py`), including
    awaiting `.watch()` before iterating it. WebSocket routes can't use the
    normal `Depends(get_current_user)` chain, so the token is decoded
    manually here, same as the audit-log live route.

    Group-thread membership is resolved once at connect time; a thread
    joined after the socket opens isn't picked up until the client
    reconnects. Typing indicators are explicitly not built (ephemeral
    UI-only concern, no real backend persistence need).
    """
    try:
        payload = decode_token(token)
        user = await User.get(payload.get("sub")) if payload.get("token_type") == "access" else None
    except ValueError:
        user = None
    if user is None or not user.is_active:
        await websocket.close(code=4403)
        return

    my_threads = await MessageThread.find({"participant_ids": user.id}).to_list()
    my_thread_ids = {str(t.id) for t in my_threads}

    await websocket.accept()
    stream = await Message.get_motor_collection().watch([{"$match": {"operationType": "insert"}}])
    try:
        async for change in stream:
            doc = change.get("fullDocument", {})
            sender_id = str(doc.get("sender_id", ""))
            recipient_id = str(doc["recipient_id"]) if doc.get("recipient_id") else None
            thread_id = str(doc["thread_id"]) if doc.get("thread_id") else None
            is_mine = (
                sender_id == str(user.id)
                or recipient_id == str(user.id)
                or (thread_id is not None and thread_id in my_thread_ids)
            )
            if not is_mine:
                continue
            await websocket.send_json(
                {
                    "id": str(doc.get("_id")),
                    "thread_key": doc.get("thread_key"),
                    "thread_id": thread_id,
                    "sender_id": sender_id,
                    "sender_role": doc.get("sender_role"),
                    "recipient_id": recipient_id,
                    "body": doc.get("body"),
                    "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
                }
            )
    except WebSocketDisconnect:
        return
    finally:
        await stream.close()
