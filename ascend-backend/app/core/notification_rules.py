"""Notification family catalog and OPSEC content-scan rules.

Families are the 9 named in docs/NOTIFICATION_RULES.md plus `message_received`
(named as a distinct core trigger there, not grouped under another family).
`category` is a UI-grouping concept, not defined in the DOCX - it is our own
reasonable inference from the Notifications screen's "Reminders"/"Records"
filter tabs, kept in its own mapping so it stays easy to revise.
"""

from __future__ import annotations

import re

CHECK_IN_REMINDERS = "check_in_reminders"
ASSIGNED_ACTION_REMINDERS = "assigned_action_reminders"
SUPPORT_REQUEST_UPDATES = "support_request_updates"
PROVIDER_FOLLOW_UP_REMINDERS = "provider_follow_up_reminders"
ASSESSMENT_DUE_REMINDERS = "assessment_due_reminders"
OFT_DUE_REMINDERS = "oft_due_reminders"
COMPLIANCE_DUE_REMINDERS = "compliance_due_reminders"
EXPORT_COMPLETION_NOTICES = "export_completion_notices"
MEDICAL_RECORD_GOVERNANCE_NOTICES = "medical_record_review_and_governance_notices"
MESSAGE_RECEIVED = "message_received"
SAFETY_BOUNDARY_PRIORITY_FLAG = "safety_boundary_priority_flag"

NOTIFICATION_FAMILIES = {
    CHECK_IN_REMINDERS,
    ASSIGNED_ACTION_REMINDERS,
    SUPPORT_REQUEST_UPDATES,
    PROVIDER_FOLLOW_UP_REMINDERS,
    ASSESSMENT_DUE_REMINDERS,
    OFT_DUE_REMINDERS,
    COMPLIANCE_DUE_REMINDERS,
    EXPORT_COMPLETION_NOTICES,
    MEDICAL_RECORD_GOVERNANCE_NOTICES,
    MESSAGE_RECEIVED,
    SAFETY_BOUNDARY_PRIORITY_FLAG,
}

FAMILY_CATEGORY: dict[str, str] = {
    CHECK_IN_REMINDERS: "reminders",
    OFT_DUE_REMINDERS: "reminders",
    ASSESSMENT_DUE_REMINDERS: "reminders",
    PROVIDER_FOLLOW_UP_REMINDERS: "reminders",
    COMPLIANCE_DUE_REMINDERS: "reminders",
    MEDICAL_RECORD_GOVERNANCE_NOTICES: "records",
    EXPORT_COMPLETION_NOTICES: "records",
    ASSIGNED_ACTION_REMINDERS: "updates",
    SUPPORT_REQUEST_UPDATES: "updates",
    MESSAGE_RECEIVED: "updates",
    SAFETY_BOUNDARY_PRIORITY_FLAG: "updates",
}


def get_category(family: str) -> str:
    """Return the UI filter-tab category for a notification family."""
    return FAMILY_CATEGORY.get(family, "updates")


# Best-effort keyword screen for the "do not share operational schedules,
# tactics, or OPSEC content" rule shown on the Notifications screen. This is
# a simple deny-list, not a real DLP/classification system - it exists to
# catch obviously unsafe provider-authored text (e.g. free-typed assigned
# action instructions), not to guarantee OPSEC safety in general.
#
# Severity (1-5) added 2026-08-24, closing a real mobile-app gap: the
# Support "chat" screen's own audit sheet and the "Data-use summary" screen
# both describe a graduated scale ("Level 5 (highest) never routes through
# messaging"), but this scan was previously an undifferentiated flat list -
# every match blocked identically, with no severity concept at all. Not
# DOCX-sourced (checked - zero hits for "OPSEC severity"/"keyword scan"
# anywhere in the DOCX), so the specific level per term below is our own
# reasonable classification, not a requirement. Every term still blocks the
# send regardless of level - severity is real, added metadata for audit/
# reporting granularity, not a loosening of the existing block-on-any-match
# behavior (an unreviewed severity-based allow-through would be a real
# security regression this session has no basis to make on its own).
# 5 = specific, unambiguous geolocation/movement data - the clearest actual
#     OPSEC exposure if sent.
# 3 = real operational-planning terms, but more likely to appear in
#     legitimate non-sensitive context (higher false-positive risk).
OPSEC_TERM_SEVERITY: dict[str, int] = {
    "grid coordinates": 5,
    "grid reference": 5,
    "troop movement": 5,
    "convoy": 5,
    "unit location": 5,
    "op order": 4,
    "operation order": 4,
    "classified": 4,
    "mission": 3,
    "deployment": 3,
}

OPSEC_BLOCKED_TERMS: tuple[str, ...] = tuple(OPSEC_TERM_SEVERITY.keys())

OPSEC_MAX_SEVERITY = 5


_OPSEC_TERM_PATTERNS = {
    term: re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE) for term in OPSEC_BLOCKED_TERMS
}


def scan_for_opsec_terms(*texts: str) -> list[str]:
    """Return any blocked terms found in the given texts (whole-word match).

    Uses word boundaries so "mission" doesn't false-positive on ordinary
    words like "submission", "permission", or "commission", and
    "classified" doesn't false-positive on "unclassified".
    """
    combined = " ".join(texts)
    return [term for term, pattern in _OPSEC_TERM_PATTERNS.items() if pattern.search(combined)]


def opsec_severity(term: str) -> int:
    """Return one matched term's real severity level (1-5)."""
    return OPSEC_TERM_SEVERITY.get(term, OPSEC_MAX_SEVERITY)


def highest_opsec_severity(terms: list[str]) -> int | None:
    """Return the highest severity among a set of matched terms, or `None` if empty."""
    if not terms:
        return None
    return max(opsec_severity(term) for term in terms)
