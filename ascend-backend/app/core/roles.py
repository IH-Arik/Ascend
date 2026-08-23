"""Role and permission definitions for Ascend."""

from typing import Final

ROLE_AIRMAN: Final[str] = "Airman"
ROLE_SCS: Final[str] = "SCS"
ROLE_PTIM: Final[str] = "PT/IM"
ROLE_NUTRITIONIST: Final[str] = "Nutritionist"
ROLE_MENTAL_PERFORMANCE: Final[str] = "Mental Performance"
ROLE_CHAPLAIN: Final[str] = "Chaplain"
ROLE_LEADERSHIP: Final[str] = "Leadership"
ROLE_IDMT: Final[str] = "IDMT"
ROLE_ADMIN: Final[str] = "DWS Admin"
ROLE_SUPERADMIN: Final[str] = "DWS Superadmin"

SUPPORTED_ROLES: Final[tuple[str, ...]] = (
    ROLE_AIRMAN,
    ROLE_SCS,
    ROLE_PTIM,
    ROLE_NUTRITIONIST,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_CHAPLAIN,
    ROLE_LEADERSHIP,
    ROLE_IDMT,
    ROLE_ADMIN,
    ROLE_SUPERADMIN,
)

# Superadmin has every Admin permission plus admin-account management -
# `ADMIN_ROLES` is the single source of truth wherever "has admin-level
# access" is being checked (route gates), while the narrower
# "can create/demote an Admin" check stays Superadmin-only inside
# `AdminUserService.change_role`.
ADMIN_ROLES: Final[tuple[str, ...]] = (ROLE_ADMIN, ROLE_SUPERADMIN)

# The 3 specialist support-pathway roles - previously `role: None` in
# `app/core/support_pathways.py` ("not yet formal system roles"). Now real,
# so My Support Team auto-assignment and the Specialist Dashboard can gate
# on them like SCS/PT-IM already do.
SPECIALIST_ROLES: Final[tuple[str, ...]] = (
    ROLE_NUTRITIONIST,
    ROLE_MENTAL_PERFORMANCE,
    ROLE_CHAPLAIN,
)

_SPECIALIST_PERMISSIONS: Final[list[str]] = [
    "view_assigned_users",
    "view_relevant_readiness_component",
    "coordinate_with_scs",
    "view_authorized_medical_summaries",
]

ROLE_PERMISSIONS: Final[dict[str, list[str]]] = {
    ROLE_AIRMAN: [
        "view_self_dashboard",
        "complete_onboarding",
        "complete_checkins",
        "view_assigned_actions",
        "request_support",
        "upload_personal_documents",
        "message_authorized_support",
    ],
    ROLE_SCS: [
        "view_assigned_users",
        "view_performance_readiness",
        "update_training_plans",
        "create_recommendations",
        "coordinate_with_ptim",
        "view_authorized_medical_summaries",
    ],
    ROLE_PTIM: [
        "view_injury_recovery",
        "manage_return_to_performance",
        "review_limitations",
        "view_authorized_medical_summaries",
        "coordinate_with_scs",
    ],
    ROLE_NUTRITIONIST: list(_SPECIALIST_PERMISSIONS),
    ROLE_MENTAL_PERFORMANCE: list(_SPECIALIST_PERMISSIONS),
    ROLE_CHAPLAIN: list(_SPECIALIST_PERMISSIONS),
    ROLE_LEADERSHIP: [
        "view_aggregate_dashboards",
        "view_reporting_trends",
        "view_authorized_reports",
    ],
    ROLE_IDMT: [
        "receive_authorized_exports",
        "view_handoff_summaries",
    ],
    ROLE_ADMIN: [
        "manage_accounts",
        "manage_roles",
        "manage_teams",
        "manage_permissions",
        "manage_exports",
        "manage_support_operations",
        "view_audit_logs",
        "view_compliance_trackers",
    ],
    ROLE_SUPERADMIN: [
        "manage_accounts",
        "manage_roles",
        "manage_teams",
        "manage_permissions",
        "manage_exports",
        "manage_support_operations",
        "view_audit_logs",
        "view_compliance_trackers",
        "manage_admin_accounts",
    ],
}


