"""
Weather Service.

Uses the Open-Meteo API (completely free, no API key required).
Geocoding is done via the Open-Meteo geocoding endpoint.
"""

from __future__ import annotations

import httpx

from services.preferences_service import resolve_weather_location

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_WEATHER_LOCATION = "SDMCET, Dharwad, Karnataka, India"
DEFAULT_WEATHER_GEOCODE_QUERY = "Dharwad, Karnataka, India"
DEFAULT_WEATHER_COORDS = {"latitude": 15.4589, "longitude": 75.0078, "country": "India"}

WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    80: "Slight showers",
    81: "Moderate showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
}


def _normalize_geocode_query(city: str) -> str:
    normalized = city.strip()
    if normalized.lower() == DEFAULT_WEATHER_LOCATION.lower():
        return DEFAULT_WEATHER_GEOCODE_QUERY
    return normalized


def _fallback_geocode_queries(city: str) -> list[str]:
    normalized = _normalize_geocode_query(city)
    parts = [part.strip() for part in normalized.split(",") if part.strip()]
    queries = [normalized]
    if len(parts) > 1:
        for index in range(1, len(parts)):
            candidate = ", ".join(parts[index:])
            if candidate and candidate not in queries:
                queries.append(candidate)
    return queries


async def get_weather(city: str = DEFAULT_WEATHER_LOCATION) -> dict:
    """
    Fetch current weather for a city using Open-Meteo (no API key needed).
    Returns temperature, wind speed, and weather condition.
    """
    requested_city = await resolve_weather_location(city or DEFAULT_WEATHER_LOCATION)
    geocode_query = _normalize_geocode_query(requested_city)

    if requested_city.strip().lower() == DEFAULT_WEATHER_LOCATION.lower():
        lat = DEFAULT_WEATHER_COORDS["latitude"]
        lon = DEFAULT_WEATHER_COORDS["longitude"]
        country = DEFAULT_WEATHER_COORDS["country"]
        async with httpx.AsyncClient(timeout=10) as client:
            wx_resp = await client.get(
                WEATHER_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current_weather": True,
                    "hourly": "relativehumidity_2m",
                    "forecast_days": 1,
                },
            )
            wx_resp.raise_for_status()
            wx_data = wx_resp.json()

        current = wx_data.get("current_weather", {})
        wmo_code = current.get("weathercode", 0)
        return {
            "city": requested_city,
            "country": country,
            "temperature_c": current.get("temperature"),
            "wind_speed_kmh": current.get("windspeed"),
            "condition": WMO_CODES.get(wmo_code, "Unknown"),
            "is_day": bool(current.get("is_day", 1)),
            "latitude": lat,
            "longitude": lon,
        }

    async with httpx.AsyncClient(timeout=10) as client:
        loc = None
        resolved_query = requested_city
        for candidate in _fallback_geocode_queries(geocode_query):
            geo_resp = await client.get(
                GEOCODE_URL,
                params={"name": candidate, "count": 1, "language": "en", "format": "json"},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            if geo_data.get("results"):
                loc = geo_data["results"][0]
                resolved_query = candidate
                break

        if not loc:
            return {"error": f"City '{requested_city}' not found."}

        lat = loc["latitude"]
        lon = loc["longitude"]

        wx_resp = await client.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": True,
                "hourly": "relativehumidity_2m",
                "forecast_days": 1,
            },
        )
        wx_resp.raise_for_status()
        wx_data = wx_resp.json()

    current = wx_data.get("current_weather", {})
    wmo_code = current.get("weathercode", 0)

    return {
        "city": requested_city if resolved_query == requested_city else f"{requested_city} (matched as {resolved_query})",
        "country": loc.get("country", ""),
        "temperature_c": current.get("temperature"),
        "wind_speed_kmh": current.get("windspeed"),
        "condition": WMO_CODES.get(wmo_code, "Unknown"),
        "is_day": bool(current.get("is_day", 1)),
        "latitude": lat,
        "longitude": lon,
    }
