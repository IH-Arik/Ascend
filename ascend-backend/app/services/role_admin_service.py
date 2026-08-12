"""Role catalog + RBAC matrix for the Admin/Superadmin "Roles & RBAC" screen.

Not DOCX-sourced (a Figma screenshot triggered this) - every field here is
either real data (member counts, real audit history) or an explicitly
stated new classification (`ROLE_CLUSTER`/`ROLE_SCOPE` in `app/core/roles.py`),
never fabricated to match the screenshot's exact shape. See
`app/core/roles.py` for the cluster/scope metadata and
`app/services/admin_confirmation_service.py` for the real second-reviewer
gate this matrix's one `gated` cell reflects.

`CAPABILITY_ROLE_GATES` below was originally derived from `ROLE_PERMISSIONS`
(a dict built for `GET /roles`'s own display purpose, not as an exhaustive
access-control map) rather than each capability's actual route-level
`require_roles(...)` gate. That produced a matrix that looked real but
wasn't: it showed PT/IM/Admin/Superadmin as unable to view their own
dashboard and Admin/Superadmin as unable to send a message, when the real
routes (`app/modules/dashboards/routes.py`, `app/modules/messaging/routes.py`)
have no role restriction at all; it also showed Admin/Superadmin excluded
from caseload/aggregate-trend/plan-authoring capabilities their real routes
(`app/modules/dashboard/routes.py`, `app/modules/recommendations/routes.py`)
explicitly grant them. Caught when asked to double-check completeness
across every Control Plane screen, not caught by the original live
verification (which only spot-checked 2 of 9 rows). Rebuilt below directly
from each capability's real route gate, with a citation on every entry, and
2 rows dropped entirely ("Send IDMT handoff", "View Authorized Performance
Summary") since neither corresponds to any real, implemented endpoint -
keeping a fabricated-looking row for a feature that doesn't exist would be
the same mistake again.
"""

from __future__ import annotations

from typing import Any

from app.core.question_registry import COMPONENT_ROUTING
from app.core.roles import (
    ADMIN_ROLES,
    ROLE_CLUSTER,
    ROLE_LEADERSHIP,
    ROLE_PTIM,
    ROLE_SCOPE,
    ROLE_SCS,
    ROLE_CHAPLAIN,
    SPECIALIST_ROLES,
    SUPPORTED_ROLES,
)
from app.core.security import utc_now
from app.core.support_pathways import get_support_pathways
from app.models.audit_log import AuditLog
from app.models.role_scope_config import DEFAULT_COHORT_K, DEFAULT_VISIBLE_COMPONENTS, RoleScopeConfig
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.services.audit_log_service import AuditLogService
from app.services.org_unit_service import OrgUnitService

# Real: inverted from `COMPONENT_ROUTING` (app/core/question_registry.py) -
# which specialist role "owns" which readiness component, for the
# Conditional pathway matrix's real `data_access` text.
ROLE_TO_COMPONENT: dict[str, str] = {role: component for component, role in COMPONENT_ROUTING.items()}

# Real per-capability role gates, each citing the exact route it's derived
# from - `None` means the real route has no role restriction at all
# (any authenticated user via `get_current_user`), not "nobody."
CAPABILITY_ROLE_GATES: dict[str, tuple[str, ...] | None] = {
    # GET /dashboards/home etc. - `get_current_user` only, no role gate.
    "View own dashboard": None,
    # Union of GET /dashboard/scs (ADMIN_ROLES+SCS), /dashboard/ptim
    # (ADMIN_ROLES+PTIM), /dashboard/specialist (SPECIALIST_ROLES).
    "View caseload records": (*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM, *SPECIALIST_ROLES),
    # POST /messaging/send - `get_current_user` only, no role gate.
    "Send message": None,
    # POST /recommendations/{user_id}/assign's real require_roles(...).
    "Author plan": (*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM, *SPECIALIST_ROLES),
    # GET /dashboard/leadership's real require_roles(...).
    "View aggregate trend": (*ADMIN_ROLES, ROLE_LEADERSHIP),
    # GET /admin/reports/{type}/export's real require_roles(...).
    "Run export": ADMIN_ROLES,
    # PATCH /admin/users/{id}/role + POST /admin/users/{id}/deactivate's
    # real require_roles(...) - the `GATED_CELLS` override below reflects
    # the real second-reviewer requirement on top of this base gate.
    "Deactivate user": ADMIN_ROLES,
}

# Real: matches `AdminUserService`/`AdminConfirmationService`'s second-
# reviewer requirement for deactivating a provider/admin-level account.
GATED_CELLS: set[tuple[str, str]] = {(role, "Deactivate user") for role in ADMIN_ROLES}


