from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config.settings import settings
from app.utils.security import decode_access_token
from app.database.supabase import get_pg_pool

# HTTP Bearer scheme
security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> Dict[str, Any]:
    """Dependency to retrieve and validate the authenticated user from JWT token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fetch user from PostgreSQL
    pool = get_pg_pool()
    if not pool:
        if settings.ENVIRONMENT == "testing":
            return {
                "id": str(user_id),
                "username": payload.get("username", "testuser"),
                "full_name": "Test User",
                "is_admin": payload.get("is_admin", False),
                "is_teacher": payload.get("is_teacher", False),
                "teacher_verified": False,
            }
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service unavailable.",
        )

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, username, full_name, avatar_url, is_teacher, teacher_verified,
                   teacher_title, is_admin, status_message, is_online, last_seen_at, created_at
            FROM users
            WHERE id = $1
            """,
            user_id
        )

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_dict = dict(row)
    user_dict["id"] = str(user_dict["id"])
    return user_dict


async def get_current_admin(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Ensure the authenticated user is an authorized administrator."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required for this action."
        )
    return current_user


async def get_current_verified_teacher(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Ensure the authenticated user is a verified teacher."""
    if not (current_user.get("is_teacher") and current_user.get("teacher_verified")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verified teacher account required."
        )
    return current_user
