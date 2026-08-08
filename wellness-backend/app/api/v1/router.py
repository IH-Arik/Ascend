"""Top-level API router for version 1."""

from fastapi import APIRouter

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

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(questions.router, prefix="/questions", tags=["questions"])
api_router.include_router(
    daily_checkins.router,
    prefix="/daily-checkins",
    tags=["daily-checkins"],
)
api_router.include_router(
    weekly_checkins.router,
    prefix="/weekly-checkins",
    tags=["weekly-checkins"],
)
api_router.include_router(
    monthly_checkins.router,
    prefix="/monthly-checkins",
    tags=["monthly-checkins"],
)
api_router.include_router(
    assessments.router,
    prefix="/assessments",
    tags=["assessments"],
)
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(scores.router, prefix="/scores", tags=["scores"])
api_router.include_router(insights.router, prefix="/insights", tags=["insights"])
