import os
import pytest
import asyncio
from typing import AsyncGenerator
import httpx
from httpx import ASGITransport

# Set testing environment before importing app
os.environ["ENVIRONMENT"] = "testing"
os.environ["DEBUG"] = "False"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-unit-testing-nodeshare-32chars"

from app.main import app
from app.config.settings import settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
