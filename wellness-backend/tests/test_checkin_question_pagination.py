"""Regression tests for check-in question pagination."""

import pytest

from app.api.v1.routes import daily_checkins, monthly_checkins, weekly_checkins
from app.services.daily_checkin_service import DailyCheckInService
from app.services.monthly_checkin_service import MonthlyCheckInService
from app.services.weekly_checkin_service import WeeklyCheckInService


@pytest.mark.asyncio
async def test_daily_questions_split_into_two_pages_of_four() -> None:
    service = DailyCheckInService()

    first_page = await service.list_questions(page=1)
    second_page = await service.list_questions(page=2)

    assert first_page["total_pages"] == 2
    assert len(first_page["questions"]) == 4
    assert len(second_page["questions"]) == 4
    assert first_page["questions"][0]["id"] == "dc_1"
    assert second_page["questions"][0]["id"] == "dc_5"


@pytest.mark.asyncio
async def test_weekly_questions_split_into_two_pages_of_five() -> None:
    service = WeeklyCheckInService()

    first_page = await service.list_questions(page=1)
    second_page = await service.list_questions(page=2)

    assert first_page["total_pages"] == 2
    assert len(first_page["questions"]) == 5
    assert len(second_page["questions"]) == 5
    assert first_page["questions"][0]["id"] == "wc_1"
    assert second_page["questions"][0]["id"] == "wc_6"


@pytest.mark.asyncio
async def test_monthly_questions_split_into_seven_and_six() -> None:
    service = MonthlyCheckInService()

    first_page = await service.list_questions(page=1)
    second_page = await service.list_questions(page=2)

    assert first_page["total_pages"] == 2
    assert len(first_page["questions"]) == 7
    assert len(second_page["questions"]) == 6
    assert first_page["questions"][0]["id"] == "mc_1"
    assert second_page["questions"][0]["id"] == "mc_8"


@pytest.mark.asyncio
async def test_daily_questions_route_returns_paged_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_questions(page: int) -> dict[str, object]:
        return {
            "page": page,
            "page_size": 4,
            "total_questions": 8,
            "total_pages": 2,
            "questions": [{"id": "dc_1"}],
        }

    monkeypatch.setattr(daily_checkins.daily_checkin_service, "list_questions", fake_list_questions)

    response = await daily_checkins.list_daily_checkin_questions(page=2)

    assert response["success"] is True
    assert response["data"]["page"] == 2
    assert response["data"]["page_size"] == 4
    assert response["data"]["questions"] == [{"id": "dc_1"}]


@pytest.mark.asyncio
async def test_weekly_questions_route_returns_paged_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_questions(page: int) -> dict[str, object]:
        return {
            "page": page,
            "page_size": 5,
            "total_questions": 10,
            "total_pages": 2,
            "questions": [{"id": "wc_1"}],
        }

    monkeypatch.setattr(weekly_checkins.weekly_checkin_service, "list_questions", fake_list_questions)

    response = await weekly_checkins.list_weekly_checkin_questions(page=2)

    assert response["success"] is True
    assert response["data"]["page"] == 2
    assert response["data"]["page_size"] == 5
    assert response["data"]["questions"] == [{"id": "wc_1"}]


@pytest.mark.asyncio
async def test_monthly_questions_route_returns_paged_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_questions(page: int) -> dict[str, object]:
        return {
            "page": page,
            "page_size": 6,
            "total_questions": 13,
            "total_pages": 2,
            "questions": [{"id": "mc_8"}],
        }

    monkeypatch.setattr(monthly_checkins.monthly_checkin_service, "list_questions", fake_list_questions)

    response = await monthly_checkins.list_monthly_checkin_questions(page=2)

    assert response["success"] is True
    assert response["data"]["page"] == 2
    assert response["data"]["page_size"] == 6
    assert response["data"]["questions"] == [{"id": "mc_8"}]
