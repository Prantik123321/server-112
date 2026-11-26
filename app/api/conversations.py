from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from app.schemas.conversations import ConversationResponse, ConversationCreate
from app.schemas.messages import MessageCreate, MessageResponse
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get("", response_model=List[ConversationResponse])
async def list_conversations(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all active direct and group conversations for the authenticated user."""
    return await ConversationService.get_user_conversations(current_user["id"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_or_get_direct_conversation(
    req: ConversationCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get existing or initiate new direct conversation between authenticated user and another user.
    """
    return await ConversationService.get_or_create_direct_conversation(
        current_user["id"],
        req.participant_id
    )


@router.get("/{id}", response_model=ConversationResponse)
async def get_conversation_details(
    id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get metadata, participants, and unread count for a conversation."""
    return await ConversationService.get_conversation_by_id(id, current_user["id"])


@router.get("/{id}/messages", response_model=List[MessageResponse])
async def get_conversation_messages(
    id: str,
    limit: int = Query(50, ge=1, le=100),
    before_timestamp: Optional[datetime] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Retrieve message history from MongoDB for authorized conversation participants.
    Supports backward pagination using before_timestamp.
    """
    return await MessageService.get_messages(
        conversation_id=id,
        user_id=current_user["id"],
        limit=limit,
        before_timestamp=before_timestamp
    )


@router.post("/{id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_conversation_message(
    id: str,
    req: MessageCreate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Send a message (text, emojis, media attachments, reply) to a conversation.
    Enforces Supabase conversation membership before persisting to MongoDB.
    Supports idempotency key for deduplication.
    """
    return await MessageService.send_message(
        conversation_id=id,
        sender_id=current_user["id"],
        sender_username=current_user["username"],
        sender_full_name=current_user["full_name"],
        data=req
    )


@router.post("/{id}/read", status_code=status.HTTP_200_OK)
async def mark_conversation_as_read(
    id: str,
    last_message_id: str = Query(...),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Mark conversation messages as read up to last_message_id."""
    return await MessageService.mark_messages_read(id, current_user["id"], last_message_id)
