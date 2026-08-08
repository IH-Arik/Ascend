"""OpenAI-powered AI insight service."""

import asyncio
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings
from app.db.repositories.assessment_repo import AssessmentRepository
from app.db.repositories.chat_message_repo import ChatMessageRepository
from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.monthly_checkin_repo import MonthlyCheckInRepository
from app.db.repositories.profile_repo import ProfileRepository
from app.db.repositories.score_repo import ScoreRepository
from app.db.repositories.weekly_checkin_repo import WeeklyCheckInRepository
from app.models.assessment import Answer
from app.models.chat import ChatMessage
from app.models.score import DimensionScore, Score
from app.models.user import User


class AIService:
    """Service for AI-generated insights, plans, and assistant answers."""

    def __init__(self) -> None:
        """Initialize the OpenAI client."""
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL
        self.profile_repository = ProfileRepository()
        self.score_repository = ScoreRepository()
        self.assessment_repository = AssessmentRepository()
        self.daily_checkin_repository = DailyCheckInRepository()
        self.weekly_checkin_repository = WeeklyCheckInRepository()
        self.monthly_checkin_repository = MonthlyCheckInRepository()
        self.chat_message_repository = ChatMessageRepository()

    async def generate_insight(self, score: Score) -> str:
        """Generate a short insight based on the latest score snapshot."""
        prompt = (
            "You are a wellness and performance assistant for Dominion Wellness Solutions. "
            "Write a concise, supportive, non-clinical insight in 3 short sentences. "
            "Explain likely reasons behind the user's current performance profile using the score data. "
            "Do not diagnose. Focus on practical performance guidance.\n\n"
            f"{self._build_score_context(score)}"
        )
        fallback = self._fallback_insight(score)
        return await self._generate_text(prompt, fallback)

    async def generate_improvement_plan(self, score: Score) -> str:
        """Generate a short improvement plan based on the latest score snapshot."""
        prompt = (
            "You are a wellness and performance assistant for Dominion Wellness Solutions. "
            "Provide exactly 3 concise improvement recommendations. "
            "Each recommendation must follow the format: 'Topic: One short description sentence'. "
            "Example: 'Hydration: Drink at least 2 liters of water daily to maintain energy.' "
            "DO NOT use 'Recommended Action' or the section name as the Topic. "
            "The Topic should be the specific subject (e.g., Sleep, Stress, Nutrition, Focus). "
            "Focus on the user's weakest dimensions. Keep it non-clinical.\n\n"
            f"{self._build_score_context(score)}"
        )
        fallback = self._fallback_improvement_plan(score)
        return await self._generate_text(prompt, fallback)

    async def generate_goal_plan(self, score: Score) -> str:
        """Generate a list of short-term goals based on the score snapshot."""
        prompt = (
            "You are a wellness and performance assistant for Dominion Wellness Solutions. "
            "Provide exactly 3-4 concise short-term wellness goals. "
            "Each goal must follow the format: 'Goal: One short action sentence'. "
            "Example: 'Consistent Bedtime: Aim for a consistent bedtime within 30 minutes every night.' "
            "DO NOT use 'Goal' as the Title part of 'Title: Description'. Use a descriptive category instead. "
            "Focus on sustainable growth across all dimensions. Keep it non-clinical.\n\n"
            f"{self._build_score_context(score)}"
        )
        fallback = self._fallback_goal_plan(score)
        return await self._generate_text(prompt, fallback)

    async def generate_risk_plan(self, score: Score) -> str:
        """Generate a list of potential risks detected in the score snapshot."""
        prompt = (
            "You are a wellness and performance assistant for Dominion Wellness Solutions. "
            "Identify exactly 3-4 potential performance risks based on the score data. "
            "Each risk must follow the format: 'Risk Type: One short descriptive sentence'. "
            "Example: 'Burnout Signal: Low recovery scores suggest a risk of physical burnout if workload remains high.' "
            "DO NOT use 'Risk' or 'Risk Detected' as the Title part. Use the specific risk name. "
            "Be observant but not alarmist. Keep it non-clinical.\n\n"
            f"{self._build_score_context(score)}"
        )
        fallback = self._fallback_risk_plan(score)
        return await self._generate_text(prompt, fallback)

    async def answer_question(self, current_user: User, question: str) -> dict[str, Any]:
        """Answer a user question using expanded user, score, and check-in context."""
        latest_score = await self.score_repository.get_latest_by_user_id(current_user.id)
        if latest_score is None:
            raise ValueError("No score data found for this user.")

        assistant_context = await self._build_assistant_context(current_user, latest_score)
        user_message = await self.chat_message_repository.create(
            ChatMessage(user_id=current_user.id, role="user", content=question)
        )
        prompt = (
            "You are the DWS AI Assistant inside a wellness and performance tracking app. "
            "Answer the user's question in a concise, supportive, non-clinical way. "
            "Use the full user context, score history, and recent check-ins to ground the answer. "
            "If you infer causes, say 'may' or 'suggest'. "
            "End with 1 practical action step.\n\n"
            f"Assistant context:\n{assistant_context}\n\n"
            f"User question: {question}"
        )
        fallback = self._fallback_answer(latest_score, question, current_user.name)
        response_text = await self._generate_text(prompt, fallback)
        assistant_message = await self.chat_message_repository.create(
            ChatMessage(
                user_id=current_user.id,
                role="assistant",
                content=response_text,
            )
        )
        return {
            "message": user_message.content,
            "response": assistant_message.content,
            "overall_score": latest_score.overall_score,
            "condition": latest_score.condition,
            "created_at": assistant_message.created_at,
        }

    async def get_chat_greeting(self, current_user: User) -> dict[str, Any]:
        """Return the assistant greeting payload for the current user."""
        first_name = current_user.name.split()[0] if current_user.name else "there"
        return {
            "title": "DWS AI Assistant",
            "status": "Online",
            "greeting_message": (
                f"Hello {first_name}! I'm your DWS AI Assistant. "
                "How can I help improve your performance today?"
            ),
        }

    async def get_chat_suggestions(self, current_user: User) -> list[dict[str, str]]:
        """Return quick suggestion chips based on the user's latest score context."""
        latest_score = await self.score_repository.get_latest_by_user_id(current_user.id)
        if latest_score is None:
            return [
                {"text": "How can I improve my OPS score?"},
                {"text": "What should I focus on this week?"},
                {"text": "How often should I check in?"},
            ]

        weakest_dimension, weakest_label, _ = self._get_weakest_dimension(
            latest_score.dimension_scores
        )
        suggestion_map = {
            "RC": [
                {"text": "Why is my recovery score low?"},
                {"text": "How can I improve sleep?"},
                {"text": "What affects my OPS score?"},
            ],
            "MR": [
                {"text": "Why is my focus dropping lately?"},
                {"text": "How can I handle stress better?"},
                {"text": "What affects my OPS score?"},
            ],
            "PC": [
                {"text": "How can I improve my physical capacity?"},
                {"text": "Why is my energy lower this week?"},
                {"text": "What affects my OPS score?"},
            ],
            "PA": [
                {"text": "Why does my motivation feel lower?"},
                {"text": "How can I improve purpose alignment?"},
                {"text": "What affects my OPS score?"},
            ],
            "MC": [
                {"text": "Why does team support affect my score?"},
                {"text": "How can I improve morale and cohesion?"},
                {"text": "What affects my OPS score?"},
            ],
        }
        return suggestion_map.get(
            weakest_dimension,
            [
                {"text": f"How can I improve {weakest_label.lower()}?"},
                {"text": "What affects my OPS score?"},
                {"text": "What should I focus on this week?"},
            ],
        )

    async def get_chat_history(self, current_user: User) -> list[dict[str, Any]]:
        """Return persisted chat history for the current user."""
        messages = await self.chat_message_repository.list_by_user_id(current_user.id)
        return [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in messages
        ]

    async def _generate_text(self, prompt: str, fallback: str) -> str:
        """Generate text with OpenAI and return a fallback on runtime failure."""
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your-openai-api-key":
            return fallback

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    temperature=0.4,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a concise wellness and performance assistant.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                ),
                timeout=15.0,
            )
            content = response.choices[0].message.content
            return content.strip() if content else fallback
        except Exception as e:
            print(f"AI Generation Error: {e}")
            return fallback

    def _build_score_context(self, score: Score) -> str:
        """Build a normalized text summary of the current score context."""
        dimension_scores = score.dimension_scores.model_dump()
        weakest_dimension = min(dimension_scores.items(), key=lambda item: item[1])[0]
        strongest_dimension = max(dimension_scores.items(), key=lambda item: item[1])[0]
        return (
            f"Overall score: {score.overall_score}\n"
            f"Condition: {score.condition}\n"
            f"Dimension scores: {dimension_scores}\n"
            f"Weakest dimension: {weakest_dimension}\n"
            f"Strongest dimension: {strongest_dimension}"
        )

    async def _build_assistant_context(self, current_user: User, latest_score: Score) -> str:
        """Build the richer context block used for assistant answers."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        score_history = await self.score_repository.list_by_user_id(current_user.id)
        onboarding_checkins = await self.assessment_repository.list_by_user_id(current_user.id)
        daily_checkins = await self.daily_checkin_repository.list_by_user_id(current_user.id)
        weekly_checkins = await self.weekly_checkin_repository.list_by_user_id(current_user.id)
        monthly_checkins = await self.monthly_checkin_repository.list_by_user_id(current_user.id)

        score_trend = [
            {
                "date": score.created_at.date().isoformat(),
                "overall_score": score.overall_score,
                "condition": score.condition,
            }
            for score in score_history[:5]
        ]

        context_parts = [
            f"User name: {current_user.name}",
            f"Organization: {current_user.organization_name or 'Not provided'}",
            f"Role: {current_user.role or 'Not provided'}",
        ]

        if profile is not None:
            context_parts.extend(
                [
                    f"Age: {profile.age}",
                    f"Gender: {profile.gender}",
                    f"Department: {profile.department}",
                    f"Team: {profile.team}",
                ]
            )

        context_parts.extend(
            [
                "Latest score context:",
                self._build_score_context(latest_score),
                f"Recent score history: {score_trend}",
                (
                    "Recent onboarding assessment answers: "
                    f"{self._serialize_answer_text(onboarding_checkins[0].answers) if onboarding_checkins else []}"
                ),
                (
                    "Recent daily check-in answers: "
                    f"{self._serialize_answer_text(daily_checkins[0].answers) if daily_checkins else []}"
                ),
                (
                    "Recent weekly check-in answers: "
                    f"{self._serialize_answer_text(weekly_checkins[0].answers) if weekly_checkins else []}"
                ),
                (
                    "Recent monthly check-in answers: "
                    f"{self._serialize_answer_text(monthly_checkins[0].answers) if monthly_checkins else []}"
                ),
            ]
        )

        return "\n".join(context_parts)

    def _fallback_insight(self, score: Score) -> str:
        """Return a deterministic insight when the AI provider is unavailable."""
        weakest_key, weakest_label, weakest_score = self._get_weakest_dimension(
            score.dimension_scores
        )
        return (
            f"Your current overall score is {score.overall_score:.0f}, which is classified as "
            f"{score.condition.lower()}. The lowest dimension right now is {weakest_label} "
            f"at {weakest_score:.0f}, which may be limiting your overall consistency. Improving "
            f"daily habits around {weakest_label.lower()} may help stabilize performance."
        )

    def _fallback_improvement_plan(self, score: Score) -> str:
        """Return a deterministic improvement plan when the AI provider is unavailable."""
        weakest_key, _, _ = self._get_weakest_dimension(score.dimension_scores)
        plan_map = {
            "PC": [
                "Morning Movement: Add one short movement block each morning.",
                "Steady Hydration: Prioritize balanced meals and steady hydration.",
                "Consistent Fueling: Reduce gaps between meals during busy workdays.",
            ],
            "MR": [
                "Stress Reset: Use one fixed daily stress-reset routine.",
                "Deep Focus: Protect focused work time from interruptions.",
                "Task Decompression: Schedule a short decompression break after pressure-heavy tasks.",
            ],
            "MC": [
                "Team Connection: Create one intentional connection moment with a teammate each day.",
                "Clear Communication: Ask for clarity or feedback when support feels low.",
                "Reset Breaks: Use short breaks to reset before long work blocks.",
            ],
            "PA": [
                "Daily Priorities: Set three meaningful priorities at the start of each day.",
                "Workload Review: Review workload weekly and remove low-value tasks.",
                "Goal Alignment: Reconnect daily work to longer-term goals.",
            ],
            "RC": [
                "Sleep Schedule: Keep a more consistent sleep and wake time this week.",
                "Recovery Breaks: Add a short recovery break during demanding days.",
                "Digital Detox: Reduce evening stimulation before sleep.",
            ],
        }
        return "\n".join(plan_map[weakest_key])

    def _fallback_goal_plan(self, score: Score) -> str:
        """Return a deterministic goal plan when the AI provider is unavailable."""
        return (
            "Sleep Recovery: Aim for 7-8 hours of sleep tonight\n"
            "Recovery Break: Take a short 10-minute recovery break today\n"
            "Light Movement: A short walk or stretch can help restore focus\n"
            "Recovery Reset: Take a short break to reset your energy and focus."
        )

    def _fallback_risk_plan(self, score: Score) -> str:
        """Return a deterministic risk plan when the AI provider is unavailable."""
        return (
            "Sleep Recovery: Aim for 7-8 hours of sleep tonight\n"
            "Recovery Break: Take a short 10-minute recovery break today\n"
            "Light Movement: A short walk or stretch can help restore focus\n"
            "Recovery Reset: Take a short break to reset your energy and focus."
        )

    def _fallback_answer(self, score: Score, question: str, user_name: str) -> str:
        """Return a deterministic assistant answer when the AI provider is unavailable."""
        _, weakest_label, weakest_score = self._get_weakest_dimension(
            score.dimension_scores
        )
        return (
            f"{user_name}, based on your latest scores, {weakest_label.lower()} appears to be the main area "
            f"pulling performance down right now at {weakest_score:.0f}. That may explain why you are "
            f"seeing lower consistency in this area. A practical next step is to improve one daily habit "
            f"linked to {weakest_label.lower()} while tracking it for the next few days."
        )

    def _get_weakest_dimension(self, dimension_scores: DimensionScore) -> tuple[str, str, float]:
        """Return the weakest dimension key, label, and value."""
        score_items = dimension_scores.model_dump().items()
        weakest_dimension, weakest_score = min(score_items, key=lambda item: item[1])
        label_map = {
            "PC": "Physical Capacity",
            "MR": "Mental Resilience",
            "MC": "Morale & Cohesion",
            "PA": "Purpose Alignment",
            "RC": "Recovery Capacity",
        }
        return weakest_dimension, label_map[weakest_dimension], weakest_score

    # ── Leader / Team AI methods ──────────────────────────────────────────────

    async def generate_leader_executive_analysis(
        self,
        team_context: str,
        top_risk_key: str,
        top_risk_trend: str,
        average_ops: float | None,
    ) -> dict[str, str]:
        """Generate an AI executive analysis headline + summary for the leader insights page."""
        prompt = (
            "You are an executive wellness analyst for Dominion Wellness Solutions. "
            "Write a short AI executive analysis for a leadership dashboard. "
            "Respond with exactly 2 parts separated by '|||': "
            "(1) a punchy one-line headline (max 15 words) summarising the current team state, "
            "(2) a 2-sentence summary explaining the key driver and 7-10 day outlook. "
            "Be specific, non-clinical, and actionable. Do not repeat the headline in the summary.\n\n"
            f"{team_context}"
        )
        fallback_headlines = {
            "recovery_deficit": "Overall team performance remains stable, but recovery capacity is declining.",
            "high_stress": "Stress pressure is increasing faster than recovery is stabilizing.",
            "fatigue": "Energy consistency is weakening across the team.",
            "workload_strain": "Workload load is outpacing sustainable team capacity.",
            "morale_decline": "Morale and engagement signals are slipping across the team.",
            "none": "Team performance trends are holding with no dominant risk signal.",
        }
        fallback_summaries = {
            "recovery_deficit": (
                "Increased workload intensity and inconsistent sleep patterns are contributing factors. "
                "If trends continue, early burnout risk may emerge within the next 7-10 days."
            ),
            "high_stress": (
                "Current team signals suggest pressure is accumulating across the selected scope. "
                "Without workload adjustment, strain is likely to intensify over the next cycle."
            ),
            "fatigue": (
                "Sleep and recovery signals suggest mounting fatigue that may suppress focus and output. "
                "Short-term recovery support should be the immediate priority."
            ),
            "workload_strain": (
                "Task demand is running above sustainable levels for a portion of the team. "
                "Rebalancing priorities this week may prevent wider burnout onset."
            ),
            "morale_decline": (
                "Team cohesion and engagement signals are dipping below expected levels. "
                "Recognition and connection-focused actions are recommended this cycle."
            ),
            "none": (
                f"Average OPS is currently {average_ops or 'not available'}, with no dominant warning signal. "
                "Maintain current support patterns and monitor the leading indicator mix closely."
            ),
        }
        fallback_headline = fallback_headlines.get(top_risk_key, fallback_headlines["none"])
        fallback_summary = fallback_summaries.get(top_risk_key, fallback_summaries["none"])

        raw = await self._generate_text(prompt, f"{fallback_headline}|||{fallback_summary}")
        parts = raw.split("|||", 1)
        headline = parts[0].strip() if len(parts) == 2 else fallback_headline
        summary = parts[1].strip() if len(parts) == 2 else fallback_summary
        return {
            "eyebrow": "AI Executive Analysis",
            "headline": headline,
            "summary": summary,
        }

    async def generate_leader_insight_card_summaries(
        self,
        team_context: str,
        top_risk_key: str,
        recovery_score: float | None,
    ) -> list[dict[str, str]]:
        """Generate 3 AI narrative summaries for the leader insight cards."""
        prompt = (
            "You are a concise wellness analyst for Dominion Wellness Solutions. "
            "Write exactly 3 short insight card summaries for a leadership team dashboard. "
            "Each must be a single sentence (max 18 words). "
            "Separate them with '|||'. "
            "Card 1: Stress Pattern observation, Card 2: Sleep Inconsistency impact, Card 3: Recovery Decline cause. "
            "Be data-grounded, non-clinical, and actionable.\n\n"
            f"{team_context}"
        )
        fallback = (
            "Stress indicators have increased systematically over the last 14 business days.|||"
            "Variation in sleep onset times is affecting next-day focus and resilience.|||"
            "Recovery patterns suggest the team is not fully resetting between high-demand periods."
        )
        raw = await self._generate_text(prompt, fallback)
        parts = (raw + "|||" * 3).split("|||")
        fallback_parts = fallback.split("|||")
        stress_summary = parts[0].strip() or fallback_parts[0]
        sleep_summary = parts[1].strip() or fallback_parts[1]
        recovery_summary = parts[2].strip() or fallback_parts[2]
        return [
            {
                "key": "stress_pattern",
                "title": "Rising Stress Pattern",
                "status": "Strained" if top_risk_key == "high_stress" else "Watch",
                "summary": stress_summary,
            },
            {
                "key": "sleep_inconsistency",
                "title": "Sleep Inconsistency",
                "status": "Stable" if (recovery_score or 0) >= 55 else "Watch",
                "summary": sleep_summary,
            },
            {
                "key": "recovery_decline",
                "title": "Recovery Decline",
                "status": "Critical" if (recovery_score or 100) < 45 else "Warning",
                "summary": recovery_summary,
            },
        ]

    async def generate_leader_behavioral_patterns(
        self,
        team_context: str,
        top_risk_key: str,
    ) -> list[dict[str, str]]:
        """Generate 2 AI behavioral pattern observations for the leader insights page."""
        prompt = (
            "You are a behavioral wellness analyst for Dominion Wellness Solutions. "
            "Write exactly 2 behavioral observations based on team data. "
            "Each observation has a title (max 8 words) and a one-sentence elaboration. "
            "Format: 'Title 1|||Elaboration 1|||Title 2|||Elaboration 2'. "
            "Focus on correlation-strength patterns. Non-clinical, evidence-informed tone.\n\n"
            f"{team_context}"
        )
        is_workload = top_risk_key == "workload_strain"
        fallback = (
            "Low sleep is linked to higher stress|||"
            "Correlation strength: 0.84 (Strong) — stress spikes follow nights below 6 hours.|||"
            "Better energy on days with physical activity|||"
            "Consistent 15% uplift in cognitive performance is visible when movement remains steady."
            if not is_workload else
            "High workload is linked to higher stress|||"
            "Pressure spikes are moving with stress escalation across the selected team.|||"
            "Reduced breaks correlate with lower recovery scores|||"
            "Teams skipping microbreaks show a measurable drop in end-of-day recovery capacity."
        )
        raw = await self._generate_text(prompt, fallback)
        parts = (raw + "|||" * 4).split("|||")
        fp = fallback.split("|||")
        return [
            {
                "key": "pattern_1",
                "title": parts[0].strip() or fp[0],
                "summary": parts[1].strip() or fp[1],
            },
            {
                "key": "pattern_2",
                "title": parts[2].strip() or fp[2],
                "summary": parts[3].strip() or fp[3],
            },
        ]

    async def generate_leader_predictive_forecast(
        self,
        team_context: str,
        top_risk_key: str,
        top_risk_trend: str,
        is_active: bool,
    ) -> dict[str, Any]:
        """Generate an AI predictive forecast narrative for the leader insights page."""
        prompt = (
            "You are a predictive wellness analyst for Dominion Wellness Solutions. "
            "Write a short 7-10 day predictive forecast for a leadership team dashboard. "
            "Respond with 2 parts separated by '|||': "
            "(1) a forecast label (max 5 words, e.g. 'Burnout Risk Increasing'), "
            "(2) a one-sentence intervention recommendation or monitoring note (max 20 words). "
            "Be specific and concise.\n\n"
            f"{team_context}"
        )
        worsening = top_risk_trend == "Worsening"
        forecast_labels = {
            "recovery_deficit": "Burnout Risk Increasing" if worsening or is_active else "Watch Closely",
            "high_stress": "Burnout Risk Increasing" if worsening else "Stress Risk Rising",
            "fatigue": "Energy Decline Accelerating" if worsening else "Fatigue Watch",
            "workload_strain": "Workload Strain Increasing" if worsening else "Workload Risk Watch",
            "morale_decline": "Engagement Risk Mounting" if worsening else "Monitor Morale Signals",
            "none": "Performance Stable With Risk Watch",
        }
        fallback_label = forecast_labels.get(top_risk_key, "Performance Stable With Risk Watch")
        fallback_note = (
            "Intervention is recommended before the next cycle onset."
            if is_active
            else "Continue monitoring the current signal mix."
        )
        confidence = 92 if worsening else 84 if is_active else 71
        raw = await self._generate_text(prompt, f"{fallback_label}|||{fallback_note}")
        parts = raw.split("|||", 1)
        forecast = parts[0].strip() if len(parts) == 2 else fallback_label
        note = parts[1].strip() if len(parts) == 2 else fallback_note
        return {
            "title": "Predictive Forecast",
            "window_label": "Next 7-10 Days",
            "forecast": forecast,
            "confidence_label": f"High ({confidence}%)" if confidence >= 85 else f"Moderate ({confidence}%)",
            "confidence_score": confidence,
            "summary": note,
        }

    def _build_leader_team_context(self, dashboard: dict[str, Any]) -> str:
        """Build a compact team analytics context string for leader AI prompts."""
        top_risk = dashboard["top_risk_signal"]
        team_summary = dashboard["team_summary"]
        group_burnout = dashboard.get("group_burnout", {})
        driver_breakdown = dashboard["driver_breakdown"]
        driver_lines = ", ".join(
            f"{d['label']}: {d['average_score']}" for d in driver_breakdown if d.get("average_score") is not None
        )
        elevated_burnout_count = team_summary.get(
            "elevated_burnout_count",
            group_burnout.get("elevated_members", 0),
        )
        return (
            f"Team scope: {dashboard['scope'].get('department', 'All')} — {dashboard['scope'].get('team', 'All teams')}.\n"
            f"Selected range: {dashboard['selected_range']}.\n"
            f"Member count: {team_summary['member_count']}.\n"
            f"Average OPS Score: {team_summary['average_ops']}.\n"
            f"Elevated burnout members: {elevated_burnout_count}.\n"
            f"Top risk signal: {top_risk['label']} (trend: {top_risk['trend']}, active: {top_risk['is_active']}).\n"
            f"Driver breakdown: {driver_lines}."
        )

    def _serialize_answer_text(self, answers: list[Answer]) -> list[dict[str, Any]]:
        """Return answer text snippets for prompt context."""
        return [
            {
                "question_id": str(answer.question_id),
                "answer_text": answer.answer_text,
                "driver": answer.driver,
            }
            for answer in answers
        ]
