import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status

from app.database.supabase import get_pg_pool
from app.schemas.auth import UserResponse
from app.schemas.friends import FriendRequestResponse, FriendshipResponse


class FriendService:

    @staticmethod
    def _row_to_user_response(r: Dict[str, Any], prefix: str = "") -> UserResponse:
        return UserResponse(
            id=str(r[f"{prefix}id"]),
            username=r[f"{prefix}username"],
            full_name=r[f"{prefix}full_name"],
            avatar_url=r[f"{prefix}avatar_url"],
            is_teacher=bool(r[f"{prefix}is_teacher"]),
            teacher_verified=bool(r[f"{prefix}teacher_verified"]),
            teacher_title=r.get(f"{prefix}teacher_title"),
            is_admin=bool(r.get(f"{prefix}is_admin", False)),
            status_message=r.get(f"{prefix}status_message"),
            is_online=bool(r.get(f"{prefix}is_online", False)),
            last_seen_at=r[f"{prefix}last_seen_at"],
            created_at=r[f"{prefix}created_at"]
        )

    @classmethod
    async def send_friend_request(cls, sender_id: str, receiver_id: str) -> FriendRequestResponse:
        if sender_id == receiver_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot send a friend request to yourself."
            )

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable."
            )

        now = datetime.now(timezone.utc)
        request_id = str(uuid.uuid4())

        async with pool.acquire() as conn:
            # 1. Check receiver exists
            receiver = await conn.fetchrow("SELECT id FROM users WHERE id = $1", receiver_id)
            if not receiver:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Target user not found."
                )

            # 2. Check blocks
            block = await conn.fetchval(
                """
                SELECT 1 FROM user_blocks 
                WHERE (blocker_id = $1 AND blocked_id = $2)
                   OR (blocker_id = $2 AND blocked_id = $1)
                """,
                sender_id, receiver_id
            )
            if block:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot send friend request to this user."
                )

            # 3. Check already friends
            u1, u2 = sorted([sender_id, receiver_id])
            already_friends = await conn.fetchval(
                "SELECT 1 FROM friendships WHERE user_id = $1 AND friend_id = $2",
                u1, u2
            )
            if already_friends:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already friends with this user."
                )

            # 4. Check existing pending request
            existing_req = await conn.fetchrow(
                """
                SELECT id, sender_id, receiver_id, status FROM friend_requests
                WHERE ((sender_id = $1 AND receiver_id = $2) OR (sender_id = $2 AND receiver_id = $1))
                  AND status = 'pending'
                """,
                sender_id, receiver_id
            )
            if existing_req:
                if str(existing_req["sender_id"]) == sender_id:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Friend request already sent and pending."
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="This user has already sent you a friend request. You can accept it."
                    )

            # 5. Insert friend request
            await conn.execute(
                """
                INSERT INTO friend_requests (id, sender_id, receiver_id, status, created_at, updated_at)
                VALUES ($1, $2, $3, 'pending', $4, $4)
                """,
                request_id, sender_id, receiver_id, now
            )

            # Insert notification for receiver
            sender_user = await conn.fetchrow("SELECT full_name FROM users WHERE id = $1", sender_id)
            sender_name = sender_user["full_name"] if sender_user else "Someone"
            await conn.execute(
                """
                INSERT INTO notifications (id, user_id, type, title, body, data, is_read, created_at)
                VALUES ($1, $2, 'friend_request', 'New Friend Request', $3, $4, FALSE, $5)
                """,
                str(uuid.uuid4()),
                receiver_id,
                f"{sender_name} sent you a friend request.",
                {"request_id": request_id, "sender_id": sender_id},
                now
            )

        return await cls.get_friend_request_by_id(request_id)

    @classmethod
    async def get_friend_request_by_id(cls, request_id: str) -> FriendRequestResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    fr.id AS req_id, fr.status AS req_status, fr.created_at AS req_created_at,
                    s.id AS s_id, s.username AS s_username, s.full_name AS s_full_name, s.avatar_url AS s_avatar_url,
                    s.is_teacher AS s_is_teacher, s.teacher_verified AS s_teacher_verified, s.teacher_title AS s_teacher_title,
                    s.is_admin AS s_is_admin, s.status_message AS s_status_message, s.is_online AS s_is_online,
                    s.last_seen_at AS s_last_seen_at, s.created_at AS s_created_at,
                    r.id AS r_id, r.username AS r_username, r.full_name AS r_full_name, r.avatar_url AS r_avatar_url,
                    r.is_teacher AS r_is_teacher, r.teacher_verified AS r_teacher_verified, r.teacher_title AS r_teacher_title,
                    r.is_admin AS r_is_admin, r.status_message AS r_status_message, r.is_online AS r_is_online,
                    r.last_seen_at AS r_last_seen_at, r.created_at AS r_created_at
                FROM friend_requests fr
                JOIN users s ON fr.sender_id = s.id
                JOIN users r ON fr.receiver_id = r.id
                WHERE fr.id = $1
                """,
                request_id
            )

        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found.")

        sender = cls._row_to_user_response(dict(row), prefix="s_")
        receiver = cls._row_to_user_response(dict(row), prefix="r_")

        return FriendRequestResponse(
            id=str(row["req_id"]),
            sender=sender,
            receiver=receiver,
            status=row["req_status"],
            created_at=row["req_created_at"]
        )

    @classmethod
    async def accept_friend_request(cls, request_id: str, current_user_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            req = await conn.fetchrow(
                "SELECT id, sender_id, receiver_id, status FROM friend_requests WHERE id = $1",
                request_id
            )
            if not req:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found.")

            if str(req["receiver_id"]) != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to accept this friend request."
                )

            if req["status"] != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot accept request with status '{req['status']}'."
                )

            sender_id = str(req["sender_id"])
            u1, u2 = sorted([sender_id, current_user_id])

            # Update request status to accepted
            await conn.execute(
                "UPDATE friend_requests SET status = 'accepted', updated_at = $1 WHERE id = $2",
                now, request_id
            )

            # Insert friendship
            await conn.execute(
                """
                INSERT INTO friendships (id, user_id, friend_id, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, friend_id) DO NOTHING
                """,
                str(uuid.uuid4()), u1, u2, now
            )

            # Notify sender
            receiver_user = await conn.fetchrow("SELECT full_name FROM users WHERE id = $1", current_user_id)
            receiver_name = receiver_user["full_name"] if receiver_user else "Someone"
            await conn.execute(
                """
                INSERT INTO notifications (id, user_id, type, title, body, data, is_read, created_at)
                VALUES ($1, $2, 'friend_accepted', 'Friend Request Accepted', $3, $4, FALSE, $5)
                """,
                str(uuid.uuid4()),
                sender_id,
                f"{receiver_name} accepted your friend request.",
                {"friend_id": current_user_id},
                now
            )

        return {"message": "Friend request accepted successfully."}

    @classmethod
    async def reject_friend_request(cls, request_id: str, current_user_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            req = await conn.fetchrow(
                "SELECT id, receiver_id, status FROM friend_requests WHERE id = $1",
                request_id
            )
            if not req:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found.")

            if str(req["receiver_id"]) != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not authorized to reject this friend request."
                )

            if req["status"] != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot reject request with status '{req['status']}'."
                )

            await conn.execute(
                "UPDATE friend_requests SET status = 'rejected', updated_at = $1 WHERE id = $2",
                now, request_id
            )

        return {"message": "Friend request rejected."}

    @classmethod
    async def cancel_friend_request(cls, request_id: str, current_user_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        now = datetime.now(timezone.utc)
        async with pool.acquire() as conn:
            req = await conn.fetchrow(
                "SELECT id, sender_id, status FROM friend_requests WHERE id = $1",
                request_id
            )
            if not req:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend request not found.")

            if str(req["sender_id"]) != current_user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only cancel requests you sent."
                )

            if req["status"] != "pending":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot cancel request with status '{req['status']}'."
                )

            await conn.execute(
                "UPDATE friend_requests SET status = 'cancelled', updated_at = $1 WHERE id = $2",
                now, request_id
            )

        return {"message": "Friend request cancelled."}

    @classmethod
    async def remove_friend(cls, current_user_id: str, friend_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        u1, u2 = sorted([current_user_id, friend_id])
        async with pool.acquire() as conn:
            deleted = await conn.execute(
                "DELETE FROM friendships WHERE user_id = $1 AND friend_id = $2",
                u1, u2
            )
            if deleted == "DELETE 0":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friendship not found.")

        return {"message": "Friend removed successfully."}

    @classmethod
    async def get_friends_list(cls, user_id: str) -> List[FriendshipResponse]:
        pool = get_pg_pool()
        if not pool:
            return []

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    f.id AS friendship_id, f.created_at AS since,
                    u.id AS u_id, u.username AS u_username, u.full_name AS u_full_name,
                    u.avatar_url AS u_avatar_url, u.is_teacher AS u_is_teacher,
                    u.teacher_verified AS u_teacher_verified, u.teacher_title AS u_teacher_title,
                    u.is_admin AS u_is_admin, u.status_message AS u_status_message,
                    u.is_online AS u_is_online, u.last_seen_at AS u_last_seen_at,
                    u.created_at AS u_created_at
                FROM friendships f
                JOIN users u ON (CASE WHEN f.user_id = $1 THEN f.friend_id ELSE f.user_id END) = u.id
                WHERE f.user_id = $1 OR f.friend_id = $1
                ORDER BY u.full_name ASC
                """,
                user_id
            )

        out = []
        for r in rows:
            friend_user = cls._row_to_user_response(dict(r), prefix="u_")
            out.append(
                FriendshipResponse(
                    friendship_id=str(r["friendship_id"]),
                    friend=friend_user,
                    since=r["since"]
                )
            )
        return out

    @classmethod
    async def get_pending_requests(cls, user_id: str, direction: str = "received") -> List[FriendRequestResponse]:
        """direction: 'received' (incoming requests) or 'sent' (outgoing requests)."""
        pool = get_pg_pool()
        if not pool:
            return []

        filter_clause = "fr.receiver_id = $1" if direction == "received" else "fr.sender_id = $1"

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT 
                    fr.id AS req_id, fr.status AS req_status, fr.created_at AS req_created_at,
                    s.id AS s_id, s.username AS s_username, s.full_name AS s_full_name, s.avatar_url AS s_avatar_url,
                    s.is_teacher AS s_is_teacher, s.teacher_verified AS s_teacher_verified, s.teacher_title AS s_teacher_title,
                    s.is_admin AS s_is_admin, s.status_message AS s_status_message, s.is_online AS s_is_online,
                    s.last_seen_at AS s_last_seen_at, s.created_at AS s_created_at,
                    r.id AS r_id, r.username AS r_username, r.full_name AS r_full_name, r.avatar_url AS r_avatar_url,
                    r.is_teacher AS r_is_teacher, r.teacher_verified AS r_teacher_verified, r.teacher_title AS r_teacher_title,
                    r.is_admin AS r_is_admin, r.status_message AS r_status_message, r.is_online AS r_is_online,
                    r.last_seen_at AS r_last_seen_at, r.created_at AS r_created_at
                FROM friend_requests fr
                JOIN users s ON fr.sender_id = s.id
                JOIN users r ON fr.receiver_id = r.id
                WHERE {filter_clause} AND fr.status = 'pending'
                ORDER BY fr.created_at DESC
                """,
                user_id
            )

        out = []
        for r in rows:
            sender = cls._row_to_user_response(dict(r), prefix="s_")
            receiver = cls._row_to_user_response(dict(r), prefix="r_")
            out.append(
                FriendRequestResponse(
                    id=str(r["req_id"]),
                    sender=sender,
                    receiver=receiver,
                    status=r["req_status"],
                    created_at=r["req_created_at"]
                )
            )
        return out

    @classmethod
    async def block_user(cls, blocker_id: str, blocked_id: str) -> Dict[str, str]:
        if blocker_id == blocked_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot block yourself.")

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        now = datetime.now(timezone.utc)
        u1, u2 = sorted([blocker_id, blocked_id])

        async with pool.acquire() as conn:
            # 1. Insert block
            await conn.execute(
                """
                INSERT INTO user_blocks (id, blocker_id, blocked_id, created_at)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (blocker_id, blocked_id) DO NOTHING
                """,
                str(uuid.uuid4()), blocker_id, blocked_id, now
            )

            # 2. Break any existing friendship
            await conn.execute(
                "DELETE FROM friendships WHERE user_id = $1 AND friend_id = $2",
                u1, u2
            )

            # 3. Cancel any pending requests
            await conn.execute(
                """
                UPDATE friend_requests SET status = 'cancelled', updated_at = $1
                WHERE ((sender_id = $2 AND receiver_id = $3) OR (sender_id = $3 AND receiver_id = $2))
                  AND status = 'pending'
                """,
                now, blocker_id, blocked_id
            )

        return {"message": "User blocked successfully."}

    @classmethod
    async def unblock_user(cls, blocker_id: str, blocked_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            deleted = await conn.execute(
                "DELETE FROM user_blocks WHERE blocker_id = $1 AND blocked_id = $2",
                blocker_id, blocked_id
            )
            if deleted == "DELETE 0":
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not blocked.")

        return {"message": "User unblocked successfully."}
