import pytest
import time
from app.utils.security import (
    hash_password,
    verify_password,
    normalize_username,
    validate_username,
    validate_password_strength,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_token,
)
from app.utils.file_validation import (
    is_allowed_file_extension,
    is_allowed_mime_type,
    validate_file_signature,
)


def test_argon2id_hashing():
    pwd = "SecurePassword123!"
    hashed = hash_password(pwd)
    
    assert hashed != pwd
    assert hashed.startswith("$argon2id$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_username_normalization_and_validation():
    assert normalize_username("  Prantik_99  ") == "prantik_99"
    assert validate_username("prantik") is True
    assert validate_username("prantik_das") is True
    assert validate_username("user123") is True
    
    # Invalid usernames
    assert validate_username("ab") is False  # too short
    assert validate_username("a" * 31) is False  # too long
    assert validate_username("user@name") is False  # special chars
    assert validate_username("user name") is False  # space


def test_password_strength():
    # Valid
    ok, _ = validate_password_strength("ValidPass123!")
    assert ok is True

    # Too short
    ok, err = validate_password_strength("Pass1")
    assert ok is False
    assert "at least 8 characters" in err

    # Missing uppercase
    ok, err = validate_password_strength("pass12345")
    assert ok is False
    assert "uppercase" in err

    # Missing number
    ok, err = validate_password_strength("PasswordOnly")
    assert ok is False
    assert "numeric digit" in err


def test_jwt_access_token_creation_and_validation():
    token = create_access_token("u-123", "prantik", is_admin=True, is_teacher=False)
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "u-123"
    assert payload["username"] == "prantik"
    assert payload["is_admin"] is True
    assert payload["type"] == "access"


def test_jwt_tampered_token_rejection():
    token = create_access_token("u-123", "prantik")
    # Tamper with token payload
    parts = token.split(".")
    tampered_token = f"{parts[0]}.eyJuYW1lIjoiZmFrZSJ9.{parts[2]}"
    assert decode_access_token(tampered_token) is None


def test_refresh_token_cryptographic_generation():
    raw_token, token_hash = generate_refresh_token()
    assert len(raw_token) > 40
    assert len(token_hash) == 64  # SHA-256 hex digest length
    assert hash_token(raw_token) == token_hash


def test_file_extension_validation():
    assert is_allowed_file_extension("document.pdf") is True
    assert is_allowed_file_extension("photo.PNG") is True
    assert is_allowed_file_extension("archive.zip") is True
    assert is_allowed_file_extension("script.exe") is False
    assert is_allowed_file_extension("payload.sh") is False
    assert is_allowed_file_extension("malware.bat") is False


def test_mime_type_validation():
    assert is_allowed_mime_type("image/jpeg") is True
    assert is_allowed_mime_type("application/pdf") is True
    assert is_allowed_mime_type("text/plain; charset=utf-8") is True
    assert is_allowed_mime_type("application/x-msdownload") is False
    assert is_allowed_mime_type("application/x-sh") is False


def test_magic_bytes_signature_validation():
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    valid, detected = validate_file_signature(png_header, "image/png")
    assert valid is True
    assert detected == "image/png"

    # JPEG signature: FF D8 FF
    jpeg_header = b"\xff\xd8\xff\xe0\x00\x10JFIF"
    valid, detected = validate_file_signature(jpeg_header, "image/jpeg")
    assert valid is True
    assert detected == "image/jpeg"

    # Plain text
    text_header = b"Hello, this is a plain text file header."
    valid, detected = validate_file_signature(text_header, "text/plain")
    assert valid is True

    # Corrupt or mismatched binary header
    corrupt_header = b"NOT_A_PNG_HEADER"
    valid, _ = validate_file_signature(corrupt_header, "image/png")
    assert valid is False
