"""Route modules package."""

from app.api.v1.routes import (
    assessments,
    auth,
    dashboard,
    daily_checkins,
    insights,
    meta,
    monthly_checkins,
    questions,
    scores,
    users,
    weekly_checkins,
)

__all__ = [
    "assessments",
    "auth",
    "dashboard",
    "daily_checkins",
    "insights",
    "meta",
    "monthly_checkins",
    "questions",
    "scores",
    "users",
    "weekly_checkins",
]
