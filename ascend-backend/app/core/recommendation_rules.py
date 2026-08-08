"""Recommendation rule table (DOCX section 4, Recommendation Engine).

Thresholds follow the DOCX "Provider Trigger Rules by Driver" table: a
component triggers "high" severity below 55 on a single check-in, or
"moderate" severity below 70 repeated across two consecutive check-ins.
"""

from __future__ import annotations

from typing import Any

HIGH_THRESHOLD = 55.0
MODERATE_THRESHOLD = 70.0

RECOMMENDATION_RULES: dict[str, dict[str, Any]] = {
    "Physical Readiness": {
        "signal_label": "Physical",
        "provider_action_type": "scs_recommendation",
        "specialist_route": "SCS",
        "follow_up_timeline": "Next check-in",
        "moderate": {
            "title": "Ease into today's training load",
            "body": (
                "Your physical readiness has been below target. A lighter session "
                "or extra warm-up can help protect your progress."
            ),
        },
        "high": {
            "title": "Scale back today's training",
            "body": (
                "Your physical readiness is significantly below target. "
                "Choose light or modified activity today."
            ),
        },
    },
    "Sleep Readiness": {
        "signal_label": "Sleep",
        "provider_action_type": "scs_recommendation",
        "specialist_route": "SCS",
        "follow_up_timeline": "Next check-in",
        "moderate": {
            "title": "Add a 20-minute wind-down tonight",
            "body": (
                "Your sleep readiness has been below target. A short, screen-free "
                "wind-down has helped others in your unit this week."
            ),
        },
        "high": {
            "title": "Prioritize recovery sleep tonight",
            "body": (
                "Your sleep readiness is significantly below target. Protect "
                "tonight's sleep window and reduce late training load."
            ),
        },
    },
    "Nutritional Readiness": {
        "signal_label": "Nutrition",
        "provider_action_type": "scs_recommendation",
        "specialist_route": "SCS",
        "follow_up_timeline": "Next check-in",
        "moderate": {
            "title": "Plan a balanced meal today",
            "body": (
                "Your fueling and hydration have been below target. A consistent, "
                "balanced meal can help steady your energy."
            ),
        },
        "high": {
            "title": "Reset your fueling and hydration today",
            "body": (
                "Your fueling and hydration are significantly below target. "
                "Prioritize regular meals and water intake today."
            ),
        },
    },
    "Mental Readiness": {
        "signal_label": "Mental",
        "provider_action_type": "scs_recommendation",
        "specialist_route": "SCS",
        "follow_up_timeline": "Next check-in",
        "moderate": {
            "title": "Try a short breathing reset",
            "body": (
                "Your stress and focus have been below target. A brief breathing "
                "reset can help you regain focus today."
            ),
        },
        "high": {
            "title": "Connect with mental performance support",
            "body": (
                "Your stress and focus are significantly below target for a "
                "repeated stretch. Consider reaching out to your support team."
            ),
        },
    },
    "Spiritual Readiness": {
        "signal_label": "Spiritual",
        "provider_action_type": "chaplain_support",
        "specialist_route": "Chaplain",
        "follow_up_timeline": "Next check-in",
        "moderate": {
            "title": "Take a moment to reconnect with purpose",
            "body": (
                "Your sense of purpose and connection has been below target. A "
                "short reflection or check-in with your team can help."
            ),
        },
        "high": {
            "title": "Reach out to your support team",
            "body": (
                "Your sense of purpose and connection is significantly below "
                "target. Your support team is available if you want to talk."
            ),
        },
    },
}

COMPONENT_PRIORITY_ORDER: list[str] = [
    "Physical Readiness",
    "Sleep Readiness",
    "Mental Readiness",
    "Nutritional Readiness",
    "Spiritual Readiness",
]


def get_recommendation_rule(component: str) -> dict[str, Any] | None:
    """Return the recommendation rule definition for a readiness component."""
    return RECOMMENDATION_RULES.get(component)
