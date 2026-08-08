"""Daily check-in service."""

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.db.repositories.assessment_repo import AssessmentRepository
from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.behavior_log_repo import BehaviorLogRepository
from app.db.repositories.score_repo import ScoreRepository
from app.models.behavior import BehaviorType
from app.models.assessment import Answer, DailyCheckIn
from app.models.score import Score
from app.models.user import User
from app.schemas.assessment import DailyCheckInCreate
from app.services.scoring_service import ScoringService
from app.services.streak_service import StreakService
from app.utils.constants import (
    DAILY_CHECKIN_QUESTION_BANK,
    DAILY_CHECKIN_QUESTION_COUNT,
    REVERSE_SCORED_QUESTION_IDS,
)
from app.utils.response import error_response


class DailyCheckInService:
    """Service for fixed daily check-in retrieval and submission."""

    QUESTION_PAGE_SIZE = 4

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.assessment_repository = AssessmentRepository()
        self.daily_checkin_repository = DailyCheckInRepository()
        self.behavior_log_repository = BehaviorLogRepository()
        self.score_repository = ScoreRepository()
        self.scoring_service = ScoringService()
        self.streak_service = StreakService()

    async def list_questions(self, page: int = 1) -> dict[str, Any]:
        """Return paginated daily check-in questions ordered for display."""
        questions = sorted(
            DAILY_CHECKIN_QUESTION_BANK, key=lambda question: question["order"]
        )
        total = len(questions)
        total_pages = (total + self.QUESTION_PAGE_SIZE - 1) // self.QUESTION_PAGE_SIZE
        current_page = min(max(page, 1), max(total_pages, 1))
        start = (current_page - 1) * self.QUESTION_PAGE_SIZE
        end = start + self.QUESTION_PAGE_SIZE
        return {
            "page": current_page,
            "page_size": self.QUESTION_PAGE_SIZE,
            "total_questions": total,
            "total_pages": total_pages,
            "questions": questions[start:end],
        }

    async def submit_daily_checkin(
        self,
        current_user: User,
        payload: DailyCheckInCreate,
    ) -> dict[str, Any]:
        """Validate and store a daily check-in submission."""
        if len(payload.answers) != DAILY_CHECKIN_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Exactly 8 daily check-in answers are required.",
                    {"answers": f"Expected {DAILY_CHECKIN_QUESTION_COUNT} answers."},
                ),
            )

        existing = await self.daily_checkin_repository.get_for_date(
            current_user.id,
            date.today(),
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response("Daily check-in already completed for today."),
            )

        question_map = {
            question["id"]: question for question in DAILY_CHECKIN_QUESTION_BANK
        }
        submitted_ids = [answer.question_id for answer in payload.answers]

        if len(set(submitted_ids)) != DAILY_CHECKIN_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Duplicate answers are not allowed.",
                    {"answers": "Each daily question must be answered exactly once."},
                ),
            )

        if set(submitted_ids) != set(question_map.keys()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Submitted daily answers do not match the required question set.",
                    {
                        "answers": "All 8 required daily questions must be answered exactly once."
                    },
                ),
            )

        normalized_answers = [
            self._normalize_answer(question_map[item.question_id], item.answer)
            for item in payload.answers
        ]

        daily_checkin = await self.daily_checkin_repository.create(
            DailyCheckIn(user_id=current_user.id, answers=normalized_answers)
        )
        behaviors = payload.behaviors or []
        if BehaviorType.GRATITUDE_REFLECTION not in behaviors:
            behaviors.append(BehaviorType.GRATITUDE_REFLECTION)

        behavior_log = await self.behavior_log_repository.upsert_for_period(
            current_user.id,
            daily_checkin.submitted_at.date(),
            "daily",
            self._normalize_behaviors(behaviors),
        )
        score_snapshot = await self._create_score_snapshot(
            current_user,
            daily_checkin,
            normalized_answers,
        )
        streak_summary = await self.streak_service.get_reflection_streak_summary(
            current_user.id
        )

        return {
            "id": str(daily_checkin.id),
            "user_id": str(daily_checkin.user_id),
            "answers": [answer.model_dump() for answer in daily_checkin.answers],
            "submitted_at": daily_checkin.submitted_at.isoformat(),
            "behavior_log_id": str(behavior_log.id),
            "behaviors": [behavior.value for behavior in behavior_log.behaviors],
            "score_snapshot_created": score_snapshot is not None,
            "score_snapshot_id": (
                str(score_snapshot.id) if score_snapshot is not None else None
            ),
            "reflection_streak_days": streak_summary["reflection_streak_days"],
            "week_progress": streak_summary["week_progress"],
            "weekly_completed_days": streak_summary["weekly_completed_days"],
            "motivation_message": streak_summary["motivation_message"],
        }

    def _normalize_answer(self, question: dict[str, Any], answer_text: str) -> Answer:
        """Validate and normalize a submitted daily answer."""
        normalized_input = answer_text.strip().casefold()
        options_lookup = {
            option.strip().casefold(): index
            for index, option in enumerate(question["options"])
        }

        if normalized_input not in options_lookup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid daily check-in answer option submitted.",
                    {
                        question[
                            "id"
                        ]: f"Answer must match one of: {', '.join(question['options'])}"
                    },
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

    def _normalize_behaviors(
        self,
        behaviors: list[BehaviorType],
    ) -> list[BehaviorType]:
        """Return a stable, de-duplicated behavior list."""
        return list(dict.fromkeys(behaviors))

    def _is_reverse_scored(self, question: dict[str, Any]) -> bool:
        """Return whether a daily question should use reverse scoring."""
        return bool(question.get("reverse_scored", False)) or (
            question["id"] in REVERSE_SCORED_QUESTION_IDS
        )

    async def _create_score_snapshot(
        self,
        current_user: User,
        daily_checkin: DailyCheckIn,
        normalized_answers: list[Answer],
    ) -> Score | None:
        """Persist a merged score snapshot using the latest available score as baseline."""
        latest_score = await self.score_repository.get_latest_by_user_id(
            current_user.id
        )
        if latest_score is None:
            return None

        partial_dimension_scores = (
            await self.scoring_service.calculate_dimension_scores(normalized_answers)
        )
        answered_drivers = {answer.driver for answer in normalized_answers}
        merged_dimension_scores = latest_score.dimension_scores.model_dump()
        onboarding_checkins = await self.assessment_repository.list_by_user_id(
            current_user.id
        )
        onboarding_days = (
            (
                daily_checkin.submitted_at.date()
                - onboarding_checkins[0].submitted_at.date()
            ).days
            if onboarding_checkins
            else 0
        )

        for driver in merged_dimension_scores:
            if driver in answered_drivers:
                merged_dimension_scores[driver] = getattr(
                    partial_dimension_scores, driver
                )
            elif onboarding_checkins:
                merged_dimension_scores[driver] = (
                    self.scoring_service.apply_baseline_decay(
                        merged_dimension_scores[driver],
                        onboarding_days,
                    )
                )

        dimension_scores = latest_score.dimension_scores.model_copy(
            update=merged_dimension_scores
        )
        overall_score = await self.scoring_service.calculate_overall_score(
            dimension_scores,
            assessment_kind="daily",
        )
        condition = await self.scoring_service.classify_condition(overall_score)

        return await self.score_repository.create(
            Score(
                user_id=current_user.id,
                checkin_id=daily_checkin.id,
                dimension_scores=dimension_scores,
                overall_score=overall_score,
                condition=condition,
            )
        )
