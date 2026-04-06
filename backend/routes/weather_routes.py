from fastapi import APIRouter
from services.weather_service import get_weather

router = APIRouter()

DEFAULT_WEATHER_LOCATION = "SDMCET, Dharwad, Karnataka, India"

@router.get("")
async def weather(city: str = DEFAULT_WEATHER_LOCATION): return await get_weather(city)
