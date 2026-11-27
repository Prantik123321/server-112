from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator


class AttachmentSchema(BaseModel):
    file_id: UUID
    file_path: str = Field(..., max_length=1024)
    filename: str = Field(..., max_length=255)
    mime_type: str = Field(..., max_length=100)
    size_bytes: int = Field(..., gt=0)


class MessageCreate(BaseModel):
    content: str = Field("", max_length=10000)
    type: Literal["text", "image", "video", "audio", "document", "file"] = "text"
    attachments: Optional[List[AttachmentSchema]] = Field(None, max_length=10)
    reply_to_message_id: Optional[UUID] = None
    idempotency_key: Optional[str] = Field(None, min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_message_content_or_attachment(self):
        if not self.content.strip() and not self.attachments:
            raise ValueError("A message must contain text or at least one attachment.")
        return self


class MessageEdit(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Message content cannot contain only whitespace.")
        return normalized


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
    attachments: List[AttachmentSchema] = Field(default_factory=list)
    reply_to_message_id: Optional[str] = None
    reply_preview: Optional[Dict[str, Any]] = None
    reactions: Dict[str, List[str]] = Field(default_factory=dict)
    is_edited: bool = False
    edit_history: List[Dict[str, Any]] = Field(default_factory=list)
    is_deleted: bool = False
    delivery_status: str = "sent"
    read_by: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
