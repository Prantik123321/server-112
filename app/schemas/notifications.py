from datetime import datetime
from typing import Dict, Any
from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    type: str
    title: str
    body: str
    data: Dict[str, Any]
    is_read: bool
    created_at: datetime
