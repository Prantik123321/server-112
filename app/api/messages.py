from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, status
from app.schemas.messages import MessageEdit, MessageReaction, MessageResponse
from app.services.message_service import MessageService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.patch("/{id}", response_model=MessageResponse)
async def edit_message(
    id: UUID,
    req: MessageEdit,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Edit message content.
    Only the message author may edit their message.
    Tracks edit history and timestamps.
    """
    return await MessageService.edit_message(str(id), current_user["id"], req)


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_message(
    id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete a message.
    Authorized for message author or group administrator.
    Performs safe soft-deletion and content redaction.
    """
    return await MessageService.delete_message(str(id), current_user["id"])


@router.post("/{id}/react", response_model=MessageResponse)
async def react_to_message(
    id: UUID,
    req: MessageReaction,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Toggle an emoji reaction on a message."""
    return await MessageService.react_to_message(str(id), current_user["id"], req.emoji)
