"""Admin user-management service (DOCX Admin Panel: "Assign roles, coaches,
specialists, teams, units, reporting groups, and support pathways.").

Every role change and manual provider assignment is audit logged -
previously nothing in this backend recorded role changes at all.

`change_role` is the one place the Admin/Superadmin split is actually
enforced: promoting a user to an admin-level role, or demoting a user who
currently holds one, requires the caller to be `ROLE_SUPERADMIN`
specifically - a plain Admin gets 403. Every other role change (Airman /
SCS / PT-IM / specialist / Leadership / IDMT) stays available to both, same
as before this pass.

Admin-level role changes additionally go through the second-reviewer
confirmation queue (`AdminConfirmationService`) instead of applying
immediately - see `app/models/pending_confirmation.py` for why. The
Superadmin-only check below decides who may *request* the change; a
different Admin/Superadmin must then approve it before it takes effect.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from app.core.roles import ADMIN_ROLES, ROLE_SUPERADMIN, SUPPORTED_ROLES, normalize_role
from app.core.security import get_password_hash, utc_now
from app.core.support_pathways import get_support_pathway
from app.services.auth_service import ACCESS_EXPIRY_DAYS
from app.models.audit_log import AuditLog
from app.models.team_assignment import TeamAssignment
from app.models.user import User
from app.schemas.admin_user import (
    AdminCreateUserRequest,
    ProviderAssignRequest,
    RoleChangeRequest,
    UnitAssignRequest,
)
from app.services.admin_confirmation_service import AdminConfirmationService
from app.services.audit_log_service import AuditLogService
from app.services.email_service import EmailService

STATUS_ENABLED = "enabled"
STATUS_LOCKED_ON = "locked_on"
# Not DOCX-sourced (a Figma "System" screen's "Deactivation grace: 14 days,
# applies to: Inactive accounts" claim triggered this) - a real inactivity
# surface, not a confirmation-expiry rule (the screen's own "applies to"
# column says accounts, not pending deactivations).
INACTIVITY_GRACE_DAYS = 14

# The audit event types that represent a real change to an account, backing
# the Roles & RBAC "Last edit" column. Deliberately excludes `login_success`
# and `login_failed` - those target a user but are activity, not an edit.
ACCOUNT_EDIT_EVENT_TYPES: tuple[str, ...] = (
    "user_provisioned",
    "role_changed",
    "role_change_requested",
    "unit_assigned",
    "access_renewed",
    "admin_password_reset",
    "password_changed",
    "admin_deactivation_requested",
)


class AdminUserService:
    """List users and manage role/unit/provider assignments."""

    def __init__(self) -> None:
        self.audit_log_service = AuditLogService()
        self.admin_confirmation_service = AdminConfirmationService()
        self.email_service = EmailService()

    async def list_users(self, role_filter: str | None = None) -> dict[str, Any]:
        """Return every user, optionally filtered by role, with a real last-edit timestamp."""
        if role_filter:
            users = await User.find(User.role == normalize_role(role_filter)).to_list()
        else:
            users = await User.find().to_list()
        users.sort(key=lambda item: item.email)
        last_edits = await self._get_last_edit_map()
        return {
            "users": [
                {**self._serialize(u), "last_edit_at": last_edits.get(str(u.id))} for u in users
            ]
        }

    async def _get_last_edit_map(self) -> dict[str, str]:
        """Return `{user_id: ISO timestamp}` of each account's most recent real edit.

        Deliberately derived from the audit log rather than `User.updated_at`.
        `updated_at` is bumped by *any* save of the document - including an
        ordinary login (`AuthService.login_user`), a daily check-in, and
        onboarding progress - so an admin-facing "Last edit" column built on
        it would move every time the person merely used the app, which is not
        what that column means. The audit log records exactly the account
        mutations (see `ACCOUNT_EDIT_EVENT_TYPES`), which is the real answer,
        and matches the Roles & RBAC screen's own stated policy that every
        modification writes to the control-plane log.

        One grouped query rather than one per user - `AuditLog` already has an
        index on `(target_entity_type, target_entity_id)`. Dict-style query
        because this codebase's Beanie version can't combine `(A) & (B)`
        conditions (documented in `docs/E2E_TEST_STATUS.md`).
        """
        entries = await AuditLog.find(
            {
                "target_entity_type": "user",
                "event_type": {"$in": list(ACCOUNT_EDIT_EVENT_TYPES)},
            }
        ).to_list()
        latest: dict[str, datetime] = {}
        for entry in entries:
            current = latest.get(entry.target_entity_id)
            if current is None or entry.created_at > current:
                latest[entry.target_entity_id] = entry.created_at
        return {user_id: stamp.isoformat() for user_id, stamp in latest.items()}

    async def list_inactive_accounts(self, grace_days: int = INACTIVITY_GRACE_DAYS) -> list[dict[str, Any]]:
        """Return real active accounts that have gone quiet for at least `grace_days`.

        Not DOCX-sourced (see `INACTIVITY_GRACE_DAYS`). An account with a
        real `last_login_at` older than the cutoff, or one that has never
        logged in but was activated before the cutoff, both count - a
        brand-new account (activated within the grace window) never does,
        even if it hasn't logged in yet. Filtered in Python, not `==`/`<=`
        in the query - this project's established Beanie boolean/`None`
        query-gotcha precedent (see `TeamService._find_active_provider`).
        """
        cutoff = utc_now() - timedelta(days=grace_days)
        all_users = await User.find().to_list()
        inactive = []
        for user in all_users:
            if not user.is_active:
                continue
            if user.last_login_at is not None:
                if user.last_login_at <= cutoff:
                    inactive.append(user)
            elif user.activation_date is not None and user.activation_date <= cutoff:
                inactive.append(user)
        return [self._serialize(u) for u in inactive]

    async def create_user(self, admin: User, payload: AdminCreateUserRequest) -> dict[str, Any]:
        """Admin directly provisions a new account (DOCX 2A Step 1). Audit logged.

        Mirrors `change_role`'s Superadmin-only gate for admin-level roles,
        but skips the confirmation-queue detour that gates an existing
        account's role change - a brand-new account has no prior state to
        revert via `snapshot_before`, so a mistaken creation is corrected by
        deactivating it (`deactivate`, already real), not reverting it.

        The generated/chosen `initial_password` is returned once in the
        response (deliberately different from `reset_password`'s
        email-only pattern - a real, explicit user decision scoped to
        initial provisioning, matching the frontend's visible/copyable/
        regeneratable password field) and is never written to the audit
        log.
        """
        new_role = normalize_role(payload.role)
        if new_role not in SUPPORTED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unsupported role.", "allowed": list(SUPPORTED_ROLES)},
            )
        if new_role in ADMIN_ROLES and admin.role != ROLE_SUPERADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a Superadmin can provision an admin-level account.",
            )

        existing = await User.find_one({"email": payload.email.lower()})
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )

        initial_password = payload.initial_password or secrets.token_urlsafe(9)
        user = User(
            email=payload.email.lower(),
            full_name=payload.full_name,
            role=new_role,
            unit_id=payload.unit_id,
            is_active=payload.is_active,
            hashed_password=get_password_hash(initial_password),
            is_verified=True,
            activation_date=utc_now(),
            access_expires_at=utc_now() + timedelta(days=ACCESS_EXPIRY_DAYS),
        )
        await user.insert()

        await self.audit_log_service.record(
            event_type="user_provisioned",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(user.id),
            summary_message=f"Admin provisioned a new {new_role} account for {user.email}.",
            # `role` here is what makes this event countable as a real edit
            # to that role's own history (see `RoleAdminService.get_catalog`'s
            # `last_edit`) - a role granted at creation is just as real an
            # edit to the role as one granted later via `change_role`.
            metadata_payload={"role": new_role},
        )
        return {**self._serialize(user), "initial_password": initial_password}

    async def change_role(self, admin: User, user_id: str, payload: RoleChangeRequest) -> dict[str, Any]:
        """Admin changes a user's role. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        new_role = normalize_role(payload.role)
        if new_role not in SUPPORTED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": "Unsupported role.", "allowed": list(SUPPORTED_ROLES)},
            )

        old_role = target.role
        touches_admin_level = new_role in ADMIN_ROLES or old_role in ADMIN_ROLES
        if touches_admin_level and admin.role != ROLE_SUPERADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only a Superadmin can grant or remove an admin-level role.",
            )

        if touches_admin_level:
            confirmation = await self.admin_confirmation_service.request_role_change(
                admin, target, old_role, new_role
            )
            return {
                "status": "pending_approval",
                "confirmation_id": str(confirmation.id),
                "target_summary": confirmation.target_summary,
                "consequence_summary": confirmation.consequence_summary,
            }

        target.role = new_role
        target.updated_at = utc_now()
        await target.save()

        await self.audit_log_service.record(
            event_type="role_changed",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Role changed from {old_role} to {new_role}.",
            metadata_payload={"old_role": old_role, "new_role": new_role},
        )
        return self._serialize(target)

    async def renew_access(self, admin: User, user_id: str) -> dict[str, Any]:
        """Admin manually extends a user's `access_expires_at` by `ACCESS_EXPIRY_DAYS`. Audit logged.

        Not DOCX-sourced (see `app/models/user.py`) - a real, manually-
        triggered action, not silent automatic renewal.
        """
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        previous_expiry = target.access_expires_at
        target.access_expires_at = utc_now() + timedelta(days=ACCESS_EXPIRY_DAYS)
        target.updated_at = utc_now()
        await target.save()

        await self.audit_log_service.record(
            event_type="access_renewed",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Access renewed for {target.email}.",
            metadata_payload={
                "previous_expiry": previous_expiry.isoformat() if previous_expiry else None,
                "new_expiry": target.access_expires_at.isoformat(),
            },
        )
        return self._serialize(target)

    async def reset_password(self, admin: User, user_id: str) -> dict[str, Any]:
        """Admin generates a real temp password and emails it to the user.

        Not DOCX-sourced - the `ascend-admin` frontend mock shows the temp
        password directly to the admin; here it's deliberately never
        returned in the response or written to the audit log - only
        emailed, via the real `EmailService.send()` (Resend) built earlier
        this session, matching the "no fabricated success" pattern already
        used for `SmsService`/`PushService` (honest `False` if unconfigured,
        never a silently skipped or fake-success delivery). Ungated - no
        caseload-reassignment consequence like a `deactivation`, and
        immediately self-correctable by the user via the normal
        forgot-password flow, unlike an admin-level `change_role`.
        """
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        temp_password = secrets.token_urlsafe(9)
        target.hashed_password = get_password_hash(temp_password)
        target.updated_at = utc_now()
        await target.save()

        await self.audit_log_service.record(
            event_type="admin_password_reset",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Admin reset password for {target.email}.",
        )

        emailed = await self.email_service.send(
            target.email,
            "Your Ascend password has been reset",
            f"<p>An administrator reset your password. Your temporary password is: <b>{temp_password}</b></p>"
            "<p>Sign in and change it as soon as possible.</p>",
        )
        return {**self._serialize(target), "emailed": emailed}

    async def assign_unit(self, admin: User, user_id: str, payload: UnitAssignRequest) -> dict[str, Any]:
        """Admin assigns a user to a unit. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        old_unit = target.unit_id
        target.unit_id = payload.unit_id
        target.updated_at = utc_now()
        await target.save()

        await self.audit_log_service.record(
            event_type="unit_assigned",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="user",
            target_entity_id=str(target.id),
            summary_message=f"Unit changed from {old_unit or '(none)'} to {payload.unit_id or '(none)'}.",
            metadata_payload={"old_unit_id": old_unit, "new_unit_id": payload.unit_id},
        )
        return self._serialize(target)

    async def assign_provider(
        self, admin: User, user_id: str, payload: ProviderAssignRequest
    ) -> dict[str, Any]:
        """Admin manually assigns/overrides a pathway's provider for a user. Audit logged."""
        target = await User.get(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        pathway = get_support_pathway(payload.pathway_key)
        if pathway is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown pathway.")
        provider = await User.get(payload.provider_user_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found.")

        assignment = await TeamAssignment.find_one(
            TeamAssignment.user_id == target.id, TeamAssignment.pathway_key == payload.pathway_key
        )
        previous_provider_id = assignment.provider_user_id if assignment else None
        if assignment is None:
            assignment = TeamAssignment(
                user_id=target.id,
                pathway_key=payload.pathway_key,
                status=STATUS_LOCKED_ON if pathway["always_available"] else STATUS_ENABLED,
            )
        assignment.provider_user_id = provider.id
        assignment.updated_at = utc_now()
        await assignment.save()

        await self.audit_log_service.record(
            event_type="provider_assigned",
            actor_id=admin.id,
            actor_role=admin.role,
            target_entity_type="team_assignment",
            target_entity_id=str(assignment.id),
            summary_message=f"{pathway['label']} provider manually assigned to {provider.full_name}.",
            metadata_payload={
                "pathway_key": payload.pathway_key,
                "previous_provider_id": str(previous_provider_id) if previous_provider_id else None,
                "new_provider_id": str(provider.id),
            },
        )
        return {
            "pathway_key": payload.pathway_key,
            "provider": {"user_id": str(provider.id), "name": provider.full_name},
        }

    def _serialize(self, user: User) -> dict[str, Any]:
        """Convert a user to the Admin user-list transport-safe dict."""
        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "unit_id": user.unit_id,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "access_expires_at": user.access_expires_at.isoformat() if user.access_expires_at else None,
            # A real fallback for the "Last edit" column on an account that
            # has genuinely never been edited (self-registered, never touched
            # by an admin) - `last_edit_at` is null there rather than being
            # backfilled with something invented.
            "created_at": user.created_at.isoformat(),
        }
