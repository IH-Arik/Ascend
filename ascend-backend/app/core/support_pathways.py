"""Static support pathway catalog (DOCX "My Support Team" routing).

SCS and PT/IM are "locked_on" - assigned automatically, cannot be disabled
(matches "Your SCS and PT/IM are assigned automatically" on the My Team
screen) - and are real system roles (`app.core.roles`), so auto-assignment
can look up an actual active provider account for them. Nutrition, Mental
Performance, and Chaplain are opt-in per the DOCX ("authorized support
pathways, not required contract positions") and are not yet formal system
roles - `role` is None for them, so auto-assignment honestly finds no
provider account rather than fabricating one; the operator toggles them
on/off but they show "not yet assigned" until that role exists.

`messaging_v1_supported` reflects the My Team screen's "Send a message ·
v1.1" labeling on the 3 optional pathways - messaging is only wired up for
the two locked-on pathways in v1.
"""

from __future__ import annotations

from typing import Any

from app.core.roles import ROLE_PTIM, ROLE_SCS

SUPPORT_PATHWAYS: list[dict[str, Any]] = [
    {
        "key": "SCS",
        "label": "Fitness",
        "role_title": "Strength & Conditioning Specialist",
        "description": "Builds and adjusts your daily training plan, monitors recovery, and runs OFT-aligned conditioning.",
        "always_available": True,
        "role": ROLE_SCS,
        "messaging_v1_supported": True,
    },
    {
        "key": "PT/IM",
        "label": "Injury-Recovery",
        "role_title": "Physical Therapy / Injury Management",
        "description": "Injury screening, reconditioning plans, and post-injury return-to-duty clearance.",
        "always_available": True,
        "role": ROLE_PTIM,
        "messaging_v1_supported": True,
    },
    {
        "key": "Nutritionist",
        "label": "Nutrition",
        "role_title": "Performance Nutrition",
        "description": "Fueling strategies, hydration, and meal-planning tied to training load.",
        "always_available": False,
        "role": None,
        "messaging_v1_supported": False,
    },
    {
        "key": "Mental Performance",
        "label": "Mental Performance",
        "role_title": "Mental Performance / Behavioral",
        "description": "Stress management, performance anxiety, and mental skills for high-tempo ops.",
        "always_available": False,
        "role": None,
        "messaging_v1_supported": False,
    },
    {
        "key": "Chaplain",
        "label": "Purpose & Spiritual",
        "role_title": "Purpose / Spiritual · Chaplain",
        "description": "Confidential conversations about purpose, meaning, and values - no record retention beyond minimum required.",
        "always_available": False,
        "role": None,
        "messaging_v1_supported": False,
    },
]


def get_support_pathways() -> list[dict[str, Any]]:
    """Return the full support pathway catalog."""
    return SUPPORT_PATHWAYS


def get_support_pathway(key: str) -> dict[str, Any] | None:
    """Return a single pathway definition by key."""
    for pathway in SUPPORT_PATHWAYS:
        if pathway["key"] == key:
            return pathway
    return None
