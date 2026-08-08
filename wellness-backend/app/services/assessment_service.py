"""Assessment and score orchestration service."""

from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.db.repositories.assessment_repo import AssessmentRepository
from app.db.repositories.question_repo import QuestionRepository
from app.db.repositories.score_repo import ScoreRepository
from app.db.repositories.user_repo import UserRepository
from app.models.assessment import Answer, CheckIn
from app.models.question import Question
from app.models.score import Score
from app.models.user import User
from app.schemas.assessment import CheckInCreate
from app.services.scoring_service import ScoringService
from app.utils.constants import (
    ASSESSMENT_QUESTION_COUNT,
    REVERSE_SCORED_QUESTION_TEXTS,
)
from app.utils.response import error_response


class AssessmentService:
    """Service for fixed assessment question retrieval and submission."""

    REASSESSMENT_INTERVAL_DAYS = 90

    def __init__(self) -> None:
        """Initialize service dependencies."""
        self.question_repository = QuestionRepository()
        self.assessment_repository = AssessmentRepository()
        self.score_repository = ScoreRepository()
        self.user_repository = UserRepository()
        self.scoring_service = ScoringService()



    async def list_questions(self, page: int = 1, size: int = 5) -> dict[str, Any]:
        """Return the fixed question bank ordered for display, with pagination."""
        questions = await self.question_repository.list_all()
        total = len(questions)
        
        # Slicing logic
        start = (page - 1) * size
        if start < 0:
            start = 0
            
        if start >= total and total > 0:
            start = ((total - 1) // size) * size
            
        end = start + size
        paged_questions = questions[start:end]
        
        return {
            "total": total,
            "page": page,
            "size": size,
            "total_pages": (total + size - 1) // size if size > 0 else 1,
            "questions": [self._serialize_question(q) for q in paged_questions]
        }

    async def submit_assessment(
        self,
        current_user: User,
        payload: CheckInCreate,
    ) -> dict[str, Any]:
        """Validate, score, and persist a completed assessment."""
        eligibility = await self.get_reassessment_status(current_user)
        if not eligibility["can_submit_assessment"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    eligibility["lock_message"],
                    {
                        "next_eligible_date": eligibility["next_eligible_date"],
                        "days_remaining": eligibility["days_remaining"],
                    },
                ),
            )

        questions = await self.question_repository.list_all()
        if len(questions) != ASSESSMENT_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_response("Question bank is not properly initialized."),
            )

        if len(payload.answers) != ASSESSMENT_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Exactly 25 answers are required.",
                    {"answers": f"Expected {ASSESSMENT_QUESTION_COUNT} answers."},
                ),
            )

        question_map = {question.code: question for question in questions}
        submitted_ids = [item.question_id for item in payload.answers]

        if len(set(submitted_ids)) != ASSESSMENT_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Duplicate answers are not allowed.",
                    {"answers": "Each question must be answered exactly once."},
                ),
            )

        if set(submitted_ids) != set(question_map.keys()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Submitted answers do not match the required question set.",
                    {"answers": "All 25 required questions must be answered exactly once."},
                ),
            )

        normalized_answers = [
            self._normalize_answer(question_map[item.question_id], item.answer)
            for item in payload.answers
        ]

        checkin = await self.assessment_repository.create(
            CheckIn(user_id=current_user.id, answers=normalized_answers)
        )

        dimension_scores = await self.scoring_service.calculate_dimension_scores(
            normalized_answers
        )
        overall_score = await self.scoring_service.calculate_overall_score(
            dimension_scores,
            assessment_kind="onboarding",
        )
        condition = await self.scoring_service.classify_condition(overall_score)

        await self.score_repository.create(
            Score(
                user_id=current_user.id,
                checkin_id=checkin.id,
                dimension_scores=dimension_scores,
                overall_score=overall_score,
                condition=condition,
            )
        )

        if not current_user.onboarding_completed:
            await self.user_repository.update_user(
                str(current_user.id),
                {"onboarding_completed": True},
            )
            current_user.onboarding_completed = True

        return {
            "overall_score": overall_score,
            "condition": condition,
            "dimension_scores": dimension_scores.model_dump(),
            "next_reassessment_date": (
                checkin.submitted_at.date() + timedelta(days=self.REASSESSMENT_INTERVAL_DAYS)
            ).isoformat(),
        }

    async def get_reassessment_status(self, current_user: User) -> dict[str, Any]:
        """Return 90-day reassessment eligibility for the authenticated user."""
        latest_checkin = await self._get_latest_assessment(current_user.id)
        if latest_checkin is None:
            return {
                "can_submit_assessment": True,
                "is_initial_assessment": True,
                "last_assessment_date": None,
                "next_eligible_date": None,
                "days_remaining": 0,
                "lock_message": None,
            }

        last_assessment_date = latest_checkin.submitted_at.date()
        next_eligible_date = last_assessment_date + timedelta(
            days=self.REASSESSMENT_INTERVAL_DAYS
        )
        days_remaining = max((next_eligible_date - date.today()).days, 0)
        can_submit = days_remaining == 0

        return {
            "can_submit_assessment": can_submit,
            "is_initial_assessment": False,
            "last_assessment_date": last_assessment_date.isoformat(),
            "next_eligible_date": next_eligible_date.isoformat(),
            "days_remaining": days_remaining,
            "lock_message": None
            if can_submit
            else (
                f"Assessment unlock হবে every 90 days. "
                f"Next reassessment date: {next_eligible_date.isoformat()}."
            ),
        }

    async def get_latest_score(self, current_user: User) -> dict[str, Any]:
        """Return the latest score for the authenticated user."""
        score = await self.score_repository.get_latest_by_user_id(current_user.id)
        if score is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("No scores found for this user."),
            )
        return self._serialize_score(score)

    async def get_score_history(self, current_user: User) -> dict[str, Any]:
        """Return full score history for the authenticated user."""
        scores = await self.score_repository.list_by_user_id(current_user.id)
        return {"items": [self._serialize_score(score) for score in scores]}

    async def get_score_by_checkin(
        self,
        current_user: User,
        checkin_id: str,
    ) -> dict[str, Any]:
        """Return a score by its related check-in identifier."""
        score = await self.score_repository.get_by_checkin_id(current_user.id, checkin_id)
        if score is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Score not found for the specified check-in."),
            )
        return self._serialize_score(score)

    def _normalize_answer(self, question: Question, answer_text: str) -> Answer:
        """Validate and normalize a submitted answer against a question."""
        normalized_input = answer_text.strip().casefold()
        options_lookup = {
            option.strip().casefold(): index for index, option in enumerate(question.options)
        }
        if normalized_input not in options_lookup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid answer option submitted.",
                    {question.code: f"Answer must match one of: {', '.join(question.options)}"},
                ),
            )

        option_index = options_lookup[normalized_input]
        numeric_value = self.scoring_service.map_option_to_score(
            option_index,
            len(question.options),
            reverse_scored=self._is_reverse_scored(question),
        )
        return Answer(
            question_id=question.code,
            question_text=question.text,
            answer_text=question.options[option_index],
            numeric_value=numeric_value,
            driver=question.driver,
        )

    def _is_reverse_scored(self, question: Question) -> bool:
        """Return whether an assessment question should use reverse scoring."""
        return (
            bool(getattr(question, "reverse_scored", False))
            or question.text in REVERSE_SCORED_QUESTION_TEXTS
        )


    def _serialize_question(self, question: Question) -> dict[str, Any]:
        """Return a serialized question payload."""
        return {
            "id": question.code,
            "text": question.text,
            "driver": question.driver,
            "response_type": question.response_type,
            "options": question.options,
            "weight": question.weight,
            "order": question.order,
            "step": (question.order - 1) // 5 + 1 if question.order > 0 else 1
        }

    def _serialize_score(self, score: Score) -> dict[str, Any]:
        """Return a serialized score payload."""
        return {
            "id": str(score.id),
            "user_id": str(score.user_id),
            "checkin_id": str(score.checkin_id),
            "dimension_scores": score.dimension_scores.model_dump(),
            "overall_score": score.overall_score,
            "condition": score.condition,
            "created_at": score.created_at,
        }

    async def _get_latest_assessment(self, user_id: Any) -> CheckIn | None:
        """Return the latest baseline assessment for a user."""
        checkins = await self.assessment_repository.list_by_user_id(user_id)
        return checkins[0] if checkins else None
