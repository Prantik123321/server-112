import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.database.supabase import get_pg_pool
from app.database.mongodb import get_mongodb
from app.services.conversation_service import ConversationService
from app.schemas.messages import MessageCreate, MessageEdit, MessageReaction, MessageResponse, AttachmentSchema

logger = logging.getLogger("nodeshare.services.messages")


class MessageService:

    @classmethod
    async def send_message(
        cls,
        conversation_id: str,
        sender_id: str,
        sender_username: str,
        sender_full_name: str,
        data: MessageCreate
    ) -> MessageResponse:
        # 1. Enforce Rule: Validate conversation membership through Supabase before accessing MongoDB
        is_member = await ConversationService.verify_conversation_membership(conversation_id, sender_id)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to send messages to this conversation."
            )

        mongo_db = get_mongodb()
        if mongo_db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Message storage service (MongoDB) unavailable."
            )

        # 2. Check Idempotency Key (Deduplication)
        if data.idempotency_key:
            existing = await mongo_db["messages"].find_one({"idempotency_key": data.idempotency_key})
            if existing:
                if (
                    existing.get("conversation_id") == conversation_id
                    and existing.get("sender_id") == sender_id
                ):
                    return cls._doc_to_response(existing)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key has already been used for another message."
                )

        now = datetime.now(timezone.utc)
        message_id = str(uuid.uuid4())

        # Reply preview lookup
        reply_preview = None
        if data.reply_to_message_id:
            reply_to_message_id = str(data.reply_to_message_id)
            parent_msg = await mongo_db["messages"].find_one(
                {"message_id": reply_to_message_id, "conversation_id": conversation_id}
            )
            if parent_msg:
                reply_preview = {
                    "message_id": parent_msg["message_id"],
                    "sender_username": parent_msg["sender_username"],
                    "content_snippet": (parent_msg["content"][:100] + "...") if len(parent_msg.get("content", "")) > 100 else parent_msg.get("content", "")
                }

        attachments_data = []
        if data.attachments:
            pool = get_pg_pool()
            if not pool:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

            requested_ids = list({att.file_id for att in data.attachments})
            async with pool.acquire() as conn:
                file_rows = await conn.fetch(
                    """
                    SELECT id, file_path, filename, mime_type, size_bytes
                    FROM file_records
                    WHERE id = ANY($1::uuid[])
                      AND uploader_id = $2
                      AND status = 'completed'
                    """,
                    requested_ids,
                    sender_id,
                )

            files_by_id = {str(row["id"]): row for row in file_rows}
            if len(files_by_id) != len(requested_ids):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="One or more attachments are unavailable or not owned by you."
                )

            attachments_data = [
                {
                    "file_id": str(files_by_id[str(att.file_id)]["id"]),
                    "file_path": files_by_id[str(att.file_id)]["file_path"],
                    "filename": files_by_id[str(att.file_id)]["filename"],
                    "mime_type": files_by_id[str(att.file_id)]["mime_type"],
                    "size_bytes": files_by_id[str(att.file_id)]["size_bytes"],
                }
                for att in data.attachments
            ]

        doc = {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "sender_username": sender_username,
            "sender_full_name": sender_full_name,
            "content": data.content,
            "type": data.type,
            "attachments": attachments_data,
            "reply_to_message_id": str(data.reply_to_message_id) if data.reply_to_message_id else None,
            "reply_preview": reply_preview,
            "reactions": {},
            "is_edited": False,
            "edit_history": [],
            "is_deleted": False,
            "delivery_status": "sent",
            "read_by": [{"user_id": sender_id, "read_at": now}],
            "created_at": now,
            "updated_at": now
        }
        if data.idempotency_key:
            doc["idempotency_key"] = data.idempotency_key

        # 3. Save message in MongoDB
        try:
            await mongo_db["messages"].insert_one(doc)
        except DuplicateKeyError as e:
            if data.idempotency_key:
                existing = await mongo_db["messages"].find_one({"idempotency_key": data.idempotency_key})
                if existing:
                    if (
                        existing.get("conversation_id") == conversation_id
                        and existing.get("sender_id") == sender_id
                    ):
                        return cls._doc_to_response(existing)
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency key has already been used for another message."
                    ) from e
            logger.exception("MongoDB rejected a message insert due to a duplicate key.")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Message could not be stored because of a duplicate identifier."
            ) from e
        except Exception as e:
            logger.exception("Failed to store message in MongoDB.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Message storage service is unavailable."
            ) from e

        # 4. Safe cross-database operation: update conversation last_message_at in Supabase PostgreSQL
        pool = get_pg_pool()
        if pool:
            try:
                async with pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE conversations SET last_message_at = $1, updated_at = $1 WHERE id = $2",
                        now, conversation_id
                    )
                    # Update sender's last read message id
                    await conn.execute(
                        """
                        UPDATE conversation_participants
                        SET last_read_at = $1, last_read_message_id = $2
                        WHERE conversation_id = $3 AND user_id = $4
                        """,
                        now, message_id, conversation_id, sender_id
                    )
            except Exception:
                logger.exception("Message stored, but conversation metadata update failed.")

        return cls._doc_to_response(doc)

    @classmethod
    async def get_messages(
        cls,
        conversation_id: str,
        user_id: str,
        limit: int = 50,
        before_timestamp: Optional[datetime] = None
    ) -> List[MessageResponse]:
        # Enforce Rule: Validate conversation membership through Supabase
        is_member = await ConversationService.verify_conversation_membership(conversation_id, user_id)
        if not is_member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view messages in this conversation."
            )

        mongo_db = get_mongodb()
        if mongo_db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Message storage service (MongoDB) unavailable."
            )

        limit = max(1, min(limit, 100))
        query: Dict[str, Any] = {"conversation_id": conversation_id}
        if before_timestamp:
            query["created_at"] = {"$lt": before_timestamp}

        cursor = mongo_db["messages"].find(query).sort("created_at", -1).limit(limit)
        docs = await cursor.to_list(length=limit)

        # Reverse to chronological order (oldest to newest)
        docs.reverse()
        return [cls._doc_to_response(doc) for doc in docs]

    @classmethod
    async def edit_message(cls, message_id: str, user_id: str, data: MessageEdit) -> MessageResponse:
        mongo_db = get_mongodb()
        if mongo_db is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MongoDB unavailable.")

        msg = await mongo_db["messages"].find_one({"message_id": message_id})
        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

        if msg["sender_id"] != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only edit your own messages."
            )

        if msg.get("is_deleted"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a deleted message.")

        now = datetime.now(timezone.utc)
        edit_entry = {
            "content": msg["content"],
            "edited_at": now
        }

        await mongo_db["messages"].update_one(
            {"message_id": message_id},
            {
                "$set": {
                    "content": data.content,
                    "is_edited": True,
                    "updated_at": now
                },
                "$push": {
                    "edit_history": edit_entry
                }
            }
        )

        updated_msg = await mongo_db["messages"].find_one({"message_id": message_id})
        return cls._doc_to_response(updated_msg)

    @classmethod
    async def delete_message(cls, message_id: str, user_id: str) -> Dict[str, str]:
        mongo_db = get_mongodb()
        if mongo_db is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MongoDB unavailable.")

        msg = await mongo_db["messages"].find_one({"message_id": message_id})
        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

        # Sender can delete their message, or group admin can delete
        is_sender = msg["sender_id"] == user_id
        is_authorized = is_sender

        if not is_authorized:
            # Check if group admin
            conv_id = msg["conversation_id"]
            pool = get_pg_pool()
            if pool:
                async with pool.acquire() as conn:
                    grp = await conn.fetchrow("SELECT id FROM groups WHERE conversation_id = $1", conv_id)
                    if grp:
                        role = await conn.fetchval(
                            "SELECT role FROM group_members WHERE group_id = $1 AND user_id = $2",
                            grp["id"], user_id
                        )
                        if role in ("owner", "admin"):
                            is_authorized = True

        if not is_authorized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

        now = datetime.now(timezone.utc)
        # Soft delete with redaction
        await mongo_db["messages"].update_one(
            {"message_id": message_id},
            {
                "$set": {
                    "is_deleted": True,
                    "content": "This message was deleted.",
                    "attachments": [],
                    "deleted_at": now,
                    "updated_at": now
                }
            }
        )

        return {"message": "Message deleted successfully."}

    @classmethod
    async def react_to_message(cls, message_id: str, user_id: str, emoji: str) -> MessageResponse:
        mongo_db = get_mongodb()
        if mongo_db is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="MongoDB unavailable.")

        msg = await mongo_db["messages"].find_one({"message_id": message_id})
        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

        # Validate membership
        is_member = await ConversationService.verify_conversation_membership(msg["conversation_id"], user_id)
        if not is_member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

        reactions = msg.get("reactions", {})
        users_for_emoji = reactions.get(emoji, [])
        if user_id in users_for_emoji:
            # Toggle off
            users_for_emoji.remove(user_id)
            if not users_for_emoji:
                reactions.pop(emoji, None)
            else:
                reactions[emoji] = users_for_emoji
        else:
            # Toggle on
            users_for_emoji.append(user_id)
            reactions[emoji] = users_for_emoji

        now = datetime.now(timezone.utc)
        await mongo_db["messages"].update_one(
            {"message_id": message_id},
            {"$set": {"reactions": reactions, "updated_at": now}}
        )

        updated_msg = await mongo_db["messages"].find_one({"message_id": message_id})
        return cls._doc_to_response(updated_msg)

    @classmethod
    async def mark_messages_read(cls, conversation_id: str, user_id: str, last_message_id: str) -> Dict[str, str]:
        # Validate membership
        is_member = await ConversationService.verify_conversation_membership(conversation_id, user_id)
        if not is_member:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")

        mongo_db = get_mongodb()
        if mongo_db is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Message storage service (MongoDB) unavailable."
            )

        ref = await mongo_db["messages"].find_one(
            {"message_id": last_message_id, "conversation_id": conversation_id}
        )
        if not ref:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

        now = datetime.now(timezone.utc)
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE conversation_participants
                SET last_read_at = $1, last_read_message_id = $2
                WHERE conversation_id = $3 AND user_id = $4
                """,
                now, last_message_id, conversation_id, user_id
            )

        await mongo_db["messages"].update_many(
            {
                "conversation_id": conversation_id,
                "created_at": {"$lte": ref["created_at"]},
                "read_by.user_id": {"$ne": user_id}
            },
            {
                "$push": {"read_by": {"user_id": user_id, "read_at": now}},
                "$set": {"delivery_status": "read"}
            }
        )

        return {"message": "Messages marked as read."}

    @staticmethod
    def _doc_to_response(doc: Dict[str, Any]) -> MessageResponse:
        attachments = [
            AttachmentSchema(
                file_id=a["file_id"],
                file_path=a["file_path"],
                filename=a["filename"],
                mime_type=a["mime_type"],
                size_bytes=a["size_bytes"]
            )
            for a in doc.get("attachments", [])
        ]

        return MessageResponse(
            message_id=doc["message_id"],
            conversation_id=doc["conversation_id"],
            sender_id=doc["sender_id"],
            sender_username=doc["sender_username"],
            sender_full_name=doc.get("sender_full_name", doc["sender_username"]),
            content=doc.get("content", ""),
            type=doc.get("type", "text"),
            attachments=attachments,
            reply_to_message_id=doc.get("reply_to_message_id"),
            reply_preview=doc.get("reply_preview"),
            reactions=doc.get("reactions", {}),
            is_edited=doc.get("is_edited", False),
            edit_history=doc.get("edit_history", []),
            is_deleted=doc.get("is_deleted", False),
            delivery_status=doc.get("delivery_status", "sent"),
            read_by=doc.get("read_by", []),
            created_at=doc["created_at"],
            updated_at=doc.get("updated_at", doc["created_at"])
        )
