"""First-use onboarding service."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import HTTPException, status
from app.core.config import get_settings
from app.core.question_bank import get_onboarding_question_bank
from app.core.question_bank import get_onboarding_question_by_id
from app.core.scoring import build_ai_payload
from app.core.scoring import build_score_band
from app.core.scoring import calculate_component_score
from app.core.scoring import calculate_confidence
from app.core.scoring import calculate_ops
from app.services.scoring_config_service import ScoringConfigService
from app.core.scoring import score_ordered_answer
from app.core.security import utc_now
from app.services.ai_insights_service import AIInsightsService
from app.models.onboarding_answer import OnboardingAnswer
from app.models.user import User
from app.schemas.onboarding import BaselineFinalizeResponse
from app.schemas.onboarding import ConsentSubmitRequest
from app.schemas.onboarding import FirstUseStatusResponse
from app.schemas.onboarding import OnboardingAnswerSubmission
from app.schemas.onboarding import OnboardingIntroResponse
from app.schemas.onboarding import OnboardingQuestionOption
from app.schemas.onboarding import OnboardingQuestionResponse
from app.schemas.onboarding import StepProgressRequest


class OnboardingService:
    """Service for first-use onboarding screens, answers, and baseline scoring."""

    def __init__(self) -> None:
        self.ai_insights_service = AIInsightsService()
        self.scoring_config_service = ScoringConfigService()

    async def get_first_use_status(self, user: User) -> dict[str, Any]:
        """Return the current first-use state for the user."""
        baseline_ops = user.onboarding_baseline_ops_score
        payload = FirstUseStatusResponse(
            onboarding_status=user.onboarding_status,
            onboarding_step=user.onboarding_step,
            onboarding_completed=user.onboarding_completed,
            day0_daily_checkin_status=user.day0_daily_checkin_status,
            current_ops_status=user.current_ops_status,
            ops_confidence_level=user.ops_confidence_level,
            next_route=self._resolve_next_route(user),
            dashboard_locked=not user.onboarding_completed
            or user.day0_daily_checkin_status != "completed",
        )
        result = payload.model_dump(mode="json")
        result["baseline_ops_score"] = baseline_ops
        result["baseline_band"] = user.onboarding_baseline_band
        result["component_scores"] = user.onboarding_component_scores or {}
        return result

    async def get_intro(self, user: User) -> dict[str, Any]:
        """Return onboarding intro data for the welcome and consent screens."""
        settings = get_settings()
        trace_id = user.first_use_trace_id or self._generate_trace_id()
        if user.first_use_trace_id != trace_id:
            user.first_use_trace_id = trace_id
            user.updated_at = utc_now()
            await user.save()

        payload = OnboardingIntroResponse(
            screen_code=user.first_use_flow_code,
            screen_title="FIRST USE",
            step_title="Before we begin",
            progress_label="2 / 4",
            operator_label="OPERATOR MOBILE",
            welcome_name=user.full_name or "Operator",
            intro_body=(
                "Your readiness baseline helps your team support you from day one. "
                "It takes about 3 minutes."
            ),
            cta_label="Begin your readiness baseline",
            privacy_summary=(
                "Your answers are visible to your assigned providers. "
                "You control optional pathways in My team."
            ),
            consent_required_label="Data-use consent",
            consent_required_description=(
                "I consent to Ascend processing my readiness data per the privacy summary above."
            ),
            optional_opt_in_label="Wellness recommendations",
            optional_opt_in_description=(
                "Send me wellness recommendations via in-app messages."
            ),
            medical_record_notice=(
                "Ascend is not a Government system of record. "
                "Your medical record stays with your healthcare team."
            ),
            policy_version=settings.policy_version,
            trace_id=trace_id,
            opsec_notice_text=settings.opsec_notice_text or None,
        )
        return payload.model_dump(mode="json")

    async def get_questions(self, user: User) -> dict[str, Any]:
        """Return the normalized onboarding question bank."""
        existing_answers = await OnboardingAnswer.find(
            OnboardingAnswer.user_id == user.id,
        ).to_list()
        existing_by_question = {answer.question_id: answer for answer in existing_answers}
        questions = []
        question_bank = get_onboarding_question_bank()
        total_questions = len(question_bank)
        for position, question in enumerate(question_bank, start=1):
            scoreable = bool(question.get("scoreable"))
            existing = existing_by_question.get(question["id"])
            options = []
            follow_up_options = {
                item.get("label"): item for item in question.get("follow_up", {}).get("options", [])
            }
            for index, option_label in enumerate(question["options"], start=1):
                follow_up_option = follow_up_options.get(option_label, {})
                options.append(
                    OnboardingQuestionOption(
                        label=option_label,
                        score=index if scoreable else None,
                        description=follow_up_option.get("description"),
                        disabled=bool(follow_up_option.get("disabled", False)),
                        value=follow_up_option.get("value"),
                    )
                )

            questions.append(
                OnboardingQuestionResponse(
                    id=question["id"],
                    code=question["code"],
                    question_number=position,
                    question_total=total_questions,
                    category=question["category"],
                    readiness_component=question["readiness_component"],
                    question=question["question"],
                    description=question["description"],
                    answer_type=question["answer_type"],
                    scoreable=scoreable,
                    reverse_scored=question.get("reverse_scored", False),
                    estimated_time_label="About 5 minutes",
                    submit_label="Choose a response",
                    footer_note="Your responses are used to build your readiness baseline, not evaluation.",
                    support_note_variant=self._support_note_variant(question),
                    follow_up_required=bool(
                        question.get("follow_up", {}).get("required_when_triggered", False)
                    ),
                    answered=existing is not None,
                    current_answer=self._current_answer(existing),
                    current_follow_up_answer=existing.follow_up_answer if existing else None,
                    options=options,
                    routing_text=question["routing_text"],
                    routing_trigger=list(question.get("routing_trigger", [])),
                    provider_route=question.get("provider_route"),
                    follow_up=question.get("follow_up"),
                    ai_tags=list(question.get("ai_tags", [])),
                ).model_dump(mode="json")
            )

        return {
            "version": "ascend-onboarding-v1",
            "total_questions": len(questions),
            "answered_questions": len(existing_answers),
            "questions": questions,
        }

    async def save_answer(
        self,
        user: User,
        payload: OnboardingAnswerSubmission,
    ) -> dict[str, Any]:
        """Persist one onboarding answer and return a live status snapshot."""
        question = get_onboarding_question_by_id(payload.question_id)
        if question is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Onboarding question not found.",
            )

        normalized = self._normalize_answer(question, payload.answer, payload.follow_up_answer)
        await self._upsert_answer(user, question, normalized)

        user.onboarding_status = "in_progress"
        user.onboarding_step = f"q{question['id']:02d}"
        user.updated_at = utc_now()
        if not user.first_use_trace_id:
            user.first_use_trace_id = self._generate_trace_id()
        await user.save()

        return {
            "saved": True,
            "question_id": question["id"],
            "question_code": question["code"],
            "question_status": "scoreable" if question["scoreable"] else "context_only",
            "provider_route": normalized["provider_route"],
            "routing_triggered": normalized["routing_triggered"],
            "follow_up_required": normalized["follow_up_required"],
            "follow_up_answer_saved": normalized["follow_up_answer"] is not None,
            "question_number": self._question_position(question["id"]),
            "total_questions": len(get_onboarding_question_bank()),
            "next_question_id": self._next_question_id(question["id"]),
            "next_step": self._next_step(question["id"]),
            "trace_id": user.first_use_trace_id,
        }

    async def submit_consent(self, user: User, payload: ConsentSubmitRequest) -> dict[str, Any]:
        """Persist required and optional consent selections."""
        if not payload.data_use_consent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Data-use consent is required before onboarding can continue.",
            )

        user.data_use_consent = True
        user.data_use_consent_at = utc_now()
        user.wellness_recommendations_opt_in = payload.wellness_recommendations_opt_in
        user.policy_version_accepted = payload.policy_version
        user.policy_acknowledged_at = utc_now()
        user.onboarding_status = "in_progress"
        user.onboarding_step = "baseline_questions"
        user.updated_at = utc_now()
        if not user.first_use_trace_id:
            user.first_use_trace_id = self._generate_trace_id()
        await user.save()

        return {
            "saved": True,
            "next_route": "/onboarding/baseline",
            "onboarding_status": user.onboarding_status,
            "onboarding_step": user.onboarding_step,
        }

    async def save_step_progress(self, user: User, payload: StepProgressRequest) -> dict[str, Any]:
        """Persist onboarding step progress for resume support."""
        user.onboarding_step = payload.onboarding_step
        user.onboarding_status = payload.onboarding_status
        user.updated_at = utc_now()
        if not user.first_use_trace_id:
            user.first_use_trace_id = self._generate_trace_id()
        await user.save()

        return {
            "saved": True,
            "onboarding_status": user.onboarding_status,
            "onboarding_step": user.onboarding_step,
            "trace_id": user.first_use_trace_id,
        }

    async def complete_baseline(self, user: User) -> dict[str, Any]:
        """Compute onboarding baseline OPS and lock the user into day-0 check-in."""
        answers = await OnboardingAnswer.find(
            OnboardingAnswer.user_id == user.id,
        ).to_list()
        question_bank = {item["id"]: item for item in get_onboarding_question_bank()}
        missing_questions = [
            item["id"]
            for item in get_onboarding_question_bank()
            if item["id"] not in {answer.question_id for answer in answers}
        ]
        if missing_questions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "All onboarding questions must be answered before completion.",
                    "missing_question_ids": missing_questions,
                },
            )

        component_scores = self._component_scores(answers, question_bank)
        active_weights = await self.scoring_config_service.get_active_weights()
        active_thresholds = await self.scoring_config_service.get_active_thresholds()
        ops_score = calculate_ops(component_scores, active_weights)
        confidence = calculate_confidence(component_scores)
        baseline_band = build_score_band(ops_score, active_thresholds)
        provider_flags = self._provider_flags(answers, question_bank)
        follow_ups = self._follow_ups(answers, question_bank)

        user.onboarding_completed = True
        user.onboarding_status = "completed"
        user.onboarding_step = "day0_daily_checkin"
        user.current_ops_status = "baseline_only"
        user.ops_confidence_level = confidence
        user.onboarding_baseline_ops_score = ops_score
        user.onboarding_baseline_band = baseline_band
        user.onboarding_component_scores = component_scores
        user.day0_daily_checkin_status = "pending"
        user.updated_at = utc_now()
        if not user.first_use_trace_id:
            user.first_use_trace_id = self._generate_trace_id()
        await user.save()

        ai_payload = build_ai_payload(
            trace_id=user.first_use_trace_id,
            user_id=str(user.id),
            answers=[
                {
                    "question_id": answer.question_id,
                    "question_code": answer.question_code,
                    "category": answer.category,
                    "component": answer.readiness_component,
                    "selected_value": answer.selected_value,
                    "selected_values": answer.selected_values,
                    "free_text": answer.free_text,
                    "raw_score_1_to_4": answer.raw_score_1_to_4,
                    "numeric_score_100": answer.numeric_score_100,
                    "scoreable": answer.scoreable,
                    "flag_only": answer.flag_only,
                    "provider_route": answer.provider_route,
                    "routing_triggered": answer.routing_triggered,
                    "ai_tags": answer.ai_tags,
                }
                for answer in answers
            ],
            component_scores=component_scores,
            ops_score=ops_score,
            confidence=confidence,
            flags=provider_flags,
            follow_ups=follow_ups,
        )
        ai_summary = await self.ai_insights_service.generate_onboarding_summary(
            user=user,
            ai_payload=ai_payload,
            baseline_ops_score=ops_score,
            baseline_band=baseline_band,
            confidence=confidence,
            provider_flags=provider_flags,
            follow_ups=follow_ups,
        )

        payload = BaselineFinalizeResponse(
            onboarding_status=user.onboarding_status,
            onboarding_step=user.onboarding_step,
            onboarding_completed=user.onboarding_completed,
            baseline_ops_score=ops_score,
            baseline_band=baseline_band,
            confidence=confidence,
            component_scores=component_scores,
            provider_flags=provider_flags,
            follow_ups=follow_ups,
            ai_payload=ai_payload,
            ai_summary=ai_summary,
        )
        return payload.model_dump(mode="json")

    async def get_baseline_preview(self, user: User) -> dict[str, Any]:
        """Return a computed baseline preview without changing state."""
        answers = await OnboardingAnswer.find(
            OnboardingAnswer.user_id == user.id,
        ).to_list()
        question_bank = {item["id"]: item for item in get_onboarding_question_bank()}
        component_scores = self._component_scores(answers, question_bank)
        active_weights = await self.scoring_config_service.get_active_weights()
        active_thresholds = await self.scoring_config_service.get_active_thresholds()
        ops_score = calculate_ops(component_scores, active_weights)
        confidence = calculate_confidence(component_scores)
        return {
            "component_scores": component_scores,
            "baseline_ops_score": ops_score,
            "baseline_band": build_score_band(ops_score, active_thresholds),
            "confidence": confidence,
            "answered_questions": len(answers),
            "total_questions": len(question_bank),
            "remaining_questions": max(len(question_bank) - len(answers), 0),
        }

    def _normalize_answer(
        self,
        question: dict[str, Any],
        answer: str | list[str] | dict[str, Any],
        follow_up_answer: str | list[str] | dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Validate and normalize a submitted onboarding answer."""
        option_labels = list(question["options"])
        selected_value: str | None = None
        selected_values: list[str] | None = None
        free_text: str | None = None

        if question["answer_type"] == "multi_select":
            if not isinstance(answer, list) or not answer:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This question requires one or more selected options.",
                )
            invalid = [item for item in answer if item not in option_labels]
            if invalid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Invalid option submitted.", "invalid": invalid},
                )
            selected_values = list(dict.fromkeys(answer))
        elif question["answer_type"] == "text":
            if not isinstance(answer, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This question requires a short text answer.",
                )
            free_text = answer.strip()
            if not free_text:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Text answer cannot be empty.",
                )
            if len(free_text) > 120:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Text answer must be 120 characters or fewer.",
                )
            if free_text not in option_labels:
                # keep text answers but preserve the selected prompt if they used the presets
                selected_value = free_text
            else:
                selected_value = free_text
        else:
            if not isinstance(answer, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This question requires a single selected option.",
                )
            selected_value = answer.strip()
            if selected_value not in option_labels:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Invalid option submitted.",
                        "allowed_options": option_labels,
                    },
                )

        scoreable = bool(question["scoreable"])
        follow_up_required = False
        raw_score = None
        numeric_score = None
        if scoreable and selected_value is not None:
            option_index = option_labels.index(selected_value)
            score = score_ordered_answer(
                option_index,
                len(option_labels),
                reverse_scored=bool(question.get("reverse_scored", False)),
                scoreable=True,
            )
            raw_score = score.raw_score_1_to_4
            numeric_score = score.numeric_score_100

        routing_triggered = False
        if selected_value is not None and selected_value in question.get("routing_trigger", []):
            routing_triggered = True
        if selected_values is not None and any(
            value in question.get("routing_trigger", []) for value in selected_values
        ):
            routing_triggered = True

        provider_route = question.get("provider_route")
        if question["id"] in {3, 16} and routing_triggered:
            provider_route = "PT/IM"
        if question["id"] == 17 and selected_value == "Yes":
            provider_route = "Document Upload"
        if question["id"] == 18:
            provider_route = "Support Pathways"
        if question["id"] == 19:
            provider_route = "Goal"
        if question["id"] == 20:
            provider_route = "Cadence Preference"

        provider_note = question["routing_text"] if routing_triggered or not scoreable else None
        if question["id"] in {17, 18, 19, 20}:
            provider_note = question["routing_text"]

        normalized_follow_up = self._normalize_follow_up_answer(
            question=question,
            selected_value=selected_value,
            selected_values=selected_values,
            follow_up_answer=follow_up_answer,
        )
        follow_up_required = normalized_follow_up is not None and self._follow_up_required(
            question=question,
            selected_value=selected_value,
            selected_values=selected_values,
        )

        if question["id"] == 18 and selected_values is not None:
            selected_values = self._normalize_support_pathways(selected_values)
            if normalized_follow_up is None:
                normalized_follow_up = selected_values

        return {
            "selected_value": selected_value,
            "selected_values": selected_values,
            "free_text": free_text,
            "follow_up_answer": normalized_follow_up,
            "raw_score_1_to_4": raw_score,
            "numeric_score_100": numeric_score,
            "scoreable": scoreable,
            "reverse_scored": bool(question.get("reverse_scored", False)),
            "flag_only": not scoreable or question["id"] in {3, 16, 17, 18, 19, 20},
            "routing_triggered": routing_triggered,
            "provider_route": provider_route,
            "provider_note": provider_note,
            "follow_up_required": follow_up_required,
            "ai_tags": list(question.get("ai_tags", [])),
        }

    async def _upsert_answer(
        self,
        user: User,
        question: dict[str, Any],
        normalized: dict[str, Any],
    ) -> None:
        """Upsert a normalized answer for a question."""
        existing = await OnboardingAnswer.find_one(
            OnboardingAnswer.user_id == user.id,
            OnboardingAnswer.question_id == question["id"],
        )
        payload = {
            "user_id": user.id,
            "question_id": question["id"],
            "question_code": question["code"],
            "question_text": question["question"],
            "category": question["category"],
            "readiness_component": question["readiness_component"],
            "answer_type": question["answer_type"],
            "selected_value": normalized["selected_value"],
            "selected_values": normalized["selected_values"],
            "free_text": normalized["free_text"],
            "follow_up_answer": normalized["follow_up_answer"],
            "raw_score_1_to_4": normalized["raw_score_1_to_4"],
            "numeric_score_100": normalized["numeric_score_100"],
            "scoreable": normalized["scoreable"],
            "reverse_scored": normalized["reverse_scored"],
            "flag_only": normalized["flag_only"],
            "routing_triggered": normalized["routing_triggered"],
            "provider_route": normalized["provider_route"],
            "provider_note": normalized["provider_note"],
            "ai_tags": normalized["ai_tags"],
            "updated_at": utc_now(),
        }
        if existing is not None:
            for key, value in payload.items():
                setattr(existing, key, value)
            await existing.save()
            return
        await OnboardingAnswer(**payload).insert()

    def _component_scores(
        self,
        answers: list[OnboardingAnswer],
        question_bank: dict[int, dict[str, Any]],
    ) -> dict[str, float | None]:
        """Aggregate component scores across scoreable onboarding answers."""
        grouped: dict[str, list[float]] = {
            "Physical Readiness": [],
            "Nutritional Readiness": [],
            "Mental Readiness": [],
            "Spiritual Readiness": [],
            "Sleep Readiness": [],
        }
        for answer in answers:
            question = question_bank.get(answer.question_id)
            if question is None or not question["scoreable"] or answer.numeric_score_100 is None:
                continue
            grouped[question["readiness_component"]].append(answer.numeric_score_100)

        return {
            component: calculate_component_score(scores)
            for component, scores in grouped.items()
        }

    def _provider_flags(
        self,
        answers: list[OnboardingAnswer],
        question_bank: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build a compact provider flag list from onboarding answers."""
        flags: list[dict[str, Any]] = []
        for answer in answers:
            question = question_bank.get(answer.question_id)
            if question is None:
                continue
            if answer.routing_triggered or answer.flag_only:
                flags.append(
                    {
                        "question_id": answer.question_id,
                        "question_code": answer.question_code,
                        "component": answer.readiness_component,
                        "provider_route": answer.provider_route,
                        "selected_value": answer.selected_value,
                        "selected_values": answer.selected_values,
                        "free_text": answer.free_text,
                        "follow_up_answer": answer.follow_up_answer,
                        "provider_note": answer.provider_note,
                    }
                )
        return flags

    def _follow_ups(
        self,
        answers: list[OnboardingAnswer],
        question_bank: dict[int, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return follow-up context that should accompany the AI payload."""
        follow_ups: list[dict[str, Any]] = []
        for answer in answers:
            question = question_bank.get(answer.question_id)
            if question is None:
                continue
            follow_up = question.get("follow_up")
            if follow_up is None:
                continue
            follow_ups.append(
                {
                    "question_id": answer.question_id,
                    "question_code": answer.question_code,
                    "follow_up_type": follow_up.get("type"),
                    "follow_up_title": follow_up.get("title"),
                    "trigger_options": follow_up.get("trigger_options", []),
                    "required_when_triggered": bool(
                        follow_up.get("required_when_triggered", False)
                    ),
                    "answer": answer.follow_up_answer,
                }
            )
        return follow_ups

    def _current_answer(self, existing: OnboardingAnswer | None) -> str | list[str] | None:
        """Return a current answer shape suitable for UI resume state."""
        if existing is None:
            return None
        if existing.selected_values is not None:
            return existing.selected_values
        return existing.selected_value

    def _support_note_variant(self, question: dict[str, Any]) -> str:
        """Return a compact UI note type for screenshot-aligned cards."""
        if question["id"] in {3, 16}:
            return "ptim_review"
        if question["scoreable"]:
            return "provider_review"
        return "context_only"

    def _question_position(self, question_id: int) -> int:
        """Return the 1-based question position within onboarding."""
        for index, question in enumerate(get_onboarding_question_bank(), start=1):
            if question["id"] == question_id:
                return index
        return 0

    def _next_step(self, current_question_id: int) -> str:
        """Return the next onboarding client step hint."""
        next_question_id = self._next_question_id(current_question_id)
        if next_question_id is None:
            return "baseline_complete"
        return f"q{next_question_id:02d}"

    def _follow_up_required(
        self,
        *,
        question: dict[str, Any],
        selected_value: str | None,
        selected_values: list[str] | None,
    ) -> bool:
        """Return whether the selected answer requires follow-up completion."""
        follow_up = question.get("follow_up")
        if not follow_up or not follow_up.get("required_when_triggered", False):
            return False

        trigger_options = set(follow_up.get("trigger_options", []))
        if selected_value is not None:
            return selected_value in trigger_options
        if selected_values is not None:
            return any(value in trigger_options for value in selected_values)
        return False

    def _normalize_follow_up_answer(
        self,
        *,
        question: dict[str, Any],
        selected_value: str | None,
        selected_values: list[str] | None,
        follow_up_answer: str | list[str] | dict[str, Any] | None,
    ) -> str | list[str] | dict[str, Any] | None:
        """Normalize and validate screenshot follow-up answers."""
        follow_up = question.get("follow_up")
        if follow_up is None:
            return None

        is_required = self._follow_up_required(
            question=question,
            selected_value=selected_value,
            selected_values=selected_values,
        )
        if not is_required and follow_up_answer is None:
            return None

        follow_up_type = follow_up.get("type")
        allowed_labels = [
            option.get("label")
            for option in follow_up.get("options", [])
            if option.get("label") is not None
        ]

        if follow_up_type == "severity_sheet":
            if not isinstance(follow_up_answer, str) or follow_up_answer not in allowed_labels:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "A severity follow-up is required for this answer.",
                        "allowed_options": allowed_labels,
                    },
                )
            return follow_up_answer

        if follow_up_type == "text_sheet":
            if not isinstance(follow_up_answer, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A short follow-up note is required for this answer.",
                )
            normalized = follow_up_answer.strip()
            max_length = int(follow_up.get("max_length", 120))
            if not normalized:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Follow-up note cannot be empty.",
                )
            if len(normalized) > max_length:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Follow-up note must be {max_length} characters or fewer.",
                )
            return normalized

        if follow_up_type == "toggle_sheet":
            if follow_up_answer is None and selected_value is not None:
                return selected_value
            if not isinstance(follow_up_answer, str) or follow_up_answer not in allowed_labels:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "A follow-up selection is required for this answer.",
                        "allowed_options": allowed_labels,
                    },
                )
            return follow_up_answer

        if follow_up_type == "role_sheet":
            if follow_up_answer is None and selected_values is not None:
                return self._normalize_support_pathways(selected_values)

            raw_values: list[str]
            if isinstance(follow_up_answer, str):
                raw_values = [follow_up_answer]
            elif isinstance(follow_up_answer, list):
                raw_values = [value for value in follow_up_answer if isinstance(value, str)]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Support pathway follow-up must be one or more selected options.",
                )

            invalid = [value for value in raw_values if value not in allowed_labels]
            if invalid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Invalid support pathway option.", "invalid": invalid},
                )
            return self._normalize_support_pathways(raw_values)

        return follow_up_answer

    def _normalize_support_pathways(self, values: list[str]) -> list[str]:
        """Deduplicate pathway choices and enforce locked SCS membership."""
        normalized = list(dict.fromkeys(values))
        if "SCS" not in normalized:
            normalized.append("SCS")
        return normalized

    def _next_question_id(self, current_question_id: int) -> int | None:
        """Return the next onboarding question id if available."""
        ids = [question["id"] for question in get_onboarding_question_bank()]
        try:
            current_index = ids.index(current_question_id)
        except ValueError:
            return None
        if current_index + 1 >= len(ids):
            return None
        return ids[current_index + 1]

    def _resolve_next_route(self, user: User) -> str:
        """Return the next client route for the first-use flow."""
        if not user.onboarding_completed:
            if not user.data_use_consent:
                return "/first-use/consent"
            return "/onboarding/baseline"
        if user.day0_daily_checkin_status != "completed":
            return "/checkins/day-0"
        return "/dashboard"

    def _generate_trace_id(self) -> str:
        """Generate a lightweight first-use trace id."""
        return f"FIRSTUSE-{secrets.token_hex(3).upper()}"
