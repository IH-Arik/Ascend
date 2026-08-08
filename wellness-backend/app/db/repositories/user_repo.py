"""Data access helpers for user documents."""

from datetime import datetime
from typing import Any

from beanie import PydanticObjectId

from app.models.user import User


class UserRepository:
    """Repository for user document operations."""

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by email address."""
        return await User.find_one({"email": email})

    async def get_by_id(self, user_id: str) -> User | None:
        """Fetch a user by identifier."""
        try:
            object_id = PydanticObjectId(user_id)
        except Exception:
            return None
        return await User.get(object_id)

    async def create_user(self, data: dict[str, Any]) -> User:
        """Persist a new user document."""
        user = User(**data)
        await user.insert()
        return user

    async def update_user(self, user_id: str, data: dict[str, Any]) -> User:
        """Update an existing user document and return the refreshed record."""
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found.")

        for field_name, value in data.items():
            setattr(user, field_name, value)

        user.updated_at = datetime.utcnow()
        await user.save()
        return user

    async def deactivate_user(self, user_id: str) -> User | None:
        """Soft-delete a user by marking the account inactive."""
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        user.is_active = False
        user.updated_at = datetime.utcnow()
        await user.save()
        return user

    async def delete_user(self, user_id: str) -> User | None:
        """Delete a user document permanently."""
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        await user.delete()
        return user
