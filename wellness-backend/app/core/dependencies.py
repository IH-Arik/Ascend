"""Dependency helpers for authenticated routes."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import decode_token
from app.db.repositories.user_repo import UserRepository
from app.models.user import User
from app.utils.response import error_response

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """Return the authenticated user from the access token."""
    payload = decode_token(token)

    if payload.get("token_type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("Invalid token type for this operation."),
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("Invalid authentication token."),
        )

    repository = UserRepository()
    user = await repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Authenticated user was not found."),
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("This account is inactive."),
        )

    return user


def user_has_leader_access(user: User) -> bool:
    """Return whether the user's role qualifies for leader dashboard access."""
    role = (user.role or "").strip().lower()
    if not role:
        return False

    if user_has_superadmin_access(user):
        return True

    leader_keywords = (
        "lead",
        "manager",
        "head",
        "executive",
        "director",
        "coach",
    )
    return any(keyword in role for keyword in leader_keywords)


def user_has_superadmin_access(user: User) -> bool:
    """Return whether the user's role qualifies for superadmin dashboard access."""
    role = (user.role or "").strip().lower()
    if not role:
        return False

    superadmin_keywords = (
        "super admin",
        "superadmin",
        "platform admin",
        "system admin",
    )
    return any(keyword in role for keyword in superadmin_keywords)


async def get_current_leader_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the authenticated user only if they have leader access."""
    if not user_has_leader_access(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                "Leader dashboard access is restricted to authorized leadership roles."
            ),
        )
    return current_user


async def get_current_superadmin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the authenticated user only if they have superadmin access."""
    if not user_has_superadmin_access(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                "Superadmin dashboard access is restricted to authorized superadmin roles."
            ),
        )
    return current_user
