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

from typing import Any

from app.core.scoring import get_band_meaning
from app.models.onboarding_answer import OnboardingAnswer
from app.models.user import User
from app.schemas.profile import ProfileResponse, UpdateProfileSettingsRequest
from app.services.team_service import TeamService

SUPPORT_PATHWAYS_QUESTION_ID = 18


class ProfileService:
    """Build the aggregated Profile screen payload."""

    def __init__(self) -> None:
        self.team_service = TeamService()

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
        """Update the locally controllable profile settings (rank/grade, theme, notifications)."""
        if payload.rank_grade is not None:
            user.rank_grade = payload.rank_grade.strip() or None
        if payload.theme_preference is not None:
            user.theme_preference = payload.theme_preference
        if payload.notifications_enabled is not None:
            user.notifications_enabled = payload.notifications_enabled
        await user.save()
        return await self.get_profile(user)

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
            if pathway["pathway_key"] == "SCS" and pathway["provider"]:
                assigned_scs = pathway["provider"]
            elif pathway["pathway_key"] == "PT/IM" and pathway["provider"]:
                assigned_ptim = pathway["provider"]
        return assigned_scs, assigned_ptim
