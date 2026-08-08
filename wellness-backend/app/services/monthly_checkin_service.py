"""Monthly check-in service."""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.behavior_log_repo import BehaviorLogRepository
from app.db.repositories.monthly_checkin_repo import MonthlyCheckInRepository
from app.db.repositories.score_repo import ScoreRepository
from app.models.behavior import BehaviorType
from app.models.assessment import Answer, MonthlyCheckIn
from app.models.score import Score
from app.models.user import User
from app.schemas.assessment import MonthlyCheckInCreate
from app.services.scoring_service import ScoringService
from app.services.streak_service import StreakService
from app.utils.constants import (
    MONTHLY_CHECKIN_QUESTION_BANK,
    MONTHLY_CHECKIN_QUESTION_COUNT,
    REVERSE_SCORED_QUESTION_IDS,
)
from app.utils.response import error_response


class MonthlyCheckInService:
    """Service for fixed monthly check-in retrieval and submission."""

    QUESTION_PAGE_SIZES = (7, 6)

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.daily_checkin_repository = DailyCheckInRepository()
        self.monthly_checkin_repository = MonthlyCheckInRepository()
        self.behavior_log_repository = BehaviorLogRepository()
        self.score_repository = ScoreRepository()
        self.scoring_service = ScoringService()
        self.streak_service = StreakService()

    async def list_questions(self, page: int = 1) -> dict[str, Any]:
        """Return paginated monthly check-in questions ordered for display."""
        questions = sorted(MONTHLY_CHECKIN_QUESTION_BANK, key=lambda question: question["order"])
        total = len(questions)
        total_pages = len(self.QUESTION_PAGE_SIZES)
        current_page = min(max(page, 1), total_pages)

        start = 0
        for index in range(current_page - 1):
            start += self.QUESTION_PAGE_SIZES[index]
        end = start + self.QUESTION_PAGE_SIZES[current_page - 1]

        return {
            "page": current_page,
            "page_size": self.QUESTION_PAGE_SIZES[current_page - 1],
            "total_questions": total,
            "total_pages": total_pages,
            "questions": questions[start:end],
        }

    async def get_status(self, current_user: User) -> dict[str, Any]:
        """Return current monthly-checkin eligibility state."""
        daily_checkins = await self.daily_checkin_repository.list_by_user_id(current_user.id)
        completed_daily_days = len({checkin.submitted_at.date() for checkin in daily_checkins})
        current_daily_streak = await self.streak_service.get_current_streak(current_user.id)
        existing_monthly = await self.monthly_checkin_repository.get_for_current_month(
            current_user.id,
            datetime.utcnow(),
        )
        monthly_completed = existing_monthly is not None
        should_show = completed_daily_days >= 30 and not monthly_completed
        return {
            "should_show_monthly_checkin": should_show,
            "eligible_after_daily_streak_days": 30,
            "completed_daily_checkin_days": completed_daily_days,
            "current_daily_streak_days": current_daily_streak,
            "monthly_checkin_completed_this_month": monthly_completed,
            "last_monthly_checkin_date": (
                existing_monthly.submitted_at if existing_monthly else None
            ),
        }

    async def submit_monthly_checkin(
        self,
        current_user: User,
        payload: MonthlyCheckInCreate,
    ) -> dict[str, Any]:
        """Validate and store a monthly check-in submission."""
        status_payload = await self.get_status(current_user)
        if not status_payload["should_show_monthly_checkin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Monthly check-in is not available yet.",
                    status_payload,
                ),
            )

        if len(payload.answers) != MONTHLY_CHECKIN_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Exactly 13 monthly check-in answers are required.",
                    {"answers": f"Expected {MONTHLY_CHECKIN_QUESTION_COUNT} answers."},
                ),
            )

        question_map = {question["id"]: question for question in MONTHLY_CHECKIN_QUESTION_BANK}
        submitted_ids = [answer.question_id for answer in payload.answers]

        if len(set(submitted_ids)) != MONTHLY_CHECKIN_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Duplicate answers are not allowed.",
                    {"answers": "Each monthly question must be answered exactly once."},
                ),
            )

        if set(submitted_ids) != set(question_map.keys()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Submitted monthly answers do not match the required question set.",
                    {"answers": "All 13 required monthly questions must be answered exactly once."},
                ),
            )

        normalized_answers = [
            self._normalize_answer(question_map[item.question_id], item.answer)
            for item in payload.answers
        ]

        monthly_checkin = await self.monthly_checkin_repository.create(
            MonthlyCheckIn(user_id=current_user.id, answers=normalized_answers)
        )
        behavior_log = await self.behavior_log_repository.upsert_for_period(
            current_user.id,
            monthly_checkin.submitted_at.date(),
            "monthly",
            self._normalize_behaviors(payload.behaviors),
        )
        monthly_dimension_scores = await self.scoring_service.calculate_dimension_scores(
            normalized_answers
        )
        overall_score = await self.scoring_service.calculate_overall_score(
            monthly_dimension_scores,
            assessment_kind="monthly",
        )
        condition = await self.scoring_service.classify_condition(overall_score)
        previous_score = await self.score_repository.get_latest_by_user_id(current_user.id)
        score_snapshot = await self.score_repository.create(
            Score(
                user_id=current_user.id,
                checkin_id=monthly_checkin.id,
                dimension_scores=monthly_dimension_scores,
                overall_score=overall_score,
                condition=condition,
            )
        )

        wellbeing_answer = next(
            (answer for answer in normalized_answers if answer.question_id == "mc_13"),
            None,
        )
        wellbeing_score = round(
            wellbeing_answer.numeric_value if wellbeing_answer else 50.0,
            2,
        )
        previous_overall_score = (
            round(previous_score.overall_score, 2)
            if previous_score is not None
            else None
        )
        monthly_progress_delta = self._calculate_monthly_progress_delta(
            wellbeing_score,
            previous_overall_score,
        )

        return {
            "id": str(monthly_checkin.id),
            "user_id": str(monthly_checkin.user_id),
            "answers": [answer.model_dump() for answer in monthly_checkin.answers],
            "submitted_at": monthly_checkin.submitted_at.isoformat(),
            "behavior_log_id": str(behavior_log.id),
            "behaviors": [behavior.value for behavior in behavior_log.behaviors],
            "score_snapshot_id": str(score_snapshot.id),
            "overall_score": overall_score,
            "condition": condition,
            "optimal_performance_score": wellbeing_score,
            "monthly_progress_delta": monthly_progress_delta,
            "monthly_progress_text": self._format_monthly_progress_text(
                monthly_progress_delta
            ),
            "message": self._build_monthly_message(monthly_progress_delta),
        }

    def _normalize_answer(self, question: dict[str, Any], answer_text: str) -> Answer:
        """Validate and normalize a submitted monthly answer."""
        normalized_input = answer_text.strip().casefold()
        options_lookup = {
            option.strip().casefold(): index for index, option in enumerate(question["options"])
        }

        if normalized_input not in options_lookup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid monthly check-in answer option submitted.",
                    {question["id"]: f"Answer must match one of: {', '.join(question['options'])}"},
                ),
            )

        option_index = options_lookup[normalized_input]
        numeric_value = self.scoring_service.map_option_to_score(
            option_index,
            len(question["options"]),
            reverse_scored=self._is_reverse_scored(question),
        )

        return Answer(
            question_id=question["id"],
            question_text=question["text"],
            answer_text=question["options"][option_index],
            numeric_value=numeric_value,
            driver=question["driver"],
        )

    def _calculate_monthly_progress_delta(
        self,
        current_score: float,
        previous_score: float | None,
    ) -> float:
        """Return the point change from the latest stored score."""
        if previous_score is None:
            return 0.0
        return round(current_score - previous_score, 2)

    def _format_monthly_progress_text(self, monthly_progress_delta: float) -> str:
        """Return human-readable monthly progress copy."""
        return f"{monthly_progress_delta:+.2f} points from last month"

    def _build_monthly_message(self, monthly_progress_delta: float) -> str:
        """Return summary copy based on monthly progress."""
        if monthly_progress_delta > 0:
            return "Long-term consistency is improving your performance."
        if monthly_progress_delta < 0:
            return "This month suggests a need to reinforce recovery and resilience."
        return "Long-term consistency is helping you maintain your performance."

    def _normalize_behaviors(
        self,
        behaviors: list[BehaviorType],
    ) -> list[BehaviorType]:
        """Return a stable, de-duplicated behavior list."""
        return list(dict.fromkeys(behaviors))

    def _is_reverse_scored(self, question: dict[str, Any]) -> bool:
        """Return whether a monthly question should use reverse scoring."""
        return bool(question.get("reverse_scored", False)) or (
            question["id"] in REVERSE_SCORED_QUESTION_IDS
        )
