"""Provider credential tracker schemas."""

from datetime import date

from pydantic import BaseModel, Field

CREDENTIAL_STATUSES = ("current", "expiring_soon", "expired", "no_expiration")
EXPIRING_SOON_DAYS = 60


class CredentialCreate(BaseModel):
    """Add a credential/certification for a provider."""

    provider_id: str
    credential_type: str = Field(min_length=1, max_length=80)
    issuing_body: str | None = Field(default=None, max_length=120)
    issued_date: date | None = None
    expiration_date: date | None = None


class CredentialResponse(BaseModel):
    """A single provider credential."""

    id: str
    provider_id: str
    provider_name: str | None
    credential_type: str
    issuing_body: str | None
    issued_date: str | None
    expiration_date: str | None
    status: str
