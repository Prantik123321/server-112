import re
from datetime import datetime, timezone

import pytest

from app.services import conversation_service
from app.services.conversation_service import ConversationService


class MockConnection:
    def __init__(self):
        self.insert_bind_counts = []

    def transaction(self):
        connection = self

        class TransactionContext:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, exc_type, exc, tb):
                return None

        return TransactionContext()

    async def fetchval(self, query, *args):
        if "FROM user_blocks" in query:
            return None
        if "FROM conversation_participants cp1" in query:
            return None
        if "FROM conversation_participants" in query:
            return True
        raise AssertionError(f"Unexpected fetchval query: {query}")

    async def execute(self, query, *args):
        placeholders = [int(value) for value in re.findall(r"\$(\d+)", query)]
        expected_arg_count = max(placeholders, default=0)
        assert len(args) == expected_arg_count
        if "INSERT INTO conversation_participants" in query:
            self.insert_bind_counts.append(len(args))

    async def fetchrow(self, query, *args):
        now = datetime.now(timezone.utc)
        return {
            "id": args[0],
            "type": "direct",
            "last_message_at": now,
            "created_at": now,
        }

    async def fetch(self, query, *args):
        return [
            {
                "id": "user-1",
                "username": "first",
                "full_name": "First User",
                "avatar_url": None,
                "is_online": False,
                "last_read_message_id": None,
            },
            {
                "id": "user-2",
                "username": "second",
                "full_name": "Second User",
                "avatar_url": None,
                "is_online": False,
                "last_read_message_id": None,
            },
        ]


class MockPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        connection = self.connection

        class ConnectionContext:
            async def __aenter__(self):
                return connection

            async def __aexit__(self, exc_type, exc, tb):
                return None

        return ConnectionContext()


@pytest.mark.asyncio
async def test_create_direct_conversation_uses_matching_participant_bind_args(monkeypatch):
    connection = MockConnection()
    monkeypatch.setattr(conversation_service, "get_pg_pool", lambda: MockPool(connection))
    monkeypatch.setattr(conversation_service, "get_mongodb", lambda: None)

    response = await ConversationService.get_or_create_direct_conversation(
        "user-1",
        "user-2",
    )

    assert response.type == "direct"
    assert {participant.user_id for participant in response.participants} == {
        "user-1",
        "user-2",
    }
    assert connection.insert_bind_counts == [4, 4]
