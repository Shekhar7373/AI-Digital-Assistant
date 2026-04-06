"""
Calendar Service.
"""

import asyncio
from datetime import datetime, timedelta

from db.mongodb import get_db
from services.google_auth_service import build_google_service

MOCK_MEETINGS = [
    {
        "id": "meet_001",
        "title": "Sprint Planning",
        "date": (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
        "duration_minutes": 60,
        "attendees": ["alice@company.com", "bob@company.com"],
        "location": "Zoom",
        "description": "Plan tasks for the upcoming sprint.",
    },
    {
        "id": "meet_002",
        "title": "Design Review",
        "date": (datetime.utcnow() + timedelta(days=1, hours=3)).strftime("%Y-%m-%d %H:%M"),
        "duration_minutes": 45,
        "attendees": ["carol@company.com", "dave@company.com"],
        "location": "Google Meet",
        "description": "Review new UI mockups.",
    },
    {
        "id": "meet_003",
        "title": "1:1 with Manager",
        "date": (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M"),
        "duration_minutes": 30,
        "attendees": ["manager@company.com"],
        "location": "Office — Room 3A",
        "description": "Weekly check-in.",
    },
]

MEETING_CACHE: list[dict] = []


def _format_event_datetime(event_time: dict) -> str:
    return event_time.get("dateTime") or event_time.get("date") or ""


def _fetch_calendar_events_sync(max_results: int = 6) -> list[dict]:
    service = build_google_service("calendar", "v3")
    response = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=datetime.utcnow().isoformat() + "Z",
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = []
    for event in response.get("items", []):
        attendees = [attendee.get("email", "") for attendee in event.get("attendees", []) if attendee.get("email")]
        start = event.get("start", {})
        end = event.get("end", {})
        events.append(
            {
                "id": event.get("id"),
                "title": event.get("summary") or "(No title)",
                "date": _format_event_datetime(start),
                "end_date": _format_event_datetime(end),
                "duration_minutes": 30,
                "attendees": attendees,
                "location": event.get("location", ""),
                "description": event.get("description", ""),
                "source": "google_calendar",
                "url": event.get("htmlLink", ""),
            }
        )
    return events


def _schedule_meeting_sync(params: dict) -> dict:
    service = build_google_service("calendar", "v3")
    start = params.get("date")
    end = params.get("end_date")
    if not start:
        raise ValueError("date is required to schedule a meeting")

    event = {
        "summary": params.get("title", "New Meeting"),
        "description": params.get("description", ""),
        "start": {"dateTime": start},
        "end": {"dateTime": end or start},
        "attendees": [{"email": email} for email in params.get("attendees", [])],
        "location": params.get("location", ""),
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return {
        "id": created.get("id"),
        "title": created.get("summary"),
        "date": _format_event_datetime(created.get("start", {})),
        "end_date": _format_event_datetime(created.get("end", {})),
        "attendees": [attendee.get("email", "") for attendee in created.get("attendees", []) if attendee.get("email")],
        "location": created.get("location", ""),
        "status": created.get("status", "scheduled"),
        "source": "google_calendar",
    }


async def _safe_replace_meetings(meetings: list[dict]):
    db = get_db()
    if db is None:
        return
    try:
        payload = [{k: v for k, v in meeting.items() if k != "_id"} for meeting in meetings]
        await db.meetings.delete_many({})
        await db.meetings.insert_many(payload)
    except Exception as error:
        print(f"[CalendarService] Failed to persist meetings: {error}")


async def _safe_insert_meeting(meeting: dict):
    db = get_db()
    if db is None:
        return
    try:
        payload = {k: v for k, v in meeting.items() if k != "_id"}
        await db.meetings.insert_one(payload)
    except Exception as error:
        print(f"[CalendarService] Failed to insert meeting: {error}")


async def fetch_meetings(limit: int = 6) -> list[dict]:
    """
    Fetch upcoming meetings from Google Calendar when authorized, otherwise use local fallback data.
    """
    global MEETING_CACHE
    max_results = max(1, min(limit or 6, 8))
    try:
        MEETING_CACHE = await asyncio.to_thread(_fetch_calendar_events_sync, max_results)
    except Exception as error:
        print(f"[CalendarService] Calendar fetch failed, using fallback data: {error}")
        MEETING_CACHE = [dict(meeting) for meeting in MOCK_MEETINGS[:max_results]]
    await _safe_replace_meetings(MEETING_CACHE)
    return MEETING_CACHE


async def schedule_meeting_mock(params: dict) -> dict:
    """
    Schedule a real calendar event when authorized, otherwise use local fallback behavior.
    """
    try:
        meeting = await asyncio.to_thread(_schedule_meeting_sync, params)
    except Exception as error:
        print(f"[CalendarService] Calendar insert failed, using fallback data: {error}")
        title = params.get("title", "New Meeting")
        date = params.get("date", (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M"))
        attendees = params.get("attendees", [])
        duration = params.get("duration_minutes", 30)

        meeting = {
            "id": f"meet_{datetime.utcnow().timestamp():.0f}",
            "title": title,
            "date": date,
            "duration_minutes": duration,
            "attendees": attendees,
            "location": "TBD",
            "status": "scheduled",
            "source": "fallback",
        }

    MEETING_CACHE.append(meeting.copy())
    await _safe_insert_meeting(meeting)
    return meeting
