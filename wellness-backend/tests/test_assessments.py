"""Assessment route regression tests."""

from datetime import datetime
from types import SimpleNamespace

import pytest
from beanie import PydanticObjectId

from app.services import assessment_service as assessment_service_module
from app.models.assessment import Answer
from app.api.v1.routes import questions as question_routes
from app.schemas.assessment import CheckInCreate
from app.services.assessment_service import AssessmentService


@pytest.mark.asyncio
async def test_list_questions_defaults_to_five_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure onboarding assessment questions default to 5 per page."""
    captured: dict[str, int] = {}

    async def fake_list_questions(page: int, size: int) -> dict[str, object]:
        captured["page"] = page
        captured["size"] = size
        return {
            "total": 25,
            "page": page,
            "size": size,
            "total_pages": 5,
            "questions": [],
        }

    monkeypatch.setattr(question_routes.assessment_service, "list_questions", fake_list_questions)

    response = await question_routes.list_questions()

    assert captured == {"page": 1, "size": 5}
    assert response["success"] is True
    assert response["data"]["size"] == 5
    assert response["data"]["total_pages"] == 5


def test_serialize_question_uses_stable_question_code() -> None:
    """Ensure client-facing assessment question IDs are stable codes like q01."""
    service = AssessmentService()
    question = SimpleNamespace(
        code="q01",
        text="How would you describe your energy on most days?",
        driver="RC",
        response_type="scale",
        options=["Very Low", "Low", "Average", "High", "Very High"],
        weight=1.0,
        order=1,
    )

    serialized = service._serialize_question(question)

    assert serialized["id"] == "q01"


@pytest.mark.asyncio
async def test_submit_assessment_marks_onboarding_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Completing onboarding assessment should persist onboarding completion."""
    service = AssessmentService()
    user_id = PydanticObjectId()
    user = SimpleNamespace(id=user_id, onboarding_completed=False)
    questions = [
        SimpleNamespace(
            code=f"q{i:02d}",
            text=f"Question {i}",
            options=["Very Low", "Low", "Average", "High", "Very High"],
        )
        for i in range(1, 26)
    ]
    payload = CheckInCreate(
        answers=[
            {"question_id": question.code, "answer": "Average"} for question in questions
        ]
    )
    captured_update: dict[str, object] = {}

    async def fake_get_reassessment_status(current_user: SimpleNamespace) -> dict[str, object]:
        assert current_user is user
        return {"can_submit_assessment": True}

    async def fake_list_all() -> list[SimpleNamespace]:
        return questions

    def fake_normalize_answer(question: SimpleNamespace, answer_text: str) -> Answer:
        return Answer(
            question_id=question.code,
            driver="RC",
            answer_text=answer_text,
            numeric_value=3,
        )

    async def fake_create_checkin(_checkin: object) -> SimpleNamespace:
        return SimpleNamespace(id="checkin-1", submitted_at=datetime(2026, 4, 24))

    async def fake_dimension_scores(_answers: list[Answer]) -> SimpleNamespace:
        return SimpleNamespace(model_dump=lambda: {"rc": 75.0})

    async def fake_overall_score(_dimension_scores: object, assessment_kind: str) -> float:
        assert assessment_kind == "onboarding"
        return 80.0

    async def fake_condition(_overall_score: float) -> str:
        return "Stable"

    async def fake_create_score(_score: object) -> SimpleNamespace:
        return SimpleNamespace()

    async def fake_update_user(user_id: str, data: dict[str, object]) -> SimpleNamespace:
        captured_update["user_id"] = user_id
        captured_update["data"] = data
        return user

    class FakeCheckIn:
        def __init__(self, user_id: PydanticObjectId, answers: list[Answer]) -> None:
            self.user_id = user_id
            self.answers = answers

    class FakeScore:
        def __init__(self, **kwargs: object) -> None:
            self.payload = kwargs

    monkeypatch.setattr(service, "get_reassessment_status", fake_get_reassessment_status)
    monkeypatch.setattr(service.question_repository, "list_all", fake_list_all)
    monkeypatch.setattr(service, "_normalize_answer", fake_normalize_answer)
    monkeypatch.setattr(assessment_service_module, "CheckIn", FakeCheckIn)
    monkeypatch.setattr(assessment_service_module, "Score", FakeScore)
    monkeypatch.setattr(service.assessment_repository, "create", fake_create_checkin)
    monkeypatch.setattr(
        service.scoring_service,
        "calculate_dimension_scores",
        fake_dimension_scores,
    )
    monkeypatch.setattr(
        service.scoring_service,
        "calculate_overall_score",
        fake_overall_score,
    )
    monkeypatch.setattr(service.scoring_service, "classify_condition", fake_condition)
    monkeypatch.setattr(service.score_repository, "create", fake_create_score)
    monkeypatch.setattr(service.user_repository, "update_user", fake_update_user)

    response = await service.submit_assessment(user, payload)

    assert response["overall_score"] == 80.0
    assert captured_update == {
        "user_id": str(user_id),
        "data": {"onboarding_completed": True},
    }
    assert user.onboarding_completed is True
