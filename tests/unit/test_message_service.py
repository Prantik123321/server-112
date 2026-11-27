import pytest

import app.services.message_service as message_service
from app.schemas.messages import MessageCreate
from app.services.message_service import MessageService


class MockMessages:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, document):
        self.inserted.append(document)


class MockMongo:
    def __init__(self):
        self.messages = MockMessages()

    def __getitem__(self, collection_name):
        assert collection_name == "messages"
        return self.messages


@pytest.mark.asyncio
async def test_messages_without_idempotency_key_omit_indexed_field(monkeypatch):
    mongo = MockMongo()

    async def verify_membership(conversation_id, sender_id):
        return True

    monkeypatch.setattr(message_service.ConversationService, "verify_conversation_membership", verify_membership)
    monkeypatch.setattr(message_service, "get_mongodb", lambda: mongo)
    monkeypatch.setattr(message_service, "get_pg_pool", lambda: None)

    await MessageService.send_message(
        conversation_id="conversation-id",
        sender_id="sender-id",
        sender_username="sender",
        sender_full_name="Sender User",
        data=MessageCreate(content="hello"),
    )

    assert len(mongo.messages.inserted) == 1
    assert "idempotency_key" not in mongo.messages.inserted[0]
