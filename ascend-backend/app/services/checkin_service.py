"""Daily check-in service (Day 0 first-use check-in and onward)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.core.cadence import current_monthly_window_start
from app.core.cadence import current_weekly_window_start
from app.core.cadence import next_monthly_review
from app.core.cadence import next_weekly_open
from app.core.cadence import phrase_relative_date
from app.core.checkin_question_bank import get_daily_checkin_question_bank
from app.core.config import get_settings
from app.core.monthly_checkin_question_bank import get_monthly_checkin_question_bank
from app.core.notification_rules import CHECK_IN_REMINDERS
from app.core.scoring import build_ai_payload
from app.core.scoring import build_score_band
from app.core.scoring import calculate_component_score
from app.core.scoring import calculate_confidence
from app.core.scoring import calculate_ops
from app.core.scoring import score_ordered_answer
from app.services.scoring_config_service import ScoringConfigService
from app.core.security import utc_now
from app.core.weekly_checkin_question_bank import get_weekly_checkin_question_bank
from app.models.checkin_answer import CheckinAnswer
from app.models.ops_snapshot import OpsSnapshot
from app.models.user import User
from app.schemas.checkin import DailyCheckinAnswerInput
from app.schemas.checkin import DailyCheckinOption
from app.schemas.checkin import DailyCheckinQuestion
from app.schemas.checkin import DailyCheckinStateResponse
from app.schemas.checkin import DailyCheckinSubmitRequest
from app.schemas.checkin import WeeklyGateResponse
from app.schemas.periodic_checkin import PeriodicCheckinOption
from app.schemas.periodic_checkin import PeriodicCheckinQuestion
from app.schemas.periodic_checkin import PeriodicCheckinStateResponse
from app.schemas.periodic_checkin import PeriodicCheckinSubmitRequest
from app.services.ai_insights_service import AIInsightsService
from app.services.notification_service import NotificationService
from app.services.recommendation_service import RecommendationService

CADENCE_DAILY = "daily"
CADENCE_WEEKLY = "weekly"
CADENCE_MONTHLY = "monthly"

PERIODIC_QUESTION_BANKS: dict[str, Any] = {
    CADENCE_WEEKLY: get_weekly_checkin_question_bank,
    CADENCE_MONTHLY: get_monthly_checkin_question_bank,
}

WEEKLY_STALE_AFTER_DAYS = 10
MONTHLY_STALE_AFTER_DAYS = 45


class CheckinService:
    """Service for the daily check-in screen, submission, and current OPS."""

    def __init__(self) -> None:
        self.ai_insights_service = AIInsightsService()
        self.recommendation_service = RecommendationService()
        self.notification_service = NotificationService()
        self.scoring_config_service = ScoringConfigService()

    async def get_daily_checkin(self, user: User) -> dict[str, Any]:
        """Return today's daily check-in screen state."""
        settings = get_settings()
        today = date.today()
        today_answers = await self._get_answers_for_date(user, today)
        answers_by_question = {answer.question_id: answer for answer in today_answers}

        if not today_answers:
            await self.remind_daily_checkin_open(user, today)

        questions = [
            DailyCheckinQuestion(
                id=question["id"],
                code=question["code"],
                label=question["label"],
                readiness_component=question["readiness_component"],
                question=question["question"],
                description=question.get("description"),
                scoreable=question["scoreable"],
                flag_only=question["flag_only"],
                answered=question["id"] in answers_by_question,
                current_answer=(
                    answers_by_question[question["id"]].selected_value
                    if question["id"] in answers_by_question
                    else None
                ),
                options=[
                    DailyCheckinOption(label=option["label"], description=option.get("description"))
                    for option in question["options"]
                ],
                follow_up=question.get("follow_up"),
                follow_up_required=bool(
                    question.get("follow_up", {}).get("required_when_triggered", False)
                ),
                current_follow_up_answer=(
                    answers_by_question[question["id"]].follow_up_answer
                    if question["id"] in answers_by_question
                    else None
                ),
            ).model_dump(mode="json")
            for question in get_daily_checkin_question_bank()
        ]

        payload = DailyCheckinStateResponse(
            is_day_zero=user.day0_daily_checkin_status != "completed",
            already_completed_today=len(today_answers) >= len(get_daily_checkin_question_bank()),
            day0_daily_checkin_status=user.day0_daily_checkin_status,
            current_ops_status=user.current_ops_status,
            ops_confidence_level=user.ops_confidence_level,
            weekly_cadence_start_date=self._format_date(user.weekly_cadence_start_date),
            monthly_cadence_start_date=self._format_date(user.monthly_cadence_start_date),
            policy_version=settings.policy_version,
            trace_id=user.first_use_trace_id or "",
            questions=questions,
            answered_questions=len(today_answers),
            total_questions=len(get_daily_checkin_question_bank()),
            submit_label="Answer D1-D6 to submit",
        )
        return payload.model_dump(mode="json")

    async def get_weekly_gate(self, user: User) -> dict[str, Any]:
        """Return the weekly check-in cadence gate status.

        Informational only - weekly check-in submission itself is not built
        yet (only daily/Day 0 is), so this reports cadence timing without
        implying a submit flow exists.
        """
        now = datetime.now(timezone.utc)
        next_open = next_weekly_open(now)
        days_until_open = max((next_open.date() - now.date()).days, 0)
        if days_until_open <= 2:
            await self.remind_weekly_checkin_opening(user, next_open.date())
        payload = WeeklyGateResponse(
            locked=True,
            today=now.date().isoformat(),
            days_until_open=days_until_open,
            next_open_at=next_open.isoformat(),
            cadence_start_date=self._format_date(user.weekly_cadence_start_date),
            trace_id=user.first_use_trace_id or "",
        )
        return payload.model_dump(mode="json")

    async def remind_daily_checkin_open(self, user: User, today: date) -> None:
        """Fire a "daily check-in is open" reminder at most once per day."""
        already_sent = await self.notification_service.exists_since(
            user.id,
            family=CHECK_IN_REMINDERS,
            related_entity_type="daily_checkin",
            related_entity_id=today.isoformat(),
        )
        if already_sent:
            return
        await self.notification_service.notify(
            user.id,
            family=CHECK_IN_REMINDERS,
            title="Daily check-in is open",
            body="Daily check-in is open - five questions, about a minute.",
            related_entity_type="daily_checkin",
            related_entity_id=today.isoformat(),
        )

    async def remind_weekly_checkin_opening(self, user: User, next_open_date: date) -> None:
        """Fire a "weekly check-in opens soon" reminder at most once per cycle."""
        already_sent = await self.notification_service.exists_since(
            user.id,
            family=CHECK_IN_REMINDERS,
            related_entity_type="weekly_checkin",
            related_entity_id=next_open_date.isoformat(),
        )
        if already_sent:
            return
        relative = phrase_relative_date(next_open_date, date.today())
        await self.notification_service.notify(
            user.id,
            family=CHECK_IN_REMINDERS,
            title="Weekly check-in opens soon",
            body=f"Weekly check-in opens {relative} - five questions, about a minute.",
            related_entity_type="weekly_checkin",
            related_entity_id=next_open_date.isoformat(),
        )

    async def submit_daily_checkin(
        self,
        user: User,
        payload: DailyCheckinSubmitRequest,
    ) -> dict[str, Any]:
        """Validate, score, and persist today's daily check-in."""
        today = date.today()
        existing = await self._get_answers_for_date(user, today)
        if len(existing) >= len(get_daily_checkin_question_bank()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Today's daily check-in has already been submitted.",
            )

        question_bank = {item["id"]: item for item in get_daily_checkin_question_bank()}
        submitted_ids = [item.question_id for item in payload.answers]
        if len(set(submitted_ids)) != len(submitted_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each daily question can only be answered once.",
            )
        missing = [qid for qid in question_bank if qid not in submitted_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "All daily check-in questions (D1-D6) must be answered.",
                    "missing_question_ids": missing,
                },
            )

        saved_answers: list[CheckinAnswer] = []
        for item in payload.answers:
            question = question_bank.get(item.question_id)
            if question is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Daily check-in question {item.question_id} not found.",
                )
            saved_answers.append(await self._save_answer(user, today, question, item))

        previous_snapshot = await self._get_previous_snapshot(user, today)

        _, provider_flags = self._score_and_flag(saved_answers, question_bank)
        merged_scores, stale_flags = await self._compute_current_component_scores(user, today)
        active_weights = await self.scoring_config_service.get_active_weights()
        active_thresholds = await self.scoring_config_service.get_active_thresholds()
        ops_score = calculate_ops(merged_scores, active_weights)
        confidence = calculate_confidence(merged_scores, stale_flags)
        ops_band = build_score_band(ops_score, active_thresholds)

        await self._upsert_todays_snapshot(
            user, today, CADENCE_DAILY, ops_score, ops_band, confidence, merged_scores, stale_flags
        )

        recommendation = await self.recommendation_service.evaluate_and_generate(
            user,
            merged_scores,
            previous_snapshot.component_scores if previous_snapshot else None,
        )

        is_first_daily_checkin = user.day0_daily_checkin_status != "completed"
        user.current_ops_score = ops_score
        user.current_ops_band = ops_band
        user.current_component_scores = merged_scores
        user.ops_confidence_level = confidence
        if is_first_daily_checkin:
            user.day0_daily_checkin_status = "completed"
            user.day0_daily_checkin_timestamp = utc_now()
            user.current_ops_status = "active"
            user.weekly_cadence_start_date = utc_now()
            user.monthly_cadence_start_date = utc_now()
        user.updated_at = utc_now()
        await user.save()

        ai_payload = build_ai_payload(
            trace_id=user.first_use_trace_id or "",
            user_id=str(user.id),
            answers=[
                {
                    "question_id": answer.question_id,
                    "question_code": answer.question_code,
                    "component": answer.readiness_component,
                    "selected_value": answer.selected_value,
                    "follow_up_answer": answer.follow_up_answer,
                    "raw_score_1_to_4": answer.raw_score_1_to_4,
                    "numeric_score_100": answer.numeric_score_100,
                    "scoreable": answer.scoreable,
                    "flag_only": answer.flag_only,
                    "provider_route": answer.provider_route,
                    "routing_triggered": answer.routing_triggered,
                }
                for answer in saved_answers
            ],
            component_scores=merged_scores,
            ops_score=ops_score,
            confidence=confidence,
            flags=provider_flags,
            follow_ups=[],
            flow="daily_checkin",
        )
        ai_summary = await self.ai_insights_service.generate_onboarding_summary(
            user=user,
            ai_payload=ai_payload,
            baseline_ops_score=ops_score,
            baseline_band=ops_band,
            confidence=confidence,
            provider_flags=provider_flags,
            follow_ups=[],
            insight_type="daily_checkin",
            title_subject="Current OPS",
            score_subject="Current OPS",
            reuse_existing=False,
        )

        return {
            "is_day_zero": is_first_daily_checkin,
            "day0_daily_checkin_status": user.day0_daily_checkin_status,
            "current_ops_status": user.current_ops_status,
            "ops_confidence_level": user.ops_confidence_level,
            "current_ops_score": ops_score,
            "current_ops_band": ops_band,
            "component_scores": merged_scores,
            "provider_flags": provider_flags,
            "weekly_cadence_start_date": self._format_date(user.weekly_cadence_start_date),
            "monthly_cadence_start_date": self._format_date(user.monthly_cadence_start_date),
            "ai_summary": ai_summary,
            "recommendation": recommendation,
        }

    async def _upsert_todays_snapshot(
        self,
        user: User,
        today: date,
        cadence: str,
        ops_score: float | None,
        ops_band: str,
        confidence: str,
        merged_scores: dict[str, float | None],
        stale_flags: dict[str, bool],
    ) -> None:
        """Create or update today's OPS snapshot.

        `OpsSnapshot` has a unique (user_id, snapshot_date) index - at most
        one snapshot per user per calendar day. Daily, weekly, and monthly
        check-ins can all be submitted on the same day, and each recomputes
        the full current-OPS state via the cascade, so a same-day resubmit
        from a different cadence should replace today's snapshot with the
        freshest merged state, not fail on a duplicate key.
        """
        existing = await OpsSnapshot.find_one(
            OpsSnapshot.user_id == user.id, OpsSnapshot.snapshot_date == today
        )
        stale_components = [c for c, stale in stale_flags.items() if stale]
        if existing is not None:
            existing.cadence = cadence
            existing.ops_score = ops_score
            existing.ops_band = ops_band
            existing.confidence_level = confidence
            existing.component_scores = merged_scores
            existing.stale_components = stale_components
            await existing.save()
            return
        await OpsSnapshot(
            user_id=user.id,
            cadence=cadence,
            snapshot_date=today,
            ops_score=ops_score,
            ops_band=ops_band,
            confidence_level=confidence,
            component_scores=merged_scores,
            stale_components=stale_components,
        ).insert()

    async def _get_previous_snapshot(self, user: User, before_date: date) -> OpsSnapshot | None:
        """Return the most recent OPS snapshot strictly before a given date."""
        snapshots = await OpsSnapshot.find(
            OpsSnapshot.user_id == user.id, OpsSnapshot.snapshot_date < before_date
        ).to_list()
        if not snapshots:
            return None
        return max(snapshots, key=lambda item: item.snapshot_date)

    async def _get_answers_for_date(self, user: User, checkin_date: date) -> list[CheckinAnswer]:
        """Return saved daily check-in answers for a given calendar date."""
        return await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id,
            CheckinAnswer.cadence == CADENCE_DAILY,
            CheckinAnswer.checkin_date == checkin_date,
        ).to_list()

    async def _save_answer(
        self,
        user: User,
        checkin_date: date,
        question: dict[str, Any],
        item: DailyCheckinAnswerInput,
    ) -> CheckinAnswer:
        """Validate and persist a single daily check-in answer."""
        option_labels = [option["label"] for option in question["options"]]
        if item.answer not in option_labels:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": f"Invalid option for question {question['id']}.",
                    "allowed_options": option_labels,
                },
            )

        raw_score = None
        numeric_score = None
        if question["scoreable"]:
            option_index = option_labels.index(item.answer)
            score = score_ordered_answer(
                option_index,
                len(option_labels),
                reverse_scored=question.get("reverse_scored", False),
                scoreable=True,
            )
            raw_score = score.raw_score_1_to_4
            numeric_score = score.numeric_score_100

        routing_triggered = item.answer in question.get("routing_trigger", [])
        follow_up_answer = self._normalize_follow_up_answer(question, item, routing_triggered)

        answer = CheckinAnswer(
            user_id=user.id,
            cadence=CADENCE_DAILY,
            checkin_date=checkin_date,
            question_id=question["id"],
            question_code=question["code"],
            question_text=question["question"],
            readiness_component=question["readiness_component"],
            h2f_component_tag=question["readiness_component"],
            selected_value=item.answer,
            follow_up_answer=follow_up_answer,
            raw_score_1_to_4=raw_score,
            numeric_score_100=numeric_score,
            scoreable=question["scoreable"],
            flag_only=question["flag_only"],
            routing_triggered=routing_triggered,
            provider_route=question.get("provider_route") if routing_triggered else None,
        )
        await answer.insert()
        return answer

    def _normalize_follow_up_answer(
        self,
        question: dict[str, Any],
        item: DailyCheckinAnswerInput,
        routing_triggered: bool,
    ) -> str | None:
        """Validate the optional free-text follow-up (e.g. injury/limitation detail)."""
        follow_up = question.get("follow_up")
        if follow_up is None:
            return None

        is_required = routing_triggered and bool(follow_up.get("required_when_triggered", False))
        if not is_required:
            return item.follow_up_answer.strip() if item.follow_up_answer else None

        if not item.follow_up_answer or not item.follow_up_answer.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": f"A follow-up answer is required for question {question['id']}.",
                    "question_id": question["id"],
                },
            )
        normalized = item.follow_up_answer.strip()
        max_length = int(follow_up.get("max_length", 120))
        if len(normalized) > max_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Follow-up answer must be {max_length} characters or fewer.",
            )
        return normalized

    def _score_and_flag(
        self,
        answers: list[CheckinAnswer],
        question_bank: dict[int, dict[str, Any]],
    ) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
        """Aggregate today's component scores and provider flags."""
        grouped: dict[str, list[float]] = {}
        flags: list[dict[str, Any]] = []
        for answer in answers:
            if answer.scoreable and answer.numeric_score_100 is not None:
                grouped.setdefault(answer.readiness_component, []).append(answer.numeric_score_100)
            if answer.routing_triggered or answer.flag_only:
                question = question_bank.get(answer.question_id, {})
                flags.append(
                    {
                        "question_id": answer.question_id,
                        "question_code": answer.question_code,
                        "component": answer.readiness_component,
                        "provider_route": answer.provider_route,
                        "selected_value": answer.selected_value,
                        "flag_only": answer.flag_only,
                        "affects_ops": not answer.flag_only,
                        "note": question.get("description"),
                        "follow_up_answer": answer.follow_up_answer,
                    }
                )
        component_scores = {
            component: calculate_component_score(scores) for component, scores in grouped.items()
        }
        return component_scores, flags

    async def _compute_current_component_scores(
        self,
        user: User,
        today: date,
    ) -> tuple[dict[str, float | None], dict[str, bool]]:
        """Compute current per-component scores using the DOCX staleness cascade.

        Priority: today's daily answer > latest weekly answer (if <= 10 days
        old, per the DOCX "Assessment Cadence Weighting" rule) > latest
        monthly answer (if <= 45 days old) > onboarding baseline (marked
        stale). The daily bank never asks about Spiritual Readiness, so that
        component in particular depends on weekly/monthly/baseline.
        """
        all_components = [
            "Physical Readiness",
            "Sleep Readiness",
            "Mental Readiness",
            "Nutritional Readiness",
            "Spiritual Readiness",
        ]
        baseline = user.onboarding_component_scores or {}

        daily_answers = await self._get_answers_for_date(user, today)
        daily_scores = self._group_scores_by_component(daily_answers)
        weekly_scores, weekly_date = await self._latest_periodic_scores(user, CADENCE_WEEKLY)
        monthly_scores, monthly_date = await self._latest_periodic_scores(user, CADENCE_MONTHLY)

        merged: dict[str, float | None] = {}
        stale_flags: dict[str, bool] = {}
        for component in all_components:
            if daily_scores.get(component) is not None:
                merged[component] = daily_scores[component]
                stale_flags[component] = False
            elif (
                weekly_scores.get(component) is not None
                and weekly_date is not None
                and (today - weekly_date).days <= WEEKLY_STALE_AFTER_DAYS
            ):
                merged[component] = weekly_scores[component]
                stale_flags[component] = False
            elif (
                monthly_scores.get(component) is not None
                and monthly_date is not None
                and (today - monthly_date).days <= MONTHLY_STALE_AFTER_DAYS
            ):
                merged[component] = monthly_scores[component]
                stale_flags[component] = False
            else:
                merged[component] = baseline.get(component)
                stale_flags[component] = merged[component] is not None
        return merged, stale_flags

    def _group_scores_by_component(self, answers: list[CheckinAnswer]) -> dict[str, float | None]:
        """Average scoreable answers into per-component scores."""
        grouped: dict[str, list[float]] = {}
        for answer in answers:
            if answer.scoreable and answer.numeric_score_100 is not None:
                grouped.setdefault(answer.readiness_component, []).append(answer.numeric_score_100)
        return {component: calculate_component_score(scores) for component, scores in grouped.items()}

    async def _latest_periodic_scores(
        self, user: User, cadence: str
    ) -> tuple[dict[str, float | None], date | None]:
        """Return component scores from the most recent weekly/monthly submission."""
        answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id, CheckinAnswer.cadence == cadence
        ).to_list()
        if not answers:
            return {}, None
        latest_date = max(answer.checkin_date for answer in answers)
        latest_answers = [answer for answer in answers if answer.checkin_date == latest_date]
        return self._group_scores_by_component(latest_answers), latest_date

    async def get_periodic_checkin(self, user: User, cadence: str) -> dict[str, Any]:
        """Return the current-period weekly/monthly check-in screen state."""
        question_bank = PERIODIC_QUESTION_BANKS[cadence]()
        today = date.today()
        period_start, period_end = self._periodic_window(user, cadence, today)

        period_answers = await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id,
            CheckinAnswer.cadence == cadence,
            CheckinAnswer.checkin_date >= period_start,
        ).to_list()
        answers_by_question = {answer.question_id: answer for answer in period_answers}

        questions = [
            PeriodicCheckinQuestion(
                id=question["id"],
                code=question["code"],
                label=question["label"],
                readiness_component=question["readiness_component"],
                question=question["question"],
                answered=question["id"] in answers_by_question,
                current_answer=(
                    answers_by_question[question["id"]].selected_value
                    if question["id"] in answers_by_question
                    else None
                ),
                options=[PeriodicCheckinOption(label=label) for label in question["options"]],
            ).model_dump(mode="json")
            for question in question_bank
        ]

        payload = PeriodicCheckinStateResponse(
            cadence=cadence,
            already_completed_this_period=len(period_answers) >= len(question_bank),
            period_start=period_start.isoformat(),
            period_end=period_end.isoformat(),
            questions=questions,
            answered_questions=len(period_answers),
            total_questions=len(question_bank),
            submit_label=f"Answer all {len(question_bank)} questions to submit",
        )
        return payload.model_dump(mode="json")

    async def submit_periodic_checkin(
        self,
        user: User,
        cadence: str,
        payload: PeriodicCheckinSubmitRequest,
    ) -> dict[str, Any]:
        """Validate, score, and persist a weekly/monthly check-in."""
        question_bank = {item["id"]: item for item in PERIODIC_QUESTION_BANKS[cadence]()}
        today = date.today()
        period_start, period_end = self._periodic_window(user, cadence, today)

        existing = await CheckinAnswer.find(
            CheckinAnswer.user_id == user.id,
            CheckinAnswer.cadence == cadence,
            CheckinAnswer.checkin_date >= period_start,
        ).to_list()
        if len(existing) >= len(question_bank):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This {cadence} check-in has already been submitted for the current period.",
            )

        submitted_ids = [item.question_id for item in payload.answers]
        if len(set(submitted_ids)) != len(submitted_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Each question can only be answered once.",
            )
        missing = [qid for qid in question_bank if qid not in submitted_ids]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": f"All {len(question_bank)} {cadence} check-in questions must be answered.",
                    "missing_question_ids": missing,
                },
            )

        saved_answers: list[CheckinAnswer] = []
        for item in payload.answers:
            question = question_bank.get(item.question_id)
            if question is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"{cadence.capitalize()} check-in question {item.question_id} not found.",
                )
            option_labels = question["options"]
            if item.answer not in option_labels:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": f"Invalid option for question {item.question_id}.",
                        "allowed_options": option_labels,
                    },
                )
            option_index = option_labels.index(item.answer)
            score = score_ordered_answer(option_index, len(option_labels), scoreable=True)
            routing_triggered = item.answer in question.get("routing_trigger", [])

            answer = CheckinAnswer(
                user_id=user.id,
                cadence=cadence,
                checkin_date=today,
                question_id=question["id"],
                question_code=question["code"],
                question_text=question["question"],
                readiness_component=question["readiness_component"],
                h2f_component_tag=question["readiness_component"],
                selected_value=item.answer,
                raw_score_1_to_4=score.raw_score_1_to_4,
                numeric_score_100=score.numeric_score_100,
                scoreable=True,
                flag_only=False,
                routing_triggered=routing_triggered,
                provider_route=question.get("provider_route") if routing_triggered else None,
            )
            await answer.insert()
            saved_answers.append(answer)

        _, provider_flags = self._score_and_flag(saved_answers, question_bank)
        merged_scores, stale_flags = await self._compute_current_component_scores(user, today)
        active_weights = await self.scoring_config_service.get_active_weights()
        active_thresholds = await self.scoring_config_service.get_active_thresholds()
        ops_score = calculate_ops(merged_scores, active_weights)
        confidence = calculate_confidence(merged_scores, stale_flags)
        ops_band = build_score_band(ops_score, active_thresholds)

        await self._upsert_todays_snapshot(
            user, today, cadence, ops_score, ops_band, confidence, merged_scores, stale_flags
        )

        recommendation = await self.recommendation_service.evaluate_and_generate(
            user, merged_scores, user.current_component_scores
        )

        user.current_ops_score = ops_score
        user.current_ops_band = ops_band
        user.current_component_scores = merged_scores
        user.ops_confidence_level = confidence
        user.updated_at = utc_now()
        await user.save()

        return {
            "cadence": cadence,
            "current_ops_score": ops_score,
            "current_ops_band": ops_band,
            "component_scores": merged_scores,
            "provider_flags": provider_flags,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "recommendation": recommendation,
        }

    def _periodic_window(self, user: User, cadence: str, today: date) -> tuple[date, date]:
        """Return (period_start, period_end) for the current weekly/monthly cycle."""
        now = datetime.now(timezone.utc)
        if cadence == CADENCE_WEEKLY:
            return current_weekly_window_start(now).date(), next_weekly_open(now).date()
        cadence_start = (
            user.monthly_cadence_start_date.date() if user.monthly_cadence_start_date else today
        )
        return (
            current_monthly_window_start(cadence_start, today),
            next_monthly_review(cadence_start, today),
        )

    def _format_date(self, value: Any) -> str | None:
        """Format an optional datetime as an ISO date string."""
        if value is None:
            return None
        return value.date().isoformat() if hasattr(value, "date") else str(value)
