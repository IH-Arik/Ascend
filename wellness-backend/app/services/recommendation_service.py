"""Recommendation generation service."""

from typing import Any

from app.models.score import DimensionScore


class RecommendationService:
    """Service for dashboard improvement and leader recommendations."""

    def __init__(self) -> None:
        """Initialize static recommendation libraries."""
        self.personal_templates: dict[str, list[dict[str, str]]] = {
            "PC": [
                {
                    "title": "Morning movement",
                    "description": "Add 10 to 15 minutes of light movement early in the day.",
                },
                {
                    "title": "Balanced fueling",
                    "description": "Build meals around protein, fiber, and consistent hydration.",
                },
                {
                    "title": "Hydration rhythm",
                    "description": "Use fixed water reminders to maintain steady hydration.",
                },
            ],
            "MR": [
                {
                    "title": "Practice daily recovery",
                    "description": "Use 10 minutes of breathing, meditation, or journaling each day.",
                },
                {
                    "title": "Focus blocks",
                    "description": "Protect two distraction-free work blocks for high-value tasks.",
                },
                {
                    "title": "Stress reset cue",
                    "description": "Create a repeatable reset routine after stressful moments.",
                },
            ],
            "MC": [
                {
                    "title": "Connection checkpoint",
                    "description": "Set one intentional touchpoint with a teammate each workday.",
                },
                {
                    "title": "Recognition habit",
                    "description": "Track wins and ask for feedback on visible contributions.",
                },
                {
                    "title": "Break consistency",
                    "description": "Take short recovery breaks during long work periods.",
                },
            ],
            "PA": [
                {
                    "title": "Priorities alignment",
                    "description": "Start each day by identifying the top three meaningful tasks.",
                },
                {
                    "title": "Workload reset",
                    "description": "Review commitments and remove low-value tasks weekly.",
                },
                {
                    "title": "Purpose reflection",
                    "description": "Connect current work to longer-term goals once per week.",
                },
            ],
            "RC": [
                {
                    "title": "Sleep 7–8 hours",
                    "description": "Prioritize deep sleep cycles tonight with a consistent bedtime.",
                },
                {
                    "title": "Evening wind-down",
                    "description": "Reduce stimulation 30 minutes before bed to improve recovery.",
                },
                {
                    "title": "Recovery window",
                    "description": "Add a short daily reset to reduce accumulated fatigue.",
                },
            ],
        }
        self.leader_templates: dict[str, list[dict[str, str]]] = {
            "PC": [
                {
                    "title": "Support sustainable routines",
                    "description": "Encourage schedules that allow meals, hydration, and movement.",
                },
                {
                    "title": "Reduce energy drains",
                    "description": "Review workload patterns that may be driving physical fatigue.",
                },
                {
                    "title": "Model healthy pacing",
                    "description": "Normalize breaks and healthy work rhythms across the team.",
                },
            ],
            "MR": [
                {
                    "title": "Protect focus time",
                    "description": "Reduce unnecessary interruptions and meeting overload.",
                },
                {
                    "title": "Create psychological safety",
                    "description": "Make it safe to surface stress, blockers, and recovery needs.",
                },
                {
                    "title": "Balance intensity",
                    "description": "Watch for sustained pressure without recovery windows.",
                },
            ],
            "MC": [
                {
                    "title": "Increase recognition",
                    "description": "Build frequent, specific recognition into leadership routines.",
                },
                {
                    "title": "Strengthen team connection",
                    "description": "Create structured moments for collaboration and peer support.",
                },
                {
                    "title": "Monitor isolation risk",
                    "description": "Watch for employees who may be disconnecting from the group.",
                },
            ],
            "PA": [
                {
                    "title": "Clarify priorities",
                    "description": "Reinforce what matters most and reduce competing demands.",
                },
                {
                    "title": "Improve workload planning",
                    "description": "Ensure scope and expectations stay realistic and visible.",
                },
                {
                    "title": "Connect work to mission",
                    "description": "Help the team see how daily tasks tie to larger outcomes.",
                },
            ],
            "RC": [
                {
                    "title": "Respect recovery time",
                    "description": "Discourage after-hours pressure that disrupts rest and reset.",
                },
                {
                    "title": "Prevent burnout build-up",
                    "description": "Look for fatigue signals and rebalance intensity early.",
                },
                {
                    "title": "Normalize recovery behaviors",
                    "description": "Promote breaks, time off, and sustainable performance practices.",
                },
            ],
        }

    async def get_personalized_improvement_plan(
        self,
        weakest_dimensions: list[str],
    ) -> list[dict[str, Any]]:
        """Return three personalized recommendations based on weakest dimensions."""
        return self._build_recommendations(weakest_dimensions, self.personal_templates)

    async def get_leader_action_plan(
        self,
        weakest_dimensions: list[str],
    ) -> list[dict[str, Any]]:
        """Return three leader recommendations based on weakest dimensions."""
        return self._build_recommendations(weakest_dimensions, self.leader_templates)

    def get_weakest_dimensions(self, dimension_scores: DimensionScore) -> list[str]:
        """Return the lowest one to two dimension keys."""
        score_pairs = list(dimension_scores.model_dump().items())
        sorted_pairs = sorted(score_pairs, key=lambda item: item[1])
        weakest = [sorted_pairs[0][0]]
        if len(sorted_pairs) > 1 and sorted_pairs[1][1] <= sorted_pairs[0][1] + 10:
            weakest.append(sorted_pairs[1][0])
        return weakest

    def _build_recommendations(
        self,
        weakest_dimensions: list[str],
        template_library: dict[str, list[dict[str, str]]],
    ) -> list[dict[str, Any]]:
        """Build exactly three recommendation cards from dimension templates."""
        recommendations: list[dict[str, Any]] = []
        dimension_cycle = weakest_dimensions or ["RC"]

        for dimension in dimension_cycle:
            for item in template_library.get(dimension, []):
                recommendations.append(
                    {
                        "title": item["title"],
                        "description": item["description"],
                        "based_on_dimension": dimension,
                    }
                )
                if len(recommendations) == 3:
                    return recommendations

        return recommendations[:3]
