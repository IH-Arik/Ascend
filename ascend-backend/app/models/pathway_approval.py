"""Real approval/enablement lifecycle for the 3 optional support pathways
(Nutritionist, Mental Performance, Chaplain).

Not DOCX-sourced (a Figma "Conditional pathway matrix" screen showed
APPROVAL/ENABLEMENT/ACCESS DATES columns with no backing anywhere - the
dates were literally identical hardcoded strings copy-pasted across all 3
pathway rows in `ascend-admin`, and `RoleAdminService.get_pathway_matrix`'s
own docstring already documented deliberately omitting invented dates).
Built as real new scope per explicit instruction (2026-08-23), same
"real new scope, not DOCX-required" category as `PendingConfirmation`.

One record per pathway (same "current record per key" style as
`RoleScopeConfig`), not a versioned history - a pathway is approved once,
then separately enabled once; re-approving/re-enabling updates the same
record rather than creating a new one, since there is no requirement here
for point-in-time history the way `QuestionBankVersion` needs it.

Unlike `PendingConfirmation`, this has no two-person-rule gate - that
pattern is reserved for destructive actions (deactivation, admin role
change) elsewhere in this codebase; approving/enabling a support pathway
isn't in that category.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_ENABLED = "enabled"


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class PathwayApproval(Document):
    """One real approval/enablement record for one optional support pathway."""

    pathway_key: str
    status: str = STATUS_PENDING
    approved_by: PydanticObjectId | None = None
    approved_at: datetime | None = None
    enabled_by: PydanticObjectId | None = None
    enabled_at: datetime | None = None
    access_policy: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    class Settings:
        """Beanie collection settings."""

        name = "pathway_approvals"
        indexes = [IndexModel([("pathway_key", 1)], unique=True)]
