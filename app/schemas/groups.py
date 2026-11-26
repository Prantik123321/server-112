from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    member_ids: Optional[List[str]] = None
    is_teacher_group: bool = False


class GroupMemberAdd(BaseModel):
    user_id: str
    role: str = Field("member", pattern="^(admin|member)$")


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
    members: List[GroupMemberResponse] = []
    created_at: datetime
    updated_at: datetime
