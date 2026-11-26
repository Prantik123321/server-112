from typing import Optional
from pydantic import BaseModel, Field


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar_url: Optional[str] = None
    status_message: Optional[str] = Field(None, max_length=255)
    teacher_title: Optional[str] = Field(None, max_length=100)


class TeacherVerifyRequest(BaseModel):
    teacher_verified: bool
