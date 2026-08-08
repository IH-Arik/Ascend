"""Role and permission definitions for Ascend."""

from typing import Final

ROLE_AIRMAN: Final[str] = "Airman"
ROLE_SCS: Final[str] = "SCS"
ROLE_PTIM: Final[str] = "PT/IM"
ROLE_LEADERSHIP: Final[str] = "Leadership"
ROLE_IDMT: Final[str] = "IDMT"
ROLE_ADMIN: Final[str] = "DWS Admin"

SUPPORTED_ROLES: Final[tuple[str, ...]] = (
    ROLE_AIRMAN,
    ROLE_SCS,
    ROLE_PTIM,
    ROLE_LEADERSHIP,
    ROLE_IDMT,
    ROLE_ADMIN,
)

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
        "leadership": ROLE_LEADERSHIP,
        "hpo manager": ROLE_LEADERSHIP,
        "leadership/hpo manager": ROLE_LEADERSHIP,
        "idmt": ROLE_IDMT,
        "dws admin": ROLE_ADMIN,
        "admin": ROLE_ADMIN,
        "contract manager": ROLE_ADMIN,
        "dws admin / contract manager": ROLE_ADMIN,
    }
    return aliases.get(value, role or "")


def is_supported_role(role: str | None) -> bool:
    """Return whether the role is in the approved Ascend role set."""
    return normalize_role(role) in SUPPORTED_ROLES


def permissions_for_role(role: str | None) -> list[str]:
    """Return the permissions for a normalized role."""
    return ROLE_PERMISSIONS.get(normalize_role(role), [])
