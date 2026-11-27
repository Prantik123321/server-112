# app/services/conversation_service.py
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from fastapi import HTTPException, status

from app.database.supabase import get_pg_pool
from app.database.mongodb import get_mongodb
from app.schemas.conversations import (
    ConversationResponse,
    ConversationParticipant,
)


class ConversationService:

    @classmethod
    async def get_or_create_direct_conversation(
        cls,
        user_id_1: str,
        user_id_2: str
    ) -> ConversationResponse:

        if user_id_1 == user_id_2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot start a direct conversation with yourself."
            )

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        async with pool.acquire() as conn:
            # 1. Block check
            block = await conn.fetchval(
                """
                SELECT 1 FROM user_blocks
                WHERE (blocker_id = $1 AND blocked_id = $2)
                   OR (blocker_id = $2 AND blocked_id = $1)
                """,
                user_id_1, user_id_2
            )
            if block:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot start conversation with this user."
                )

            # 2. Existing direct conversation check
            existing_conv_id = await conn.fetchval(
                """
                SELECT cp1.conversation_id
                FROM conversation_participants cp1
                JOIN conversation_participants cp2
                    ON cp1.conversation_id = cp2.conversation_id
                JOIN conversations c
                    ON cp1.conversation_id = c.id
                WHERE c.type = 'direct'
                  AND cp1.user_id = $1
                  AND cp2.user_id = $2
                """,
                user_id_1, user_id_2
            )

            if existing_conv_id:
                return await cls.get_conversation_by_id(
                    str(existing_conv_id), user_id_1
                )

            # 3. Create new conversation
            now = datetime.now(timezone.utc)
            new_conv_id = str(uuid.uuid4())

            await conn.execute(
                """
                INSERT INTO conversations
                    (id, type, last_message_at, created_at, updated_at)
                VALUES ($1, 'direct', $2, $2, $2)
                """,
                new_conv_id, now
            )

            # 4. Insert participants - SEPARATE QUERIES (Fix for placeholder mismatch)
            p1_id = str(uuid.uuid4())
            p2_id = str(uuid.uuid4())

            await conn.execute(
                """
                INSERT INTO conversation_participants
                    (id, conversation_id, user_id, joined_at)
                VALUES ($1, $2, $3, $4)
                """,
                p1_id, new_conv_id, user_id_1, now
            )

            await conn.execute(
                """
                INSERT INTO conversation_participants
                    (id, conversation_id, user_id, joined_at)
                VALUES ($1, $2, $3, $4)
                """,
                p2_id, new_conv_id, user_id_2, now
            )

        return await cls.get_conversation_by_id(new_conv_id, user_id_1)

    @classmethod
    async def get_user_conversations(cls, user_id: str) -> List[ConversationResponse]:

        pool = get_pg_pool()
        if not pool:
            return []

        async with pool.acquire() as conn:
            conv_rows = await conn.fetch(
                """
                SELECT c.id, c.type, c.last_message_at, c.created_at
                FROM conversations c
                JOIN conversation_participants cp ON c.id = cp.conversation_id
                WHERE cp.user_id = $1
                ORDER BY c.last_message_at DESC
                """,
                user_id
            )

        out = []
        for r in conv_rows:
            conv_resp = await cls.get_conversation_by_id(str(r["id"]), user_id)
            out.append(conv_resp)

        return out

    @classmethod
    async def get_conversation_by_id(
        cls,
        conversation_id: str,
        current_user_id: str
    ) -> ConversationResponse:

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        async with pool.acquire() as conn:
            conv = await conn.fetchrow(
                """
                SELECT id, type, last_message_at, created_at
                FROM conversations
                WHERE id = $1
                """,
                conversation_id
            )
            if not conv:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found."
                )

            is_participant = await conn.fetchval(
                """
                SELECT 1 FROM conversation_participants
                WHERE conversation_id = $1 AND user_id = $2
                """,
                conversation_id, current_user_id
            )
            if not is_participant:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to access this conversation."
                )

            part_rows = await conn.fetch(
                """
                SELECT
                    u.id, u.username, u.full_name, u.avatar_url, u.is_online,
                    cp.last_read_message_id
                FROM conversation_participants cp
                JOIN users u ON cp.user_id = u.id
                WHERE cp.conversation_id = $1
                """,
                conversation_id
            )

            group_details = None
            if conv["type"] == "group":
                grp = await conn.fetchrow(
                    """
                    SELECT id, name, description, avatar_url, creator_id,
                           is_teacher_group, created_at
                    FROM groups
                    WHERE conversation_id = $1
                    """,
                    conversation_id
                )
                if grp:
                    group_details = {
                        "group_id": str(grp["id"]),
                        "name": grp["name"],
                        "description": grp["description"],
                        "avatar_url": grp["avatar_url"],
                        "creator_id": str(grp["creator_id"]) if grp["creator_id"] else None,
                        "is_teacher_group": grp["is_teacher_group"]
                    }

        participants = [
            ConversationParticipant(
                user_id=str(p["id"]),
                username=p["username"],
                full_name=p["full_name"],
                avatar_url=p["avatar_url"],
                is_online=bool(p["is_online"]),
                last_read_message_id=p["last_read_message_id"]
            )
            for p in part_rows
        ]

        # Fetch last message from MongoDB
        last_message = None
        unread_count = 0
        mongo_db = get_mongodb()

        if mongo_db is not None:
            try:
                last_msg_doc = await mongo_db["messages"].find_one(
                    {"conversation_id": conversation_id, "is_deleted": False},
                    sort=[("created_at", -1)]
                )
                if last_msg_doc:
                    last_message = {
                        "message_id": last_msg_doc.get("message_id"),
                        "content": last_msg_doc.get("content"),
                        "sender_username": last_msg_doc.get("sender_username"),
                        "type": last_msg_doc.get("type"),
                        "created_at": last_msg_doc.get("created_at")
                    }

                curr_part = next(
                    (p for p in part_rows if str(p["id"]) == current_user_id),
                    None
                )
                last_read_msg_id = curr_part["last_read_message_id"] if curr_part else None

                if last_read_msg_id:
                    ref_msg = await mongo_db["messages"].find_one(
                        {"message_id": last_read_msg_id}
                    )
                    if ref_msg:
                        unread_count = await mongo_db["messages"].count_documents({
                            "conversation_id": conversation_id,
                            "created_at": {"$gt": ref_msg["created_at"]},
                            "sender_id": {"$ne": current_user_id},
                            "is_deleted": False
                        })
                else:
                    unread_count = await mongo_db["messages"].count_documents({
                        "conversation_id": conversation_id,
                        "sender_id": {"$ne": current_user_id},
                        "is_deleted": False
                    })
            except Exception:
                pass

        return ConversationResponse(
            id=str(conv["id"]),
            type=conv["type"],
            participants=participants,
            last_message=last_message,
            last_message_at=conv["last_message_at"],
            unread_count=unread_count,
            group_details=group_details,
            created_at=conv["created_at"]
        )

    @classmethod
    async def verify_conversation_membership(
        cls,
        conversation_id: str,
        user_id: str
    ) -> bool:
        """Validate conversation membership through Supabase before accessing MongoDB messages."""
        pool = get_pg_pool()
        if not pool:
            return False
        async with pool.acquire() as conn:
            is_member = await conn.fetchval(
                """
                SELECT 1 FROM conversation_participants
                WHERE conversation_id = $1 AND user_id = $2
                """,
                conversation_id, user_id
            )
        return bool(is_member)
