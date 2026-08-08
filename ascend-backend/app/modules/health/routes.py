"""Health-check routes."""

from fastapi import APIRouter

from app.common.utils.responses import success_response
from app.core.database import is_database_configured
from app.core.database import is_database_connected

router = APIRouter()


@router.get("", summary="Health check")
async def health_check():
    """Return application health state."""
    return success_response(
        "Ascend backend health check passed.",
        {
            "status": "ok",
            "database_configured": is_database_configured(),
            "database_connected": is_database_connected(),
        },
    )
