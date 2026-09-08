"""Deterministic anonymized display codes.

Net-new (2026-09-07, explicit user go-ahead). The Chaplain/Purpose pathway
mock shows "No rank, no PII" - airmen appear only as a stable code like
"A-1042", never a name. No such concept existed anywhere in this backend.
This derives a real, stable code from the real user id (never stored,
never randomized per-call) - the same user always gets the same code, but
the code alone never reveals rank, name, or any other real field.
"""

import hashlib
from typing import Any


def anonymized_code(user_id: Any) -> str:
    """Return a stable "A-NNNN" code derived from a real user id."""
    digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()
    number = 1000 + (int(digest[:8], 16) % 9000)
    return f"A-{number}"
