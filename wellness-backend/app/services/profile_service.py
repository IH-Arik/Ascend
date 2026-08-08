"""User profile service."""

import uuid
from typing import Any

import boto3
from fastapi import HTTPException, status
from fastapi import UploadFile

from app.db.repositories.profile_repo import ProfileRepository
from app.db.repositories.user_repo import UserRepository
from app.core.config import settings
from app.models.user import User
from app.schemas.profile import ProfileCreate, ProfileUpdate
from app.services.meta_service import MetaService
from app.utils.response import error_response


class ProfileService:
    """Service for onboarding and profile management."""

    def __init__(self) -> None:
        """Initialize repository dependencies."""
        self.profile_repository = ProfileRepository()
        self.user_repository = UserRepository()
        self.meta_service = MetaService()
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )

    async def get_my_profile(self, current_user: User) -> dict[str, Any]:
        """Return the authenticated user's profile."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )
        return self._serialize_profile(profile)

    async def create_my_profile(
        self,
        current_user: User,
        data: ProfileCreate,
    ) -> dict[str, Any]:
        """Create a profile for the authenticated user."""
        self._validate_profile_metadata(
            data.company, data.department, data.team, data.role
        )
        existing_profile = await self.profile_repository.get_by_user_id(current_user.id)
        if existing_profile is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response("Profile already exists for this user."),
            )

        profile = await self.profile_repository.create_for_user(
            current_user.id,
            data.model_dump(),
        )
        await self.user_repository.update_user(
            str(current_user.id),
            {
                "name": data.name,
                "organization_name": data.company,
                "role": data.role,
            },
        )
        return self._serialize_profile(profile)

    async def update_my_profile(
        self,
        current_user: User,
        data: ProfileUpdate,
    ) -> dict[str, Any]:
        """Update a profile for the authenticated user."""
        update_payload = data.model_dump(exclude_unset=True)
        if not update_payload:
            profile = await self.profile_repository.get_by_user_id(current_user.id)
            if profile is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=error_response("Profile not found for this user."),
                )
            return self._serialize_profile(profile)

        existing_profile = await self.profile_repository.get_by_user_id(current_user.id)
        if existing_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        company = update_payload.get("company", existing_profile.company)
        department = update_payload.get("department", existing_profile.department)
        team = update_payload.get("team", existing_profile.team)
        role = update_payload.get("role", existing_profile.role)
        self._validate_profile_metadata(company, department, team, role)

        profile = await self.profile_repository.update_by_user_id(
            current_user.id,
            update_payload,
        )
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        mirrored_user_fields: dict[str, object] = {}
        if "name" in update_payload:
            mirrored_user_fields["name"] = update_payload["name"]
        if "company" in update_payload:
            mirrored_user_fields["organization_name"] = update_payload["company"]
        if "role" in update_payload:
            mirrored_user_fields["role"] = update_payload["role"]

        if mirrored_user_fields:
            await self.user_repository.update_user(
                str(current_user.id), mirrored_user_fields
            )

        return self._serialize_profile(profile)

    async def upload_profile_image(
        self,
        current_user: User,
        image_file: UploadFile,
    ) -> dict[str, Any]:
        """Upload a profile image to S3 and persist the resulting URL."""
        profile = await self.profile_repository.get_by_user_id(current_user.id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )

        if image_file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    "Unsupported image type.",
                    {"file": "Supported types are JPEG, PNG, and WEBP."},
                ),
            )

        if settings.AWS_ACCESS_KEY_ID.startswith(
            "your-"
        ) or settings.AWS_BUCKET_NAME.startswith("your-"):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_response(
                    "AWS S3 is not configured for profile image uploads."
                ),
            )

        file_bytes = await image_file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response("Uploaded image file is empty."),
            )

        file_extension = (image_file.filename or "image").split(".")[-1].lower()
        object_key = f"profile-images/{current_user.id}/{uuid.uuid4()}.{file_extension}"

        try:
            self.s3_client.put_object(
                Bucket=settings.AWS_BUCKET_NAME,
                Key=object_key,
                Body=file_bytes,
                ContentType=image_file.content_type,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_response(f"S3 Upload failed: {str(exc)}"),
            ) from exc
        image_url = (
            f"https://{settings.AWS_BUCKET_NAME}.s3."
            f"{settings.AWS_REGION}.amazonaws.com/{object_key}"
        )
        updated_profile = await self.profile_repository.update_by_user_id(
            current_user.id,
            {"profile_image_url": image_url},
        )
        if updated_profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response("Profile not found for this user."),
            )
        return {
            "profile_image_url": image_url,
            "profile": self._serialize_profile(updated_profile),
        }

    def _validate_profile_metadata(
        self,
        organization_name: str | None,
        department: str | None,
        team: str | None,
        role: str | None,
    ) -> None:
        """Validate profile organization, department, team, and role selections."""
        try:
            self.meta_service.validate_organization_role(organization_name, role)
            self.meta_service.validate_department(organization_name, department)
            self.meta_service.validate_team(organization_name, department, team)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response(
                    str(exc),
                    {
                        "company": str(exc),
                        "department": str(exc),
                        "team": str(exc),
                        "role": str(exc),
                    },
                ),
            ) from exc

    def _serialize_profile(self, profile: Any) -> dict[str, Any]:
        """Return a response-safe profile payload."""
        return {
            "id": str(profile.id),
            "user_id": str(profile.user_id),
            "name": profile.name,
            "age": profile.age,
            "gender": profile.gender,
            "company": profile.company,
            "department": profile.department,
            "team": profile.team,
            "role": profile.role,
            "height_cm": profile.height_cm,
            "weight_kg": profile.weight_kg,
            "profile_image_url": profile.profile_image_url,
            "contact_number": profile.contact_number,
            "employee_id": profile.employee_id,
            "company_address": profile.company_address,
            "company_logo_url": profile.company_logo_url,
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
