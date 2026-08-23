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
2 rows dropped at that time ("Send IDMT handoff", "View Authorized
Performance Summary") since neither corresponded to any real, implemented
endpoint - keeping a fabricated-looking row for a feature that doesn't
exist would be the same mistake again.

Both rows are now restored (2026-08-23), because both features have since
been genuinely built and that exclusion had gone stale: the IDMT handoff
lifecycle landed 2026-08-13 (`IdmtHandoffService`), and the Medical History
Performance Summary - a fully DOCX-specified entity (its own data-dictionary
row and a per-role visibility row in Table 23) that had simply never been
implemented - was built alongside this change
(`app/services/performance_summary_service.py`). That also introduced the
matrix's fourth real cell state, `conditional`, for a role that genuinely
reaches a capability but receives a deliberately minimum-necessary subset
rather than all-or-nothing.

IMPORTANT - the matrix is now a DECLARED POLICY view, not a reflection of
runtime enforcement (2026-08-23). `DECLARED_MATRIX` is transcribed
cell-for-cell from the Roles & RBAC design and is what `matrix` returns.
The product owner chose this explicitly after being shown the full list of
cells where the design disagrees with what the code actually permits - for
example the design shows Operator as unable to view their own dashboard
(the real route has no role gate at all) and SCS as conditionally able to
view aggregate trends (the real route would 403 them). Rather than silently
serving either version as "the truth", `get_matrix` returns all three:
`matrix` (declared, for display), `enforced` (what each capability's real
route gate produces, computed by `_enforced_cell`), and `divergences` (the
explicit list of disagreements). Anything making an actual access decision
must use the real route gates, never this matrix.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.core.question_registry import COMPONENT_ROUTING
from app.core.roles import (
    ADMIN_ROLES,
    ROLE_AIRMAN,
    ROLE_CLUSTER,
    ROLE_LEADERSHIP,
    ROLE_PTIM,
    ROLE_SCOPE,
    ROLE_SCS,
    ROLE_CHAPLAIN,
    ROLE_IDMT,
    SPECIALIST_ROLES,
    SUPPORTED_ROLES,
)
from app.core.security import utc_now
from app.core.support_pathways import get_support_pathways
from app.models.audit_log import AuditLog
from app.models.pending_confirmation import PendingConfirmation
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
    # POST /admin/idmt-handoffs' real require_roles(*ADMIN_ROLES, ROLE_PTIM),
    # plus IDMT's own acknowledge/download access. Previously dropped from
    # this matrix as "no real, implemented endpoint" - that was true when
    # written and is no longer: `IdmtHandoffService` and the full
    # prepare/approve/transmit/acknowledge lifecycle were built 2026-08-13.
    "Send IDMT handoff": (*ADMIN_ROLES, ROLE_PTIM, ROLE_IDMT),
    # GET /performance-summaries/{user_id}'s real access. Every role with a
    # DOCX Table 23 cell can reach the entity; what differs is how much of
    # it they receive, which is what `CONDITIONAL_CELLS` below expresses.
    "View Authorized Performance Summary": (
        *ADMIN_ROLES,
        ROLE_PTIM,
        ROLE_SCS,
        *SPECIALIST_ROLES,
        ROLE_LEADERSHIP,
    ),
}

# Real: matches `AdminUserService`/`AdminConfirmationService`'s second-
# reviewer requirement for deactivating a provider/admin-level account.
GATED_CELLS: set[tuple[str, str]] = {(role, "Deactivate user") for role in ADMIN_ROLES}
# The IDMT handoff itself is second-reviewer gated before it can be
# transmitted (`AdminConfirmationService`), so the preparing roles are
# "gated", not "full".
GATED_CELLS |= {(role, "Send IDMT handoff") for role in (*ADMIN_ROLES, ROLE_PTIM)}

