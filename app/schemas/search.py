from typing import Optional
from pydantic import BaseModel


class UserSearchResult(BaseModel):
    id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    is_online: bool = False
    is_teacher: bool = False
    teacher_verified: bool = False
    teacher_title: Optional[str] = None
    score: Optional[float] = None
    match_tier: Optional[int] = None
    match_reason: Optional[str] = None
