"""MongoDB connection and collection access."""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_mongodb() -> None:
    """Connect to MongoDB. Call once during FastAPI lifespan startup."""
    global _client, _db
    mongo_url = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = os.getenv("MONGODB_DATABASE", "trippy")

    _client = AsyncIOMotorClient(mongo_url)
    _db = _client[db_name]

    # Quick connectivity check
    try:
        await _client.admin.command("ping")
        logger.info("MongoDB connected: %s / %s", mongo_url, db_name)
    except Exception as e:
        logger.warning("MongoDB ping failed (will retry on first use): %s", e)


async def close_mongodb() -> None:
    """Close the MongoDB connection. Call during FastAPI lifespan shutdown."""
    global _client
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")


def get_db() -> AsyncIOMotorDatabase:
    """Return the database handle. Raises if init_mongodb() hasn't been called."""
    if _db is None:
        raise RuntimeError("MongoDB not initialized — call init_mongodb() first")
    return _db
