import pytest
import httpx
from unittest.mock import patch, AsyncMock
from app.utils.security import hash_password, create_access_token


@pytest.mark.asyncio
async def test_root_and_health_endpoints(client: httpx.AsyncClient):
    # Test Root
    res = await client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["app"] == "NodeShare Backend"
    assert data["status"] == "online"

    # Test Health
    health_res = await client.get("/api/health")
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert "databases" in health_data
    assert "supabase_postgresql" in health_data["databases"]
    assert "mongodb_atlas" in health_data["databases"]


@pytest.mark.asyncio
async def test_registration_validation(client: httpx.AsyncClient):
    # Passwords mismatch
    payload = {
        "full_name": "Test User",
        "username": "testuser",
        "password": "Password123!",
        "confirm_password": "DifferentPassword123!"
    }
    res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 422

    # Weak password
    weak_payload = {
        "full_name": "Test User",
        "username": "testuser",
        "password": "pwd",
        "confirm_password": "pwd"
    }
    res2 = await client.post("/api/auth/register", json=weak_payload)
    assert res2.status_code == 422


@pytest.mark.asyncio
async def test_protected_routes_require_auth(client: httpx.AsyncClient):
    # Call /api/users/me without Authorization header
    res = await client.get("/api/users/me")
    assert res.status_code == 401
    assert "detail" in res.json()

    # Call /api/conversations without token
    res2 = await client.get("/api/conversations")
    assert res2.status_code == 401

    # Call /api/friends/requests without token
    res3 = await client.get("/api/friends/requests")
    assert res3.status_code == 401

    # Call with invalid token
    res4 = await client.get("/api/users/me", headers={"Authorization": "Bearer invalid.token.value"})
    assert res4.status_code == 401


@pytest.mark.asyncio
async def test_malformed_uuid_path_returns_validation_error(client: httpx.AsyncClient):
    token = create_access_token("test-user-id", "testuser")
    response = await client.get(
        "/api/files/not-a-uuid/download-url",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_authenticated_user_access():
    token = create_access_token("test-user-id", "testuser", is_admin=False, is_teacher=False)
    assert token is not None
