from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    is_teacher: bool = False
    teacher_verified: bool = False
    teacher_title: Optional[str] = None
    is_admin: bool = False
    status_message: Optional[str] = None
    is_online: bool = False
    last_seen_at: datetime
    created_at: datetime


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    is_teacher: bool = False
    teacher_title: Optional[str] = None

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("New passwords do not match.")
        return self
