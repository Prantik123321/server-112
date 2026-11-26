from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AttachmentSchema(BaseModel):
    file_id: str
    file_path: str
    filename: str
    mime_type: str
    size_bytes: int


class MessageCreate(BaseModel):
    content: str = ""
    type: str = "text"  # 'text', 'image', 'video', 'audio', 'document', 'file'
    attachments: Optional[List[AttachmentSchema]] = None
    reply_to_message_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class MessageEdit(BaseModel):
    content: str = Field(..., min_length=1)


class MessageReaction(BaseModel):
    emoji: str = Field(..., min_length=1, max_length=16)


class MessageDeliveryStatus(BaseModel):
    status: str  # 'delivered', 'read'


class MessageResponse(BaseModel):
    message_id: str
    conversation_id: str
    sender_id: str
    sender_username: str
    sender_full_name: str
    content: str
    type: str
    attachments: List[AttachmentSchema] = []
    reply_to_message_id: Optional[str] = None
    reply_preview: Optional[Dict[str, Any]] = None
    reactions: Dict[str, List[str]] = {}
    is_edited: bool = False
    edit_history: List[Dict[str, Any]] = []
    is_deleted: bool = False
    delivery_status: str = "sent"
    read_by: List[Dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime
