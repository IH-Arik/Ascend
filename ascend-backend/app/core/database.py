"""MongoDB and Beanie initialization utilities."""

import logging

from beanie import init_beanie
import certifi
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.models import AppSetting
from app.models import AIInsight
from app.models import Assessment
from app.models import AuditLog
from app.models import Briefing
from app.models import CheckinAnswer
from app.models import CoverageLog
from app.models import DeactivationRequest
from app.models import EmergencyContactConfig
from app.models import EquipmentGap
from app.models import IdmtHandoff
from app.models import LeadershipAnnotation
from app.models import MedicalRecord
from app.models import MedicalRecordAccessEvent
from app.models import Message
from app.models import MessageThread
from app.models import Notification
from app.models import OFTRecord
from app.models import OnboardingAnswer
from app.models import OpsSnapshot
from app.models import OrgUnit
from app.models import PathwayApproval
from app.models import PendingConfirmation
from app.models import ProviderCredential
from app.models import ReconditioningEvent
from app.models import ReconditioningPlan
from app.models import Recommendation
from app.models import Restriction
from app.models import RomMeasurement
from app.models import RecommendationThresholdConfig
from app.models import ReportExport
from app.models import RoleScopeConfig
from app.models import ScheduledExport
from app.models import SchedulerJobRun
from app.models import ScoringConfig
from app.models import PerformanceSummary
from app.models import QuestionBankVersion
from app.models import SpecialistNote
from app.models import SupportRequest
from app.models import TeamAssignment
from app.models import User
from app.models import UtilizationEvent
from app.models import WorkoutLog

client: AsyncMongoClient | None = None
database: AsyncDatabase | None = None
logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Initialize the MongoDB client and register Beanie document models."""
    global client, database

    if client is not None and database is not None:
        return

    settings = get_settings()
    client_options: dict[str, object] = {
        "serverSelectionTimeoutMS": 30000 if settings.db_required else 2000,
        # Without this, datetimes read back from MongoDB are naive (UTC-implied,
        # no tzinfo), while every datetime created in this app is timezone-aware
        # (datetime.now(timezone.utc)). Mixing the two raises TypeError on any
        # subtraction/comparison (e.g. computing "updated N minutes ago").
        "tz_aware": True,
    }
    if settings.mongodb_tls:
        client_options["tls"] = True
        client_options["tlsCAFile"] = certifi.where()

    client = AsyncMongoClient(settings.mongodb_url, **client_options)
    database = client[settings.mongodb_db_name]

    try:
        await init_beanie(
            database=database,
            document_models=[
                User,
                AppSetting,
                AIInsight,
                OnboardingAnswer,
                CheckinAnswer,
                OpsSnapshot,
                Recommendation,
                SupportRequest,
                Notification,
                OFTRecord,
                Assessment,
                WorkoutLog,
                Message,
                AuditLog,
                TeamAssignment,
                DeactivationRequest,
                ReconditioningPlan,
                MedicalRecord,
                MedicalRecordAccessEvent,
                EmergencyContactConfig,
                ProviderCredential,
                EquipmentGap,
                UtilizationEvent,
                CoverageLog,
                ScoringConfig,
                ReportExport,
                PathwayApproval,
                PendingConfirmation,
                SchedulerJobRun,
                OrgUnit,
                RoleScopeConfig,
                ScheduledExport,
                RecommendationThresholdConfig,
                MessageThread,
                LeadershipAnnotation,
                Briefing,
                IdmtHandoff,
                RomMeasurement,
                ReconditioningEvent,
                Restriction,
                PerformanceSummary,
                QuestionBankVersion,
                SpecialistNote,
            ],
        )
    except Exception:
        await close_db()
        if settings.db_required:
            raise
        logger.warning(
            "MongoDB is unavailable. Ascend will continue without database connectivity."
        )


async def close_db() -> None:
    """Close the MongoDB client if it has been initialized."""
    global client, database

    if client is not None:
        await client.aclose()
    client = None
    database = None


def get_database() -> AsyncDatabase:
    """Return the initialized MongoDB database instance."""
    if database is None:
        raise RuntimeError("Database has not been initialized.")
    return database


def is_database_configured() -> bool:
    """Return whether MongoDB settings are present."""
    settings = get_settings()
    return bool(settings.mongodb_url and settings.mongodb_db_name)


def is_database_connected() -> bool:
    """Return whether the MongoDB client is initialized."""
    return client is not None and database is not None
