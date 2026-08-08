"""DWS Hybrid Intervention Engine.

Flow:
  1. Enforce max-1-per-day (return cache if already issued today)
  2. Evaluate triggers from burnout metrics + dimension scores
  3. Select single highest-priority category (TRIGGER_PRIORITY order)
  4. Apply memory rules:  no consecutive repeat, avoid last-3 if possible
  5. Apply escalation (level from InterventionMemory.current_levels)
  6. Pick recommendation text from static INTERVENTION_LIBRARY
  7. Generate AI reason_line via OpenAI; fall back to static REASON_LINES
  8. Persist to InterventionMemory and return output
"""

import random
from datetime import date
from typing import Any

from beanie import PydanticObjectId
from openai import AsyncOpenAI

from app.core.config import settings
from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.intervention_repo import InterventionMemoryRepository
from app.db.repositories.monthly_checkin_repo import MonthlyCheckInRepository
from app.db.repositories.score_repo import ScoreRepository
from app.db.repositories.weekly_checkin_repo import WeeklyCheckInRepository
from app.models.intervention_memory import CompletionStatus, InterventionMemory
from app.services.burnout_service import BurnoutService
from app.utils.intervention_library import (
    FALLBACK_RECOMMENDATIONS,
    INTERVENTION_LIBRARY,
    REASON_LINES,
    TRIGGER_PRIORITY,
)


# ---------------------------------------------------------------------------
# Trigger evaluation thresholds
# ---------------------------------------------------------------------------
_RED_THRESHOLD = 45.0
_YELLOW_THRESHOLD = 65.0
_SLEEP_LOW = 6.0
_STRESS_HIGH = 60.0
_STRESS_EXTREME = 75.0


