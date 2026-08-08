"""Provider credential/certification tracker (DOCX 1.4.7 PT/IM Qualifications,
1.4.7 SCS Qualifications - "Credential tracker and BLS expiration support" /
"Credential tracker and certification status support").
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ProviderCredential(Document):
    """A single credential/certification held by a provider (SCS or PT/IM)."""

    provider_id: PydanticObjectId
    credential_type: str
    issuing_body: str | None = None
    issued_date: date | None = None
    expiration_date: date | None = None
    added_by: PydanticObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "provider_credentials"
        indexes = [
            IndexModel([("provider_id", 1), ("expiration_date", 1)]),
        ]
