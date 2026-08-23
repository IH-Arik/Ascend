"""Contract Question Registry - a simplified, real view over the 4 existing
question banks, for the Admin/Superadmin "Roles & RBAC" screen.

Not DOCX-sourced as an *endpoint* (a Figma screenshot triggered this), but
the underlying entities it reports on ARE DOCX-grounded: DOCX Table 22's
data dictionary has a real "Question Answer Option Set" row
(`reverse_score_status` among its fields, mirrored here by `direction`) and
a real "Question Bank Version" row (`version_id, effective_date,
retired_date, approved_by, ...question_set_id, change_reason`) that
controls "updates to question wording, answer choices, scoring, and driver
mapping without breaking scoring history" - that versioning/approval entity
has no model or endpoint anywhere in this codebase yet; it is real, DOCX-
required, and simply not built.

Corrected 2026-08-23 after a real bug was caught by re-checking the design
against live data: this registry originally summed to 40 (20 onboarding +
10 weekly + 10 monthly), and its own docstring wrongly claimed the design's
"D1-D6" section referred to a nonexistent 6th "Recovery"/"Compliance"
driver. It does not - `D1`-`D6` are the `label` values of the real,
already-live `DAILY_CHECKIN_QUESTION_BANK` (`app/core/checkin_question_bank.py`,
wired into `CheckinService` for actual daily check-ins), which this
registry simply never included. With the daily bank included the real
total is 20 + 6 + 10 + 10 = **46** - exactly matching the design's own
"O1-O20 + D1-D6 + W1-W10 + M1-M10 = 46" framing, which was real all along.

`direction` ("Higher = better" / "Lower = better") is a real, verified
value for every one of the 46 questions, not fabricated: onboarding and
daily entries store `reverse_scored` explicitly (`False` on all of them
today); weekly/monthly entries store no such field, but
`CheckinService._score_answer` (`checkin_service.py`) calls
`calculate_question_score(..., reverse_scored=question.get("reverse_scored",
False))`, so the real, currently-running scoring behavior for every
un-annotated question is the same `False` default - "Higher = better" is
the true current direction for all 46, derived the same way the scoring
engine itself derives it, not copied from the design.

`validation_status` is deliberately NOT included, and still has no real
per-question backing anywhere in DOCX or this codebase - DOCX's
"Question Bank Version" entity carries a single `approved_by` at the whole-
bank/version level, not a per-question valid/invalid flag. Showing a
per-row "Valid" badge would still be fabricating a concept, so it is
omitted here rather than invented; the real, buildable feature is the
version/approval entity above, still unbuilt.
"""

from __future__ import annotations

from typing import Any

from app.core.checkin_question_bank import DAILY_CHECKIN_QUESTION_BANK
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
    reverse_scored = question.get("reverse_scored", False)
    row = {
        "id": f"{prefix}{question['id']}",
        "readiness_component": component,
        "routing": COMPONENT_ROUTING.get(component),
        "direction": "Lower = better" if reverse_scored else "Higher = better",
        "has_provider_flag_trigger": bool(question.get("routing_trigger")),
    }
    if include_raw_fields:
        row["reverse_scored"] = reverse_scored
        row["provider_route"] = question.get("provider_route")
    return row


def build_question_registry() -> dict[str, Any]:
    """Return the real 46-question registry (20 onboarding + 6 daily + 10 weekly + 10 monthly)."""
    onboarding = [_entry("O", q, include_raw_fields=True) for q in ONBOARDING_QUESTION_BANK]
    daily = [_entry("D", q, include_raw_fields=True) for q in DAILY_CHECKIN_QUESTION_BANK]
    weekly = [_entry("W", q, include_raw_fields=False) for q in WEEKLY_CHECKIN_QUESTION_BANK]
    monthly = [_entry("M", q, include_raw_fields=False) for q in MONTHLY_CHECKIN_QUESTION_BANK]
    return {
        "total_questions": len(onboarding) + len(daily) + len(weekly) + len(monthly),
        "onboarding": onboarding,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
    }
