import uuid
import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from app.config.settings import settings
from app.database.supabase import get_pg_pool, get_supabase_client
from app.utils.file_validation import (
    is_allowed_file_extension,
    is_allowed_mime_type,
    validate_file_signature,
    get_file_extension,
)
from app.schemas.files import (
    UploadUrlRequest,
    UploadUrlResponse,
    CompleteUploadRequest,
    FileResponse,
    DownloadUrlResponse,
)


class FileService:

    @classmethod
    async def create_upload_url(cls, user_id: str, req: UploadUrlRequest) -> UploadUrlResponse:
        # 1. Extension and MIME Validation
        if not is_allowed_file_extension(req.filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension not permitted. Allowed: .jpg, .png, .webp, .gif, .mp4, .webm, .mp3, .wav, .pdf, .txt, .docx, .xlsx, .zip"
            )

        if not is_allowed_mime_type(req.mime_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"MIME type '{req.mime_type}' is not permitted."
            )

        # 2. Maximum File Size Check
        if req.size_bytes > settings.MAX_FILE_SIZE_BYTES:
            max_mb = settings.MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"File size exceeds maximum allowed limit of {max_mb} MB."
            )

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        # 3. User Storage Quota Check
        async with pool.acquire() as conn:
            current_used = await conn.fetchval(
                """
                SELECT COALESCE(SUM(size_bytes), 0)
                FROM file_records
                WHERE uploader_id = $1 AND status != 'deleted'
                """,
                user_id
            )
            if (current_used + req.size_bytes) > settings.STORAGE_QUOTA_PER_USER_BYTES:
                quota_mb = settings.STORAGE_QUOTA_PER_USER_BYTES // (1024 * 1024)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Upload would exceed your storage quota of {quota_mb} MB."
                )

            # 4. Generate unique file path
            file_id = str(uuid.uuid4())
            ext = get_file_extension(req.filename)
            file_path = f"users/{user_id}/{file_id}{ext}"
            bucket_name = settings.SUPABASE_STORAGE_BUCKET
            now = datetime.now(timezone.utc)

            # Insert pending file record in PostgreSQL
            await conn.execute(
                """
                INSERT INTO file_records (id, uploader_id, bucket_name, file_path, filename, mime_type, size_bytes, status, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', $8, $8)
                """,
                file_id, user_id, bucket_name, file_path, req.filename, req.mime_type, req.size_bytes, now
            )

        # 5. Generate Signed Upload URL via Supabase Storage
        upload_url = ""
        expires_in = 3600  # 1 hour
        client = get_supabase_client()
        if client:
            try:
                res = client.storage.from_(bucket_name).create_signed_upload_url(file_path)
                upload_url = res.get("signed_url") or res.get("signedUrl") or ""
            except Exception as e:
                # If Supabase bucket isn't initialized yet, provide endpoint URL
                upload_url = f"{settings.SUPABASE_URL}/storage/v1/object/upload/sign/{bucket_name}/{file_path}"
        else:
            upload_url = f"https://mock-storage.local/{bucket_name}/{file_path}"

        return UploadUrlResponse(
            file_id=file_id,
            bucket_name=bucket_name,
            file_path=file_path,
            upload_url=upload_url,
            expires_in=expires_in
        )

    @classmethod
    async def complete_upload(cls, user_id: str, req: CompleteUploadRequest) -> FileResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            rec = await conn.fetchrow(
                "SELECT * FROM file_records WHERE id = $1",
                req.file_id
            )
            if not rec:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File record not found.")

            if str(rec["uploader_id"]) != user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

            # Magic bytes validation if client provided header sample
            if req.header_bytes_base64:
                try:
                    header_bytes = base64.b64decode(req.header_bytes_base64)
                    is_valid, detected = validate_file_signature(header_bytes, rec["mime_type"])
                    if not is_valid:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"File signature validation failed: {detected}"
                        )
                except Exception as e:
                    if isinstance(e, HTTPException):
                        raise e
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrupted header bytes.")

            now = datetime.now(timezone.utc)
            updated = await conn.fetchrow(
                """
                UPDATE file_records
                SET status = 'completed', updated_at = $1
                WHERE id = $2
                RETURNING *
                """,
                now, req.file_id
            )

        return FileResponse(
            id=str(updated["id"]),
            uploader_id=str(updated["uploader_id"]),
            filename=updated["filename"],
            file_path=updated["file_path"],
            mime_type=updated["mime_type"],
            size_bytes=updated["size_bytes"],
            status=updated["status"],
            created_at=updated["created_at"],
            updated_at=updated["updated_at"]
        )

    @classmethod
    async def get_download_url(cls, user_id: str, file_id: str) -> DownloadUrlResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            rec = await conn.fetchrow(
                "SELECT * FROM file_records WHERE id = $1 AND status != 'deleted'",
                file_id
            )
            if not rec:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found or deleted.")

        # Generate signed download URL via Supabase Storage SDK
        client = get_supabase_client()
        expires_in = 3600
        download_url = ""
        if client:
            try:
                res = client.storage.from_(rec["bucket_name"]).create_signed_url(rec["file_path"], expires_in)
                download_url = res.get("signed_url") or res.get("signedURL") or ""
            except Exception:
                download_url = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{rec['bucket_name']}/{rec['file_path']}?token=signed"
        else:
            download_url = f"https://mock-storage.local/download/{rec['bucket_name']}/{rec['file_path']}"

        return DownloadUrlResponse(
            file_id=str(rec["id"]),
            filename=rec["filename"],
            download_url=download_url,
            expires_in=expires_in
        )

    @classmethod
    async def delete_file(cls, user_id: str, file_id: str) -> Dict[str, str]:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            rec = await conn.fetchrow("SELECT * FROM file_records WHERE id = $1", file_id)
            if not rec:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

            if str(rec["uploader_id"]) != user_id:
                # Check if admin
                is_admin = await conn.fetchval("SELECT is_admin FROM users WHERE id = $1", user_id)
                if not is_admin:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")

            now = datetime.now(timezone.utc)
            await conn.execute(
                "UPDATE file_records SET status = 'deleted', updated_at = $1 WHERE id = $2",
                now, file_id
            )

        # Remove from Supabase Storage bucket
        client = get_supabase_client()
        if client:
            try:
                client.storage.from_(rec["bucket_name"]).remove([rec["file_path"]])
            except Exception:
                pass

        return {"message": "File deleted successfully."}
