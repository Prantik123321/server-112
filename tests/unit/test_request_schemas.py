from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.conversations import ConversationCreate
from app.schemas.files import CompleteUploadRequest
from app.schemas.groups import GroupMemberAdd
from app.schemas.messages import MessageCreate, MessageEdit


def test_message_schema_requires_content_or_attachment():
    with pytest.raises(ValidationError):
        MessageCreate(content="   ")

    message = MessageCreate(content=" ", attachments=[{
        "file_id": str(uuid4()),
        "file_path": "ignored",
        "filename": "image.png",
        "mime_type": "image/png",
        "size_bytes": 1,
    }])
    assert message.content == ""


def test_message_schema_rejects_unknown_type_and_invalid_reply_id():
    with pytest.raises(ValidationError):
        MessageCreate(content="hello", type="unsupported")
    with pytest.raises(ValidationError):
        MessageCreate(content="hello", reply_to_message_id="not-a-uuid")


def test_message_edit_rejects_whitespace_only_content():
    with pytest.raises(ValidationError):
        MessageEdit(content="   ")
    with pytest.raises(ValidationError):
        MessageEdit(content="x" * 10001)


def test_group_member_role_cannot_be_set_to_owner():
    with pytest.raises(ValidationError):
        GroupMemberAdd(user_id=uuid4(), role="owner")


def test_conversation_participant_id_must_be_uuid():
    with pytest.raises(ValidationError):
        ConversationCreate(participant_id="not-a-uuid")


def test_upload_header_sample_is_size_limited():
    with pytest.raises(ValidationError):
        CompleteUploadRequest(file_id=uuid4(), header_bytes_base64="A" * 16385)
