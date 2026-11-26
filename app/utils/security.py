import re
import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
import jwt

from app.config.settings import settings

# Argon2id password hasher with secure configuration:
# type=Type.ID (Argon2id protects against both side-channel and GPU cracking)
# time_cost=3 iterations, memory_cost=65536 KiB (64 MB), parallelism=4 threads
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32
)

# Username regex: 3 to 30 lowercase alphanumeric characters and underscores
USERNAME_REGEX = re.compile(r"^[a-z0-9_]{3,30}$")


def hash_password(password: str) -> str:
    """Hash password using Argon2id."""
    return _password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against stored Argon2id hash."""
    try:
        return _password_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def normalize_username(username: str) -> str:
    """Normalize username: lowercase, stripped of whitespace."""
    if not username:
        return ""
    return username.strip().lower()


def validate_username(username: str) -> bool:
    """Validate username matches character and length constraints."""
    normalized = normalize_username(username)
    return bool(USERNAME_REGEX.match(normalized))


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password has minimum length and adequate complexity."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one numeric digit."
    return True, ""


def create_access_token(user_id: str, username: str, is_admin: bool = False, is_teacher: bool = False) -> str:
    """Create a signed JWT access token."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "is_teacher": is_teacher,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access"
    }
    
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify signed JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "access":
            return None
        return payload
    except (jwt.PyJWTError, Exception):
        return None


def generate_refresh_token() -> tuple[str, str]:
    """
    Generate an opaque high-entropy refresh token and its SHA-256 hash.
    Returns: (raw_token, token_hash)
    The raw_token is delivered to the client; only the token_hash is persisted in DB.
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(token: str) -> str:
    """Hash token with SHA-256 for secure database storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
