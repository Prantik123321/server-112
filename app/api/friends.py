from typing import Dict, Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from app.schemas.friends import FriendRequestResponse, FriendshipResponse
from app.services.friend_service import FriendService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/friends", tags=["Friends"])


@router.post("/requests/{user_id}", response_model=FriendRequestResponse, status_code=status.HTTP_201_CREATED)
async def send_friend_request(
    user_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Send a friend request to a user."""
    return await FriendService.send_friend_request(current_user["id"], str(user_id))


@router.get("/requests", response_model=List[FriendRequestResponse])
async def get_friend_requests(
    direction: str = Query("received", pattern="^(received|sent)$"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """List pending incoming or outgoing friend requests."""
    return await FriendService.get_pending_requests(current_user["id"], direction=direction)


@router.post("/requests/{request_id}/accept", status_code=status.HTTP_200_OK)
async def accept_friend_request(
    request_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Accept an incoming friend request."""
    return await FriendService.accept_friend_request(str(request_id), current_user["id"])


@router.post("/requests/{request_id}/reject", status_code=status.HTTP_200_OK)
async def reject_friend_request(
    request_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Reject an incoming friend request."""
    return await FriendService.reject_friend_request(str(request_id), current_user["id"])


@router.post("/requests/{request_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_friend_request(
    request_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Cancel an outgoing pending friend request."""
    return await FriendService.cancel_friend_request(str(request_id), current_user["id"])


@router.get("", response_model=List[FriendshipResponse])
async def list_friends(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List current accepted friends."""
    return await FriendService.get_friends_list(current_user["id"])


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def remove_friend(
    user_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Remove a user from friends."""
    return await FriendService.remove_friend(current_user["id"], str(user_id))


@router.post("/block/{user_id}", status_code=status.HTTP_200_OK)
async def block_user(
    user_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Block a user, cancel pending requests, and remove existing friendship."""
    return await FriendService.block_user(current_user["id"], str(user_id))


@router.post("/unblock/{user_id}", status_code=status.HTTP_200_OK)
async def unblock_user(
    user_id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Unblock a previously blocked user."""
    return await FriendService.unblock_user(current_user["id"], str(user_id))
