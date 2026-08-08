"""Weekly check-in question bank - exact wording/scoring from the DOCX
"Weekly Check-In - Required Questions, Answer Choices, and Scoring" table
(IDs W1-W10, two scored questions per HPO/H2F readiness component).
"""

from __future__ import annotations

from typing import Any

WEEKLY_CHECKIN_QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": 1,
        "code": "w_01",
        "label": "W1",
        "readiness_component": "Physical Readiness",
        "question": "How consistent was your physical activity this week?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very inconsistent", "Inconsistent", "Consistent", "Very consistent"],
        "routing_trigger": [],
    },
    {
        "id": 2,
        "code": "w_02",
        "label": "W2",
        "readiness_component": "Physical Readiness",
        "question": "Did pain, injury, profile, or limitation affect your training this week?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Significantly", "Moderately", "Slightly", "Not at all"],
        "routing_trigger": ["Significantly", "Moderately"],
        "provider_route": "PT/IM",
    },
    {
        "id": 3,
        "code": "w_03",
        "label": "W3",
        "readiness_component": "Nutritional Readiness",
        "question": "How consistent were your meals this week?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very inconsistent", "Inconsistent", "Consistent", "Very consistent"],
        "routing_trigger": [],
    },
    {
        "id": 4,
        "code": "w_04",
        "label": "W4",
        "readiness_component": "Nutritional Readiness",
        "question": "How well did hydration support your energy and recovery?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not at all", "Slightly", "Mostly", "Fully"],
        "routing_trigger": [],
    },
    {
        "id": 5,
        "code": "w_05",
        "label": "W5",
        "readiness_component": "Mental Readiness",
        "question": "How high was your stress level overall this week?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very high", "High", "Low", "Very low"],
        "routing_trigger": [],
    },
    {
        "id": 6,
        "code": "w_06",
        "label": "W6",
        "readiness_component": "Mental Readiness",
        "question": "How well did you stay focused during demanding tasks?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very low", "Low", "Good", "Excellent"],
        "routing_trigger": [],
    },
    {
        "id": 7,
        "code": "w_07",
        "label": "W7",
        "readiness_component": "Spiritual Readiness",
        "question": "How motivated did you feel toward your responsibilities this week?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very low", "Low", "Good", "Strong"],
        "routing_trigger": [],
    },
    {
        "id": 8,
        "code": "w_08",
        "label": "W8",
        "readiness_component": "Spiritual Readiness",
        "question": "How connected did you feel to your purpose, values, or team?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not connected", "Slightly connected", "Connected", "Strongly connected"],
        "routing_trigger": [],
    },
    {
        "id": 9,
        "code": "w_09",
        "label": "W9",
        "readiness_component": "Sleep Readiness",
        "question": "How consistent was your sleep schedule this week?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very inconsistent", "Inconsistent", "Consistent", "Very consistent"],
        "routing_trigger": [],
    },
    {
        "id": 10,
        "code": "w_10",
        "label": "W10",
        "readiness_component": "Sleep Readiness",
        "question": "How well did you recover after demanding days?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not recovered", "Slightly recovered", "Recovered", "Fully recovered"],
        "routing_trigger": [],
    },
]


def get_weekly_checkin_question_bank() -> list[dict[str, Any]]:
    """Return the normalized weekly check-in question bank."""
    return WEEKLY_CHECKIN_QUESTION_BANK
