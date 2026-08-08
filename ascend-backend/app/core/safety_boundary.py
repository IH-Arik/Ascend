"""Level 5 - Safety Boundary keyword flag (DOCX section 5, Routing Threshold Rules).

DOCX: "User language indicates emergency, self-harm, violence, medical
emergency, or urgent operational risk -> Show approved safety/emergency
language and route outside app according to DWS/Government procedures ...
Do not let AI or app decide care; follow approved procedure."

This module is deliberately a small, deterministic keyword match - no AI/LLM
involvement in detection or response. It never blocks a submission and never
generates any clinical or care-related text; it only flags the request for
priority human review by the assigned provider and admin, and surfaces a
generic, publicly known emergency-resource notice back to the user. A real
"approved safety/emergency language" and DWS/Government routing procedure
still needs to be supplied by the organization - this is a conservative
interim safety net, not that approved procedure.
"""

from __future__ import annotations

import re

SAFETY_BOUNDARY_TERMS: tuple[str, ...] = (
    "suicide",
    "suicidal",
    "kill myself",
    "end my life",
    "want to die",
    "self-harm",
    "self harm",
    "hurt myself",
    "harm myself",
)

_SAFETY_BOUNDARY_PATTERNS = {
    term: re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE) for term in SAFETY_BOUNDARY_TERMS
}

SAFETY_NOTICE = (
    "If this is a medical emergency or safety crisis, call 911 or the Veterans/Military "
    "Crisis Line at 988 (Press 1) now. This app is not monitored in real time and is not "
    "a substitute for emergency care."
)


def scan_for_safety_boundary_terms(*texts: str) -> list[str]:
    """Return any Level 5 safety-boundary terms found in the given texts (whole-phrase match)."""
    combined = " ".join(t for t in texts if t)
    return [term for term, pattern in _SAFETY_BOUNDARY_PATTERNS.items() if pattern.search(combined)]
