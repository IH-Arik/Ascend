"""Top-level API router."""

from fastapi import APIRouter

from app.modules.admin.routes import router as admin_router
from app.modules.ai_insights.routes import router as ai_insights_router
from app.modules.assessments.routes import router as assessments_router
from app.modules.auth.routes import router as auth_router
from app.modules.checkins.routes import router as checkins_router
from app.modules.dashboard.routes import router as provider_dashboard_router
from app.modules.dashboards.routes import router as dashboards_router
from app.modules.health.routes import router as health_router
from app.modules.messaging.routes import router as messaging_router
from app.modules.notifications.routes import router as notifications_router
from app.modules.oft.routes import router as oft_router
from app.modules.onboarding.routes import router as onboarding_router
from app.modules.performance_summaries.routes import router as performance_summaries_router
from app.modules.records.routes import router as records_router
from app.modules.recommendations.routes import router as recommendations_router
from app.modules.roles.routes import router as roles_router
from app.modules.specialist_notes.routes import router as specialist_notes_router
from app.modules.support_requests.routes import router as support_router
from app.modules.users.routes import router as users_router
from app.modules.workouts.routes import router as workouts_router

api_router = APIRouter()

api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(ai_insights_router, prefix="/ai-insights", tags=["ai-insights"])
api_router.include_router(onboarding_router, prefix="/onboarding", tags=["onboarding"])
api_router.include_router(checkins_router, prefix="/checkins", tags=["checkins"])
api_router.include_router(dashboards_router, prefix="/dashboards", tags=["dashboards"])
api_router.include_router(provider_dashboard_router, prefix="/dashboard", tags=["provider-dashboard"])
api_router.include_router(recommendations_router, prefix="/recommendations", tags=["recommendations"])
api_router.include_router(support_router, prefix="/support", tags=["support"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(oft_router, prefix="/oft", tags=["oft"])
api_router.include_router(assessments_router, prefix="/assessments", tags=["assessments"])
api_router.include_router(workouts_router, prefix="/workouts", tags=["workouts"])
api_router.include_router(messaging_router, prefix="/messaging", tags=["messaging"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(roles_router, prefix="/roles", tags=["roles"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(records_router, prefix="/records", tags=["records"])
api_router.include_router(specialist_notes_router, prefix="/specialist-notes", tags=["specialist-notes"])
api_router.include_router(performance_summaries_router, prefix="/performance-summaries", tags=["performance-summaries"])
