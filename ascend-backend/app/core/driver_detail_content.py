"""Static "Try this" suggestion copy for the Driver Detail screen, per component.

Not derived from any docx-specified rule (the DOCX does not define these
suggestion texts) - these are generic, safe, non-clinical self-care actions
in the same spirit as the DOCX's recommendation examples (section 4).
"""

from __future__ import annotations

TRY_THIS_SUGGESTIONS: dict[str, list[str]] = {
    "Physical Readiness": [
        "Log a 10-minute mobility session before tomorrow's shift.",
        "Pair today's check-in with a brief walk after lunch.",
        "Schedule your next readiness check-in before Friday.",
    ],
    "Sleep Readiness": [
        "Set a consistent lights-out time for the next three nights.",
        "Add a 20-minute screen-free wind-down before bed.",
        "Log tonight's sleep in tomorrow's check-in to track the trend.",
    ],
    "Mental Readiness": [
        "Try a short breathing reset before your next demanding task.",
        "Block 10 minutes today with no notifications to reset focus.",
        "Note one stressor in your next check-in so your team can help.",
    ],
    "Nutritional Readiness": [
        "Plan tomorrow's meals tonight to avoid skipped meals.",
        "Carry water with you for the next full duty day.",
        "Log a balanced meal in your next check-in.",
    ],
    "Spiritual Readiness": [
        "Take five minutes today to reflect on your top goal.",
        "Reach out to one teammate for a check-in conversation.",
        "Revisit your support pathway preferences in your profile.",
    ],
}


def get_try_this_suggestions(component: str) -> list[str]:
    """Return the Try This suggestions for a readiness component."""
    return TRY_THIS_SUGGESTIONS.get(component, [])
