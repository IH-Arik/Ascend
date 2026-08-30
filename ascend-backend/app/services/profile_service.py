"""User profile aggregation service.

Identity is self-reported at registration (email/password) - this project
has no CAC/PKI integration, so unlike a CAC-sourced identity model, `role`,
`full_name`, and `unit_id` are admin/provisioning-set fields (per the DOCX's
admin-led account creation), and `rank_grade` is a user-editable, optional,
self-reported field rather than something read from a smart card. There is
no EDIPI (CAC-issued military ID number) equivalent - nothing here can
source or verify one, so it is not fabricated or displayed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status

from app.core.scoring import get_band_meaning
from app.core.security import utc_now
from app.models.onboarding_answer import OnboardingAnswer
from app.models.user import User
from app.schemas.profile import (
    AVATAR_ALLOWED_EXTENSIONS,
    AVATAR_CONTENT_TYPES,
    AVATAR_MAX_BYTES,
    ProfileResponse,
    UpdateProfileSettingsRequest,
)
from app.services.audit_log_service import AuditLogService
from app.services.file_storage_service import FileStorageService, scan_file_stub
from app.services.team_service import TeamService

SUPPORT_PATHWAYS_QUESTION_ID = 18


class ProfileService:
    """Build the aggregated Profile screen payload."""

    def __init__(self) -> None:
        self.team_service = TeamService()
        self.audit_log_service = AuditLogService()
        self.file_storage_service = FileStorageService(namespace="avatars")

    async def get_profile(self, user: User) -> dict[str, Any]:
        """Return the authenticated user's profile summary."""
        support_pathways = await self._get_support_pathways(user)
        assigned_scs, assigned_ptim = await self._get_assigned_providers(user)
        payload = ProfileResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            unit_id=user.unit_id,
            rank_grade=user.rank_grade,
            avatar_url=self._avatar_url(user.id) if user.avatar_storage_path is not None else None,
            is_verified=user.is_verified,
            onboarding_completed=user.onboarding_completed,
            onboarding_status=user.onboarding_status,
            day0_daily_checkin_status=user.day0_daily_checkin_status,
            current_ops_score=user.current_ops_score,
            current_ops_band=user.current_ops_band,
            current_ops_band_meaning=get_band_meaning(user.current_ops_band or "Unavailable"),
            ops_confidence_level=user.ops_confidence_level,
            onboarding_baseline_ops_score=user.onboarding_baseline_ops_score,
            onboarding_baseline_band=user.onboarding_baseline_band,
            support_pathways_opted_in=support_pathways,
            assigned_scs=assigned_scs,
            assigned_ptim=assigned_ptim,
            communications_preference="Regular" if user.wellness_recommendations_opt_in else "Limited",
            theme_preference=user.theme_preference,
            notifications_enabled=user.notifications_enabled,
            data_use_consent=user.data_use_consent,
            wellness_recommendations_opt_in=user.wellness_recommendations_opt_in,
            policy_version_accepted=user.policy_version_accepted,
            policy_acknowledged_at=user.policy_acknowledged_at,
            sign_in_activation={
                "is_verified": user.is_verified,
                "member_since": user.created_at,
                "last_login_at": user.last_login_at,
            },
            member_since=user.created_at,
        )
        return payload.model_dump(mode="json")

    async def update_settings(
        self, user: User, payload: UpdateProfileSettingsRequest
    ) -> dict[str, Any]:
        """Update the locally controllable profile settings (name, rank/grade, theme, notifications)."""
        if payload.full_name is not None:
            stripped_name = payload.full_name.strip()
            if not stripped_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Full name cannot be empty.",
                )
            user.full_name = stripped_name
        if payload.rank_grade is not None:
            user.rank_grade = payload.rank_grade.strip() or None
        if payload.theme_preference is not None:
            user.theme_preference = payload.theme_preference
        if payload.notifications_enabled is not None:
            user.notifications_enabled = payload.notifications_enabled
        user.updated_at = utc_now()
        await user.save()
        return await self.get_profile(user)

    async def upload_avatar(self, user: User, file: UploadFile) -> dict[str, Any]:
        """Upload/replace the user's own profile photo. Real image types only, 5 MB cap."""
        file_name = file.filename or "avatar"
        extension = Path(file_name).suffix.lower()
        if extension not in AVATAR_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Avatar must be a JPG, PNG, or HEIC image.",
            )
        if not scan_file_stub(file_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This file type is not allowed.",
            )

        content = await file.read()
        if len(content) > AVATAR_MAX_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Avatar exceeds the {AVATAR_MAX_BYTES // (1024 * 1024)} MB limit.",
            )

        storage_path = self.file_storage_service.save_file(str(user.id), file_name, content)
        user.avatar_storage_path = storage_path
        user.avatar_file_name = file_name
        user.avatar_content_type = AVATAR_CONTENT_TYPES[extension]
        user.avatar_uploaded_at = utc_now()
        user.updated_at = utc_now()
        await user.save()

        await self.audit_log_service.record(
            event_type="avatar_updated",
            actor_id=user.id,
            actor_role=user.role,
            target_entity_type="user",
            target_entity_id=str(user.id),
            summary_message="User updated their profile photo.",
        )
        return await self.get_profile(user)

    async def delete_avatar(self, user: User) -> dict[str, Any]:
        """Remove the user's own profile photo, if any."""
        if user.avatar_storage_path is not None:
            user.avatar_storage_path = None
            user.avatar_file_name = None
            user.avatar_content_type = None
            user.avatar_uploaded_at = None
            user.updated_at = utc_now()
            await user.save()
            await self.audit_log_service.record(
                event_type="avatar_removed",
                actor_id=user.id,
                actor_role=user.role,
                target_entity_type="user",
                target_entity_id=str(user.id),
                summary_message="User removed their profile photo.",
            )
        return await self.get_profile(user)

    async def get_avatar_bytes(self, target: User) -> tuple[bytes, str]:
        """Return the raw decrypted avatar bytes and content-type for a user."""
        if target.avatar_storage_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This user has no profile photo set.",
            )
        content = self.file_storage_service.read_file(target.avatar_storage_path)
        return content, target.avatar_content_type or "application/octet-stream"

    @staticmethod
    def _avatar_url(user_id: Any) -> str:
        """Return the real, public, direct image URL for a user's avatar.

        Path-only (no host) so the client's own base URL is what resolves
        it - this backend doesn't know its own externally-visible URL
        (e.g. behind an ngrok tunnel), so it must never hardcode one.
        """
        return f"/users/{user_id}/avatar"

    async def _get_support_pathways(self, user: User) -> list[str]:
        """Return the support pathways the user opted into during onboarding."""
        answer = await OnboardingAnswer.find_one(
            OnboardingAnswer.user_id == user.id,
            OnboardingAnswer.question_id == SUPPORT_PATHWAYS_QUESTION_ID,
        )
        if answer is None or not isinstance(answer.follow_up_answer, list):
            return []
        return answer.follow_up_answer

    async def _get_assigned_providers(
        self, user: User
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Return the (SCS, PT/IM) providers currently assigned via My Support Team."""
        team = await self.team_service.get_my_team(user)
        assigned_scs = None
        assigned_ptim = None
        for pathway in team["pathways"]:
            provider = pathway["provider"]
            if provider is None:
                continue
            # team_service returns {user_id, name} only - always attach the
            # URL by user_id rather than an extra lookup to check whether
            # this specific provider has actually uploaded a photo yet; a
            # provider with no avatar 404s on this URL like any other user,
            # same as a broken <img> - client-side fallback handles it.
            enriched = {**provider, "avatar_url": self._avatar_url(provider["user_id"])}
            if pathway["pathway_key"] == "SCS":
                assigned_scs = enriched
            elif pathway["pathway_key"] == "PT/IM":
                assigned_ptim = enriched
        return assigned_scs, assigned_ptim
