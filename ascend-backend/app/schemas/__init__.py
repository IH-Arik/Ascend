"""Application schema exports."""

from app.schemas.auth import (
    AuthScreenConfigResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationCodeRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyEmailRequest,
    VerifyResetCodeRequest,
)
from app.schemas.ai_insights import AIInsightResponse
from app.schemas.onboarding import (
    BaselineFinalizeResponse,
    ConsentSubmitRequest,
    FirstUseStatusResponse,
    OnboardingIntroResponse,
    OnboardingAnswerSubmission,
    OnboardingQuestionOption,
    OnboardingQuestionResponse,
    StepProgressRequest,
)

__all__ = [
    "AuthScreenConfigResponse",
    "AIInsightResponse",
    "BaselineFinalizeResponse",
    "ConsentSubmitRequest",
    "FirstUseStatusResponse",
    "ForgotPasswordRequest",
    "LoginRequest",
    "OnboardingAnswerSubmission",
    "OnboardingIntroResponse",
    "OnboardingQuestionOption",
    "OnboardingQuestionResponse",
    "RefreshRequest",
    "RegisterRequest",
    "ResendVerificationCodeRequest",
    "ResetPasswordRequest",
    "StepProgressRequest",
    "UserResponse",
    "VerifyEmailRequest",
    "VerifyResetCodeRequest",
]
