"""Normalized Ascend daily check-in question bank (Day 0 and onward)."""

from __future__ import annotations

from typing import Any

DAILY_CHECKIN_QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": 1,
        "code": "d0_01",
        "label": "D1",
        "category": "PHYSICAL",
        "readiness_component": "Physical Readiness",
        "question": "How ready does your body feel for today's demands?",
        "scoreable": True,
        "reverse_scored": False,
        "flag_only": False,
        "options": [
            {"label": "Below standard", "description": "My body feels drained."},
            {"label": "Building", "description": "I can manage but with effort."},
            {"label": "Ready", "description": "I am functioning at my normal level."},
            {"label": "Peak", "description": "My body feels energized."},
        ],
        "provider_route": "PT/IM",
        "routing_trigger": ["Below standard"],
        "ai_tags": ["physical", "daily"],
    },
    {
        "id": 2,
        "code": "d0_02",
        "label": "D2",
        "category": "SLEEP",
        "readiness_component": "Sleep Readiness",
        "question": "How much sleep did you get last night?",
        "scoreable": True,
        "reverse_scored": False,
        "flag_only": False,
        "options": [
            {"label": "<5h", "description": "Less than five hours."},
            {"label": "5-6h", "description": "About five to six hours."},
            {"label": "6-8h", "description": "A solid six to eight hours."},
            {"label": "8+h", "description": "Eight hours or more."},
        ],
        "provider_route": "PT/IM",
        "routing_trigger": ["<5h"],
        "ai_tags": ["sleep", "daily"],
    },
    {
        "id": 3,
        "code": "d0_03",
        "label": "D3",
        "category": "SLEEP",
        "readiness_component": "Sleep Readiness",
        "question": "How recovered do you feel overall?",
        "scoreable": True,
        "reverse_scored": False,
        "flag_only": False,
        "options": [
            {"label": "Poor", "description": "I feel worn down."},
            {"label": "Fair", "description": "I am still recovering."},
            {"label": "Good", "description": "I feel restored."},
            {"label": "Excellent", "description": "Fully recovered and ready."},
        ],
        "provider_route": "PT/IM",
        "routing_trigger": ["Poor"],
        "ai_tags": ["sleep", "recovery", "daily"],
    },
    {
        "id": 4,
        "code": "d0_04",
        "label": "D4",
        "category": "NUTRITIONAL",
        "readiness_component": "Nutritional Readiness",
        "question": "How well are you fueling and hydrating?",
        "scoreable": True,
        "reverse_scored": False,
        "flag_only": False,
        "options": [
            {"label": "Below standard", "description": "Skipping meals or hydration."},
            {"label": "Adequate", "description": "Some meals and hydration."},
            {"label": "Strong", "description": "On plan with meals + hydration."},
            {"label": "Peak", "description": "On top of meals and hydration."},
        ],
        "provider_route": "PT/IM",
        "routing_trigger": ["Below standard"],
        "ai_tags": ["nutrition", "daily"],
    },
    {
        "id": 5,
        "code": "d0_05",
        "label": "D5",
        "category": "MENTAL",
        "readiness_component": "Mental Readiness",
        "question": "How is your stress and focus right now?",
        "scoreable": True,
        "reverse_scored": False,
        "flag_only": False,
        "options": [
            {"label": "Stressed", "description": "Focus is hard to hold."},
            {"label": "Managing", "description": "Focus is workable."},
            {"label": "Steady", "description": "I can focus and adapt."},
            {"label": "Sharp", "description": "Mentally clear and present."},
        ],
        "provider_route": "PT/IM",
        "routing_trigger": ["Stressed"],
        "ai_tags": ["mental", "daily"],
    },
    {
        "id": 6,
        "code": "d0_06",
        "label": "D6",
        "category": "PHYSICAL",
        "readiness_component": "Physical Readiness",
        "question": "Pain, injury, or limitation. Anything limiting you today?",
        "description": "Flag-only - does not affect your OPS.",
        "scoreable": False,
        "reverse_scored": False,
        "flag_only": True,
        "options": [
            {"label": "None", "description": "Nothing to flag."},
            {"label": "Something to flag", "description": "My support team will review."},
        ],
        "provider_route": "PT/IM",
        "routing_trigger": ["Something to flag"],
        "follow_up": {
            "type": "text_sheet",
            "title": "Explain your injury, or limitation",
            "required_when_triggered": True,
            "save_label": "Done",
            "trigger_options": ["Something to flag"],
            "placeholder": "Short answer (120 char max)",
            "max_length": 120,
        },
        "ai_tags": ["physical", "flag-only", "ptim-review", "daily"],
    },
]


def get_daily_checkin_question_bank() -> list[dict[str, Any]]:
    """Return the normalized daily check-in question bank."""
    return DAILY_CHECKIN_QUESTION_BANK


def get_daily_checkin_question_by_id(question_id: int) -> dict[str, Any] | None:
    """Return a daily check-in question definition by numeric id."""
    for question in DAILY_CHECKIN_QUESTION_BANK:
        if question["id"] == question_id:
            return question
    return None
