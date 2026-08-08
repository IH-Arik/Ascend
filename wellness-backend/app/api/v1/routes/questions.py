"""Question routes."""

from typing import Any

from fastapi import APIRouter, status


from app.schemas.question import PaginatedQuestions
from app.services.assessment_service import AssessmentService
from app.utils.response import success_response

router = APIRouter()
assessment_service = AssessmentService()


@router.get("", status_code=status.HTTP_200_OK)
async def list_questions(
    page: int = 1,
    size: int = 5,
) -> dict[str, Any]:
    """Return all fixed assessment questions ordered for display, with pagination."""
    data = await assessment_service.list_questions(page=page, size=size)
    return success_response(
        "Questions fetched successfully.",
        PaginatedQuestions(**data).model_dump(),
    )
