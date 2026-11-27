from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    member_ids: Optional[List[UUID]] = None
    is_teacher_group: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Group name must contain at least 2 non-whitespace characters.")
        return normalized


class GroupMemberAdd(BaseModel):
    user_id: UUID
    role: str = Field("member", pattern="^(admin|member)$")


class GroupOwnershipTransfer(BaseModel):
    user_id: UUID


class GroupMemberResponse(BaseModel):
    user_id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    role: str  # 'owner', 'admin', 'member'
    is_teacher: bool = False
    teacher_verified: bool = False
    joined_at: datetime


class GroupResponse(BaseModel):
    id: str
    conversation_id: str
    name: str
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    creator_id: Optional[str] = None
    is_teacher_group: bool = False
    members: List[GroupMemberResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
