import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status

from app.config.settings import settings
from app.database.supabase import get_pg_pool
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    PasswordChangeRequest,
)
from app.utils.security import (
    hash_password,
    verify_password,
    normalize_username,
    validate_username,
    validate_password_strength,
    create_access_token,
    generate_refresh_token,
    hash_token,
)


class AuthService:

    @staticmethod
    async def register_user(data: RegisterRequest) -> Tuple[TokenResponse, UserResponse]:
        username = normalize_username(data.username)
        if not validate_username(username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username must be 3-30 characters long and contain only lowercase letters, numbers, and underscores."
            )

        valid_pwd, pwd_error = validate_password_strength(data.password)
        if not valid_pwd:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=pwd_error
            )

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable. Please check Supabase configuration."
            )

        pwd_hash = hash_password(data.password)
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Teacher registration: if user signs up as teacher, teacher_verified is ALWAYS False until verified by admin
        is_teacher = bool(data.is_teacher)
        teacher_verified = False  # Strict rule: Never allow self-assigned verification!
        teacher_title = data.teacher_title if is_teacher else None

        async with pool.acquire() as conn:
            # Check unique username
            existing = await conn.fetchval(
                "SELECT id FROM users WHERE username = $1", username
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Username is already taken. Please choose another username."
                )

            # Insert user
            await conn.execute(
                """
                INSERT INTO users (
                    id, username, full_name, password_hash, is_teacher,
                    teacher_verified, teacher_title, is_admin, is_online, last_seen_at, created_at, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                user_id, username, data.full_name.strip(), pwd_hash, is_teacher,
                teacher_verified, teacher_title, False, True, now, now, now
            )

            # Generate tokens
            access_token = create_access_token(user_id, username, is_admin=False, is_teacher=is_teacher)
            raw_refresh, refresh_hash = generate_refresh_token()
            refresh_expiry = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            await conn.execute(
                """
                INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, created_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(uuid.uuid4()), user_id, refresh_hash, refresh_expiry, now
            )

        user_resp = UserResponse(
            id=user_id,
            username=username,
            full_name=data.full_name.strip(),
            avatar_url=None,
            is_teacher=is_teacher,
            teacher_verified=teacher_verified,
            teacher_title=teacher_title,
            is_admin=False,
            status_message=None,
            is_online=True,
            last_seen_at=now,
            created_at=now
        )

        token_resp = TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_resp
        )

        return token_resp, user_resp

    @staticmethod
    async def login_user(data: LoginRequest, user_agent: Optional[str] = None, ip_address: Optional[str] = None) -> TokenResponse:
        username = normalize_username(data.username)
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable. Please check Supabase configuration."
            )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, full_name, password_hash, avatar_url,
                       is_teacher, teacher_verified, teacher_title, is_admin,
                       status_message, is_online, last_seen_at, created_at
                FROM users
                WHERE username = $1
                """,
                username
            )

            if not row or not verify_password(data.password, row["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            user_id = str(row["id"])
            now = datetime.now(timezone.utc)

            # Update presence to online
            await conn.execute(
                "UPDATE users SET is_online = TRUE, last_seen_at = $1 WHERE id = $2",
                now, user_id
            )

            # Issue tokens
            access_token = create_access_token(
                user_id=user_id,
                username=row["username"],
                is_admin=row["is_admin"],
                is_teacher=row["is_teacher"]
            )
            raw_refresh, refresh_hash = generate_refresh_token()
            refresh_expiry = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            await conn.execute(
                """
                INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, user_agent, ip_address, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                str(uuid.uuid4()), user_id, refresh_hash, refresh_expiry, user_agent, ip_address, now
            )

        user_resp = UserResponse(
            id=user_id,
            username=row["username"],
            full_name=row["full_name"],
            avatar_url=row["avatar_url"],
            is_teacher=row["is_teacher"],
            teacher_verified=row["teacher_verified"],
            teacher_title=row["teacher_title"],
            is_admin=row["is_admin"],
            status_message=row["status_message"],
            is_online=True,
            last_seen_at=now,
            created_at=row["created_at"]
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_resp
        )

    @staticmethod
    async def refresh_token(raw_token: str, user_agent: Optional[str] = None, ip_address: Optional[str] = None) -> TokenResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable."
            )

        token_hash = hash_token(raw_token)
        now = datetime.now(timezone.utc)

        async with pool.acquire() as conn:
            token_record = await conn.fetchrow(
                """
                SELECT id, user_id, token_hash, expires_at, revoked
                FROM refresh_tokens
                WHERE token_hash = $1
                """,
                token_hash
            )

            if not token_record:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token."
                )

            # Security: Detect reuse of revoked token (Token family breach protection)
            if token_record["revoked"]:
                # Potential token compromise: Revoke all active sessions for this user
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1",
                    token_record["user_id"]
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Revoked token reuse detected. All sessions terminated for security."
                )

            # Check expiration
            if token_record["expires_at"] < now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has expired."
                )

            user_id = str(token_record["user_id"])
            user_row = await conn.fetchrow(
                """
                SELECT id, username, full_name, avatar_url, is_teacher,
                       teacher_verified, teacher_title, is_admin, status_message,
                       is_online, last_seen_at, created_at
                FROM users WHERE id = $1
                """,
                user_id
            )

            if not user_row:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User account no longer exists."
                )

            # Token Rotation: Revoke old token and issue new token
            new_raw_refresh, new_refresh_hash = generate_refresh_token()
            new_expiry = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

            await conn.execute(
                """
                UPDATE refresh_tokens
                SET revoked = TRUE, replaced_by_token_hash = $1
                WHERE id = $2
                """,
                new_refresh_hash, token_record["id"]
            )

            await conn.execute(
                """
                INSERT INTO refresh_tokens (id, user_id, token_hash, expires_at, user_agent, ip_address, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                str(uuid.uuid4()), user_id, new_refresh_hash, new_expiry, user_agent, ip_address, now
            )

            new_access_token = create_access_token(
                user_id=user_id,
                username=user_row["username"],
                is_admin=user_row["is_admin"],
                is_teacher=user_row["is_teacher"]
            )

        user_resp = UserResponse(
            id=user_id,
            username=user_row["username"],
            full_name=user_row["full_name"],
            avatar_url=user_row["avatar_url"],
            is_teacher=user_row["is_teacher"],
            teacher_verified=user_row["teacher_verified"],
            teacher_title=user_row["teacher_title"],
            is_admin=user_row["is_admin"],
            status_message=user_row["status_message"],
            is_online=user_row["is_online"],
            last_seen_at=user_row["last_seen_at"],
            created_at=user_row["created_at"]
        )

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=user_resp
        )

    @staticmethod
    async def logout_user(user_id: str, raw_refresh_token: Optional[str] = None) -> None:
        pool = get_pg_pool()
        if not pool:
            return

        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            if raw_refresh_token:
                token_hash = hash_token(raw_refresh_token)
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = $1 AND user_id = $2",
                    token_hash, user_id
                )
            else:
                # Revoke all sessions for this user
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1",
                    user_id
                )

            # Update presence to offline
            await conn.execute(
                "UPDATE users SET is_online = FALSE, last_seen_at = $1 WHERE id = $2",
                now, user_id
            )

    @staticmethod
    async def change_password(user_id: str, data: PasswordChangeRequest) -> None:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service unavailable."
            )

        valid_pwd, pwd_error = validate_password_strength(data.new_password)
        if not valid_pwd:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=pwd_error
            )

        async with pool.acquire() as conn:
            user = await conn.fetchrow(
                "SELECT password_hash FROM users WHERE id = $1", user_id
            )
            if not user or not verify_password(data.current_password, user["password_hash"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect."
                )

            new_hash = hash_password(data.new_password)
            now = datetime.now(timezone.utc)

            await conn.execute(
                "UPDATE users SET password_hash = $1, updated_at = $2 WHERE id = $3",
                new_hash, now, user_id
            )

            # Invalidate all active refresh tokens after password change
            await conn.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1",
                user_id
            )
