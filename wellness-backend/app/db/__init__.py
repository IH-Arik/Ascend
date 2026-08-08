"""Database package."""

from app.db.mongodb import get_database, init_db

__all__ = ["get_database", "init_db"]
