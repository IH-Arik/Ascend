"""Per-role cohort-k minimum + readiness-component visibility config.

Not DOCX-sourced (a Figma "Scope matrix" screen showed a configurable
cohort-size selector and per-role driver-visibility toggles, neither of
which existed - the k-anonymity minimum was a fixed constant
(`MIN_UNIT_COHORT_SIZE` in `app/services/dashboard_service.py`) and there
was no component-visibility concept at all). Real, wired into actual
behavior - see `RoleAdminService.get_scope_config` and its call sites in
`dashboard_service.py`/`provider_dashboard_service.py`, not a stored
setting nobody reads.

Same versioned-admin-config style precedent as `app/models/scoring_config.py`,
simplified to "one current record per role" (upserted, not versioned) since
there's no effective-dating requirement here.
"""

from datetime import datetime, timezone

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import IndexModel

DEFAULT_COHORT_K = 5
DEFAULT_VISIBLE_COMPONENTS = [
    "Physical Readiness",
    "Sleep Readiness",
    "Mental Readiness",
    "Nutritional Readiness",
    "Spiritual Readiness",
]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RoleScopeConfig(Document):
    """One real, admin-editable scope config for a single role."""

    role: str
    cohort_k: int = DEFAULT_COHORT_K
    visible_components: list[str] = Field(default_factory=lambda: list(DEFAULT_VISIBLE_COMPONENTS))
    updated_at: datetime = Field(default_factory=utc_now)
    updated_by: PydanticObjectId | None = None

    class Settings:
        """Beanie collection settings."""

        name = "role_scope_configs"
        indexes = [IndexModel([("role", 1)], unique=True)]
