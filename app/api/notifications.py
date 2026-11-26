from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Query, status
from app.schemas.notifications import NotificationResponse
from app.services.notification_service import NotificationService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=List[NotificationResponse])
async def list_notifications(
    limit: int = Query(50, ge=1, le=100),
    unread_only: bool = Query(False),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieve notifications for the authenticated user."""
    return await NotificationService.get_notifications(
        user_id=current_user["id"],
        limit=limit,
        unread_only=unread_only
    )


@router.patch("/{id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Mark a notification as read."""
    return await NotificationService.mark_as_read(id, current_user["id"])
