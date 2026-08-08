"""Monthly check-in question bank - exact wording/scoring from the DOCX
"Monthly Check-In - Required Questions, Answer Choices, and Scoring" table
(IDs M1-M10, two scored questions per HPO/H2F readiness component).
"""

from __future__ import annotations

from typing import Any

MONTHLY_CHECKIN_QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": 1,
        "code": "m_01",
        "label": "M1",
        "readiness_component": "Physical Readiness",
        "question": "How has your physical readiness changed this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Declined significantly", "Declined somewhat", "Stayed stable", "Improved"],
        "routing_trigger": [],
    },
    {
        "id": 2,
        "code": "m_02",
        "label": "M2",
        "readiness_component": "Physical Readiness",
        "question": "How confident are you in your current training plan?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not confident", "Slightly confident", "Confident", "Very confident"],
        "routing_trigger": [],
    },
    {
        "id": 3,
        "code": "m_03",
        "label": "M3",
        "readiness_component": "Nutritional Readiness",
        "question": "How consistent were your nutrition habits this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very inconsistent", "Inconsistent", "Consistent", "Very consistent"],
        "routing_trigger": [],
    },
    {
        "id": 4,
        "code": "m_04",
        "label": "M4",
        "readiness_component": "Nutritional Readiness",
        "question": "How much did nutrition support your energy, recovery, or training?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not at all", "Slightly", "Mostly", "Fully"],
        "routing_trigger": [],
    },
    {
        "id": 5,
        "code": "m_05",
        "label": "M5",
        "readiness_component": "Mental Readiness",
        "question": "How well did you manage stress this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Poorly", "Fairly", "Well", "Very well"],
        "routing_trigger": [],
    },
    {
        "id": 6,
        "code": "m_06",
        "label": "M6",
        "readiness_component": "Mental Readiness",
        "question": "How mentally prepared do you feel for upcoming demands?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not prepared", "Slightly prepared", "Prepared", "Very prepared"],
        "routing_trigger": [],
    },
    {
        "id": 7,
        "code": "m_07",
        "label": "M7",
        "readiness_component": "Spiritual Readiness",
        "question": "How aligned did your actions feel with your purpose, values, or priorities this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not aligned", "Slightly aligned", "Aligned", "Strongly aligned"],
        "routing_trigger": [],
    },
    {
        "id": 8,
        "code": "m_08",
        "label": "M8",
        "readiness_component": "Spiritual Readiness",
        "question": "How supported or connected did you feel this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not supported", "Slightly supported", "Supported", "Strongly supported"],
        "routing_trigger": [],
    },
    {
        "id": 9,
        "code": "m_09",
        "label": "M9",
        "readiness_component": "Sleep Readiness",
        "question": "How would you rate your sleep quality this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Very poor", "Poor", "Good", "Excellent"],
        "routing_trigger": [],
    },
    {
        "id": 10,
        "code": "m_10",
        "label": "M10",
        "readiness_component": "Sleep Readiness",
        "question": "How well did you recover from demanding days this month?",
        "scoreable": True,
        "flag_only": False,
        "options": ["Not recovered", "Slightly recovered", "Recovered", "Fully recovered"],
        "routing_trigger": [],
    },
]


def get_monthly_checkin_question_bank() -> list[dict[str, Any]]:
    """Return the normalized monthly check-in question bank."""
    return MONTHLY_CHECKIN_QUESTION_BANK
