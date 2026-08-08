"""Core application package."""

from app.core.config import settings
from app.core.dependencies import get_current_user

__all__ = ["get_current_user", "settings"]
