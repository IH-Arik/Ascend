"""Metadata service for frontend dropdowns."""

from app.utils.constants import (
    ORGANIZATION_DEPARTMENT_OPTIONS,
    ORGANIZATION_OPTIONS,
    ORGANIZATION_ROLE_OPTIONS,
    ORGANIZATION_TEAM_OPTIONS,
)


class MetaService:
    """Service for returning frontend dropdown metadata."""

    async def get_organizations(self) -> dict[str, list[dict[str, str]]]:
        """Return all available organizations as dropdown options."""
        return {
            "organizations": [
                {"label": organization, "value": organization}
                for organization in ORGANIZATION_OPTIONS
            ]
        }

    async def get_roles(
        self,
        organization_name: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        """Return roles for an organization or the union of all roles."""
        if organization_name and organization_name in ORGANIZATION_ROLE_OPTIONS:
            roles = ORGANIZATION_ROLE_OPTIONS[organization_name]
        else:
            roles = sorted(
                {
                    role
                    for role_list in ORGANIZATION_ROLE_OPTIONS.values()
                    for role in role_list
                }
            )

        return {"roles": [{"label": role, "value": role} for role in roles]}

    async def get_departments(
        self,
        organization_name: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        """Return departments for an organization or the union of all departments."""
        if organization_name and organization_name in ORGANIZATION_DEPARTMENT_OPTIONS:
            departments = ORGANIZATION_DEPARTMENT_OPTIONS[organization_name]
        else:
            departments = sorted(
                {
                    department
                    for department_list in ORGANIZATION_DEPARTMENT_OPTIONS.values()
                    for department in department_list
                }
            )
        return {
            "departments": [
                {"label": department, "value": department}
                for department in departments
            ]
        }

    async def get_teams(
        self,
        organization_name: str | None = None,
        department: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        """Return teams for an organization and optional department filter."""
        teams: list[str] = []
        if (
            organization_name
            and organization_name in ORGANIZATION_TEAM_OPTIONS
            and department
            and department in ORGANIZATION_TEAM_OPTIONS[organization_name]
        ):
            teams = ORGANIZATION_TEAM_OPTIONS[organization_name][department]
        elif organization_name and organization_name in ORGANIZATION_TEAM_OPTIONS:
            teams = sorted(
                {
                    team
                    for team_list in ORGANIZATION_TEAM_OPTIONS[organization_name].values()
                    for team in team_list
                }
            )
        else:
            teams = sorted(
                {
                    team
                    for org_teams in ORGANIZATION_TEAM_OPTIONS.values()
                    for team_list in org_teams.values()
                    for team in team_list
                }
            )
        return {"teams": [{"label": team, "value": team} for team in teams]}

    def validate_organization_role(
        self,
        organization_name: str | None,
        role: str | None,
    ) -> None:
        """Validate organization and role pairing when values are provided."""
        if organization_name is None and role is None:
            return

        if organization_name is not None and organization_name not in ORGANIZATION_ROLE_OPTIONS:
            raise ValueError("Selected organization is not supported.")

        if role is None:
            return

        if organization_name is None:
            all_roles = {
                role_value
                for role_list in ORGANIZATION_ROLE_OPTIONS.values()
                for role_value in role_list
            }
            if role not in all_roles:
                raise ValueError("Selected role is not supported.")
            return

        if role not in ORGANIZATION_ROLE_OPTIONS[organization_name]:
            raise ValueError("Selected role is not valid for the selected organization.")

    def validate_department(
        self,
        organization_name: str | None,
        department: str | None,
    ) -> None:
        """Validate a department for the selected organization."""
        if department is None:
            return
        if organization_name is None:
            raise ValueError("Organization is required when selecting a department.")
        if organization_name not in ORGANIZATION_DEPARTMENT_OPTIONS:
            raise ValueError("Selected organization is not supported.")
        if department not in ORGANIZATION_DEPARTMENT_OPTIONS[organization_name]:
            raise ValueError("Selected department is not valid for the selected organization.")

    def validate_team(
        self,
        organization_name: str | None,
        department: str | None,
        team: str | None,
    ) -> None:
        """Validate a team for the selected organization and department."""
        if team is None:
            return
        if organization_name is None or department is None:
            raise ValueError("Organization and department are required when selecting a team.")
        if organization_name not in ORGANIZATION_TEAM_OPTIONS:
            raise ValueError("Selected organization is not supported.")
        if department not in ORGANIZATION_TEAM_OPTIONS[organization_name]:
            raise ValueError("Selected department is not valid for the selected organization.")
        if team not in ORGANIZATION_TEAM_OPTIONS[organization_name][department]:
            raise ValueError("Selected team is not valid for the selected department.")
