import os
from typing import Optional, Set
import filetype

# Allowlist of supported MIME types
ALLOWED_MIME_TYPES: Set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/webm",
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
}

# Allowlist of supported file extensions
ALLOWED_EXTENSIONS: Set[str] = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".mp4", ".webm",
    ".mp3", ".wav",
    ".pdf",
    ".txt",
    ".docx", ".xlsx",
    ".zip"
}

# Mapping of extensions to typical MIME types
EXTENSION_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
}


def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension including dot."""
    _, ext = os.path.splitext(filename)
    return ext.lower()


def is_allowed_file_extension(filename: str) -> bool:
    """Verify filename has an authorized extension."""
    ext = get_file_extension(filename)
    return ext in ALLOWED_EXTENSIONS


def is_allowed_mime_type(mime_type: str) -> bool:
    """Verify MIME type is in the authorized allowlist."""
    if not mime_type:
        return False
    # Strip any parameters like charset=utf-8
    clean_mime = mime_type.split(";")[0].strip().lower()
    return clean_mime in ALLOWED_MIME_TYPES


def validate_file_signature(content_header: bytes, expected_mime: Optional[str] = None) -> tuple[bool, str]:
    """
    Validate file magic bytes / signature against expected MIME type.
    Handles binary formats and plain text.
    """
    if not content_header:
        return False, "File content is empty."

    # Plain text detection
    if expected_mime == "text/plain":
        try:
            # Check if bytes are valid UTF-8 / ASCII text
            content_header.decode("utf-8")
            return True, "text/plain"
        except UnicodeDecodeError:
            return False, "Content does not match valid text/plain encoding."

    # Use filetype for binary magic bytes detection
    kind = filetype.guess(content_header)
    if kind is None:
        # Some DOCX / XLSX are zip containers
        if expected_mime in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/zip"
        ) and content_header.startswith(b"PK\x03\x04"):
            return True, expected_mime
        return False, "Unknown file signature or corrupt header."

    detected_mime = kind.mime
    if not is_allowed_mime_type(detected_mime):
        return False, f"Detected MIME type {detected_mime} is not authorized."

    # If an expected MIME was provided, check compatibility
    if expected_mime:
        clean_expected = expected_mime.split(";")[0].strip().lower()
        # Handle wav / x-wav alias
        if clean_expected in ("audio/wav", "audio/x-wav") and detected_mime in ("audio/wav", "audio/x-wav"):
            return True, detected_mime
        # Handle docx / xlsx detected as application/zip
        if clean_expected in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ) and detected_mime == "application/zip":
            return True, clean_expected

        if clean_expected != detected_mime:
            return False, f"Declared MIME type {expected_mime} does not match file signature {detected_mime}."

    return True, detected_mime
