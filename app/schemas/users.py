from typing import Optional
from pydantic import BaseModel, Field, field_validator


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    avatar_url: Optional[str] = None
    status_message: Optional[str] = Field(None, max_length=255)
    teacher_title: Optional[str] = Field(None, max_length=100)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Full name must contain at least 2 non-whitespace characters.")
        return normalized


class TeacherVerifyRequest(BaseModel):
    teacher_verified: bool
