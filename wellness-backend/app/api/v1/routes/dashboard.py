"""Dashboard routes."""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import (
    get_current_leader_user,
    get_current_superadmin_user,
    get_current_user,
)
from app.models.user import User
from app.schemas.dashboard import (
    LeaderSettingsCompanyUpdate,
    LeaderSettingsProfileUpdate,
    LeaderSettingsScopeUpdate,
    SuperadminFAQCreate,
    SuperadminFAQUpdate,
    SuperadminLegalContentUpdate,
    SuperadminUserUpdate,
    TeamActionLogCreate,
)
from app.services.dashboard_service import DashboardService
from app.services.report_service import ReportService
from app.utils.response import success_response

router = APIRouter()
dashboard_service = DashboardService()
report_service = ReportService()


@router.get("/home", status_code=status.HTTP_200_OK)
async def get_home_dashboard(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the complete home dashboard payload."""
    data = await dashboard_service.get_home_dashboard(current_user)
    return success_response("Home dashboard fetched successfully", data)


@router.get("/checkin-status", status_code=status.HTTP_200_OK)
async def get_checkin_status(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the next required check-in type for the user."""
    data = await dashboard_service.get_checkin_status(current_user.id)
    return success_response("Check-in status fetched successfully.", data)


@router.get("/progress", status_code=status.HTTP_200_OK)
async def get_progress(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the last seven days progress chart payload."""
    data = await dashboard_service.get_last_7_days_progress(current_user.id)
    return success_response("Dashboard progress fetched successfully", {"progress": data})


@router.get("/streaks", status_code=status.HTTP_200_OK)
async def get_streaks(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return dashboard streak cards."""
    data = await dashboard_service.get_behavior_streaks(current_user.id)
    return success_response("Dashboard streaks fetched successfully", {"streaks": data})


@router.get("/recommendations", status_code=status.HTTP_200_OK)
async def get_recommendations(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return dashboard recommendation cards."""
    personalized = await dashboard_service.get_personalized_improvement_plan(
        current_user.id
    )
    leader = await dashboard_service.get_leader_action_plan(current_user.id)
    return success_response(
        "Dashboard recommendations fetched successfully",
        {
            "personalized_improvement_plan": personalized,
            "leader_action_plan": leader,
        },
    )


@router.get("/report", status_code=status.HTTP_200_OK)
async def get_performance_report(
    week: str = Query(default="all"),
    month: int = Query(default=datetime.utcnow().month),
    year: int = Query(default=datetime.utcnow().year),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the performance report payload."""
    data = await report_service.get_performance_report(
        current_user.id,
        week,
        month,
        year,
    )
    return success_response("Performance report fetched successfully.", data)


@router.get("/team", status_code=status.HTTP_200_OK)
async def get_team_dashboard(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return aggregated team/leader dashboard data for the selected scope."""
    data = await dashboard_service.get_team_dashboard(
        current_user,
        department=department,
        team=team,
    )
    return success_response("Team dashboard fetched successfully.", data)


@router.get("/leader", status_code=status.HTTP_200_OK)
async def get_leader_dashboard(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return leader dashboard data using leader-focused route naming."""
    data = await dashboard_service.get_team_dashboard(
        current_user,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Leader dashboard fetched successfully.", data)


@router.get("/superadmin", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return superadmin dashboard data scoped to a selected company/team."""
    data = await dashboard_service.get_team_dashboard(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Superadmin dashboard fetched successfully.", data)


@router.get("/superadmin/organizations", status_code=status.HTTP_200_OK)
async def list_superadmin_organizations(
    query: str | None = Query(default=None),
    risk_filter: str = Query(default="all"),
    sort_by: str = Query(default="performance"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin organizations overview page payload."""
    data = await dashboard_service.list_superadmin_organizations(
        current_user,
        query=query,
        risk_filter=risk_filter,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin organizations fetched successfully.", data)


@router.get("/superadmin/organizations/{company_name}", status_code=status.HTTP_200_OK)
async def get_superadmin_company_dashboard(
    company_name: str,
    query: str | None = Query(default=None),
    risk_filter: str = Query(default="all"),
    sort_by: str = Query(default="performance"),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the company performance dashboard for a selected organization."""
    data = await dashboard_service.get_superadmin_company_dashboard(
        current_user,
        company=company_name,
        query=query,
        risk_filter=risk_filter,
        sort_by=sort_by,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin company dashboard fetched successfully.", data)


@router.get(
    "/superadmin/organizations/{company_name}/members/{member_user_id}",
    status_code=status.HTTP_200_OK,
)
async def get_superadmin_company_member_detail(
    company_name: str,
    member_user_id: str,
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return member detail analysis for a member inside a selected company dashboard."""
    data = await dashboard_service.get_superadmin_company_member_detail(
        current_user,
        company=company_name,
        member_user_id=member_user_id,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response(
        "Superadmin company member detail fetched successfully.",
        data,
    )


@router.get("/superadmin/users", status_code=status.HTTP_200_OK)
async def list_superadmin_users(
    query: str | None = Query(default=None),
    status_filter: str = Query(default="all"),
    sort_by: str = Query(default="company"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin user management page payload."""
    _ = current_user
    data = await dashboard_service.list_superadmin_users(
        query=query,
        status_filter=status_filter,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin users fetched successfully.", data)


@router.get("/superadmin/users/{user_id}", status_code=status.HTTP_200_OK)
async def get_superadmin_user_detail(
    user_id: str,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return a single user detail payload for superadmin management flows."""
    _ = current_user
    data = await dashboard_service.get_superadmin_user_detail(user_id)
    return success_response("Superadmin user fetched successfully.", data)


@router.patch("/superadmin/users/{user_id}", status_code=status.HTTP_200_OK)
async def update_superadmin_user(
    user_id: str,
    payload: SuperadminUserUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Update a user from the superadmin user management page."""
    _ = current_user
    data = await dashboard_service.update_superadmin_user(user_id, payload)
    return success_response("Superadmin user updated successfully.", data)


@router.delete("/superadmin/users/{user_id}", status_code=status.HTTP_200_OK)
async def deactivate_superadmin_user(
    user_id: str,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Deactivate a user from the superadmin user management page."""
    _ = current_user
    data = await dashboard_service.deactivate_superadmin_user(user_id)
    return success_response("Superadmin user deactivated successfully.", data)


@router.post("/team/actions", status_code=status.HTTP_201_CREATED)
async def create_team_action_log(
    payload: TeamActionLogCreate,
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Create a leader action log entry for the selected team scope."""
    data = await dashboard_service.create_team_action_log(current_user, payload)
    return success_response("Leader action logged successfully.", data)


@router.post("/leader/actions", status_code=status.HTTP_201_CREATED)
async def create_leader_action_log(
    payload: TeamActionLogCreate,
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Create a leader action log using leader-focused route naming."""
    data = await dashboard_service.create_team_action_log(current_user, payload)
    return success_response("Leader action logged successfully.", data)


@router.post("/superadmin/actions", status_code=status.HTTP_201_CREATED)
async def create_superadmin_action_log(
    payload: TeamActionLogCreate,
    company: str | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Create a superadmin action log entry for the selected company/team scope."""
    data = await dashboard_service.create_team_action_log(
        current_user,
        payload,
        company=company,
    )
    return success_response("Superadmin action logged successfully.", data)


@router.get("/team/actions", status_code=status.HTTP_200_OK)
async def list_team_action_logs(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return recent leader action logs for the selected team scope."""
    data = await dashboard_service.list_team_action_logs(
        current_user,
        department=department,
        team=team,
        limit=limit,
    )
    return success_response("Leader actions fetched successfully.", data)


@router.get("/leader/actions", status_code=status.HTTP_200_OK)
async def list_leader_action_logs(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return leader action logs using leader-focused route naming."""
    data = await dashboard_service.list_team_action_logs(
        current_user,
        department=department,
        team=team,
        limit=limit,
    )
    return success_response("Leader actions fetched successfully.", data)


@router.get("/leader/actions/history", status_code=status.HTTP_200_OK)
async def get_leader_action_history(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    outcome: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return the leader action history page payload."""
    data = await dashboard_service.get_leader_action_history(
        current_user,
        department=department,
        team=team,
        range_key=range,
        outcome=outcome,
        page=page,
        page_size=page_size,
    )
    return success_response("Leader action history fetched successfully.", data)


@router.get("/leader/members", status_code=status.HTTP_200_OK)
async def list_leader_dashboard_members(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    query: str | None = Query(default=None),
    risk_filter: str = Query(default="all"),
    sort_by: str = Query(default="performance"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return paginated leader dashboard member rows."""
    data = await dashboard_service.list_leader_members(
        current_user,
        department=department,
        team=team,
        query=query,
        risk_filter=risk_filter,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    return success_response("Leader members fetched successfully.", data)


@router.get("/superadmin/members", status_code=status.HTTP_200_OK)
async def list_superadmin_dashboard_members(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    query: str | None = Query(default=None),
    risk_filter: str = Query(default="all"),
    sort_by: str = Query(default="performance"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return paginated superadmin member rows scoped by company/team."""
    data = await dashboard_service.list_leader_members(
        current_user,
        company=company,
        department=department,
        team=team,
        query=query,
        risk_filter=risk_filter,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin members fetched successfully.", data)


@router.get("/leader/members/{member_user_id}", status_code=status.HTTP_200_OK)
async def get_leader_dashboard_member_detail(
    member_user_id: str,
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return the member detail analysis payload for a leader-selected member."""
    data = await dashboard_service.get_leader_member_detail(
        current_user,
        member_user_id=member_user_id,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Leader member detail fetched successfully.", data)


@router.get("/superadmin/members/{member_user_id}", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard_member_detail(
    member_user_id: str,
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin member detail analysis payload."""
    data = await dashboard_service.get_leader_member_detail(
        current_user,
        member_user_id=member_user_id,
        company=company,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Superadmin member detail fetched successfully.", data)


@router.get("/leader/insights", status_code=status.HTTP_200_OK)
@router.get("/leader/ai-insights", status_code=status.HTTP_200_OK)
async def get_leader_dashboard_insights(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return the leader AI insights page payload."""
    data = await dashboard_service.get_leader_ai_insights(
        current_user,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Leader AI insights fetched successfully.", data)


@router.get("/superadmin/insights", status_code=status.HTTP_200_OK)
@router.get("/superadmin/ai-insights", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard_insights(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin AI insights page payload."""
    data = await dashboard_service.get_superadmin_ai_insights(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Superadmin AI insights fetched successfully.", data)


@router.get("/leader/report", status_code=status.HTTP_200_OK)
@router.get("/leader/reports", status_code=status.HTTP_200_OK)
async def get_leader_dashboard_report(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return the leader reports page payload."""
    data = await dashboard_service.get_leader_report(
        current_user,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return success_response("Leader report fetched successfully.", data)


@router.get("/superadmin/report", status_code=status.HTTP_200_OK)
@router.get("/superadmin/reports", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard_report(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin reports page payload."""
    data = await dashboard_service.get_superadmin_report(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin report fetched successfully.", data)


@router.get("/leader/alerts", status_code=status.HTTP_200_OK)
@router.get("/leader/risk-alerts", status_code=status.HTTP_200_OK)
async def get_leader_dashboard_alerts(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return leader alert detail cards."""
    data = await dashboard_service.get_leader_alerts(
        current_user,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Leader alerts fetched successfully.", data)


@router.get("/superadmin/alerts", status_code=status.HTTP_200_OK)
@router.get("/superadmin/risk-alerts", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard_alerts(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return superadmin alert detail cards."""
    data = await dashboard_service.get_superadmin_alerts(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Superadmin alerts fetched successfully.", data)


@router.get("/leader/burnout-recommendations", status_code=status.HTTP_200_OK)
async def get_leader_burnout_recommendations(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return the leader burnout recommendations page payload."""
    data = await dashboard_service.get_leader_burnout_recommendations(
        current_user,
        department=department,
        team=team,
        range_key=range,
    )
    return success_response("Leader burnout recommendations fetched successfully.", data)


@router.get("/superadmin/burnout-recommendations", status_code=status.HTTP_200_OK)
async def get_superadmin_burnout_recommendations(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin burnout recommendations page payload."""
    data = await dashboard_service.get_leader_burnout_recommendations(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
    )
    return success_response("Superadmin burnout recommendations fetched successfully.", data)


@router.get("/leader/burnout-details", status_code=status.HTTP_200_OK)
async def get_leader_burnout_details(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return the leader burnout risk details page payload."""
    data = await dashboard_service.get_leader_burnout_details(
        current_user,
        department=department,
        team=team,
        range_key=range,
    )
    return success_response("Leader burnout details fetched successfully.", data)


@router.get("/superadmin/burnout-details", status_code=status.HTTP_200_OK)
async def get_superadmin_burnout_details(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin burnout risk details page payload."""
    data = await dashboard_service.get_leader_burnout_details(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
    )
    return success_response("Superadmin burnout details fetched successfully.", data)


@router.get("/leader/ops-trend", status_code=status.HTTP_200_OK)
async def get_leader_dashboard_ops_trend(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return dedicated leader OPS trend chart data."""
    data = await dashboard_service.get_leader_ops_trend(
        current_user,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Leader OPS trend fetched successfully.", data)


@router.get("/superadmin/ops-trend", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard_ops_trend(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return dedicated superadmin OPS trend chart data."""
    data = await dashboard_service.get_leader_ops_trend(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )
    return success_response("Superadmin OPS trend fetched successfully.", data)


@router.get("/leader/settings", status_code=status.HTTP_200_OK)
async def get_leader_dashboard_settings(
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Return leader dashboard settings and filter metadata."""
    data = await dashboard_service.get_leader_settings(
        current_user,
        department=department,
        team=team,
    )
    return success_response("Leader settings fetched successfully.", data)


@router.get("/superadmin/settings", status_code=status.HTTP_200_OK)
async def get_superadmin_dashboard_settings(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin settings menu payload."""
    data = await dashboard_service.get_superadmin_settings_menu(
        current_user,
        company=company,
        department=department,
        team=team,
    )
    return success_response("Superadmin settings fetched successfully.", data)


@router.get("/superadmin/settings/profile", status_code=status.HTTP_200_OK)
async def get_superadmin_settings_profile(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin profile settings page payload."""
    data = await dashboard_service.get_superadmin_settings_profile(current_user)
    return success_response("Superadmin profile settings fetched successfully.", data)


@router.get("/superadmin/settings/company", status_code=status.HTTP_200_OK)
async def get_superadmin_settings_company(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin company settings page payload."""
    data = await dashboard_service.get_superadmin_settings_company(current_user)
    return success_response("Superadmin company settings fetched successfully.", data)


@router.get("/superadmin/settings/scope", status_code=status.HTTP_200_OK)
async def get_superadmin_settings_scope(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin scope settings page payload."""
    data = await dashboard_service.get_superadmin_settings_scope(
        current_user,
        company=company,
        department=department,
        team=team,
    )
    return success_response("Superadmin scope settings fetched successfully.", data)


@router.get("/superadmin/settings/change-password", status_code=status.HTTP_200_OK)
async def get_superadmin_change_password_settings(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin change password page payload."""
    data = await dashboard_service.get_superadmin_change_password_settings(current_user)
    return success_response(
        "Superadmin change password settings fetched successfully.",
        data,
    )


@router.get("/superadmin/settings/forgot-password", status_code=status.HTTP_200_OK)
async def get_superadmin_forgot_password_settings() -> dict[str, Any]:
    """Return the superadmin forgot password page payload."""
    data = await dashboard_service.get_superadmin_forgot_password_settings()
    return success_response(
        "Superadmin forgot password settings fetched successfully.",
        data,
    )


@router.get("/superadmin/settings/verify-reset-code", status_code=status.HTTP_200_OK)
async def get_superadmin_verify_reset_code_settings() -> dict[str, Any]:
    """Return the superadmin verify reset code page payload."""
    data = await dashboard_service.get_superadmin_verify_reset_code_settings()
    return success_response(
        "Superadmin verify reset code settings fetched successfully.",
        data,
    )


@router.get("/superadmin/settings/privacy-policy", status_code=status.HTTP_200_OK)
async def get_superadmin_privacy_policy_settings(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the editable superadmin privacy policy payload."""
    _ = current_user
    data = await dashboard_service.get_superadmin_legal_content("privacy_policy")
    return success_response("Superadmin privacy policy fetched successfully.", data)


@router.patch("/superadmin/settings/privacy-policy", status_code=status.HTTP_200_OK)
async def update_superadmin_privacy_policy_settings(
    payload: SuperadminLegalContentUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Persist superadmin privacy policy content."""
    data = await dashboard_service.save_superadmin_legal_content(
        current_user,
        "privacy_policy",
        payload,
    )
    return success_response("Superadmin privacy policy updated successfully.", data)


@router.get(
    "/superadmin/settings/terms-and-conditions",
    status_code=status.HTTP_200_OK,
)
async def get_superadmin_terms_settings(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the editable superadmin terms and conditions payload."""
    _ = current_user
    data = await dashboard_service.get_superadmin_legal_content("terms_and_conditions")
    return success_response(
        "Superadmin terms and conditions fetched successfully.",
        data,
    )


@router.patch(
    "/superadmin/settings/terms-and-conditions",
    status_code=status.HTTP_200_OK,
)
async def update_superadmin_terms_settings(
    payload: SuperadminLegalContentUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Persist superadmin terms and conditions content."""
    data = await dashboard_service.save_superadmin_legal_content(
        current_user,
        "terms_and_conditions",
        payload,
    )
    return success_response(
        "Superadmin terms and conditions updated successfully.",
        data,
    )


@router.get("/superadmin/settings/about-us", status_code=status.HTTP_200_OK)
async def get_superadmin_about_us_settings(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the editable superadmin about us payload."""
    _ = current_user
    data = await dashboard_service.get_superadmin_legal_content("about_us")
    return success_response("Superadmin about us fetched successfully.", data)


@router.patch("/superadmin/settings/about-us", status_code=status.HTTP_200_OK)
async def update_superadmin_about_us_settings(
    payload: SuperadminLegalContentUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Persist superadmin about us content."""
    data = await dashboard_service.save_superadmin_legal_content(
        current_user,
        "about_us",
        payload,
    )
    return success_response("Superadmin about us updated successfully.", data)


@router.get("/superadmin/audit-logs", status_code=status.HTTP_200_OK)
async def get_superadmin_audit_logs(
    company: str | None = Query(default=None),
    query: str | None = Query(default=None),
    time_filter: str = Query(default="today"),
    user_filter: str = Query(default="all"),
    status_filter: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin audit log page payload."""
    data = await dashboard_service.get_superadmin_audit_logs(
        current_user,
        company=company,
        query=query,
        time_filter=time_filter,
        user_filter=user_filter,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin audit logs fetched successfully.", data)


@router.get("/superadmin/audit-logs/{action_log_id}", status_code=status.HTTP_200_OK)
async def get_superadmin_audit_log_detail(
    action_log_id: str,
    company: str | None = Query(default=None),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin audit log detail modal payload."""
    data = await dashboard_service.get_superadmin_audit_log_detail(
        current_user,
        action_log_id=action_log_id,
        company=company,
    )
    return success_response("Superadmin audit log detail fetched successfully.", data)


@router.get("/superadmin/actions/history", status_code=status.HTTP_200_OK)
async def get_superadmin_action_history(
    company: str | None = Query(default=None),
    department: str | None = Query(default=None),
    team: str | None = Query(default=None),
    range: str = Query(default="30d"),
    outcome: str = Query(default="all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Return the superadmin action history page payload."""
    data = await dashboard_service.get_superadmin_action_history(
        current_user,
        company=company,
        department=department,
        team=team,
        range_key=range,
        outcome=outcome,
        page=page,
        page_size=page_size,
    )
    return success_response("Superadmin action history fetched successfully.", data)


@router.patch("/leader/settings/profile", status_code=status.HTTP_200_OK)
async def update_leader_settings_profile(
    payload: LeaderSettingsProfileUpdate,
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Update the leader settings profile section."""
    data = await dashboard_service.update_leader_settings_profile(current_user, payload)
    return success_response("Leader profile settings updated successfully.", data)


@router.patch("/superadmin/settings/profile", status_code=status.HTTP_200_OK)
async def update_superadmin_settings_profile(
    payload: LeaderSettingsProfileUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Update the superadmin settings profile section."""
    data = await dashboard_service.update_leader_settings_profile(current_user, payload)
    return success_response("Superadmin profile settings updated successfully.", data)


@router.patch("/leader/settings/company", status_code=status.HTTP_200_OK)
async def update_leader_settings_company(
    payload: LeaderSettingsCompanyUpdate,
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Update the leader settings company section."""
    data = await dashboard_service.update_leader_settings_company(current_user, payload)
    return success_response("Leader company settings updated successfully.", data)


@router.patch("/superadmin/settings/company", status_code=status.HTTP_200_OK)
async def update_superadmin_settings_company(
    payload: LeaderSettingsCompanyUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Update the superadmin settings company section."""
    data = await dashboard_service.update_leader_settings_company(current_user, payload)
    return success_response("Superadmin company settings updated successfully.", data)


@router.patch("/leader/settings/scope", status_code=status.HTTP_200_OK)
async def update_leader_settings_scope(
    payload: LeaderSettingsScopeUpdate,
    current_user: User = Depends(get_current_leader_user),
) -> dict[str, Any]:
    """Update the leader settings scope section."""
    data = await dashboard_service.update_leader_settings_scope(current_user, payload)
    return success_response("Leader scope settings updated successfully.", data)


@router.patch("/superadmin/settings/scope", status_code=status.HTTP_200_OK)
async def update_superadmin_settings_scope(
    payload: LeaderSettingsScopeUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Update the superadmin settings scope section."""
    data = await dashboard_service.update_leader_settings_scope(current_user, payload)
    return success_response("Superadmin scope settings updated successfully.", data)


@router.get("/superadmin/faqs", status_code=status.HTTP_200_OK)
async def get_superadmin_faqs(
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Get all FAQs for superadmin management."""
    data = await dashboard_service.get_faqs()
    return success_response("FAQs retrieved successfully.", data)


@router.post("/superadmin/faqs", status_code=status.HTTP_201_CREATED)
async def create_superadmin_faq(
    payload: SuperadminFAQCreate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Create a new FAQ."""
    data = await dashboard_service.create_faq(payload)
    return success_response("FAQ created successfully.", data)


@router.patch("/superadmin/faqs/{faq_id}", status_code=status.HTTP_200_OK)
async def update_superadmin_faq(
    faq_id: str,
    payload: SuperadminFAQUpdate,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Update an existing FAQ."""
    data = await dashboard_service.update_faq(faq_id, payload)
    return success_response("FAQ updated successfully.", data)


@router.delete("/superadmin/faqs/{faq_id}", status_code=status.HTTP_200_OK)
async def delete_superadmin_faq(
    faq_id: str,
    current_user: User = Depends(get_current_superadmin_user),
) -> dict[str, Any]:
    """Delete an FAQ."""
    await dashboard_service.delete_faq(faq_id)
    return success_response("FAQ deleted successfully.", None)
