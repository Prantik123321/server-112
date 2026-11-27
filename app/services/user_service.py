from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status
from app.database.supabase import get_pg_pool
from app.schemas.auth import UserResponse
from app.schemas.users import UserUpdateRequest, TeacherVerifyRequest


class UserService:

    @staticmethod
    async def get_user_by_id(user_id: str) -> UserResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, full_name, avatar_url, is_teacher,
                       teacher_verified, teacher_title, is_admin, status_message,
                       is_online, last_seen_at, created_at
                FROM users
                WHERE id = $1
                """,
                user_id
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        return UserResponse(
            id=str(row["id"]),
            username=row["username"],
            full_name=row["full_name"],
            avatar_url=row["avatar_url"],
            is_teacher=row["is_teacher"],
            teacher_verified=row["teacher_verified"],
            teacher_title=row["teacher_title"],
            is_admin=row["is_admin"],
            status_message=row["status_message"],
            is_online=row["is_online"],
            last_seen_at=row["last_seen_at"],
            created_at=row["created_at"]
        )

    @staticmethod
    async def update_profile(user_id: str, data: UserUpdateRequest) -> UserResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        updates = []
        params = []
        idx = 1

        if data.full_name is not None:
            updates.append(f"full_name = ${idx}")
            params.append(data.full_name.strip())
            idx += 1

        if data.avatar_url is not None:
            updates.append(f"avatar_url = ${idx}")
            params.append(data.avatar_url)
            idx += 1

        if data.status_message is not None:
            updates.append(f"status_message = ${idx}")
            params.append(data.status_message)
            idx += 1

        if data.teacher_title is not None:
            updates.append(f"teacher_title = ${idx}")
            params.append(data.teacher_title)
            idx += 1

        if not updates:
            return await UserService.get_user_by_id(user_id)

        now = datetime.now(timezone.utc)
        updates.append(f"updated_at = ${idx}")
        params.append(now)
        idx += 1

        params.append(user_id)
        sql = f"UPDATE users SET {', '.join(updates)} WHERE id = ${idx} RETURNING *"

        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *params)

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        return UserResponse(
            id=str(row["id"]),
            username=row["username"],
            full_name=row["full_name"],
            avatar_url=row["avatar_url"],
            is_teacher=row["is_teacher"],
            teacher_verified=row["teacher_verified"],
            teacher_title=row["teacher_title"],
            is_admin=row["is_admin"],
            status_message=row["status_message"],
            is_online=row["is_online"],
            last_seen_at=row["last_seen_at"],
            created_at=row["created_at"]
        )

    @staticmethod
    async def verify_teacher(target_user_id: str, req: TeacherVerifyRequest) -> UserResponse:
        """
        Verify or unverify a teacher account.
        Strict rule: Must be performed by an admin, never self-assigned.
        """
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            target = await conn.fetchrow("SELECT is_teacher FROM users WHERE id = $1", target_user_id)
            if not target:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found."
                )
            if not target["is_teacher"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Target user is not registered as a teacher."
                )

            row = await conn.fetchrow(
                """
                UPDATE users
                SET teacher_verified = $1, updated_at = $2
                WHERE id = $3
                RETURNING *
                """,
                req.teacher_verified, now, target_user_id
            )

        return UserResponse(
            id=str(row["id"]),
            username=row["username"],
            full_name=row["full_name"],
            avatar_url=row["avatar_url"],
            is_teacher=row["is_teacher"],
            teacher_verified=row["teacher_verified"],
            teacher_title=row["teacher_title"],
            is_admin=row["is_admin"],
            status_message=row["status_message"],
            is_online=row["is_online"],
            last_seen_at=row["last_seen_at"],
            created_at=row["created_at"]
        )

    @staticmethod
    async def update_presence(user_id: str, is_online: bool) -> None:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )
        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET is_online = $1, last_seen_at = $2 WHERE id = $3",
                is_online, now, user_id
            )
