"""Insight request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class InsightGenerateRequest(BaseModel):
    """Payload for explicitly generating an insight."""

    force_refresh: bool = False


class AssistantChatRequest(BaseModel):
    """Payload for assistant chat questions."""

    message: str = Field(min_length=1, max_length=1000)


class ChatMessageRead(BaseModel):
    """Serialized assistant chat history item."""

    role: str
    content: str
    created_at: datetime


class ChatGreetingRead(BaseModel):
    """Serialized assistant greeting payload."""

    title: str
    status: str
    greeting_message: str


class ChatSuggestionRead(BaseModel):
    """Serialized quick suggestion chip."""

    text: str
