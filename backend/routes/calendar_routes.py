from fastapi import APIRouter
from pydantic import BaseModel
from services.calendar_service import fetch_meetings, schedule_meeting_mock

router = APIRouter()

@router.get("/meetings")
async def meetings(limit: int = 6): return await fetch_meetings(limit=limit)

@router.post("/schedule")
async def schedule(body: dict): return await schedule_meeting_mock(body)
