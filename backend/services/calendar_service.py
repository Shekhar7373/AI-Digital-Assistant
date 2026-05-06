"""
Calendar Service.
"""

import asyncio
from datetime import datetime

from db.mongodb import get_db
from services.google_auth_service import CALENDAR_WRITE_SCOPES, build_google_service, google_action_error

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
        "url": created.get("htmlLink", ""),
    }


async def _safe_replace_meetings(meetings: list[dict]):
    db = get_db()
    if db is None:
        return
    try:
        payload = [{k: v for k, v in meeting.items() if k != "_id"} for meeting in meetings]
        await db.meetings.delete_many({})
        if payload:
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


async def _safe_load_meetings(limit: int) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    try:
        return await db.meetings.find({}, {"_id": 0}).sort("date", 1).to_list(length=max(limit, 1))
    except Exception as error:
        print(f"[CalendarService] Failed to load meetings: {error}")
        return []


async def fetch_meetings(limit: int = 6) -> list[dict]:
    """
    Fetch upcoming meetings from Google Calendar and cache only real results.
    """
    global MEETING_CACHE
    max_results = max(1, min(limit or 6, 8))
    try:
        MEETING_CACHE = await asyncio.to_thread(_fetch_calendar_events_sync, max_results)
    except Exception as error:
        print(f"[CalendarService] Calendar fetch failed: {error}")
        cached = await _safe_load_meetings(max_results)
        MEETING_CACHE = cached if cached else []
    await _safe_replace_meetings(MEETING_CACHE)
    return MEETING_CACHE[:max_results]


async def schedule_meeting_mock(params: dict) -> dict:
    """
    Schedule a real calendar event when authorized.
    """
    auth_error = google_action_error("create a Google Calendar event", CALENDAR_WRITE_SCOPES)
    if auth_error:
        return {"error": auth_error}

    try:
        meeting = await asyncio.to_thread(_schedule_meeting_sync, params)
    except Exception as error:
        print(f"[CalendarService] Calendar insert failed: {error}")
        return {"error": f"Unable to create the Google Calendar event: {error}"}

    MEETING_CACHE.append(meeting.copy())
    await _safe_insert_meeting(meeting)
    return meeting
