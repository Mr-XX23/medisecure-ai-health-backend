"""MongoDB database connection and management."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)


class Database:
    """MongoDB database connection manager."""

    client: Optional[AsyncIOMotorClient] = None
    database: Optional[AsyncIOMotorDatabase] = None

    @classmethod
    async def connect_db(cls):
        """Connect to MongoDB."""
        try:
            cls.client = AsyncIOMotorClient(settings.mongodb_uri)
            cls.database = cls.client[settings.mongodb_database]

            # Test connection
            await cls.client.admin.command("ping")
            logger.info(f"Connected to MongoDB: {settings.mongodb_database}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise

    @classmethod
    async def close_db(cls):
        """Close MongoDB connection."""
        if cls.client:
            cls.client.close()
            logger.info("Closed MongoDB connection")

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """Get database instance."""
        if cls.database is None:
            raise RuntimeError("Database not initialized. Call connect_db() first.")
        return cls.database

    @classmethod
    def get_collection(cls, collection_name: str):
        """Get a collection from the database."""
        db = cls.get_database()
        return db[collection_name]


# Convenience functions
async def get_sessions_collection():
    """Get symptom_sessions collection."""
    return Database.get_collection(settings.mongodb_collection_sessions)


async def get_assessments_collection():
    """Get triage_assessments collection."""
    return Database.get_collection(settings.mongodb_collection_assessments)
