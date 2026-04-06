from fastapi import APIRouter
from pydantic import BaseModel

from services.preferences_service import get_user_preferences, update_user_preferences

router = APIRouter()


class PreferencesUpdate(BaseModel):
    weather_location: str


@router.get("")
async def get_preferences():
    return await get_user_preferences()


@router.put("")
async def put_preferences(payload: PreferencesUpdate):
    return await update_user_preferences(payload.weather_location)
