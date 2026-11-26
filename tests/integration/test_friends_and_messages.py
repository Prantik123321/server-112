import pytest
from app.services.friend_service import FriendService
from app.services.message_service import MessageService
from app.services.group_service import GroupService
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_friend_request_self_prevention():
    # Sender cannot send friend request to themselves
    with pytest.raises(HTTPException) as exc_info:
        await FriendService.send_friend_request("user-1", "user-1")
    assert exc_info.value.status_code == 400
    assert "yourself" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_block_user_self_prevention():
    with pytest.raises(HTTPException) as exc_info:
        await FriendService.block_user("user-1", "user-1")
    assert exc_info.value.status_code == 400
    assert "yourself" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_conversation_self_prevention():
    from app.services.conversation_service import ConversationService
    with pytest.raises(HTTPException) as exc_info:
        await ConversationService.get_or_create_direct_conversation("user-1", "user-1")
    assert exc_info.value.status_code == 400
    assert "yourself" in exc_info.value.detail.lower()
