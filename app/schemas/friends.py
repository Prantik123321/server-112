from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.schemas.auth import UserResponse


class FriendRequestCreate(BaseModel):
    receiver_id: str


class FriendRequestResponse(BaseModel):
    id: str
    sender: UserResponse
    receiver: UserResponse
    status: str
    created_at: datetime


class FriendshipResponse(BaseModel):
    friendship_id: str
    friend: UserResponse
    since: datetime


class BlockUserRequest(BaseModel):
    user_id: str
