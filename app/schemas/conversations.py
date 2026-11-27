from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel


class ConversationCreate(BaseModel):
    participant_id: UUID


class ConversationParticipant(BaseModel):
    user_id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    is_online: bool = False
    last_read_message_id: Optional[str] = None


class ConversationResponse(BaseModel):
    id: str
    type: str  # 'direct' or 'group'
    participants: List[ConversationParticipant]
    last_message: Optional[Dict[str, Any]] = None
    last_message_at: datetime
    unread_count: int = 0
    group_details: Optional[Dict[str, Any]] = None
    created_at: datetime
