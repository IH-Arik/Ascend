"""General helper utilities."""

from datetime import datetime
from random import randint


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.utcnow()


def generate_verification_code() -> str:
    """Return a zero-padded 4-digit verification code."""
    return f"{randint(0, 9999):04d}"


def is_code_expired(expires_at: datetime | None) -> bool:
    """Return whether a verification code has expired."""
    if expires_at is None:
        return True
    return datetime.utcnow() >= expires_at