class InterventionService:
    """Hybrid rule-based engine with AI-generated reason lines."""

    def __init__(self) -> None:
        """Initialize dependencies."""
        self.memory_repo = InterventionMemoryRepository()
        self.score_repo = ScoreRepository()
        self.daily_repo = DailyCheckInRepository()
        self.weekly_repo = WeeklyCheckInRepository()
        self.monthly_repo = MonthlyCheckInRepository()
        self.burnout_service = BurnoutService()
        self.openai = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def get_today_intervention(
        self,
        user_id: PydanticObjectId,
    ) -> dict[str, Any]:
        """Return today's single intervention recommendation.

        Returns the same cached recommendation for all same-day calls.
        Generates a new one if none has been issued today.
        """
        memory = await self.memory_repo.get_or_create(user_id)

        # Enforce max-1-per-day: return cache if already issued today
        if memory.last_issued_date == date.today() and memory.cached_recommendation:
            return self._serialize_output(
                memory.cached_category,
                memory.cached_recommendation,
                memory.cached_reason_line or REASON_LINES.get(
                    memory.cached_category, REASON_LINES["recovery"]
                ),
                from_cache=True,
            )

        # Gather score and burnout data
        latest_score = await self.score_repo.get_latest_by_user_id(user_id)
        daily = await self.daily_repo.list_by_user_id(user_id)
        weekly = await self.weekly_repo.list_by_user_id(user_id)
        monthly = await self.monthly_repo.list_by_user_id(user_id)
        burnout = self.burnout_service.build_payload_from_checkins(
            daily, weekly, monthly
        )
        metrics = burnout["metrics"]

        # Determine triggered category (highest priority + override rules)
        category = self._evaluate_triggers(metrics, latest_score, daily[:1])

        # Determine escalation level for this category
        level = self._get_level(memory, category)

        # Select recommendation text (anti-repeat rules)
        recommendation = self._pick_recommendation(memory, category, level)

        # Generate AI reason line (falls back to static)
        reason_line = await self._generate_reason_line(
            category, metrics, latest_score
        )

        # Persist to memory
        await self.memory_repo.save_issued(
            memory, category, recommendation, reason_line
        )

        return self._serialize_output(category, recommendation, reason_line)

    async def record_completion(
        self,
        user_id: PydanticObjectId,
        status: CompletionStatus,
    ) -> dict[str, Any]:
        """Record the user's completion response for today's recommendation.

        Applies escalation rules to the stored level map and returns the
        updated memory state summary.
        """
        memory = await self.memory_repo.get_or_create(user_id)
        category = memory.last_category or "recovery"
        await self.memory_repo.record_completion(memory, status, category)
        return {
            "recorded_status": status,
            "category": category,
            "current_level": memory.current_levels.get(category, 1),
            "message": self._completion_message(status),
        }

    # ------------------------------------------------------------------ #
    # Trigger evaluation                                                 #
    # ------------------------------------------------------------------ #

    def _evaluate_triggers(
        self,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
        recent_daily: list[Any] | None = None,
    ) -> str:
        """Return the single highest-priority triggered category.

        Checks each category in TRIGGER_PRIORITY order and returns the first
        that is triggered.  Falls back to the static fallback category.
        """
        if self._dual_risk_override(latest_score):
            return "recovery"
        if self._recovery_override(recent_daily or []):
            return "recovery"
        if self._mental_override(metrics, latest_score):
            return "workload"

        triggered: dict[str, bool] = {
            "recovery": self._trigger_recovery(metrics),
            "workload": self._trigger_workload(metrics),
            "physical_activity": self._trigger_physical_activity(metrics, latest_score),
            "nutrition": self._trigger_nutrition(metrics, latest_score),
            "engagement": self._trigger_engagement(metrics, latest_score),
        }

        for category in TRIGGER_PRIORITY:
            if triggered.get(category):
                return category

        return "recovery"

    def _recovery_override(self, recent_daily: list[Any]) -> bool:
        """Force recovery priority when sleep or energy is critically low."""
        if not recent_daily:
            return False
        latest_daily = recent_daily[0]
        answer_map = {
            str(answer.question_id): answer.numeric_value
            for answer in latest_daily.answers
        }
        return any(
            value is not None and value <= 25.0
            for value in (
                answer_map.get("dc_1"),
                answer_map.get("dc_5"),
                answer_map.get("dc_6"),
            )
        )

    def _mental_override(
        self,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
    ) -> bool:
        """Force workload/stress reduction when mental load is critical."""
        mental_score = latest_score.dimension_scores.MR if latest_score is not None else None
        stress_value = metrics.get("stress", {}).get("value")
        return (
            (stress_value is not None and stress_value >= _STRESS_EXTREME)
            or (mental_score is not None and mental_score < _RED_THRESHOLD)
        )

    def _dual_risk_override(self, latest_score: Any | None) -> bool:
        """Return whether recovery and mental are both in the red zone."""
        if latest_score is None:
            return False
        return (
            latest_score.dimension_scores.RC < _RED_THRESHOLD
            and latest_score.dimension_scores.MR < _RED_THRESHOLD
        )

    def _trigger_recovery(self, metrics: dict[str, dict[str, Any]]) -> bool:
        sleep_v = metrics.get("sleep", {}).get("value")
        energy_v = metrics.get("energy", {}).get("value")
        recovery_v = metrics.get("recovery", {}).get("value")
        return (
            (sleep_v is not None and sleep_v < _SLEEP_LOW)
            or (energy_v is not None and energy_v < _YELLOW_THRESHOLD)
            or (recovery_v is not None and recovery_v < _YELLOW_THRESHOLD)
        )

    def _trigger_workload(self, metrics: dict[str, dict[str, Any]]) -> bool:
        stress_v = metrics.get("stress", {}).get("value")
        workload_v = metrics.get("workload", {}).get("value")
        return (
            (stress_v is not None and stress_v > _STRESS_HIGH)
            or (workload_v is not None and workload_v < _YELLOW_THRESHOLD)
        )

    def _trigger_physical_activity(
        self,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
    ) -> bool:
        stress_v = metrics.get("stress", {}).get("value")
        # Use Physical Capacity dimension score as proxy for movement
        pc_v = (
            latest_score.dimension_scores.PC
            if latest_score is not None
            else None
        )
        return (
            (stress_v is not None and stress_v > _STRESS_HIGH)
            and (pc_v is not None and pc_v < _YELLOW_THRESHOLD)
        )

    def _trigger_nutrition(
        self,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
    ) -> bool:
        energy_v = metrics.get("energy", {}).get("value")
        stress_v = metrics.get("stress", {}).get("value")
        # Nutrition signal: low energy AND high stress (no direct nutrition metric)
        return (
            (energy_v is not None and energy_v < _YELLOW_THRESHOLD)
            and (stress_v is not None and stress_v > _STRESS_HIGH)
        )

    def _trigger_engagement(
        self,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
    ) -> bool:
        motivation_v = metrics.get("motivation", {}).get("value")
        pa_v = (
            latest_score.dimension_scores.PA
            if latest_score is not None
            else None
        )
        return (
            (motivation_v is not None and motivation_v < _YELLOW_THRESHOLD)
            or (pa_v is not None and pa_v < _YELLOW_THRESHOLD)
        )

    # ------------------------------------------------------------------ #
    # Level / escalation helpers                                         #
    # ------------------------------------------------------------------ #

    def _get_level(self, memory: InterventionMemory, category: str) -> int:
        """Return the current escalation level (1–3) for a category."""
        return memory.current_levels.get(category, 1)

    # ------------------------------------------------------------------ #
    # Recommendation selection (anti-repeat rules)                       #
    # ------------------------------------------------------------------ #

    def _pick_recommendation(
        self,
        memory: InterventionMemory,
        category: str,
        level: int,
    ) -> str:
        """Select a recommendation text obeying anti-repeat rules.

        Rules (in order):
          1. Never repeat the immediate last recommendation consecutively.
          2. Avoid any of the last 3 if possible.
          3. If all level items appear in last-3, pick least-recent (index 3+).
        """
        pool: list[str] = INTERVENTION_LIBRARY.get(category, {}).get(level, [])
        if not pool:
            return random.choice(FALLBACK_RECOMMENDATIONS)

        last_3 = set(memory.last_3_recommendations)
        last_1 = memory.last_3_recommendations[0] if memory.last_3_recommendations else None

        # Prefer items not in last-3
        preferred = [r for r in pool if r not in last_3]
        if preferred:
            return random.choice(preferred)

        # All items in last-3 → pick least recent (those not equal to last_1)
        not_last_1 = [r for r in pool if r != last_1]
        if not_last_1:
            return random.choice(not_last_1)

        # Edge case: only one item in pool
        return pool[0]

    # ------------------------------------------------------------------ #
    # AI reason line generation                                          #
    # ------------------------------------------------------------------ #

    async def _generate_reason_line(
        self,
        category: str,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
    ) -> str:
        """Generate a personalized one-sentence reason via OpenAI.

        Falls back to the static reason line if the API is unavailable or
        returns an empty response.
        """
        static_fallback = REASON_LINES.get(category, REASON_LINES["recovery"])

        if (
            not settings.OPENAI_API_KEY
            or settings.OPENAI_API_KEY == "your-openai-api-key"
        ):
            return static_fallback

        # Build a compact score context for the prompt
        score_context = self._build_score_context(metrics, latest_score)

        prompt = (
            "You are a performance and wellness coach inside the DWS app. "
            "Write exactly ONE short sentence (under 20 words) explaining WHY "
            f"the '{category}' intervention is recommended today based on the "
            "user data below. Be specific and non-clinical. "
            "Do not start with 'I' or 'You are'. "
            "Do not include a category label in the sentence.\n\n"
            f"User data:\n{score_context}"
        )

        try:
            response = await self.openai.chat.completions.create(
                model=self.model,
                temperature=0.3,
                max_tokens=60,
                messages=[
                    {
                        "role": "system",
                        "content": "You write concise, factual one-sentence coaching reasons.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            content = response.choices[0].message.content
            if content and content.strip():
                return content.strip().rstrip(".")
        except Exception:
            pass

        return static_fallback

    # ------------------------------------------------------------------ #
    # Serialization helpers                                              #
    # ------------------------------------------------------------------ #

    def _serialize_output(
        self,
        category: str | None,
        recommendation: str,
        reason_line: str,
        from_cache: bool = False,
    ) -> dict[str, Any]:
        """Return the standardized intervention output payload."""
        return {
            "category": category,
            "recommendation": recommendation,
            "reason_line": reason_line,
            "from_cache": from_cache,
        }

    def _build_score_context(
        self,
        metrics: dict[str, dict[str, Any]],
        latest_score: Any | None,
    ) -> str:
        """Build a compact text block for the AI prompt."""
        lines = []
        for key, data in metrics.items():
            value = data.get("value")
            in_risk = data.get("in_risk", False)
            if value is not None:
                lines.append(f"  {key}: {value:.1f} (in_risk={in_risk})")
        if latest_score is not None:
            lines.append(f"  OPS overall_score: {latest_score.overall_score:.1f}")
            lines.append(f"  condition: {latest_score.condition}")
            dim = latest_score.dimension_scores.model_dump()
            for k, v in dim.items():
                lines.append(f"  {k}: {v:.1f}")
        return "\n".join(lines) if lines else "No data available."

    def _completion_message(self, status: CompletionStatus) -> str:
        """Return a short feedback message for a given completion status."""
        messages = {
            "completed": "Great work. Keep the momentum going.",
            "partial": "Good effort. A similar focus is recommended next time.",
            "not_completed": "No worries. Tomorrow's recommendation will step it up.",
            "no_response": "Reminder logged. Try to action tomorrow's recommendation.",
        }
        return messages.get(status, "Response recorded.")
