"""Weekly check-in service."""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.behavior_log_repo import BehaviorLogRepository
from app.db.repositories.score_repo import ScoreRepository
from app.db.repositories.weekly_checkin_repo import WeeklyCheckInRepository
from app.models.behavior import BehaviorType
from app.models.assessment import Answer, WeeklyCheckIn
from app.models.score import Score
from app.models.user import User
from app.schemas.assessment import WeeklyCheckInCreate
from app.services.scoring_service import ScoringService
from app.services.streak_service import StreakService
from app.utils.constants import (
    REVERSE_SCORED_QUESTION_IDS,
    WEEKLY_CHECKIN_QUESTION_BANK,
    WEEKLY_CHECKIN_QUESTION_COUNT,
)
from app.utils.response import error_response


class WeeklyCheckInService:
    """Service for fixed weekly check-in retrieval and submission."""

    QUESTION_PAGE_SIZE = 5

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.weekly_checkin_repository = WeeklyCheckInRepository()
        self.daily_checkin_repository = DailyCheckInRepository()
        self.behavior_log_repository = BehaviorLogRepository()
        self.score_repository = ScoreRepository()
        self.scoring_service = ScoringService()
        self.streak_service = StreakService()

    async def list_questions(self, page: int = 1) -> dict[str, Any]:
        """Return paginated weekly check-in questions ordered for display."""
        questions = sorted(WEEKLY_CHECKIN_QUESTION_BANK, key=lambda question: question["order"])
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

    async def get_status(self, current_user: User) -> dict[str, Any]:
        """Return current weekly-checkin eligibility state."""
        current_daily_streak = await self.streak_service.get_current_streak(current_user.id)
        existing_weekly = await self.weekly_checkin_repository.get_for_current_week(
            current_user.id,
            datetime.utcnow(),
        )
        weekly_completed = existing_weekly is not None
        should_show = current_daily_streak >= 7 and not weekly_completed
        return {
            "should_show_weekly_checkin": should_show,
            "eligible_after_daily_streak_days": 7,
            "current_daily_streak_days": current_daily_streak,
            "weekly_checkin_completed_this_week": weekly_completed,
            "last_weekly_checkin_date": (
                existing_weekly.submitted_at if existing_weekly else None
            ),
        }

    async def submit_weekly_checkin(
        self,
        current_user: User,
        payload: WeeklyCheckInCreate,
    ) -> dict[str, Any]:
        """Validate and store a weekly check-in submission."""
        status_payload = await self.get_status(current_user)
        if not status_payload["should_show_weekly_checkin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Weekly check-in is not available yet.",
                    status_payload,
                ),
            )

        if len(payload.answers) != WEEKLY_CHECKIN_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Exactly 10 weekly check-in answers are required.",
                    {"answers": f"Expected {WEEKLY_CHECKIN_QUESTION_COUNT} answers."},
                ),
            )

        question_map = {question["id"]: question for question in WEEKLY_CHECKIN_QUESTION_BANK}
        submitted_ids = [answer.question_id for answer in payload.answers]

        if len(set(submitted_ids)) != WEEKLY_CHECKIN_QUESTION_COUNT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Duplicate answers are not allowed.",
                    {"answers": "Each weekly question must be answered exactly once."},
                ),
            )

        if set(submitted_ids) != set(question_map.keys()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Submitted weekly answers do not match the required question set.",
                    {"answers": "All 10 required weekly questions must be answered exactly once."},
                ),
            )

        normalized_answers = [
            self._normalize_answer(question_map[item.question_id], item.answer)
            for item in payload.answers
        ]

        weekly_checkin = await self.weekly_checkin_repository.create(
            WeeklyCheckIn(user_id=current_user.id, answers=normalized_answers)
        )
        behavior_log = await self.behavior_log_repository.upsert_for_period(
            current_user.id,
            weekly_checkin.submitted_at.date(),
            "weekly",
            self._normalize_behaviors(payload.behaviors),
        )
        weekly_dimension_scores = await self.scoring_service.calculate_dimension_scores(
            normalized_answers
        )
        overall_score = await self.scoring_service.calculate_overall_score(
            weekly_dimension_scores,
            assessment_kind="weekly",
        )
        condition = await self.scoring_service.classify_condition(overall_score)
        previous_score = await self.score_repository.get_latest_by_user_id(current_user.id)
        focus_score = round(weekly_dimension_scores.MR, 2)
        previous_focus_score = (
            round(previous_score.dimension_scores.MR, 2)
            if previous_score is not None
            else None
        )
        score_snapshot = await self.score_repository.create(
            Score(
                user_id=current_user.id,
                checkin_id=weekly_checkin.id,
                dimension_scores=weekly_dimension_scores,
                overall_score=overall_score,
                condition=condition,
            )
        )
        focus_score_delta = self._calculate_focus_score_delta(
            focus_score,
            previous_focus_score,
        )
        current_daily_streak_days = await self.streak_service.get_current_streak(
            current_user.id
        )

        return {
            "id": str(weekly_checkin.id),
            "user_id": str(weekly_checkin.user_id),
            "answers": [answer.model_dump() for answer in weekly_checkin.answers],
            "submitted_at": weekly_checkin.submitted_at.isoformat(),
            "behavior_log_id": str(behavior_log.id),
            "behaviors": [behavior.value for behavior in behavior_log.behaviors],
            "score_snapshot_id": str(score_snapshot.id),
            "overall_score": overall_score,
            "condition": condition,
            "current_daily_streak_days": current_daily_streak_days,
            "achievement_title": self._build_achievement_title(focus_score_delta),
            "achievement_delta": focus_score_delta,
            "achievement_summary": self._build_achievement_summary(focus_score_delta),
            "weekly_progress_delta": focus_score_delta,
            "focus_score": focus_score,
            "focus_score_label": self._get_focus_score_label(focus_score),
            "focus_driver": "Mental Resilience",
        }

    def _normalize_answer(self, question: dict[str, Any], answer_text: str) -> Answer:
        """Validate and normalize a submitted weekly answer."""
        normalized_input = answer_text.strip().casefold()
        options_lookup = {
            option.strip().casefold(): index for index, option in enumerate(question["options"])
        }

        if normalized_input not in options_lookup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Invalid weekly check-in answer option submitted.",
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

    def _calculate_focus_score_delta(
        self,
        current_focus_score: float,
        previous_focus_score: float | None,
    ) -> float:
        """Return the change in focus score compared with the latest stored score."""
        if previous_focus_score is None:
            return 0.0
        return round(current_focus_score - previous_focus_score, 2)

    def _build_achievement_title(self, focus_score_delta: float) -> str:
        """Return the weekly achievement headline."""
        if focus_score_delta > 0:
            return f"Mental Resilience improved {focus_score_delta:+.2f}%"
        if focus_score_delta < 0:
            return f"Mental Resilience changed {focus_score_delta:+.2f}%"
        return "Mental Resilience remained steady"

    def _build_achievement_summary(self, focus_score_delta: float) -> str:
        """Return short achievement copy derived from the weekly delta."""
        if focus_score_delta > 0:
            return "Consistency builds resilience."
        if focus_score_delta < 0:
            return "This week suggests focus and recovery need more support."
        return "Your focus patterns remained stable this week."

    def _get_focus_score_label(self, focus_score: float) -> str:
        """Return a frontend-friendly label for the weekly focus score."""
        if focus_score >= 80:
            return "Excellent"
        if focus_score >= 60:
            return "Good"
        if focus_score >= 40:
            return "Developing"
        return "Needs Attention"

    def _normalize_behaviors(
        self,
        behaviors: list[BehaviorType],
    ) -> list[BehaviorType]:
        """Return a stable, de-duplicated behavior list."""
        return list(dict.fromkeys(behaviors))

    def _is_reverse_scored(self, question: dict[str, Any]) -> bool:
        """Return whether a weekly question should use reverse scoring."""
        return bool(question.get("reverse_scored", False)) or (
            question["id"] in REVERSE_SCORED_QUESTION_IDS
        )
