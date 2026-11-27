from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, status
from app.schemas.files import (
    UploadUrlRequest,
    UploadUrlResponse,
    CompleteUploadRequest,
    FileResponse,
    DownloadUrlResponse,
)
from app.services.file_service import FileService
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/files", tags=["Files"])


@router.post("/upload-url", response_model=UploadUrlResponse, status_code=status.HTTP_201_CREATED)
async def get_upload_url(
    req: UploadUrlRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Generate a pre-signed upload URL for direct client-to-Supabase upload.
    Validates file extension, MIME type, max file size, and user storage quota.
    """
    return await FileService.create_upload_url(current_user["id"], req)


@router.post("/complete-upload", response_model=FileResponse)
async def complete_upload(
    req: CompleteUploadRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Finalize file upload and perform file signature (magic bytes) validation.
    Marks file record as completed.
    """
    return await FileService.complete_upload(current_user["id"], req)


@router.get("/{id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Generate a secure signed download URL for an uploaded file with TTL.
    """
    return await FileService.get_download_url(current_user["id"], str(id))


@router.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_file(
    id: UUID,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Delete file from Supabase storage bucket and update file record.
    Authorized for file owner or administrator.
    """
    return await FileService.delete_file(current_user["id"], str(id))
