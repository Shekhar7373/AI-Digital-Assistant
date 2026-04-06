"""
Preference service for lightweight app-level user settings.
"""

from __future__ import annotations

from datetime import datetime

from db.mongodb import get_db

DEFAULT_WEATHER_LOCATION = "SDMCET, Dharwad, Karnataka, India"

PREFERENCES_CACHE: dict[str, str] = {
    "weather_location": DEFAULT_WEATHER_LOCATION,
}


def _default_preferences() -> dict:
    return {
        "weather_location": PREFERENCES_CACHE["weather_location"],
        "updated_at": "",
    }


async def get_user_preferences() -> dict:
    db = get_db()
    if db is not None:
        try:
            doc = await db.user_preferences.find_one({"key": "singleton"}, {"_id": 0, "key": 0})
            if doc:
                PREFERENCES_CACHE.update({k: v for k, v in doc.items() if k in PREFERENCES_CACHE and v})
                return {**_default_preferences(), **doc}
        except Exception as error:
            print(f"[PreferencesService] Failed to load preferences: {error}")
    return _default_preferences()


async def update_user_preferences(weather_location: str | None = None) -> dict:
    normalized_location = (weather_location or "").strip() or DEFAULT_WEATHER_LOCATION
    payload = {
        "key": "singleton",
        "weather_location": normalized_location,
        "updated_at": datetime.utcnow().isoformat(),
    }

    db = get_db()
    if db is not None:
        try:
            await db.user_preferences.replace_one({"key": "singleton"}, payload, upsert=True)
        except Exception as error:
            print(f"[PreferencesService] Failed to persist preferences: {error}")

    PREFERENCES_CACHE["weather_location"] = normalized_location
    return {k: v for k, v in payload.items() if k != "key"}


async def resolve_weather_location(requested_location: str | None = None) -> str:
    normalized = (requested_location or "").strip()
    if normalized and normalized.lower() not in {"current location", "my location", "user's location"}:
        return normalized

    preferences = await get_user_preferences()
    return preferences.get("weather_location") or DEFAULT_WEATHER_LOCATION
