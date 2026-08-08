"""Provider credential/certification tracker service (DOCX 1.4.7 PT/IM/SCS
Qualifications - "Credential tracker and BLS expiration support").

Admin manages credentials for any provider; a provider can view their own.
`status` is always derived from `expiration_date` at read time, never
stored, so it's never stale.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.notification_rules import COMPLIANCE_DUE_REMINDERS
from app.models.provider_credential import ProviderCredential
from app.models.user import User
from app.schemas.provider_credential import EXPIRING_SOON_DAYS, CredentialCreate
from app.services.notification_service import NotificationService


class CredentialService:
    """Track and report on provider credentials/certifications."""

    def __init__(self) -> None:
        self.notification_service = NotificationService()

    async def add_credential(self, payload: CredentialCreate, added_by: Any) -> dict[str, Any]:
        """Add a credential/certification record for a provider."""
        provider = await User.get(payload.provider_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")

        record = ProviderCredential(
            provider_id=provider.id,
            credential_type=payload.credential_type,
            issuing_body=payload.issuing_body,
            issued_date=payload.issued_date,
            expiration_date=payload.expiration_date,
            added_by=added_by,
        )
        await record.insert()
        return await self._serialize(record)

    async def list_for_provider(self, provider_id: Any) -> dict[str, Any]:
        """Return every credential on file for one provider."""
        records = await ProviderCredential.find(ProviderCredential.provider_id == provider_id).to_list()
        records.sort(key=lambda item: item.expiration_date or date.max)
        return {"credentials": [await self._serialize(r) for r in records]}

    async def list_all(self) -> dict[str, Any]:
        """Return every credential on file, for the Admin credential dashboard."""
        records = await ProviderCredential.find().to_list()
        records.sort(key=lambda item: item.expiration_date or date.max)
        return {"credentials": [await self._serialize(r) for r in records]}

    async def remind_expiring_soon(self) -> int:
        """Notify each provider whose credential expires within EXPIRING_SOON_DAYS.

        Deduped per credential via a stable `related_entity_id`. Returns the
        number of reminders actually sent.
        """
        today = date.today()
        cutoff = today + timedelta(days=EXPIRING_SOON_DAYS)
        candidates = await ProviderCredential.find(
            ProviderCredential.expiration_date >= today, ProviderCredential.expiration_date <= cutoff
        ).to_list()

        sent = 0
        for record in candidates:
            already_sent = await self.notification_service.exists_since(
                record.provider_id,
                family=COMPLIANCE_DUE_REMINDERS,
                related_entity_type="credential_expiring",
                related_entity_id=str(record.id),
            )
            if already_sent:
                continue
            await self.notification_service.notify(
                record.provider_id,
                family=COMPLIANCE_DUE_REMINDERS,
                title=f"{record.credential_type} expiring soon",
                body=f"Expires {record.expiration_date.isoformat()}.",
                related_entity_type="credential_expiring",
                related_entity_id=str(record.id),
            )
            sent += 1
        return sent

    def _derive_status(self, expiration_date: date | None) -> str:
        """Return current/expiring_soon/expired/no_expiration for a credential."""
        if expiration_date is None:
            return "no_expiration"
        today = date.today()
        if expiration_date < today:
            return "expired"
        if expiration_date <= today + timedelta(days=EXPIRING_SOON_DAYS):
            return "expiring_soon"
        return "current"

    async def _serialize(self, record: ProviderCredential) -> dict[str, Any]:
        """Convert a stored credential to a transport-safe dict."""
        provider = await User.get(record.provider_id)
        return {
            "id": str(record.id),
            "provider_id": str(record.provider_id),
            "provider_name": provider.full_name if provider else None,
            "credential_type": record.credential_type,
            "issuing_body": record.issuing_body,
            "issued_date": record.issued_date.isoformat() if record.issued_date else None,
            "expiration_date": record.expiration_date.isoformat() if record.expiration_date else None,
            "status": self._derive_status(record.expiration_date),
        }
