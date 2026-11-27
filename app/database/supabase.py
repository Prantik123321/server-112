import asyncio
import json
import logging
from typing import Optional
import asyncpg
from supabase import create_client, Client
from app.config.settings import settings

logger = logging.getLogger("nodeshare.database.supabase")

# Global asyncpg connection pool
_pg_pool: Optional[asyncpg.Pool] = None

# Global Supabase client (for Storage & Realtime)
_supabase_client: Optional[Client] = None

# Last connection error (sanitized, without credentials)
_last_pg_error: Optional[str] = None
_pg_init_lock = asyncio.Lock()


async def _init_pg_connection(conn: asyncpg.Connection) -> None:
    """Register JSON/JSONB codecs so Python dicts serialize/deserialize cleanly."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def init_supabase_db() -> Optional[asyncpg.Pool]:
    """Initialize asyncpg connection pool to Supabase PostgreSQL."""
    global _pg_pool, _supabase_client, _last_pg_error

    # Initialize Supabase SDK client if credentials present
    service_key = settings.effective_service_role_key
    if settings.SUPABASE_URL and service_key:
        try:
            _supabase_client = create_client(
                settings.SUPABASE_URL,
                service_key
            )
            logger.info("Successfully initialized Supabase Client SDK.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase Client SDK: {e}")
            _supabase_client = None

    if not settings.SUPABASE_POSTGRES_URL:
        _last_pg_error = "SUPABASE_POSTGRES_URL not set"
        logger.warning(
            "SUPABASE_POSTGRES_URL is not set. Database operations requiring PostgreSQL will not connect."
        )
        return None

    if "YOUR_REAL_DB_PASSWORD" in settings.SUPABASE_POSTGRES_URL:
        _last_pg_error = "SUPABASE_POSTGRES_URL still contains placeholder password (YOUR_REAL_DB_PASSWORD)"
        logger.warning(_last_pg_error)
        return None

    try:
        # statement_cache_size=0 is required for Supabase PgBouncer Transaction Pooler (port 6543)
        _pg_pool = await asyncpg.create_pool(
            dsn=settings.SUPABASE_POSTGRES_URL,
            min_size=1,
            max_size=5,
            command_timeout=30.0,
            max_inactive_connection_lifetime=300.0,
            statement_cache_size=0,
            init=_init_pg_connection,
        )
        _last_pg_error = None
        logger.info("Successfully connected to Supabase PostgreSQL asyncpg pool.")
    except Exception as e:
        _last_pg_error = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to connect to Supabase PostgreSQL: {e}")
        _pg_pool = None

    return _pg_pool


async def ensure_supabase_db() -> Optional[asyncpg.Pool]:
    """Lazily initialize PostgreSQL pool if not yet connected (essential for Vercel serverless)."""
    if _pg_pool is not None:
        return _pg_pool
    async with _pg_init_lock:
        if _pg_pool is not None:
            return _pg_pool
        return await init_supabase_db()


async def close_supabase_db() -> None:
    """Close asyncpg connection pool."""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("Closed Supabase PostgreSQL connection pool.")


def get_pg_pool() -> Optional[asyncpg.Pool]:
    """Get the active asyncpg connection pool."""
    return _pg_pool


def get_supabase_client() -> Optional[Client]:
    """Get the initialized Supabase Python SDK client."""
    return _supabase_client


async def check_supabase_health() -> dict:
    """Check health of Supabase PostgreSQL connection."""
    global _pg_pool, _last_pg_error
    if not _pg_pool:
        if not settings.SUPABASE_POSTGRES_URL or "YOUR_REAL_DB_PASSWORD" in settings.SUPABASE_POSTGRES_URL:
            return {
                "status": "unconfigured",
                "message": "PostgreSQL connection is not configured.",
            }
        return {"status": "disconnected", "message": "PostgreSQL connection pool is unavailable."}

    try:
        async with _pg_pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            if result == 1:
                return {"status": "healthy", "latency_ms": 1}
    except Exception as e:
        logger.error(f"Supabase health check failed: {e}")
        return {"status": "unhealthy", "message": "PostgreSQL health check failed."}

    return {"status": "unknown"}
