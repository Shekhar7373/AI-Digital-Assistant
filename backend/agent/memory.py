"""
Agent memory module.
Stores and retrieves chat history and intermediate results (emails, tasks, etc.)
in MongoDB so the agent has context across turns.
"""

from datetime import datetime
from db.mongodb import get_db


async def save_message(session_id: str, role: str, content: str):
    """Persist a single chat message to MongoDB."""
    db = get_db()
    if db is None:
        return
    await db.chat_history.insert_one({
        "session_id": session_id,
        "role": role,           # "user" | "assistant"
        "content": content,
        "timestamp": datetime.utcnow(),
    })


async def get_history(session_id: str, limit: int = 20) -> list[dict]:
    """
    Retrieve the last `limit` messages for a session.
    Returns list of {"role": ..., "content": ...} dicts.
    """
    db = get_db()
    if db is None:
        return []
    cursor = db.chat_history.find(
        {"session_id": session_id},
        {"_id": 0, "role": 1, "content": 1}
    ).sort("timestamp", -1).limit(limit)
    messages = await cursor.to_list(length=limit)
    return list(reversed(messages))  # chronological order


async def clear_history(session_id: str):
    """Delete all messages for a session (e.g., on user logout or reset)."""
    db = get_db()
    if db is None:
        return
    await db.chat_history.delete_many({"session_id": session_id})


async def save_context(key: str, value):
    """
    Store arbitrary key-value context (e.g., last fetched emails).
    Overwrites if key already exists.
    """
    db = get_db()
    if db is None:
        return
    await db.agent_context.replace_one(
        {"key": key},
        {"key": key, "value": value, "updated_at": datetime.utcnow()},
        upsert=True,
    )


async def get_context(key: str):
    """Retrieve stored context value by key. Returns None if not found."""
    db = get_db()
    if db is None:
        return None
    doc = await db.agent_context.find_one({"key": key}, {"_id": 0, "value": 1})
    return doc["value"] if doc else None
