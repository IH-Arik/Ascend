"""Data access helpers for editable app settings."""

from datetime import datetime, timezone

from app.models.app_setting import AppSetting


class AppSettingRepository:
    """Repository for app settings document operations."""

    async def get_by_key(self, key: str) -> AppSetting | None:
        """Fetch a setting document by key."""
        return await AppSetting.find_one(AppSetting.key == key)

    async def upsert(
        self,
        key: str,
        title: str,
        content: str,
        image_url: str | None = None,
        updated_by_user_id: object | None = None,
    ) -> AppSetting:
        """Create or update a setting document."""
        setting = await self.get_by_key(key)
        if setting is None:
            setting = AppSetting(
                key=key,
                title=title,
                content=content,
                image_url=image_url,
                updated_by_user_id=updated_by_user_id,
            )
            await setting.insert()
            return setting

        setting.title = title
        setting.content = content
        setting.image_url = image_url
        setting.updated_by_user_id = updated_by_user_id
        setting.updated_at = datetime.now(timezone.utc)
        await setting.save()
        return setting
