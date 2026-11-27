import pytest
from app.services.file_service import FileService
from app.services import file_service
from app.schemas.files import UploadUrlRequest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_file_upload_validation_rules():
    # 1. Invalid extension (executable)
    req_bad_ext = UploadUrlRequest(
        filename="malware.exe",
        mime_type="application/octet-stream",
        size_bytes=1024
    )
    with pytest.raises(HTTPException) as exc_info:
        await FileService.create_upload_url("user-1", req_bad_ext)
    assert exc_info.value.status_code == 400
    assert "extension not permitted" in exc_info.value.detail.lower()

    # 2. Invalid MIME type
    req_bad_mime = UploadUrlRequest(
        filename="test.png",
        mime_type="application/x-sh",
        size_bytes=1024
    )
    with pytest.raises(HTTPException) as exc_info:
        await FileService.create_upload_url("user-1", req_bad_mime)
    assert exc_info.value.status_code == 400
    assert "mime type" in exc_info.value.detail.lower()

    # 3. File size exceeds max limit (e.g. > 100MB)
    req_too_large = UploadUrlRequest(
        filename="video.mp4",
        mime_type="video/mp4",
        size_bytes=200 * 1024 * 1024  # 200 MB
    )
    with pytest.raises(HTTPException) as exc_info:
        await FileService.create_upload_url("user-1", req_too_large)
    assert exc_info.value.status_code == 413
    assert "exceeds maximum allowed limit" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_upload_url_fails_when_storage_is_not_configured(monkeypatch):
    monkeypatch.setattr(file_service, "get_supabase_client", lambda: None)
    req = UploadUrlRequest(
        filename="photo.png",
        mime_type="image/png",
        size_bytes=1024
    )

    with pytest.raises(HTTPException) as exc_info:
        await FileService.create_upload_url("user-1", req)

    assert exc_info.value.status_code == 503
    assert "storage service is unavailable" in exc_info.value.detail.lower()