# Real "conditional (reason required / minimum-necessary)" cells - a role
# genuinely reaches the capability but receives a deliberately reduced view,
# rather than all-or-nothing. Derived from each role's real DOCX Table 23
# cell as encoded in `PerformanceSummaryService.ROLE_VISIBLE_FIELDS`: PT/IM
# is the authoring clinical role ("Yes", full), Admin is "Metadata; content
# only if approved", and every other role gets a strict subset.
CONDITIONAL_CELLS: set[tuple[str, str]] = {
    (role, "View Authorized Performance Summary")
    for role in (ROLE_SCS, *SPECIALIST_ROLES, ROLE_LEADERSHIP, *ADMIN_ROLES)
}

# The screen's 10 display columns. `role` maps a column to the real
# `SUPPORTED_ROLES` value it represents; `None` means the column is
# display-only with no backing role - see `Plan` below. ADMIN covers both
# real admin-level roles, which the screen does not separate.
MATRIX_COLUMNS: list[dict[str, Any]] = [
    {"key": "OPERATOR", "label": "Operator", "role": "Airman"},
    {"key": "SCS", "label": "SCS", "role": ROLE_SCS},
    {"key": "PT/IM", "label": "PT/IM", "role": ROLE_PTIM},
    {"key": "MP", "label": "Mental Performance", "role": "Mental Performance"},
    {"key": "NUTR", "label": "Nutritionist", "role": "Nutritionist"},
    {"key": "PURPOSE", "label": "Purpose Coach", "role": ROLE_CHAPLAIN},
    # Display-only. `Plan` is deliberately NOT in `SUPPORTED_ROLES` - that
    # tuple drives real auth (`require_roles`, registration validation, the
    # People directory's role list), so adding a role with no permissions,
    # no dashboard, and no DOCX requirement would be a real system change,
    # not a display one. Twice-confirmed skip decision (2026-08-09,
    # 2026-08-13). The column renders; nothing can hold the role.
    {"key": "PLAN", "label": "Plan", "role": None},
    {"key": "LEAD", "label": "Leadership", "role": ROLE_LEADERSHIP},
    {"key": "ADMIN", "label": "Admin", "role": "DWS Admin"},
    {"key": "IDMT", "label": "IDMT", "role": ROLE_IDMT},
]

_F, _C, _G, _N = "full", "conditional", "gated", "none"

# The policy matrix exactly as the Roles & RBAC screen declares it,
# transcribed cell-for-cell from the design. Explicitly chosen by the
# product owner over the enforcement-derived version after being shown the
# full divergence list - see this module's docstring. `get_matrix` returns
# the real enforced value alongside each row so the two never get confused.
DECLARED_MATRIX: dict[str, dict[str, str]] = {
    #                                     OPER  SCS  PT/IM  MP   NUTR PURP PLAN LEAD ADMIN IDMT
    "View own dashboard":                 dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _F,  _F,  _F,  _F,  _F,  _F,  _F,  _F,  _N])),
    "View caseload records":              dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _F,  _G,  _G,  _G,  _G,  _N,  _N,  _F,  _G])),
    "View Authorized Performance Summary": dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _C,  _G,  _C,  _N,  _N,  _N,  _N,  _F,  _C])),
    "Send message":                       dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_F,  _F,  _F,  _F,  _F,  _F,  _F,  _N,  _F,  _G])),
    "Send IDMT handoff":                  dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _N,  _G,  _G,  _N,  _N,  _N,  _N,  _F,  _G])),
    "Author plan":                        dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _F,  _F,  _F,  _F,  _F,  _F,  _N,  _F,  _N])),
    "View aggregate trend":               dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _C,  _C,  _C,  _C,  _C,  _F,  _F,  _F,  _N])),
    "Run export":                         dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _N,  _N,  _N,  _N,  _N,  _G,  _G,  _F,  _N])),
    "Deactivate user":                    dict(zip(
        [c["key"] for c in MATRIX_COLUMNS],
        [_N,  _N,  _N,  _N,  _N,  _N,  _N,  _N,  _G,  _N])),
}


