"""Shared API dependencies."""

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.config import Settings, get_settings
from app.core.roles import normalize_role
from app.core.security import decode_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_app_settings() -> Settings:
    """Provide application settings to request handlers."""
    return get_settings()


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Return the authenticated user from a bearer token."""
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
        ) from exc

    if payload.get("token_type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
        )

    user = await User.get(payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    """Create a dependency that restricts access to specific roles."""

    normalized_allowed_roles = {normalize_role(role) for role in allowed_roles}

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        """Return the current user only if their role is allowed."""
        if normalize_role(current_user.role) not in normalized_allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
        return current_user

    return dependency
