"""Question Bank Version - DOCX Table 22 data dictionary:

"Question Bank Version | version_id, effective_date, retired_date,
approved_by, onboarding_question_set_id, daily_question_set_id,
weekly_question_set_id, monthly_question_set_id, change_reason | Controls
updates to question wording, answer choices, scoring, and driver mapping
without breaking scoring history or longitudinal trend integrity."

Real, DOCX-required entity that had no model or endpoint until 2026-08-23,
found while re-checking the Contract Question Registry against the DOCX
data dictionary. Approval/versioning is tracked at the whole-question-bank
level here, not per individual question - there is no DOCX or codebase
concept of a per-question "valid/invalid" flag (see
`app/core/question_registry.py`'s docstring for that finding).

Versioned and effective-dated like `ScoringConfig` (same file's sibling
pattern): the active version is the most recent one whose `effective_date`
is today or earlier AND is not yet retired. Unlike `ScoringConfig`,
`retired_date` is a real DOCX field, so retiring is an explicit action
(`QuestionBankVersionService.retire_version`) rather than an implicit
side effect of creating a newer version - old versions are kept, not
replaced, "without breaking scoring history".
"""

from datetime import date, datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class QuestionBankVersion(Document):
    """One versioned, effective-dated, admin-approved question bank record."""

    version_id: str
    effective_date: date = Field(default_factory=date.today)
    retired_date: date | None = None
    approved_by: PydanticObjectId
    onboarding_question_set_id: str | None = None
    daily_question_set_id: str | None = None
    weekly_question_set_id: str | None = None
    monthly_question_set_id: str | None = None
    change_reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "question_bank_versions"
        indexes = [
            IndexModel([("effective_date", -1)]),
        ]
