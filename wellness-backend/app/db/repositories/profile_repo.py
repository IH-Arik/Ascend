"""Data access helpers for profile documents."""

from datetime import datetime, timezone

from beanie import PydanticObjectId

from app.models.profile import Profile


class ProfileRepository:
    """Repository for profile document operations."""

    async def get_by_user_id(self, user_id: PydanticObjectId) -> Profile | None:
        """Fetch a profile by owning user identifier."""
        return await Profile.find_one(Profile.user_id == user_id)

    async def create(self, profile: Profile) -> Profile:
        """Persist a new profile document."""
        await profile.insert()
        return profile

    async def list_by_scope(
        self,
        company: str,
        department: str | None = None,
        team: str | None = None,
    ) -> list[Profile]:
        """Return profiles for an organization scope."""
        filters = [Profile.company == company]
        if department is not None:
            filters.append(Profile.department == department)
        if team is not None:
            filters.append(Profile.team == team)

        return await Profile.find(*filters).sort(Profile.name).to_list()

    async def create_for_user(
        self,
        user_id: PydanticObjectId,
        data: dict[str, object],
    ) -> Profile:
        """Create a new profile document for a user."""
        profile = Profile(user_id=user_id, **data)
        await profile.insert()
        return profile

    async def update(self, profile: Profile) -> Profile:
        """Persist changes to an existing profile document."""
        await profile.save()
        return profile

    async def update_by_user_id(
        self,
        user_id: PydanticObjectId,
        data: dict[str, object],
    ) -> Profile | None:
        """Update a profile by user identifier and return the updated document."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return None

        for field_name, value in data.items():
            setattr(profile, field_name, value)

        profile.updated_at = datetime.now(timezone.utc)
        await profile.save()
        return profile

    async def delete_by_user_id(self, user_id: PydanticObjectId) -> bool:
        """Delete a profile by user identifier if it exists."""
        profile = await self.get_by_user_id(user_id)
        if profile is None:
            return False

        await profile.delete()
        return True
