"""Account summary and account lifecycle service."""

from typing import Any

from fastapi import HTTPException, status

from app.db.repositories.profile_repo import ProfileRepository
from app.db.repositories.assessment_repo import AssessmentRepository
from app.db.repositories.daily_checkin_repo import DailyCheckInRepository
from app.db.repositories.monthly_checkin_repo import MonthlyCheckInRepository
from app.db.repositories.score_repo import ScoreRepository
from app.db.repositories.user_repo import UserRepository
from app.db.repositories.support_request_repo import SupportRequestRepository
from app.db.repositories.weekly_checkin_repo import WeeklyCheckInRepository
from app.db.repositories.app_setting_repo import AppSettingRepository
from app.db.repositories.faq_repo import FAQRepository
from app.models.user import User
from app.utils.constants import APP_VERSION, ORGANIZATION_METADATA
from app.utils.response import error_response


class AccountService:
    """Service for account screen aggregation and account actions."""

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.profile_repository = ProfileRepository()
        self.assessment_repository = AssessmentRepository()
        self.daily_checkin_repository = DailyCheckInRepository()
        self.weekly_checkin_repository = WeeklyCheckInRepository()
        self.monthly_checkin_repository = MonthlyCheckInRepository()
        self.score_repository = ScoreRepository()
        self.user_repository = UserRepository()
        self.support_request_repository = SupportRequestRepository()
        self.app_setting_repository = AppSettingRepository()
        self.faq_repository = FAQRepository()
        self.dimension_labels = {
            "PC": "Physical Capacity",
            "MR": "Mental Resilience",
            "MC": "Morale & Cohesion",
            "PA": "Purpose Alignment",
            "RC": "Recovery Capacity",
        }
        self.legal_items = [
            "Dominion Wellness Solutions is designed to support wellness awareness and performance improvement.",
            "The platform is not intended to provide clinical diagnosis, treatment, or emergency support.",
            "Users are responsible for reviewing generated insights as guidance rather than medical direction.",
            "Your assessment and account information are processed to improve personalized recommendations.",
            "Use of the platform implies agreement with the current policies and acceptable use standards.",
        ]
        self.faqs = [
            {
                "question": "What is OPS Score?",
                "answer": "Your overall performance score based on your daily and weekly inputs. It reflects your readiness across physical, mental, and recovery drivers.",
            },
            {
                "question": "How is my score calculated?",
                "answer": "Scores are calculated from your assessment answers, grouped into five drivers, normalized to a 0-100 scale, and combined into an overall OPS score.",
            },
            {
                "question": "How can I improve my score?",
                "answer": "Focus on the lowest driver in your dashboard, maintain consistent daily check-ins, and follow the recommended improvement actions.",
            },
            {
                "question": "How often should I check in?",
                "answer": "Daily check-ins should be completed every day, weekly check-ins unlock after 7 daily check-ins, and monthly check-ins unlock after 30 completed daily check-ins.",
            },
        ]

    async def get_account_summary(self, current_user: User) -> dict[str, Any]:
        """Return account screen data for the authenticated user."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        latest_score = await self.score_repository.get_latest_by_user_id(current_user.id)

        strongest_driver = None
        focus_driver = None
        current_ops_score = 0.0

        if latest_score is not None:
            dimension_scores = latest_score.dimension_scores.model_dump()
            strongest_key = max(dimension_scores, key=dimension_scores.get)
            weakest_key = min(dimension_scores, key=dimension_scores.get)
            strongest_driver = self.dimension_labels[strongest_key]
            focus_driver = self.dimension_labels[weakest_key]
            current_ops_score = latest_score.overall_score

        subtitle_parts: list[str] = []
        organization_name = (
            profile.company if profile is not None else current_user.organization_name
        )
        organization_code = None
        if organization_name:
            organization_code = ORGANIZATION_METADATA.get(organization_name, {}).get("code")

        if profile is not None:
            if profile.department:
                subtitle_parts.append(profile.department)
            if profile.team:
                subtitle_parts.append(profile.team)
            elif profile.role:
                subtitle_parts.append(profile.role)
        elif current_user.role:
            subtitle_parts.append(current_user.role)

        subtitle = " | ".join(subtitle_parts) if subtitle_parts else None
        if organization_code and subtitle:
            subtitle = f"{organization_code} - {subtitle}"
        elif organization_code:
            subtitle = organization_code

        return {
            "profile": {
                "name": current_user.name,
                "email": current_user.email,
                "age": profile.age if profile is not None else None,
                "profile_image": (
                    profile.profile_image_url
                    if profile is not None
                    else None
                ),
            },
            "organization": {
                "organization_name": organization_name,
                "organization_code": organization_code,
                "subtitle": subtitle,
            },
            "performance_profile": {
                "current_ops_score": current_ops_score,
                "strongest_driver": strongest_driver,
                "focus_driver": focus_driver,
            },
            "settings_support": [
                {"title": "Settings", "key": "settings"},
                {"title": "Help Center", "key": "help_center"},
                {"title": "Contact Support", "key": "contact_support"},
            ],
            "app_version": APP_VERSION,
        }

    async def get_help_center(self) -> dict[str, Any]:
        """Return help center content."""
        faqs = await self.faq_repository.get_all()
        faq_list = (
            [{"question": f.question, "answer": f.answer} for f in faqs]
            if faqs
            else self.faqs
        )
        return {
            "title": "How can we help?",
            "subtitle": "Search our knowledge base or browse FAQs below.",
            "faqs": faq_list,
            "support_cta_title": "Still need help?",
            "support_cta_description": "Our support team is available 24/7 to assist you with any questions.",
        }

    async def get_privacy_policy(self) -> dict[str, Any]:
        """Return privacy policy content."""
        setting = await self.app_setting_repository.get_by_key("privacy_policy")
        if setting:
            return {
                "title": setting.title,
                "items": [i.strip() for i in setting.content.split("\n") if i.strip()],
            }
        return {"title": "Privacy Policy", "items": self.legal_items}

    async def get_terms_of_condition(self) -> dict[str, Any]:
        """Return terms of condition content."""
        setting = await self.app_setting_repository.get_by_key("terms_and_conditions")
        if setting:
            return {
                "title": setting.title,
                "items": [i.strip() for i in setting.content.split("\n") if i.strip()],
            }
        return {"title": "Terms of Condition", "items": self.legal_items}

    async def get_about_us(self) -> dict[str, Any]:
        """Return about us content."""
        setting = await self.app_setting_repository.get_by_key("about_us")
        if setting:
            return {
                "title": setting.title,
                "items": [i.strip() for i in setting.content.split("\n") if i.strip()],
            }
        return {"title": "About Us", "items": self.legal_items}

    async def submit_support_request(
        self,
        current_user: User,
        issue: str,
    ) -> dict[str, str]:
        """Return a support request acknowledgement."""
        if not issue.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Issue description is required.",
                    {"issue": "Please describe the issue you are experiencing."},
                ),
            )
        # Persist the support request
        await self.support_request_repository.create(
            user_id=current_user.id,
            email=current_user.email,
            issue=issue.strip(),
        )

        return {
            "email": current_user.email,
            "issue": issue.strip(),
            "estimated_response": "Within 2 hours",
        }

    async def logout_user(self, current_user: User) -> dict[str, str]:
        """Return a logout acknowledgement for JWT clients."""
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_response("This account is inactive."),
            )
        return {"action": "logout", "detail": "Session cleared on client side."}

    async def delete_account(self, current_user: User) -> dict[str, str]:
        """Permanently delete the authenticated user's account and profile."""
        await self.score_repository.delete_by_user_id(current_user.id)
        await self.assessment_repository.delete_by_user_id(current_user.id)
        await self.daily_checkin_repository.delete_by_user_id(current_user.id)
        await self.weekly_checkin_repository.delete_by_user_id(current_user.id)
        await self.monthly_checkin_repository.delete_by_user_id(current_user.id)
        await self.support_request_repository.delete_by_user_id(current_user.id)
        await self.profile_repository.delete_by_user_id(current_user.id)
        user = await self.user_repository.delete_user(str(current_user.id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("User not found."),
            )
        return {"action": "delete_account", "detail": "Account deleted successfully."}

