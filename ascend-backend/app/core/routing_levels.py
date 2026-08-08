"""Routing Threshold Levels L0-L5 (DOCX Table 20, "Routing Threshold Rules").

This is the DOCX's own escalation taxonomy, verbatim. It is broader than
what any single engine in this backend currently computes:
- `app/core/recommendation_rules.py`'s moderate/high severities are single-
  component threshold checks, not the DOCX's multi-day pattern triggers
  (e.g. L2's "two low scores within 3 days", L3's "monthly decline >15%").
- `app/core/safety_boundary.py` implements L5 directly (keyword match).

Where a `route_level` is attached to a Recommendation elsewhere in this
codebase, it is a documented **approximation** onto this table (moderate ->
L2, high -> L4), not a full re-implementation of every L1-L4 trigger
condition (missed-check-in streaks, OFT failure, monthly decline %). Treat
it as directional severity context, not a precise DOCX-conformant
classifier - a true L0-L4 engine would need to evaluate streaks/patterns
this backend doesn't currently track per readiness component.
"""

from __future__ import annotations

from typing import Any

ROUTING_LEVELS: list[dict[str, Any]] = [
    {
        "level": "L0",
        "name": "Normal",
        "trigger": "Score within normal range; no concerning trend.",
        "user_experience": "Show OPS/readiness component status and normal recommended habit.",
        "coach_admin_action": "No coach flag.",
        "specialist_routing": "No specialist route.",
    },
    {
        "level": "L1",
        "name": "Low Signal",
        "trigger": "One low response in a readiness component or one missed check-in.",
        "user_experience": "Show one recommendation and optional self-support resource.",
        "coach_admin_action": "No flag by default; visible in dashboard trend.",
        "specialist_routing": "No route unless user requests support.",
    },
    {
        "level": "L2",
        "name": "Pattern Concern",
        "trigger": (
            "Two low readiness component scores within 3 days OR two missed "
            "check-ins within 7 days OR one weekly low score."
        ),
        "user_experience": "Recommendation plus support button.",
        "coach_admin_action": "Soft coach flag in dashboard.",
        "specialist_routing": "Optional route if user selects support.",
    },
    {
        "level": "L3",
        "name": "Persistent Concern",
        "trigger": (
            "Three low readiness component scores within 5 days OR three missed "
            "workouts/check-ins within 10 days OR monthly decline >15% in a "
            "readiness component."
        ),
        "user_experience": "Recommendation plus stronger support prompt.",
        "coach_admin_action": "Active coach follow-up flag.",
        "specialist_routing": "Route to authorized support pathway.",
    },
    {
        "level": "L4",
        "name": "High Priority",
        "trigger": (
            "User reports pain/limitation; OFT failure; marked recovery decline; "
            "unresolved injury follow-up; repeated severe stress/fatigue pattern."
        ),
        "user_experience": "Prompt to request appropriate support and clarify app is not emergency care.",
        "coach_admin_action": "Priority flag to SCS/PT/IM or authorized provider.",
        "specialist_routing": "Route according to readiness component and permission rules.",
    },
    {
        "level": "L5",
        "name": "Safety Boundary",
        "trigger": (
            "User language indicates emergency, self-harm, violence, medical "
            "emergency, or urgent operational risk."
        ),
        "user_experience": "Show approved safety/emergency language and route outside app according to DWS/Government procedures.",
        "coach_admin_action": "Immediate admin/provider notification only if approved by policy.",
        "specialist_routing": "Do not let AI or app decide care; follow approved procedure.",
    },
]


def get_routing_level(level: str) -> dict[str, Any] | None:
    """Return a single routing level definition by code (e.g. "L2")."""
    for entry in ROUTING_LEVELS:
        if entry["level"] == level:
            return entry
    return None


def get_routing_levels() -> list[dict[str, Any]]:
    """Return the full L0-L5 routing level catalog."""
    return ROUTING_LEVELS
