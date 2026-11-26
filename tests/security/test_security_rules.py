import pytest
from app.utils.security import hash_password, verify_password, validate_username
from app.middleware.security import SecurityHeadersMiddleware
import httpx


@pytest.mark.asyncio
async def test_security_headers_present(client: httpx.AsyncClient):
    res = await client.get("/")
    assert res.status_code == 200
    headers = res.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-xss-protection") == "1; mode=block"
    assert headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_sql_injection_username_rejection():
    # Attempt SQL injection usernames
    assert validate_username("admin' OR '1'='1") is False
    assert validate_username("user; DROP TABLE users;--") is False
    assert validate_username("test--") is False
    assert validate_username("admin/*") is False


def test_password_argon2id_format():
    hashed = hash_password("Secret123456!")
    # Argon2id identifier
    assert hashed.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
