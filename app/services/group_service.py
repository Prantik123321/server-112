import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status

from app.database.supabase import get_pg_pool
from app.schemas.groups import (
    GroupCreate,
    GroupMemberAdd,
    GroupMemberResponse,
    GroupOwnershipTransfer,
    GroupResponse,
)


class GroupService:

    @classmethod
    async def create_group(cls, creator_id: str, data: GroupCreate) -> GroupResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        now = datetime.now(timezone.utc)
        conv_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Check teacher group requirement
                creator = await conn.fetchrow(
                    "SELECT is_teacher, teacher_verified FROM users WHERE id = $1",
                    creator_id
                )
                if data.is_teacher_group:
                    if not (creator and creator["is_teacher"] and creator["teacher_verified"]):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only verified teachers can create official teacher groups."
                        )

                await conn.execute(
                    """
                    INSERT INTO conversations (id, type, last_message_at, created_at, updated_at)
                    VALUES ($1, 'group', $2, $2, $2)
                    """,
                    conv_id, now
                )

                await conn.execute(
                    """
                    INSERT INTO groups (id, conversation_id, name, description, avatar_url, creator_id, is_teacher_group, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $8)
                    """,
                    group_id, conv_id, data.name, data.description, data.avatar_url,
                    creator_id, data.is_teacher_group, now
                )

                await conn.execute(
                    """
                    INSERT INTO group_members (id, group_id, user_id, role, joined_at)
                    VALUES ($1, $2, $3, 'owner', $4)
                    """,
                    str(uuid.uuid4()), group_id, creator_id, now
                )

                await conn.execute(
                    """
                    INSERT INTO conversation_participants (id, conversation_id, user_id, joined_at, last_read_at)
                    VALUES ($1, $2, $3, $4, $4)
                    """,
                    str(uuid.uuid4()), conv_id, creator_id, now
                )

                if data.member_ids:
                    for member_id in set(data.member_ids):
                        mid = str(member_id)
                        if mid == creator_id:
                            continue
                        m_exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", mid)
                        if m_exists:
                            await conn.execute(
                                """
                                INSERT INTO group_members (id, group_id, user_id, role, joined_at)
                                VALUES ($1, $2, $3, 'member', $4)
                                ON CONFLICT (group_id, user_id) DO NOTHING
                                """,
                                str(uuid.uuid4()), group_id, mid, now
                            )
                            await conn.execute(
                                """
                                INSERT INTO conversation_participants (id, conversation_id, user_id, joined_at, last_read_at)
                                VALUES ($1, $2, $3, $4, $4)
                                ON CONFLICT (conversation_id, user_id) DO NOTHING
                                """,
                                str(uuid.uuid4()), conv_id, mid, now
                            )

        return await cls.get_group_by_id(group_id, creator_id)

    @classmethod
    async def get_group_by_id(cls, group_id: str, current_user_id: str) -> GroupResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            grp = await conn.fetchrow(
                """
                SELECT id, conversation_id, name, description, avatar_url,
                       creator_id, is_teacher_group, created_at, updated_at
                FROM groups
                WHERE id = $1
                """,
                group_id
            )
            if not grp:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")

            # Check membership
            is_member = await conn.fetchval(
                "SELECT 1 FROM group_members WHERE group_id = $1 AND user_id = $2",
                group_id, current_user_id
            )
            if not is_member:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this group."
                )

            # Fetch members
            m_rows = await conn.fetch(
                """
                SELECT gm.role, gm.joined_at, u.id, u.username, u.full_name,
                       u.avatar_url, u.is_teacher, u.teacher_verified
                FROM group_members gm
                JOIN users u ON gm.user_id = u.id
                WHERE gm.group_id = $1
                ORDER BY CASE gm.role WHEN 'owner' THEN 1 WHEN 'admin' THEN 2 ELSE 3 END, u.full_name ASC
                """,
                group_id
            )

        members = [
            GroupMemberResponse(
                user_id=str(r["id"]),
                username=r["username"],
                full_name=r["full_name"],
                avatar_url=r["avatar_url"],
                role=r["role"],
                is_teacher=r["is_teacher"],
                teacher_verified=r["teacher_verified"],
                joined_at=r["joined_at"]
            )
            for r in m_rows
        ]

        return GroupResponse(
            id=str(grp["id"]),
            conversation_id=str(grp["conversation_id"]),
            name=grp["name"],
            description=grp["description"],
            avatar_url=grp["avatar_url"],
            creator_id=str(grp["creator_id"]) if grp["creator_id"] else None,
            is_teacher_group=grp["is_teacher_group"],
            members=members,
            created_at=grp["created_at"],
            updated_at=grp["updated_at"]
        )

    @classmethod
    async def add_member(cls, group_id: str, actor_id: str, req: GroupMemberAdd) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        now = datetime.now(timezone.utc)
        target_user_id = str(req.user_id)
        async with pool.acquire() as conn:
            # 1. Verify actor has permissions (owner or admin)
            actor_role = await conn.fetchval(
                "SELECT role FROM group_members WHERE group_id = $1 AND user_id = $2",
                group_id, actor_id
            )
            if actor_role not in ("owner", "admin"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only group owners and admins can add members."
                )

            # 2. Verify target user exists
            target_exists = await conn.fetchval("SELECT 1 FROM users WHERE id = $1", target_user_id)
            if not target_exists:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target user not found.")

            # 3. Check already in group
            in_group = await conn.fetchval(
                "SELECT 1 FROM group_members WHERE group_id = $1 AND user_id = $2",
                group_id, target_user_id
            )
            if in_group:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already in this group.")

            grp = await conn.fetchrow("SELECT conversation_id, name FROM groups WHERE id = $1", group_id)
            conv_id = str(grp["conversation_id"])

            # 4. Insert into group_members and conversation_participants
            await conn.execute(
                """
                INSERT INTO group_members (id, group_id, user_id, role, joined_at)
                VALUES ($1, $2, $3, $4, $5)
                """,
                str(uuid.uuid4()), group_id, target_user_id, req.role, now
            )
            await conn.execute(
                """
                INSERT INTO conversation_participants (id, conversation_id, user_id, joined_at, last_read_at)
                VALUES ($1, $2, $3, $4, $4)
                ON CONFLICT (conversation_id, user_id) DO NOTHING
                """,
                str(uuid.uuid4()), conv_id, target_user_id, now
            )

            # 5. Notify added user
            await conn.execute(
                """
                INSERT INTO notifications (id, user_id, type, title, body, data, is_read, created_at)
                VALUES ($1, $2, 'group_invite', 'Added to Group', $3, $4, FALSE, $5)
                """,
                str(uuid.uuid4()),
                target_user_id,
                f"You were added to '{grp['name']}'.",
                {"group_id": group_id, "conversation_id": conv_id},
                now
            )

        return {"message": "Member added to group successfully."}

    @classmethod
    async def transfer_ownership(
        cls,
        group_id: str,
        actor_id: str,
        req: GroupOwnershipTransfer,
    ) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")
        target_user_id = str(req.user_id)
        if actor_id == target_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You are already the group owner.")

        async with pool.acquire() as conn:
            async with conn.transaction():
                actor_role = await conn.fetchval(
                    "SELECT role FROM group_members WHERE group_id = $1 AND user_id = $2 FOR UPDATE",
                    group_id, actor_id
                )
                if actor_role != "owner":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Only the current group owner can transfer ownership."
                    )

                target_role = await conn.fetchval(
                    "SELECT role FROM group_members WHERE group_id = $1 AND user_id = $2 FOR UPDATE",
                    group_id, target_user_id
                )
                if not target_role:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="The new owner must already be a group member."
                    )

                await conn.execute(
                    "UPDATE group_members SET role = 'admin' WHERE group_id = $1 AND user_id = $2",
                    group_id, actor_id
                )
                await conn.execute(
                    "UPDATE group_members SET role = 'owner' WHERE group_id = $1 AND user_id = $2",
                    group_id, target_user_id
                )

        return {"message": "Group ownership transferred successfully."}

    @classmethod
    async def remove_member(cls, group_id: str, actor_id: str, target_user_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            # Check actor role
            actor_role = await conn.fetchval(
                "SELECT role FROM group_members WHERE group_id = $1 AND user_id = $2",
                group_id, actor_id
            )
            target_role = await conn.fetchval(
                "SELECT role FROM group_members WHERE group_id = $1 AND user_id = $2",
                group_id, target_user_id
            )

            if not target_role:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this group.")

            # Permissions:
            # Self-removal (leaving group) is allowed for any non-sole-owner
            is_self = actor_id == target_user_id
            if not is_self:
                if actor_role not in ("owner", "admin"):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
                if target_role == "owner":
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot remove group owner.")
                if actor_role == "admin" and target_role == "admin":
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admins cannot remove other admins.")
            elif target_role == "owner":
                owner_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM group_members WHERE group_id = $1 AND role = 'owner'",
                    group_id
                )
                if owner_count <= 1:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Transfer group ownership before leaving the group."
                    )

            grp = await conn.fetchrow("SELECT conversation_id FROM groups WHERE id = $1", group_id)
            conv_id = str(grp["conversation_id"])

            # Delete member
            await conn.execute(
                "DELETE FROM group_members WHERE group_id = $1 AND user_id = $2",
                group_id, target_user_id
            )
            await conn.execute(
                "DELETE FROM conversation_participants WHERE conversation_id = $1 AND user_id = $2",
                conv_id, target_user_id
            )

        return {"message": "Member removed from group successfully."}
