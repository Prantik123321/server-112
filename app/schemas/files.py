from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class UploadUrlRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    mime_type: str = Field(..., min_length=3, max_length=100)
    size_bytes: int = Field(..., gt=0)


class UploadUrlResponse(BaseModel):
    file_id: str
    bucket_name: str
    file_path: str
    upload_url: str
    expires_in: int


class CompleteUploadRequest(BaseModel):
    file_id: str
    header_bytes_base64: Optional[str] = None


class FileResponse(BaseModel):
    id: str
    uploader_id: str
    filename: str
    file_path: str
    mime_type: str
    size_bytes: int
    status: str
    created_at: datetime
    updated_at: datetime


class DownloadUrlResponse(BaseModel):
    file_id: str
    filename: str
    download_url: str
    expires_in: int
