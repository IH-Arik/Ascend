"""Role and permission routes."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.deps import require_roles
from app.common.utils.responses import success_response
from app.core.roles import ADMIN_ROLES
from app.core.roles import ROLE_PERMISSIONS
from app.core.roles import SUPPORTED_ROLES
from app.core.roles import permissions_for_role
from app.models.user import User
from app.schemas.org_unit import RoleScopeConfigUpdate
from app.schemas.pathway_approval import PathwayEnableRequest
from app.services.pathway_approval_service import PathwayApprovalService
from app.services.role_admin_service import RoleAdminService

router = APIRouter()
role_admin_service = RoleAdminService()
pathway_approval_service = PathwayApprovalService()


@router.get("", summary="List supported roles")
async def list_roles(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Return the supported roles and their permissions."""
    return success_response(
        "Roles loaded successfully.",
        {
            "roles": list(SUPPORTED_ROLES),
            "permission_matrix": ROLE_PERMISSIONS,
            "requested_by": {
                "id": str(current_user.id),
                "role": current_user.role,
            },
        },
    )


@router.get("/catalog", summary="Role catalog - cluster/scope metadata + real member/audit counts")
async def get_role_catalog(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Admin/Superadmin "Roles & RBAC" screen - real per-role counts, not fabricated."""
    data = await role_admin_service.get_catalog()
    return success_response("Role catalog loaded successfully.", data)


@router.get(
    "/accounts-onboarding-summary",
    summary="Accounts & onboarding card - account status, onboarding, access expiration, assigned providers, permissions, purpose consent",
)
async def get_accounts_onboarding_summary(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Real per-metric counts for the Roles & RBAC "Accounts & onboarding" card."""
    data = await role_admin_service.get_accounts_and_onboarding_summary()
    return success_response("Accounts & onboarding summary loaded successfully.", data)


@router.get("/matrix", summary="RBAC matrix - role x permission, full/gated/none")
async def get_role_matrix(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Real capability rows derived from `ROLE_PERMISSIONS`; `gated` only where a real second-reviewer gate exists."""
    data = await role_admin_service.get_matrix()
    return success_response("RBAC matrix loaded successfully.", data)


@router.get("/scope-config", summary="Real per-role cohort-k + visible-components config")
async def list_scope_configs(
    role: str | None = None,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """One role's config (`?role=X`) or every role's (defaults for roles never explicitly set)."""
    if role:
        data = await role_admin_service.get_scope_config(role)
    else:
        data = await role_admin_service.list_scope_configs()
    return success_response("Scope config loaded successfully.", data)


@router.patch("/scope-config/{role}", summary="Set a role's real cohort-k + visible components")
async def update_scope_config(
    role: str,
    payload: RoleScopeConfigUpdate,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Admin sets a real, enforced cohort-k minimum and readiness-component visibility for a role."""
    data = await role_admin_service.update_scope_config(
        current_user, role, payload.cohort_k, payload.visible_components
    )
    return success_response("Scope config updated successfully.", data)


@router.get("/scope-matrix", summary="Admin coverage map - real per-role scope columns")
async def get_scope_matrix(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Real self/unit/caseload/opt-in/aggregate/global columns per role - not a screenshot replica."""
    data = await role_admin_service.get_coverage_map()
    return success_response("Scope matrix loaded successfully.", data)


@router.get("/scope-resolve", summary="Scope matrix per-user drill-down - real resolved unit ancestor path + role coverage")
async def resolve_scope(
    role: str,
    unit_id: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Real `OrgUnit` ancestor path for `unit_id` combined with that role's real coverage-map row."""
    data = await role_admin_service.resolve_scope(role, unit_id)
    return success_response("Scope resolved successfully.", data)


@router.get("/pathway-matrix", summary="Conditional pathway matrix - real staffing/opt-in + real approval/enablement")
async def get_pathway_matrix(
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Real staffing/opt-in counts for the 3 optional pathways, merged with each one's real `PathwayApproval` state."""
    data = await role_admin_service.get_pathway_matrix()
    approvals = {p["pathway_key"]: p for p in (await pathway_approval_service.list_all())["pathways"]}
    for row in data["pathways"]:
        row["approval"] = approvals.get(row["pathway_key"])
    return success_response("Pathway matrix loaded successfully.", data)


@router.post("/pathway-approvals/{pathway_key}/approve", summary="Approve an optional support pathway")
async def approve_pathway(
    pathway_key: str,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Admin/Superadmin approves one of the 3 optional pathways (Nutritionist, Mental Performance, Chaplain)."""
    data = await pathway_approval_service.approve(current_user, pathway_key)
    return success_response("Pathway approved successfully.", data)


@router.post("/pathway-approvals/{pathway_key}/enable", summary="Enable a previously-approved optional support pathway")
async def enable_pathway(
    pathway_key: str,
    payload: PathwayEnableRequest,
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
) -> dict[str, Any]:
    """Admin/Superadmin enables a pathway already approved, optionally recording its access policy."""
    data = await pathway_approval_service.enable(current_user, pathway_key, payload)
    return success_response("Pathway enabled successfully.", data)


@router.get("/me", summary="List current role permissions")
async def get_my_role_permissions(
    current_user: User = Depends(require_roles(*SUPPORTED_ROLES)),
) -> dict[str, Any]:
    """Return the permissions for the current user's role."""
    return success_response(
        "Role permissions loaded successfully.",
        {
            "role": current_user.role,
            "permissions": permissions_for_role(current_user.role),
        },
    )