class RoleAdminService:
    """Build the real role catalog, RBAC matrix, and purpose-consent summary."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.org_unit_service = OrgUnitService()

    async def get_catalog(self) -> dict[str, Any]:
        """One row per real role: cluster/scope metadata + real member/audit counts."""
        # Two real event types grant a role: `role_changed` (an existing
        # account moved into it) and `user_provisioned` (a brand-new account
        # created with it directly, via POST /admin/users). Missing the
        # second meant a role's `last_edit` stayed frozen forever if every
        # member of it had only ever been provisioned, never switched -
        # caught live: provisioning a new IDMT account correctly moved
        # member_count 3 -> 4 but silently left last_edit unchanged.
        role_grant_events = await AuditLog.find(
            {"event_type": {"$in": ["role_changed", "user_provisioned"]}}
        ).to_list()

        rows = []
        for role in SUPPORTED_ROLES:
            member_count = await User.find(User.role == role).count()
            audit_entry_count = await AuditLog.find(AuditLog.actor_role == role).count()

            matching_events = [
                e
                for e in role_grant_events
                if e.metadata_payload.get("new_role") == role
                or e.metadata_payload.get("role") == role
            ]
            matching_events.sort(key=lambda e: e.created_at, reverse=True)
            last_edit = matching_events[0].created_at.isoformat() if matching_events else None

            rows.append(
                {
                    "role": role,
                    "cluster": ROLE_CLUSTER.get(role),
                    "scope": ROLE_SCOPE.get(role),
                    "member_count": member_count,
                    "last_edit": last_edit,
                    "audit_entry_count": audit_entry_count,
                    "is_real_role": True,
                }
            )

        # The screen lists a `Plan` row. It is deliberately not a real role -
        # see `MATRIX_COLUMNS` - so it renders with honest zeros and an
        # explicit `is_real_role: False` rather than being omitted (which
        # would not match the design) or faked with invented counts.
        rows.append(
            {
                "role": "Plan",
                "cluster": "Contractor",
                "scope": "Flight",
                "member_count": 0,
                "last_edit": None,
                "audit_entry_count": 0,
                "is_real_role": False,
            }
        )

        return {
            "role_count": len(SUPPORTED_ROLES),
            "roles": rows,
            "purpose_consent": await self._purpose_consent_summary(),
        }

    async def get_accounts_and_onboarding_summary(self) -> dict[str, Any]:
        """The Roles & RBAC screen's "Accounts & onboarding" card (6 metrics).

        Not DOCX-sourced (a Figma screenshot triggered this). Every metric
        below is real data with two deliberate corrections:

        1. The mock's Access Expiration panel reads "All scopes renew
           automatically on annual review", but `app/models/user.py`
           already documents that `access_expires_at` is "not auto-renewed
           by any background process" - renewal is a manual Admin action
           (`POST /admin/users/{id}/renew-access`). Product owner chose
           (2026-08-23) to keep this panel honest: real counts plus an
           explicit `renewal_note` stating renewal is manual.
        2. Onboarding is scoped to `ROLE_AIRMAN` only, not every account.
           `ROLE_PERMISSIONS` (`app/core/roles.py`) grants
           `complete_onboarding` exclusively to Airman, and the onboarding
           routes are never called by any other role - a staff/admin
           account's `onboarding_status` sits at its model default
           ("incomplete") forever, not because onboarding is stuck, but
           because the concept never applies to them. Counting every role
           would have inflated "in flight" with accounts that were never
           onboarding in the first place (caught live: 116/117 accounts
           counted before this fix, because ~55 of them are staff/admin).
        """
        users = await User.find_all().to_list()

        active_count = sum(1 for u in users if u.is_active)
        access_expiration = self._access_expiration_summary(users)

        onboarding_in_flight_count = sum(
            1 for u in users if u.role == ROLE_AIRMAN and u.onboarding_status != "completed"
        )
        awaiting_role_confirmation_count = await PendingConfirmation.find(
            PendingConfirmation.action_type == "role_change",
            PendingConfirmation.status == "pending",
        ).count()

        assigned_provider_pathways = [
            p["key"] for p in get_support_pathways() if p["always_available"]
        ]

        return {
            "account_status": {
                "active_count": active_count,
                "expired_count": access_expiration["expired_count"],
                "total_count": len(users),
            },
            "onboarding": {
                "in_flight_count": onboarding_in_flight_count,
                "awaiting_role_confirmation_count": awaiting_role_confirmation_count,
            },
            "access_expiration": {
                **access_expiration,
                "renewal_note": (
                    "Requires manual renewal via Admin "
                    "(POST /admin/users/{id}/renew-access) - not automatic."
                ),
            },
            "assigned_providers": {
                "always_available_pathways": assigned_provider_pathways,
            },
            "effective_permissions": {
                "note": "See GET /roles/matrix for the full role x capability RBAC matrix.",
            },
            "purpose_consent": await self._purpose_consent_summary(),
        }

    def _access_expiration_summary(self, users: list[User], expiring_soon_days: int = 30) -> dict[str, Any]:
        """Real `User.access_expires_at` counts - not DOCX-sourced (see `app/models/user.py`).

        Shared by `get_accounts_and_onboarding_summary` and the System
        overview dashboard (`ProviderDashboardService._access_expiration_summary`,
        an independent copy with the same logic - not imported from here to
        avoid a cross-service dependency for one small helper).
        """
        soon_cutoff = utc_now() + timedelta(days=expiring_soon_days)
        with_expiry = [u for u in users if u.access_expires_at is not None]
        expired_count = sum(1 for u in with_expiry if u.access_expires_at < utc_now())
        expiring_soon_count = sum(
            1 for u in with_expiry if utc_now() <= u.access_expires_at <= soon_cutoff
        )
        return {"expiring_soon_30d_count": expiring_soon_count, "expired_count": expired_count}

    async def get_matrix(self) -> dict[str, Any]:
        """The Roles & RBAC screen's declared policy matrix (9 rows x 10 columns).

        Returns `DECLARED_MATRIX` - the intended policy as shown on the
        screen - alongside `enforced`, the cell each row's real route gate
        would actually produce, and `divergences`, the explicit list of
        cells where the two disagree. `matrix` is the display source; the
        other two exist so the difference is inspectable rather than hidden.
        """
        matrix: list[dict[str, Any]] = []
        divergences: list[dict[str, str]] = []

        for capability in DECLARED_MATRIX:
            declared = DECLARED_MATRIX[capability]
            enforced: dict[str, str] = {}

            for column in MATRIX_COLUMNS:
                key = column["key"]
                role = column["role"]
                enforced[key] = (
                    "unenforced" if role is None else self._enforced_cell(capability, role)
                )
                if enforced[key] != declared[key]:
                    divergences.append(
                        {
                            "capability": capability,
                            "column": key,
                            "declared": declared[key],
                            "enforced": enforced[key],
                        }
                    )

            matrix.append(
                {"capability": capability, "roles": dict(declared), "enforced": enforced}
            )

        return {
            "roles": [c["key"] for c in MATRIX_COLUMNS],
            "columns": MATRIX_COLUMNS,
            "matrix": matrix,
            "divergences": divergences,
            "divergence_count": len(divergences),
        }

    def _enforced_cell(self, capability: str, role: str) -> str:
        """What this capability's real route gate actually permits for `role`."""
        if (role, capability) in GATED_CELLS:
            return "gated"
        if (role, capability) in CONDITIONAL_CELLS:
            return "conditional"
        allowed_roles = CAPABILITY_ROLE_GATES.get(capability)
        if allowed_roles is None or role in allowed_roles:
            return "full"
        return "none"

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
