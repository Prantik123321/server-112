import pytest
from fastapi import HTTPException

import app.services.friend_service as friend_service
import app.services.notification_service as notification_service
import app.services.search_service as search_service
from app.services.friend_service import FriendService
from app.services.notification_service import NotificationService
from app.services.search_service import SearchService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_module", "operation"),
    [
        (friend_service, lambda: FriendService.get_friends_list("user-id")),
        (friend_service, lambda: FriendService.get_pending_requests("user-id")),
        (notification_service, lambda: NotificationService.get_notifications("user-id")),
        (search_service, lambda: SearchService.search_users("query")),
    ],
)
async def test_database_backed_list_services_report_unavailable(monkeypatch, service_module, operation):
    monkeypatch.setattr(service_module, "get_pg_pool", lambda: None)

    with pytest.raises(HTTPException) as exc_info:
        await operation()

    assert exc_info.value.status_code == 503
