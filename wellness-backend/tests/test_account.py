"""Account lifecycle regression tests."""

from types import SimpleNamespace

import pytest

from app.services.account_service import AccountService


@pytest.mark.asyncio
async def test_delete_account_deactivates_user_and_deletes_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting an account should cascade through all user-owned records."""
    service = AccountService()
    user = SimpleNamespace(id="user-1")
    deleted_user = SimpleNamespace(id="user-1")
    captured_calls: list[tuple[str, object]] = []

    async def fake_delete_scores(user_id: str) -> int:
        captured_calls.append(("scores", user_id))
        return 2

    async def fake_delete_assessments(user_id: str) -> int:
        captured_calls.append(("assessments", user_id))
        return 1

    async def fake_delete_daily(user_id: str) -> int:
        captured_calls.append(("daily", user_id))
        return 3

    async def fake_delete_weekly(user_id: str) -> int:
        captured_calls.append(("weekly", user_id))
        return 1

    async def fake_delete_monthly(user_id: str) -> int:
        captured_calls.append(("monthly", user_id))
        return 1

    async def fake_delete_profile(user_id: str) -> bool:
        captured_calls.append(("profile", user_id))
        return True

    async def fake_delete_user(user_id: str) -> SimpleNamespace:
        captured_calls.append(("user", user_id))
        assert user_id == "user-1"
        return deleted_user

    monkeypatch.setattr(service.user_repository, "delete_user", fake_delete_user)
    monkeypatch.setattr(service.score_repository, "delete_by_user_id", fake_delete_scores)
    monkeypatch.setattr(
        service.assessment_repository,
        "delete_by_user_id",
        fake_delete_assessments,
    )
    monkeypatch.setattr(
        service.daily_checkin_repository,
        "delete_by_user_id",
        fake_delete_daily,
    )
    monkeypatch.setattr(
        service.weekly_checkin_repository,
        "delete_by_user_id",
        fake_delete_weekly,
    )
    monkeypatch.setattr(
        service.monthly_checkin_repository,
        "delete_by_user_id",
        fake_delete_monthly,
    )
    monkeypatch.setattr(
        service.profile_repository,
        "delete_by_user_id",
        fake_delete_profile,
    )

    response = await service.delete_account(user)

    assert response == {
        "action": "delete_account",
        "detail": "Account deleted successfully.",
    }
    assert captured_calls == [
        ("scores", "user-1"),
        ("assessments", "user-1"),
        ("daily", "user-1"),
        ("weekly", "user-1"),
        ("monthly", "user-1"),
        ("profile", "user-1"),
        ("user", "user-1"),
    ]