# Not DOCX-sourced - a "Roles & RBAC" admin screen (Figma) groups roles into
# clusters and color-codes them by scope. Roles were flat strings before
# this; this is our own reasonable classification, not a DOCX requirement.
# Display-only metadata for the Roles & RBAC "Role catalog" table - never
# consulted for an access decision (only `RoleAdminService.get_catalog`
# reads these). Originally an invented classification (Mobile/Staff/
# Aggregate/Control/Secure) that guessed at the screen's vocabulary before
# the design was available; corrected 2026-08-23 to the taxonomy the screen
# actually uses, which its own CATEGORY filter buttons enumerate:
# ALL / STAFF / CONTRACTOR / OFFICER / SYSTEM.
ROLE_CLUSTER: Final[dict[str, str]] = {
    ROLE_AIRMAN: "Staff",
    ROLE_SCS: "Staff",
    ROLE_PTIM: "Staff",
    ROLE_NUTRITIONIST: "Staff",
    ROLE_MENTAL_PERFORMANCE: "Staff",
    ROLE_CHAPLAIN: "Staff",
    ROLE_LEADERSHIP: "Contractor",
    ROLE_ADMIN: "Officer",
    # Not shown as its own row on the screen (ADMIN covers both admin-level
    # roles there), so it follows Admin's classification.
    ROLE_SUPERADMIN: "Officer",
    ROLE_IDMT: "System",
}

# Display-only, same as `ROLE_CLUSTER` above - the real access scoping lives
# in `RoleScopeConfig` (cohort_k / visible_components) and each route's own
# `require_roles(...)`, not here. Values match the screen's SCOPE column.
ROLE_SCOPE: Final[dict[str, str]] = {
    ROLE_AIRMAN: "Own",
    ROLE_SCS: "Flight",
    ROLE_PTIM: "Caseload",
    ROLE_NUTRITIONIST: "Caseload",
    ROLE_MENTAL_PERFORMANCE: "Caseload",
    ROLE_CHAPLAIN: "Caseload",
    ROLE_LEADERSHIP: "Global",
    ROLE_ADMIN: "Global",
    ROLE_SUPERADMIN: "Global",
    ROLE_IDMT: "Caseload",
}


def normalize_role(role: str | None) -> str:
    """Normalize role text into the supported Ascend role set."""
    value = (role or "").strip().lower()
    aliases = {
        "airman": ROLE_AIRMAN,
        "operator": ROLE_AIRMAN,
        "user": ROLE_AIRMAN,
        "scs": ROLE_SCS,
        "strength and conditioning specialist": ROLE_SCS,
        "fitness coach": ROLE_SCS,
        "pt/im": ROLE_PTIM,
        "pt": ROLE_PTIM,
        "injury manager": ROLE_PTIM,
        "physical therapist": ROLE_PTIM,
        "nutritionist": ROLE_NUTRITIONIST,
        "nutrition": ROLE_NUTRITIONIST,
        "performance nutrition": ROLE_NUTRITIONIST,
        "mental performance": ROLE_MENTAL_PERFORMANCE,
        "mental performance / behavioral": ROLE_MENTAL_PERFORMANCE,
        "chaplain": ROLE_CHAPLAIN,
        "purpose coach": ROLE_CHAPLAIN,
        "spiritual readiness coach": ROLE_CHAPLAIN,
        "leadership": ROLE_LEADERSHIP,
        "hpo manager": ROLE_LEADERSHIP,
        "leadership/hpo manager": ROLE_LEADERSHIP,
        "idmt": ROLE_IDMT,
        "dws admin": ROLE_ADMIN,
        "admin": ROLE_ADMIN,
        "contract manager": ROLE_ADMIN,
        "dws admin / contract manager": ROLE_ADMIN,
        "dws superadmin": ROLE_SUPERADMIN,
        "superadmin": ROLE_SUPERADMIN,
        "super admin": ROLE_SUPERADMIN,
    }
    return aliases.get(value, role or "")


def is_supported_role(role: str | None) -> bool:
    """Return whether the role is in the approved Ascend role set."""
    return normalize_role(role) in SUPPORTED_ROLES


def permissions_for_role(role: str | None) -> list[str]:
    """Return the permissions for a normalized role."""
    return ROLE_PERMISSIONS.get(normalize_role(role), [])
