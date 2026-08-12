"""Contract Question Registry - a simplified, real view over the 3 existing
question banks, for the Admin/Superadmin "Roles & RBAC" screen.

Not DOCX-sourced (a Figma screenshot triggered this, showing 46 rows across
O1-O20/D1-D6/W1-W10/M1-M10 with per-question routing/reverse-scoring/
versioning/validation-status). Checked against the real data: this project
has exactly 40 real questions (20 onboarding + 10 weekly + 10 monthly), not
46 - there is no 6th "Recovery" driver or a "Compliance" driver anywhere in
the 5-component system (`COMPONENT_PRIORITY_ORDER` in
`app/core/recommendation_rules.py`), no question-bank versioning, and no
per-question validation-status field. Weekly/monthly questions have no
stored `reverse_scored`/`provider_route` field at all; onboarding questions
do (`app/core/question_bank.py`), but `provider_route` there is almost
uniformly `"PT/IM"` regardless of component (never differentiated by
Nutritionist/Mental Performance/Chaplain), and `reverse_scored` is `False`
on every entry - stored real data, included as-is for onboarding, but not
a meaningful per-component routing signal, which is why `routing` below is
a separate, explicitly-derived field rather than a re-labeling of
`provider_route`.
"""

from __future__ import annotations

from typing import Any

from app.core.monthly_checkin_question_bank import MONTHLY_CHECKIN_QUESTION_BANK
from app.core.question_bank import ONBOARDING_QUESTION_BANK
from app.core.roles import ROLE_CHAPLAIN, ROLE_MENTAL_PERFORMANCE, ROLE_NUTRITIONIST, ROLE_SCS
from app.core.weekly_checkin_question_bank import WEEKLY_CHECKIN_QUESTION_BANK

# Real, derived from the same specialist/SCS component ownership already
# established elsewhere (`SPECIALIST_COMPONENT_BY_ROLE` in
# `app/services/provider_dashboard_service.py`), extended to cover
# Physical/Sleep -> SCS since those 2 components don't belong to a
# specialist role.
COMPONENT_ROUTING: dict[str, str] = {
    "Physical Readiness": ROLE_SCS,
    "Sleep Readiness": ROLE_SCS,
    "Mental Readiness": ROLE_MENTAL_PERFORMANCE,
    "Nutritional Readiness": ROLE_NUTRITIONIST,
    "Spiritual Readiness": ROLE_CHAPLAIN,
}


def _entry(prefix: str, question: dict[str, Any], include_raw_fields: bool) -> dict[str, Any]:
    component = question.get("readiness_component")
    row = {
        "id": f"{prefix}{question['id']}",
        "readiness_component": component,
        "routing": COMPONENT_ROUTING.get(component),
        "has_provider_flag_trigger": bool(question.get("routing_trigger")),
    }
    if include_raw_fields:
        row["reverse_scored"] = question.get("reverse_scored", False)
        row["provider_route"] = question.get("provider_route")
    return row


def build_question_registry() -> dict[str, Any]:
    """Return the real 40-question registry (20 onboarding + 10 weekly + 10 monthly)."""
    onboarding = [_entry("O", q, include_raw_fields=True) for q in ONBOARDING_QUESTION_BANK]
    weekly = [_entry("W", q, include_raw_fields=False) for q in WEEKLY_CHECKIN_QUESTION_BANK]
    monthly = [_entry("M", q, include_raw_fields=False) for q in MONTHLY_CHECKIN_QUESTION_BANK]
    return {
        "total_questions": len(onboarding) + len(weekly) + len(monthly),
        "onboarding": onboarding,
        "weekly": weekly,
        "monthly": monthly,
    }
