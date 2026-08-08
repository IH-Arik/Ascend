"""Insight routes backed by OpenAI."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_current_user
from app.db.repositories.score_repo import ScoreRepository
from app.models.user import User
from app.schemas.insight import AssistantChatRequest, InsightGenerateRequest
from app.services.ai_service import AIService
from app.services.dashboard_service import DashboardService
from app.utils.response import error_response, success_response

router = APIRouter()
ai_service = AIService()
score_repository = ScoreRepository()
dashboard_service = DashboardService()


@router.get("/latest", status_code=status.HTTP_200_OK)
async def get_latest_insight(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return an AI-generated insight and improvement plan for the authenticated user."""
    latest_score = await score_repository.get_latest_by_user_id(current_user.id)
    if latest_score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("No score data found for this user."),
        )

    insight = await ai_service.generate_insight(latest_score)
    improvement_plan = await ai_service.generate_improvement_plan(latest_score)
    goal_plan = await ai_service.generate_goal_plan(latest_score)
    risk_plan = await ai_service.generate_risk_plan(latest_score)
    return success_response(
        "Latest insight fetched successfully.",
        {
            "insight": insight,
            "improvement_plan": improvement_plan,
            "goal_plan": goal_plan,
            "risk_plan": risk_plan,
            "overall_score": latest_score.overall_score,
            "condition": latest_score.condition,
            "dimension_scores": latest_score.dimension_scores.model_dump(),
            "trend_insight": await dashboard_service.get_trend_insight(current_user.id),
            "last_updated_at": latest_score.created_at.isoformat(),
            "live_sync_status": await dashboard_service.get_live_sync_status(current_user.id),
        },
    )


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_insight(
    payload: InsightGenerateRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Generate a fresh AI insight from the latest score snapshot."""
    latest_score = await score_repository.get_latest_by_user_id(current_user.id)
    if latest_score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("No score data found for this user."),
        )

    insight = await ai_service.generate_insight(latest_score)
    improvement_plan = await ai_service.generate_improvement_plan(latest_score)
    goal_plan = await ai_service.generate_goal_plan(latest_score)
    risk_plan = await ai_service.generate_risk_plan(latest_score)
    return success_response(
        "Insight generated successfully.",
        {
            "force_refresh": payload.force_refresh,
            "insight": insight,
            "improvement_plan": improvement_plan,
            "goal_plan": goal_plan,
            "risk_plan": risk_plan,
            "trend_insight": await dashboard_service.get_trend_insight(current_user.id),
            "last_updated_at": latest_score.created_at.isoformat(),
            "live_sync_status": await dashboard_service.get_live_sync_status(current_user.id),
        },
    )


@router.post("/chat", status_code=status.HTTP_200_OK)
async def chat_with_assistant(
    payload: AssistantChatRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Answer a user question using the latest score context."""
    latest_score = await score_repository.get_latest_by_user_id(current_user.id)
    if latest_score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("No score data found for this user."),
        )

    answer = await ai_service.answer_question(current_user, payload.message)
    return success_response(
        "Assistant response generated successfully.",
        answer,
    )


@router.get("/chat/greeting", status_code=status.HTTP_200_OK)
async def get_chat_greeting(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the assistant greeting header payload."""
    data = await ai_service.get_chat_greeting(current_user)
    return success_response("Assistant greeting fetched successfully.", data)


@router.get("/chat/suggestions", status_code=status.HTTP_200_OK)
async def get_chat_suggestions(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return quick suggestion chips for the assistant chat UI."""
    data = await ai_service.get_chat_suggestions(current_user)
    return success_response(
        "Assistant suggestions fetched successfully.",
        {"suggestions": data},
    )


@router.get("/chat/history", status_code=status.HTTP_200_OK)
async def get_chat_history(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return persisted assistant chat history for the user."""
    data = await ai_service.get_chat_history(current_user)
    return success_response(
        "Assistant chat history fetched successfully.",
        {"messages": data},
    )
