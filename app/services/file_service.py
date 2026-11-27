import uuid
import base64
import logging
from datetime import datetime, timezone
from typing import Dict
from urllib.parse import quote
from fastapi import HTTPException, status
import httpx
from starlette.concurrency import run_in_threadpool

from app.config.settings import settings
from app.database.supabase import get_pg_pool, get_supabase_client
from app.database.mongodb import get_mongodb
from app.services.conversation_service import ConversationService
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

logger = logging.getLogger("nodeshare.services.files")


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

        client = get_supabase_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service is unavailable."
            )

        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        # Serialize uploads per user so concurrent requests cannot exceed the quota.
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.fetchval("SELECT id FROM users WHERE id = $1 FOR UPDATE", user_id)
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

                file_id = str(uuid.uuid4())
                ext = get_file_extension(req.filename)
                file_path = f"users/{user_id}/{file_id}{ext}"
                bucket_name = settings.SUPABASE_STORAGE_BUCKET
                now = datetime.now(timezone.utc)

                try:
                    result = await run_in_threadpool(
                        client.storage.from_(bucket_name).create_signed_upload_url,
                        file_path,
                    )
                except Exception as e:
                    logger.exception("Failed to generate signed upload URL.")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Could not create an upload URL."
                    ) from e

                upload_url = result.get("signed_url") or result.get("signedUrl")
                if not isinstance(upload_url, str) or not upload_url.startswith(("https://", "http://")):
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Storage provider returned an invalid upload URL."
                    )

                await conn.execute(
                    """
                    INSERT INTO file_records (id, uploader_id, bucket_name, file_path, filename, mime_type, size_bytes, status, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending', $8, $8)
                    """,
                    file_id, user_id, bucket_name, file_path, req.filename, req.mime_type, req.size_bytes, now
                )

        expires_in = 3600

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

            if rec["status"] == "completed":
                return cls._file_response(rec)
            if rec["status"] != "pending":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload is not pending.")

            client = get_supabase_client()
            if not client:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="File storage service is unavailable."
                )

            try:
                info = await run_in_threadpool(
                    client.storage.from_(rec["bucket_name"]).info,
                    rec["file_path"],
                )
            except Exception as e:
                logger.exception("Could not verify uploaded file metadata.")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Uploaded object is missing or could not be verified."
                ) from e

            metadata = info.get("metadata") or {}
            actual_size = info.get("size") or metadata.get("size")
            if actual_size is None or int(actual_size) != rec["size_bytes"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file size does not match the requested size."
                )

            actual_mime = info.get("mimetype") or metadata.get("mimetype")
            if actual_mime and str(actual_mime).lower() != rec["mime_type"].split(";")[0].strip().lower():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file MIME type does not match the requested MIME type."
                )

            actual_header = await cls._read_storage_header(
                rec["bucket_name"],
                rec["file_path"],
            )
            is_valid, detected = validate_file_signature(actual_header, rec["mime_type"])
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File signature validation failed: {detected}"
                )

            # Retain validation for older clients that still send a header sample.
            if req.header_bytes_base64:
                try:
                    header_bytes = base64.b64decode(req.header_bytes_base64, validate=True)
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

        return cls._file_response(updated)

    @staticmethod
    async def _read_storage_header(bucket_name: str, file_path: str) -> bytes:
        service_key = settings.effective_service_role_key
        if not settings.SUPABASE_URL or not service_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service is unavailable."
            )

        url = (
            f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/authenticated/"
            f"{quote(bucket_name, safe='')}/{quote(file_path, safe='/')}"
        )
        headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Range": "bytes=0-8191",
            "Accept-Encoding": "identity",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 404:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Uploaded object was not found in storage."
                        )
                    if response.status_code not in (200, 206):
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="Storage provider could not verify the uploaded object."
                        )
                    prefix = bytearray()
                    async for chunk in response.aiter_bytes():
                        prefix.extend(chunk[:8192 - len(prefix)])
                        if len(prefix) >= 8192:
                            break
        except HTTPException:
            raise
        except httpx.HTTPError as e:
            logger.exception("Could not read uploaded file bytes from storage.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not verify uploaded file content."
            ) from e

        return bytes(prefix)

    @classmethod
    async def get_download_url(cls, user_id: str, file_id: str) -> DownloadUrlResponse:
        pool = get_pg_pool()
        if not pool:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable.")

        async with pool.acquire() as conn:
            rec = await conn.fetchrow(
                "SELECT * FROM file_records WHERE id = $1 AND status = 'completed'",
                file_id
            )
            if not rec:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Completed file not found.")

            if str(rec["uploader_id"]) != user_id:
                is_admin = await conn.fetchval("SELECT is_admin FROM users WHERE id = $1", user_id)
                if not is_admin:
                    mongo_db = get_mongodb()
                    if mongo_db is None:
                        raise HTTPException(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Message storage service (MongoDB) unavailable."
                        )
                    linked_message = await mongo_db["messages"].find_one(
                        {
                            "attachments.file_id": str(rec["id"]),
                            "is_deleted": {"$ne": True},
                        },
                        {"conversation_id": 1},
                    )
                    if not linked_message or not await ConversationService.verify_conversation_membership(
                        linked_message["conversation_id"], user_id
                    ):
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

        # Generate signed download URL via Supabase Storage SDK
        client = get_supabase_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service is unavailable."
            )

        expires_in = 3600
        try:
            result = await run_in_threadpool(
                client.storage.from_(rec["bucket_name"]).create_signed_url,
                rec["file_path"],
                expires_in,
            )
        except Exception as e:
            logger.exception("Failed to generate signed download URL.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not create a download URL."
            ) from e

        download_url = result.get("signed_url") or result.get("signedURL")
        if not isinstance(download_url, str) or not download_url.startswith(("https://", "http://")):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Storage provider returned an invalid download URL."
            )

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

            if rec["status"] == "deleted":
                return {"message": "File deleted successfully."}

        client = get_supabase_client()
        if not client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service is unavailable."
            )

        try:
            await run_in_threadpool(
                client.storage.from_(rec["bucket_name"]).remove,
                [rec["file_path"]],
            )
        except Exception as e:
            logger.exception("Failed to remove file from storage.")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Could not delete the file from storage."
            ) from e

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE file_records SET status = 'deleted', updated_at = $1 WHERE id = $2",
                datetime.now(timezone.utc), file_id
            )

        return {"message": "File deleted successfully."}

    @staticmethod
    def _file_response(rec) -> FileResponse:
        return FileResponse(
            id=str(rec["id"]),
            uploader_id=str(rec["uploader_id"]),
            filename=rec["filename"],
            file_path=rec["file_path"],
            mime_type=rec["mime_type"],
            size_bytes=rec["size_bytes"],
            status=rec["status"],
            created_at=rec["created_at"],
            updated_at=rec["updated_at"]
        )
