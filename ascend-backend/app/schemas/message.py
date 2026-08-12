"""Direct messaging schemas (DOCX section 10).

`SendMessageRequest` documents the field shapes only - the actual
`POST /messaging/send` route accepts these as multipart form fields (plus
an optional file), not a JSON body, since an attachment may be present.
"""

from pydantic import BaseModel, Field

MESSAGE_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024
MESSAGE_ATTACHMENT_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".heic"}


class SendMessageRequest(BaseModel):
    """Send a direct message to another user."""

    recipient_id: str
    body: str = Field(min_length=1, max_length=2000)
    related_recommendation_id: str | None = None


class MessageAttachment(BaseModel):
    """A file attached to a message."""

    file_name: str
    file_size_bytes: int


class MessageResponse(BaseModel):
    """A single direct message."""

    id: str
    thread_key: str
    sender_id: str
    sender_role: str
    recipient_id: str
    body: str
    is_read: bool
    source_type: str
    related_recommendation_id: str | None
    attachment: MessageAttachment | None
    created_at: str


class ThreadSource(BaseModel):
    """Where a message thread originated - a plan link, or the operator directly."""

    source_type: str
    plan_link_id: str | None
    readiness_driver: str | None
    route_level: str | None
    assigned_to: str | None


class LastSendAuditRow(BaseModel):
    """Audit trace for the most recent message send in a thread."""

    message_id: str
    audit_event_id: str
    audit_timestamp: str
    attachment_count: int
    opsec_scan: str
    role_scope: str


class MessageTraceResponse(BaseModel):
    """The "Audit & decisions" trace panel for a message thread."""

    thread_source: ThreadSource
    last_send_audit: LastSendAuditRow | None


class ThreadPreview(BaseModel):
    """A conversation preview for the thread list screen."""

    thread_key: str
    other_user_id: str
    other_user_name: str | None
    other_user_role: str
    last_message_body: str
    last_message_at: str
    unread_count: int


class PathwayContext(BaseModel):
    """The support pathway a message thread belongs to, if the other party is a provider."""

    pathway_key: str
    label: str
    role_title: str
    status: str | None


class ScanPreviewRequest(BaseModel):
    """Preview a message body against the OPSEC content scan before sending."""

    body: str = Field(max_length=2000)


class GroupThreadCreateRequest(BaseModel):
    """Create a real multi-participant group message thread."""

    participant_ids: list[str] = Field(min_length=1)
    title: str | None = Field(default=None, max_length=120)


class GroupThreadSendRequest(BaseModel):
    """Send a message into an existing group thread."""

    body: str = Field(min_length=1, max_length=2000)
