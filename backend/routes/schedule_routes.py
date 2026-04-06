from fastapi import APIRouter
from pydantic import BaseModel

from services.schedule_service import (
    create_recurring_weather_email_schedule,
    delete_schedule,
    list_recurring_jobs,
    update_schedule_active,
)

router = APIRouter()


class ScheduleCreate(BaseModel):
    recipient_email: str
    city: str = ""
    schedule_time: str = "18:00"
    timezone: str = "Asia/Calcutta"
    email_subject: str = ""
    schedule_name: str = ""


class ScheduleStatusUpdate(BaseModel):
    active: bool


@router.get("")
async def get_schedules(active_only: bool = False):
    return await list_recurring_jobs(active_only=active_only)


@router.post("")
async def create_schedule(payload: ScheduleCreate):
    return await create_recurring_weather_email_schedule(payload.model_dump())


@router.patch("/{schedule_id}")
async def patch_schedule(schedule_id: str, payload: ScheduleStatusUpdate):
    return await update_schedule_active(schedule_id, payload.active)


@router.delete("/{schedule_id}")
async def remove_schedule(schedule_id: str):
    return await delete_schedule(schedule_id)
