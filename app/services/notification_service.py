import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status

from app.database.supabase import get_pg_pool
from app.schemas.notifications import NotificationResponse


class NotificationService:

    @classmethod
    async def get_notifications(cls, user_id: str, limit: int = 50, unread_only: bool = False) -> List[NotificationResponse]:
        pool = get_pg_pool()
        if not pool:
            return []

        limit = max(1, min(limit, 100))
        filter_sql = "AND is_read = FALSE" if unread_only else ""

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, user_id, type, title, body, data, is_read, created_at
                FROM notifications
                WHERE user_id = $1 {filter_sql}
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id, limit
            )

        out = []
        for r in rows:
            data_val = r["data"]
            if isinstance(data_val, str):
                try:
                    data_val = json.loads(data_val)
                except Exception:
                    data_val = {}
            elif data_val is None:
                data_val = {}

            out.append(
                NotificationResponse(
                    id=str(r["id"]),
                    user_id=str(r["user_id"]),
                    type=r["type"],
                    title=r["title"],
                    body=r["body"],
                    data=data_val,
                    is_read=bool(r["is_read"]),
                    created_at=r["created_at"]
                )
            )
        return out

    @classmethod
    async def mark_as_read(cls, notification_id: str, user_id: str) -> NotificationResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE notifications
                SET is_read = TRUE
                WHERE id = $1 AND user_id = $2
                RETURNING *
                """,
                notification_id, user_id
            )

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")

        data_val = row["data"]
        if isinstance(data_val, str):
            try:
                data_val = json.loads(data_val)
            except Exception:
                data_val = {}

        return NotificationResponse(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            type=row["type"],
            title=row["title"],
            body=row["body"],
            data=data_val or {},
            is_read=bool(row["is_read"]),
            created_at=row["created_at"]
        )
