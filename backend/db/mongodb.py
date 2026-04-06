"""
MongoDB connection manager using Motor (async MongoDB driver).
Provides a shared database instance to the rest of the app.
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "agentic_assistant")

# Global client and db references
client: AsyncIOMotorClient = None
db = None


async def connect_db():
    """Called at app startup to initialize the MongoDB connection."""
    global client, db
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    print(f"[DB] Connected to MongoDB: {MONGO_URI} / {DB_NAME}")


async def disconnect_db():
    """Called at app shutdown to close the MongoDB connection."""
    global client
    if client:
        client.close()
        print("[DB] Disconnected from MongoDB")


def get_db():
    """Returns the active database instance."""
    return db
