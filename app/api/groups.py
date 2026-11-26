from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from app.schemas.groups import GroupCreate, GroupMemberAdd, GroupResponse
from app.services.group_service import GroupService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    req: GroupCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a new group chat.
    Sets the creator as owner.
    If is_teacher_group=True, requires the creator to be a verified teacher.
    """
    return await GroupService.create_group(current_user["id"], req)


@router.get("/{id}", response_model=GroupResponse)
async def get_group(
    id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieve group details and member list for authorized members."""
    return await GroupService.get_group_by_id(id, current_user["id"])


@router.post("/{id}/members", status_code=status.HTTP_200_OK)
async def add_group_member(
    id: str,
    req: GroupMemberAdd,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Add a member to the group (Authorized for group owners and admins)."""
    return await GroupService.add_member(id, current_user["id"], req)


@router.delete("/{id}/members/{user_id}", status_code=status.HTTP_200_OK)
async def remove_group_member(
    id: str,
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Remove a member from the group.
    Authorized for owners/admins to remove members, or for members to leave the group.
    """
    return await GroupService.remove_member(id, current_user["id"], user_id)
