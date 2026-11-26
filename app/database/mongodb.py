import asyncio
import logging
from typing import Optional
import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
import pymongo
from app.config.settings import settings

logger = logging.getLogger("nodeshare.database.mongodb")

_mongo_client: Optional[AsyncIOMotorClient] = None
_mongo_db: Optional[AsyncIOMotorDatabase] = None
_last_mongo_error: Optional[str] = None
_mongo_init_lock = asyncio.Lock()


async def init_mongodb() -> Optional[AsyncIOMotorDatabase]:
    """Initialize AsyncIOMotorClient to MongoDB Atlas."""
    global _mongo_client, _mongo_db, _last_mongo_error

    if not settings.MONGODB_URI:
        _last_mongo_error = "MONGODB_URI not set"
        logger.warning(
            "MONGODB_URI is not set. MongoDB operations for chat messages will not connect."
        )
        return None

    try:
        # Configure client with timeouts and certifi CA bundle for serverless & Windows compatibility
        _mongo_client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            maxPoolSize=10,
            minPoolSize=1
        )
        _mongo_db = _mongo_client[settings.MONGODB_DATABASE]

        # Verify connection with ping
        await _mongo_client.admin.command("ping")
        _last_mongo_error = None
        logger.info(f"Successfully connected to MongoDB Atlas database: {settings.MONGODB_DATABASE}")

        # Ensure indexes for chat messages collection
        await _ensure_mongo_indexes(_mongo_db)

    except Exception as e:
        _last_mongo_error = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to connect to MongoDB Atlas: {e}")
        if _mongo_client:
            _mongo_client.close()
        _mongo_client = None
        _mongo_db = None

    return _mongo_db


async def ensure_mongodb() -> Optional[AsyncIOMotorDatabase]:
    """Lazily initialize MongoDB if not yet connected (essential for Vercel serverless)."""
    if _mongo_db is not None:
        return _mongo_db
    async with _mongo_init_lock:
        if _mongo_db is not None:
            return _mongo_db
        return await init_mongodb()


async def _ensure_mongo_indexes(db: AsyncIOMotorDatabase) -> None:
    """Create essential MongoDB indexes for message retrieval and idempotency."""
    try:
        messages = db["messages"]
        # Index for paginated conversation history lookup
        await messages.create_index(
            [("conversation_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)],
            name="idx_conv_created"
        )
        # Unique index on message_id
        await messages.create_index(
            [("message_id", pymongo.ASCENDING)],
            unique=True,
            name="idx_unique_message_id"
        )
        # Sparse unique index on idempotency_key for deduplication
        await messages.create_index(
            [("idempotency_key", pymongo.ASCENDING)],
            unique=True,
            sparse=True,
            name="idx_unique_idempotency_key"
        )
        # Index on sender_id
        await messages.create_index(
            [("sender_id", pymongo.ASCENDING)],
            name="idx_sender_id"
        )
        logger.info("MongoDB message indexes ensured.")
    except Exception as e:
        logger.error(f"Failed to ensure MongoDB indexes: {e}")


async def close_mongodb() -> None:
    """Close MongoDB connection client."""
    global _mongo_client, _mongo_db
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        _mongo_db = None
        logger.info("Closed MongoDB client connection.")


def get_mongodb() -> Optional[AsyncIOMotorDatabase]:
    """Get active MongoDB database instance."""
    return _mongo_db


async def check_mongodb_health() -> dict:
    """Check health of MongoDB connection."""
    global _mongo_client, _last_mongo_error
    if not _mongo_client:
        if not settings.MONGODB_URI:
            return {"status": "unconfigured", "message": "MONGODB_URI not set"}
        resp = {"status": "disconnected", "message": "Client not initialized"}
        if _last_mongo_error:
            resp["error"] = _last_mongo_error
        return resp

    try:
        await _mongo_client.admin.command("ping")
        return {"status": "healthy"}
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