class RoleAdminService:
    """Build the real role catalog, RBAC matrix, and purpose-consent summary."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.org_unit_service = OrgUnitService()

    async def get_catalog(self) -> dict[str, Any]:
        """One row per real role: cluster/scope metadata + real member/audit counts."""
        role_change_events = await AuditLog.find(AuditLog.event_type == "role_changed").to_list()

        rows = []
        for role in SUPPORTED_ROLES:
            member_count = await User.find(User.role == role).count()
            audit_entry_count = await AuditLog.find(AuditLog.actor_role == role).count()

            matching_changes = [
                e for e in role_change_events if e.metadata_payload.get("new_role") == role
            ]
            matching_changes.sort(key=lambda e: e.created_at, reverse=True)
            last_edit = matching_changes[0].created_at.isoformat() if matching_changes else None

            rows.append(
                {
                    "role": role,
                    "cluster": ROLE_CLUSTER.get(role),
                    "scope": ROLE_SCOPE.get(role),
                    "member_count": member_count,
                    "last_edit": last_edit,
                    "audit_entry_count": audit_entry_count,
                }
            )

        return {
            "role_count": len(SUPPORTED_ROLES),
            "roles": rows,
            "purpose_consent": await self._purpose_consent_summary(),
        }

    async def get_matrix(self) -> dict[str, Any]:
        """7 real capability rows x every real role, full/gated/none - each row's
        access derived from its actual route-level `require_roles(...)` gate
        (`CAPABILITY_ROLE_GATES`), not an inferred permission-string mapping.
        """
        matrix = []
        for capability, allowed_roles in CAPABILITY_ROLE_GATES.items():
            cells = {}
            for role in SUPPORTED_ROLES:
                if (role, capability) in GATED_CELLS:
                    cells[role] = "gated"
                elif allowed_roles is None or role in allowed_roles:
                    cells[role] = "full"
                else:
                    cells[role] = "none"
            matrix.append({"capability": capability, "roles": cells})
        return {"roles": list(SUPPORTED_ROLES), "matrix": matrix}

    async def _purpose_consent_summary(self) -> dict[str, Any]:
        """Reuses the existing Chaplain/Purpose pathway toggle - no new model.

        `active_count` is real `TeamAssignment` state. `withdrawn_count`
        counts distinct users with a real explicit disable action in
        `AuditLog` - a never-toggled (default) assignment is not "withdrawn",
        only an explicit enabled->disabled transition is.
        """
        active_count = await TeamAssignment.find(
            TeamAssignment.pathway_key == ROLE_CHAPLAIN, TeamAssignment.status == "enabled"
        ).count()

        # A currently-disabled assignment only counts as "withdrawn" if it
        # was ever explicitly toggled off (real audit event) - a
        # never-toggled default-disabled assignment (nobody ever opted in)
        # is not a withdrawal. A user who disabled then later re-enabled is
        # correctly excluded here (their current status is "enabled", so
        # they're in `active_count` instead) - this reflects *current*
        # withdrawal state, not "ever disabled once".
        currently_disabled = await TeamAssignment.find(
            TeamAssignment.pathway_key == ROLE_CHAPLAIN, TeamAssignment.status == "disabled"
        ).to_list()
        disabled_assignment_ids = {str(a.id) for a in currently_disabled}

        toggle_events = await AuditLog.find(AuditLog.event_type == "support_pathway_toggle").to_list()
        explicitly_disabled_ids = {
            e.target_entity_id
            for e in toggle_events
            if e.metadata_payload.get("pathway_key") == ROLE_CHAPLAIN
            and e.metadata_payload.get("new_status") == "disabled"
        }
        withdrawn_count = len(disabled_assignment_ids & explicitly_disabled_ids)
        return {"active_count": active_count, "withdrawn_count": withdrawn_count}

    async def get_scope_config(self, role: str) -> dict[str, Any]:
        """Return a role's real cohort-k + visible-components config.

        Returns an honest in-memory default (`cohort_k=5`, all components
        visible) if no config has been saved yet - same "real, not
        fabricated" pattern as `system_health`'s `insufficient_data`, not a
        pretend record that was never actually set.
        """
        record = await RoleScopeConfig.find_one(RoleScopeConfig.role == role)
        if record is None:
            return {
                "role": role,
                "cohort_k": DEFAULT_COHORT_K,
                "visible_components": list(DEFAULT_VISIBLE_COMPONENTS),
                "is_default": True,
            }
        return {
            "role": role,
            "cohort_k": record.cohort_k,
            "visible_components": record.visible_components,
            "is_default": False,
        }

    async def update_scope_config(
        self, admin: User, role: str, cohort_k: int, visible_components: list[str]
    ) -> dict[str, Any]:
        """Admin sets a role's real cohort-k + visible-components. Audit logged."""
        record = await RoleScopeConfig.find_one(RoleScopeConfig.role == role)
        if record is None:
            record = RoleScopeConfig(role=role)
        old_k, old_components = record.cohort_k, record.visible_components
        record.cohort_k = cohort_k
        record.visible_components = visible_components
        record.updated_at = utc_now()
        record.updated_by = admin.id
        await record.save()

        await self.audit_log_service.record(
            event_type="scope_config_updated",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="role_scope_config",
            target_entity_id=str(record.id),
            summary_message=f"Scope config updated for {role}: k {old_k}->{cohort_k}.",
            metadata_payload={
                "role": role,
                "old_cohort_k": old_k,
                "new_cohort_k": cohort_k,
                "old_visible_components": old_components,
                "new_visible_components": visible_components,
            },
        )
        return {"role": role, "cohort_k": record.cohort_k, "visible_components": record.visible_components}

    async def list_scope_configs(self) -> dict[str, Any]:
        """Return every role's real scope config (defaults for roles never explicitly configured)."""
        return {"configs": [await self.get_scope_config(role) for role in SUPPORTED_ROLES]}

    async def get_coverage_map(self) -> dict[str, Any]:
        """Real per-role scope columns - not a replica of the screenshot's asymmetric mockup.

        Every column is grounded in a real route-level `require_roles(...)`
        gate, cited inline - not the `ROLE_PERMISSIONS` heuristic (see this
        module's docstring for why that produced a wrong `GET /roles/matrix`
        that had to be rebuilt). Unlike the Figma screenshot, which showed
        an asymmetric pattern (e.g. Nutrition getting "Flight" visibility
        that Mental Performance/Purpose didn't), this system's real
        permission model treats the 3 specialist roles symmetrically
        (`SPECIALIST_ROLES`).
        """
        rows = []
        for role in SUPPORTED_ROLES:
            member_count = await User.find(User.role == role).count()

            # GET /dashboard/scs + /dashboard/ptim's real combined role
            # gate - Admin/Superadmin genuinely have this, unlike the
            # earlier version of this method.
            unit_visibility = "active" if role in (*ADMIN_ROLES, ROLE_SCS, ROLE_PTIM) else "none"
            # Real `TeamAssignment` caseload holders specifically (not
            # "can view a caseload dashboard") - Admin/Superadmin view
            # org-wide via `unit_visibility` above but don't personally
            # hold assignments, a real, distinct thing from `unit_visibility`.
            caseload = "active" if role in (ROLE_SCS, ROLE_PTIM) else "none"

            opt_in = "none"
            if role in SPECIALIST_ROLES:
                active_count = await TeamAssignment.find(
                    TeamAssignment.pathway_key == role, TeamAssignment.status == "enabled"
                ).count()
                opt_in = f"opt-in ({active_count} active)"

            # GET /dashboard/leadership's real combined role gate.
            aggregate_wing = "none"
            if role in (*ADMIN_ROLES, ROLE_LEADERSHIP):
                scope_config = await self.get_scope_config(role)
                aggregate_wing = f"k>={scope_config['cohort_k']}"

            global_scope = "active" if role in ADMIN_ROLES else "none"

            rows.append(
                {
                    "role": role,
                    "self": member_count,
                    "unit_visibility": unit_visibility,
                    "caseload": caseload,
                    "opt_in": opt_in,
                    "aggregate_wing": aggregate_wing,
                    "global": global_scope,
                }
            )
        return {"roles": rows}

    async def resolve_scope(self, role: str, unit_id: str) -> dict[str, Any]:
        """Real per-user/per-role live-resolved view - the Scope matrix's deferred
        "Coverage · active selection"/"Scope inheritance" panel.

        Not DOCX-sourced (a Figma "Scope matrix" screen triggered this - see
        `app/models/org_unit.py`). Real `OrgUnit` ancestor path for
        `unit_id` + this one role's real coverage-map row (reuses
        `get_coverage_map` rather than re-deriving the same real logic).
        """
        ancestor_path = await self.org_unit_service.resolve_ancestors(unit_id)
        member_count = await User.find(User.role == role, User.unit_id == unit_id).count()

        coverage = await self.get_coverage_map()
        role_row = next((r for r in coverage["roles"] if r["role"] == role), None)

        return {
            "role": role,
            "unit_id": unit_id,
            "ancestor_path": ancestor_path,
            "member_count_in_unit": member_count,
            "role_scope": role_row,
        }

    async def get_pathway_matrix(self) -> dict[str, Any]:
        """Partial real Conditional pathway matrix - no fabricated approval/enablement dates.

        Only the 3 optional pathways (Nutritionist, Mental Performance,
        Chaplain) - SCS/PT-IM are `always_available`, not conditional.
        """
        pathways = [p for p in get_support_pathways() if not p["always_available"]]
        rows = []
        for pathway in pathways:
            role = pathway["role"]
            # Filter `is_active` in Python, not `== True` in the query - the
            # documented Beanie boolean-equality gotcha used throughout this
            # codebase (see `TeamService._find_active_provider`).
            role_holders = await User.find(User.role == role).to_list()
            staffing = sum(1 for u in role_holders if u.is_active)
            active_opt_in_count = await TeamAssignment.find(
                TeamAssignment.pathway_key == pathway["key"], TeamAssignment.status == "enabled"
            ).count()
            component = ROLE_TO_COMPONENT.get(role)
            rows.append(
                {
                    "pathway_key": pathway["key"],
                    "label": pathway["label"],
                    "staffing": staffing,
                    "active_opt_in_count": active_opt_in_count,
                    "provider_assignment_model": "Opt-in only",
                    "data_access": f"Authorized {component} context only" if component else None,
                }
            )
        return {"pathways": rows}
