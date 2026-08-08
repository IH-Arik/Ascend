"""Authentication regression tests."""

from datetime import timedelta, datetime
from types import SimpleNamespace

import pytest

from app.schemas.auth import RegisterRequest, VerifyResetCodeRequest
from app.services.auth_service import AuthService
from app.utils.helpers import utc_now


@pytest.mark.asyncio
async def test_verify_reset_code_marks_user_as_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset code verification should mark the account as verified."""
    service = AuthService()
    user = SimpleNamespace(
        id="user-1",
        email="arik@example.com",
        password_reset_code="1234",
        password_reset_expires_at=utc_now() + timedelta(minutes=10),
        is_verified=False,
    )
    captured_update: dict[str, object] = {}

    async def fake_get_by_email(email: str) -> SimpleNamespace:
        assert email == "arik@example.com"
        return user

    async def fake_update_user(user_id: str, data: dict[str, object]) -> SimpleNamespace:
        captured_update["user_id"] = user_id
        captured_update["data"] = data
        user.is_verified = bool(data.get("is_verified"))
        return user

    monkeypatch.setattr(service.user_repository, "get_by_email", fake_get_by_email)
    monkeypatch.setattr(service.user_repository, "update_user", fake_update_user)

    payload = VerifyResetCodeRequest(email="arik@example.com", code="1234")

    response = await service.verify_reset_code(payload)

    assert response == {}
    assert captured_update == {"user_id": "user-1", "data": {"is_verified": True}}
    assert user.is_verified is True


@pytest.mark.asyncio
async def test_register_reactivates_soft_deleted_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-registering a deleted account should reactivate the existing email record."""
    service = AuthService()
    inactive_user = SimpleNamespace(
        id="user-1",
        email="arik@example.com",
        name="Old Name",
        is_active=False,
        is_verified=True,
        onboarding_completed=True,
        organization_name="Old Org",
        role="Old Role",
        created_at=datetime(2026, 4, 24),
    )
    captured_update: dict[str, object] = {}
    sent_email: dict[str, object] = {}

    async def fake_get_by_email(email: str) -> SimpleNamespace:
        assert email == "arik@example.com"
        return inactive_user

    async def fake_update_user(user_id: str, data: dict[str, object]) -> SimpleNamespace:
        captured_update["user_id"] = user_id
        captured_update["data"] = data
        for field_name, value in data.items():
            setattr(inactive_user, field_name, value)
        return inactive_user

    async def fake_send_verification_email(to: str, name: str, code: str) -> None:
        sent_email["to"] = to
        sent_email["name"] = name
        sent_email["code"] = code

    monkeypatch.setattr(service.user_repository, "get_by_email", fake_get_by_email)
    monkeypatch.setattr(service.user_repository, "update_user", fake_update_user)
    monkeypatch.setattr(
        service.email_service,
        "send_verification_email",
        fake_send_verification_email,
    )

    payload = RegisterRequest(
        name="Arik Hassan",
        email="arik@example.com",
        password="SecurePass123!",
        organization_name="Dominion Wellness Solutions",
        role="Operations Lead",
    )

    response = await service.register_user(payload)

    assert response["user"]["email"] == "arik@example.com"
    assert response["user"]["is_verified"] is False
    assert response["user"]["onboarding_completed"] is False
    assert captured_update["user_id"] == "user-1"
    assert captured_update["data"]["is_active"] is True
    assert captured_update["data"]["password_reset_code"] is None
    assert isinstance(captured_update["data"]["email_verification_code"], str)
    assert len(captured_update["data"]["email_verification_code"]) == 4
    assert sent_email == {
        "to": "arik@example.com",
        "name": "Arik Hassan",
        "code": captured_update["data"]["email_verification_code"],
    }
