"""Direct messaging routes (DOCX section 10)."""

from typing import Any

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from app.api.deps import get_current_user
from app.common.utils.responses import success_response
from app.core.routing_levels import get_routing_levels
from app.models.user import User
from app.schemas.message import ScanPreviewRequest, SendMessageRequest
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
) -> Response:
    """Download a message's attachment (thread participants only)."""
    content, file_name = await messaging_service.get_attachment(current_user, message_id)
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


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
