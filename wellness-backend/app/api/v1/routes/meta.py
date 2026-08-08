"""Metadata routes for dropdown options."""

from typing import Any

from fastapi import APIRouter, Query, status

from app.services.meta_service import MetaService
from app.utils.response import success_response

router = APIRouter()
meta_service = MetaService()


@router.get("/organizations", status_code=status.HTTP_200_OK)
async def list_organizations() -> dict[str, Any]:
    """Return organization dropdown options."""
    data = await meta_service.get_organizations()
    return success_response("Organizations fetched successfully.", data)


@router.get("/roles", status_code=status.HTTP_200_OK)
async def list_roles(
    organization_name: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return role dropdown options, optionally filtered by organization."""
    data = await meta_service.get_roles(organization_name)
    return success_response("Roles fetched successfully.", data)


@router.get("/departments", status_code=status.HTTP_200_OK)
async def list_departments(
    organization_name: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return department dropdown options, optionally filtered by organization."""
    data = await meta_service.get_departments(organization_name)
    return success_response("Departments fetched successfully.", data)


@router.get("/teams", status_code=status.HTTP_200_OK)
async def list_teams(
    organization_name: str | None = Query(default=None),
    department: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return team dropdown options, optionally filtered by organization and department."""
    data = await meta_service.get_teams(organization_name, department)
    return success_response("Teams fetched successfully.", data)
