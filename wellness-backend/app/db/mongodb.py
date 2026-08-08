"""MongoDB and Beanie initialization utilities."""

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
import certifi

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.models.action_log import LeaderActionLog
from app.models.assessment import CheckIn
from app.models.assessment import DailyCheckIn
from app.models.assessment import MonthlyCheckIn
from app.models.assessment import WeeklyCheckIn
from app.models.behavior import BehaviorLog
from app.models.chat import ChatMessage
from app.models.intervention_memory import InterventionMemory
from app.models.profile import Profile
from app.models.question import Question
from app.models.score import Score
from app.models.support_request import SupportRequest
from app.models.faq import FAQ
from app.models.user import User
from app.utils.constants import QUESTION_BANK

client: AsyncMongoClient | None = None
database: AsyncDatabase | None = None


async def init_db() -> None:
    """Initialize the MongoDB client and register Beanie document models."""
    global client, database

    client_options: dict[str, object] = {
        "serverSelectionTimeoutMS": 30000,
    }
    if settings.MONGODB_TLS:
        client_options["tls"] = True
        client_options["tlsCAFile"] = certifi.where()

    client = AsyncMongoClient(settings.MONGODB_URL, **client_options)
    database = client[settings.MONGODB_DB_NAME]

    await init_beanie(
        database=database,
        document_models=[
            User,
            Profile,
            AppSetting,
            LeaderActionLog,
            CheckIn,
            DailyCheckIn,
            WeeklyCheckIn,
            MonthlyCheckIn,
            BehaviorLog,
            ChatMessage,
            InterventionMemory,
            Score,
            Question,
            SupportRequest,
            FAQ,
        ],
    )
    await seed_questions()
    await seed_faqs()


async def seed_questions() -> None:
    """Seed the fixed 25-question assessment bank if it is missing or outdated."""
    existing_questions = await Question.find_all().sort(Question.order).to_list()
    has_expected_count = len(existing_questions) == len(QUESTION_BANK)
    has_expected_codes = all(
        getattr(question, "code", None) == expected["code"]
        for question, expected in zip(existing_questions, QUESTION_BANK)
    )
    if has_expected_count and has_expected_codes:
        return

    await Question.find_all().delete()
    question_documents = [Question(**question_data) for question_data in QUESTION_BANK]
    await Question.insert_many(question_documents)


async def seed_faqs() -> None:
    """Seed initial FAQs if none exist."""
    if await FAQ.count() > 0:
        return

    initial_faqs = [
        {
            "question": "What is OPS Score?",
            "answer": "Your overall performance score based on your daily and weekly inputs. It reflects your readiness across physical, mental, and recovery drivers.",
            "order": 1,
        },
        {
            "question": "How is my score calculated?",
            "answer": "Scores are calculated from your assessment answers, grouped into five drivers, normalized to a 0-100 scale, and combined into an overall OPS score.",
            "order": 2,
        },
        {
            "question": "How can I improve my score?",
            "answer": "Focus on the lowest driver in your dashboard, maintain consistent daily check-ins, and follow the recommended improvement actions.",
            "order": 3,
        },
        {
            "question": "How often should I check in?",
            "answer": "Daily check-ins should be completed every day, weekly check-ins unlock after 7 daily check-ins, and monthly check-ins unlock after 30 completed daily check-ins.",
            "order": 4,
        },
    ]
    await FAQ.insert_many([FAQ(**f) for f in initial_faqs])


def get_database() -> AsyncDatabase:
    """Return the initialized MongoDB database instance."""
    if database is None:
        raise RuntimeError("Database has not been initialized.")
    return database
