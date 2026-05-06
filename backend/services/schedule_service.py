"""
Schedule service for recurring weather delivery and one-time task reminders.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from db.mongodb import get_db
from services.notification_service import send_summary_email, send_telegram_notification
from services.preferences_service import resolve_weather_location
from services.weather_service import get_weather

APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Calcutta")
SCHEDULER_POLL_SECONDS = int(os.getenv("SCHEDULER_POLL_SECONDS", "30"))
SUPPORTED_SCHEDULE_TYPES = {"weather_email", "task_reminder"}
SUPPORTED_RECURRENCES = {"daily", "once"}

SCHEDULE_CACHE: list[dict] = []


def _frontend_base_url() -> str:
    return (os.getenv("FRONTEND_BASE_URL") or os.getenv("APP_FRONTEND_URL") or "").strip().rstrip("/")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timezone_or_default(name: str | None = None) -> ZoneInfo:
    try:
        return ZoneInfo(name or APP_TIMEZONE)
    except Exception:
        return ZoneInfo(APP_TIMEZONE)


def _normalize_time_local(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return "18:00"

    if raw in {"morning"}:
        return "09:00"
    if raw in {"afternoon"}:
        return "15:00"
    if raw in {"evening"}:
        return "18:00"
    if raw in {"night"}:
        return "21:00"

    try:
        parsed = datetime.strptime(raw.replace(".", ":"), "%H:%M")
        return parsed.strftime("%H:%M")
    except Exception:
        pass

    for fmt in ("%I:%M%p", "%I%p", "%I:%M %p", "%I %p"):
        try:
            parsed = datetime.strptime(raw.replace(" ", ""), fmt.replace(" ", ""))
            return parsed.strftime("%H:%M")
        except Exception:
            continue

    return "18:00"


def _compute_next_run_at(time_local: str, timezone_name: str, now_utc: datetime | None = None) -> str:
    now_utc = now_utc or _utc_now()
    tz = _timezone_or_default(timezone_name)
    local_now = now_utc.astimezone(tz)
    hour, minute = (int(part) for part in time_local.split(":", 1))
    next_local = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_local <= local_now:
        next_local = next_local + timedelta(days=1)
    return next_local.astimezone(timezone.utc).isoformat()


def _resume_next_run_at(job: dict, now_utc: datetime | None = None) -> str:
    now_utc = now_utc or _utc_now()
    if job.get("recurrence") == "once":
        due_raw = job.get("task_due_date") or job.get("next_run_at") or ""
        due_at = _normalize_datetime(due_raw, job.get("timezone", APP_TIMEZONE))
        if not due_at:
            return (now_utc + timedelta(minutes=1)).isoformat()
        try:
            parsed_due = datetime.fromisoformat(due_at)
        except Exception:
            return (now_utc + timedelta(minutes=1)).isoformat()
        if parsed_due <= now_utc:
            return (now_utc + timedelta(minutes=1)).isoformat()
        return due_at

    return _compute_next_run_at(job.get("time_local", "18:00"), job.get("timezone", APP_TIMEZONE), now_utc=now_utc)


def _normalize_datetime(value: str | None, timezone_name: str | None = None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return ""

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_timezone_or_default(timezone_name))
    return parsed.astimezone(timezone.utc).isoformat()


def _serialize_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "_id"}


async def _insert_job(job: dict) -> str:
    db = get_db()
    if db is not None:
        try:
            payload = _serialize_job(job)
            result = await db.recurring_jobs.insert_one(payload)
            return str(result.inserted_id)
        except Exception as error:
            print(f"[ScheduleService] Failed to persist schedule: {error}")
    return job["id"]


async def _replace_cached_job(job: dict):
    for index, existing in enumerate(SCHEDULE_CACHE):
        if existing.get("id") == job.get("id"):
            SCHEDULE_CACHE[index] = job
            return
    SCHEDULE_CACHE.append(job)


def _build_weather_email_content(weather: dict) -> tuple[str, dict]:
    city = weather.get("city", "your preferred location")
    condition = weather.get("condition", "Unknown")
    temperature = weather.get("temperature_c")
    wind_speed = weather.get("wind_speed_kmh")

    body_lines = [
        f"Today's weather report for {city}",
        "",
        f"Temperature: {temperature} C" if temperature is not None else "Temperature: unavailable",
        f"Condition: {condition}",
    ]
    if wind_speed is not None:
        body_lines.append(f"Wind speed: {wind_speed} km/h")

    body = "\n".join(body_lines)
    context = {
        "query": f"Weather report for {city}",
        "summary": body,
        "items": [
            {
                "title": "Current conditions",
                "summary": body.replace("\n", " | "),
                "url": "",
            }
        ],
    }
    return body, context


async def list_recurring_jobs(active_only: bool = False) -> list[dict]:
    query = {"active": True} if active_only else {}
    db = get_db()
    if db is not None:
        try:
            jobs = await db.recurring_jobs.find(query, {"_id": 0}).sort("created_at", -1).to_list(length=200)
            SCHEDULE_CACHE.clear()
            SCHEDULE_CACHE.extend(jobs)
            return jobs
        except Exception as error:
            print(f"[ScheduleService] Failed to load schedules: {error}")

    if active_only:
        return [job for job in SCHEDULE_CACHE if job.get("active")]
    return list(SCHEDULE_CACHE)


async def create_recurring_weather_email_schedule(params: dict) -> dict:
    recipient_email = (params.get("recipient_email") or "").strip()
    if not recipient_email:
        return {"error": "A recipient email is required for recurring weather delivery."}

    recurrence = (params.get("schedule_frequency") or "daily").strip().lower()
    if recurrence not in SUPPORTED_RECURRENCES:
        return {"error": f"Unsupported recurrence '{recurrence}'. Only daily schedules are supported right now."}

    schedule_type = (params.get("schedule_type") or "weather_email").strip().lower()
    if schedule_type not in SUPPORTED_SCHEDULE_TYPES:
        return {"error": f"Unsupported schedule type '{schedule_type}'."}

    timezone_name = (params.get("timezone") or APP_TIMEZONE).strip() or APP_TIMEZONE
    time_local = _normalize_time_local(params.get("schedule_time") or params.get("time"))
    city = await resolve_weather_location(params.get("city"))
    subject = (params.get("email_subject") or f"Daily weather report for {city}").strip()
    created_at = datetime.utcnow().isoformat()

    job = {
        "id": f"schedule_{uuid4().hex[:12]}",
        "name": (params.get("schedule_name") or f"Daily weather email for {city}").strip(),
        "schedule_type": schedule_type,
        "recurrence": recurrence,
        "time_local": time_local,
        "timezone": timezone_name,
        "city": city,
        "recipient_email": recipient_email,
        "email_subject": subject,
        "active": True,
        "last_run_at": "",
        "last_status": "scheduled",
        "last_error": "",
        "created_at": created_at,
        "updated_at": created_at,
        "next_run_at": _compute_next_run_at(time_local, timezone_name),
        "url": f"{_frontend_base_url()}/" if _frontend_base_url() else "",
    }

    await _insert_job(job)
    await _replace_cached_job(job)
    return job


async def create_task_reminder_schedule(params: dict) -> dict:
    task_id = (params.get("task_id") or "").strip()
    title = (params.get("task_title") or params.get("title") or "").strip()
    due_date = _normalize_datetime(params.get("due_date") or params.get("date"), params.get("timezone") or APP_TIMEZONE)
    if not task_id:
        return {"error": "task_id is required to create a reminder schedule."}
    if not due_date:
        return {"error": "A valid due date is required to create a reminder schedule."}

    created_at = datetime.utcnow().isoformat()
    timezone_name = (params.get("timezone") or APP_TIMEZONE).strip() or APP_TIMEZONE
    job = {
        "id": f"schedule_{uuid4().hex[:12]}",
        "name": (params.get("schedule_name") or f"Reminder for {title or 'task'}").strip(),
        "schedule_type": "task_reminder",
        "recurrence": "once",
        "time_local": "",
        "timezone": timezone_name,
        "task_id": task_id,
        "task_title": title or "Untitled task",
        "task_due_date": due_date,
        "recipient_email": (params.get("recipient_email") or "").strip(),
        "telegram_chat_id": str(params.get("telegram_chat_id") or "").strip(),
        "active": True,
        "last_run_at": "",
        "last_status": "scheduled",
        "last_error": "",
        "created_at": created_at,
        "updated_at": created_at,
        "next_run_at": due_date,
        "url": f"{_frontend_base_url()}/" if _frontend_base_url() else "",
    }

    await _insert_job(job)
    await _replace_cached_job(job)
    return job


async def update_schedule_active(job_id: str, active: bool) -> dict:
    jobs = await list_recurring_jobs()
    job = next((item for item in jobs if item.get("id") == job_id), None)
    if not job:
        return {"error": f"Schedule '{job_id}' was not found."}

    updated = {
        **job,
        "active": bool(active),
        "updated_at": datetime.utcnow().isoformat(),
        "last_status": "scheduled" if active else "paused",
        "next_run_at": _resume_next_run_at(job) if active else "",
    }

    db = get_db()
    if db is not None:
        try:
            await db.recurring_jobs.update_one({"id": job_id}, {"$set": _serialize_job(updated)})
        except Exception as error:
            print(f"[ScheduleService] Failed to update schedule: {error}")

    await _replace_cached_job(updated)
    return updated


async def delete_schedule(job_id: str) -> dict:
    deleted = False
    db = get_db()
    if db is not None:
        try:
            result = await db.recurring_jobs.delete_one({"id": job_id})
            deleted = bool(result.deleted_count)
        except Exception as error:
            print(f"[ScheduleService] Failed to delete schedule: {error}")

    for index, job in enumerate(list(SCHEDULE_CACHE)):
        if job.get("id") == job_id:
            SCHEDULE_CACHE.pop(index)
            deleted = True
            break

    return {"id": job_id, "deleted": deleted}


async def _mark_job(job_id: str, **updates):
    payload = {"updated_at": datetime.utcnow().isoformat(), **updates}
    db = get_db()
    if db is not None:
        try:
            await db.recurring_jobs.update_one({"id": job_id}, {"$set": payload})
        except Exception as error:
            print(f"[ScheduleService] Failed to mark schedule state: {error}")


async def _execute_weather_email_job(job: dict) -> dict:
    city = await resolve_weather_location(job.get("city"))
    weather = await get_weather(city)
    if weather.get("error"):
        return weather

    body, context = _build_weather_email_content(weather)
    result = await send_summary_email(
        job.get("recipient_email", ""),
        job.get("email_subject", f"Daily weather report for {city}"),
        body,
        context,
    )
    if result.get("error"):
        return result
    return {"weather": weather, "delivery": result}


async def _complete_linked_task(job: dict):
    task_id = job.get("task_id")
    if not task_id:
        return

    db = get_db()
    if db is None:
        return
    try:
        await db.tasks.update_one(
            {"id": task_id},
            {"$set": {"updated_at": datetime.utcnow().isoformat()}},
        )
    except Exception as error:
        print(f"[ScheduleService] Failed to touch linked task '{task_id}': {error}")


async def _execute_task_reminder_job(job: dict) -> dict:
    title = job.get("task_title", "Untitled task")
    due_date = job.get("task_due_date", job.get("next_run_at", ""))
    reminder_text = (
        f"Task reminder\n\n"
        f"Title: {title}\n"
        f"Due: {due_date}\n"
        f"Task ID: {job.get('task_id', 'unknown')}"
    )

    deliveries: list[dict] = []
    telegram_chat_id = job.get("telegram_chat_id", "").strip()
    recipient_email = job.get("recipient_email", "").strip()

    if telegram_chat_id:
        telegram_result = await send_telegram_notification(telegram_chat_id, reminder_text)
        deliveries.append({"channel": "telegram", "result": telegram_result})

    if recipient_email:
        email_result = await send_summary_email(
            recipient_email,
            f"Task reminder: {title}",
            reminder_text,
            {
                "query": f"Reminder for {title}",
                "summary": reminder_text,
                "items": [],
            },
        )
        deliveries.append({"channel": "email", "result": email_result})

    await _complete_linked_task(job)

    if not deliveries:
        return {
            "deliveries": [{"channel": "dashboard", "result": {"ok": True}}],
            "note": "Reminder reached its due time. Review it from the dashboard.",
        }

    errors = [item["result"].get("error") for item in deliveries if item["result"].get("error")]
    if errors:
        return {"error": "; ".join(errors), "deliveries": deliveries}
    return {"deliveries": deliveries}


async def run_due_schedules_once() -> list[dict]:
    now_utc = _utc_now()
    due_jobs = []
    for job in await list_recurring_jobs(active_only=True):
        next_run_at = job.get("next_run_at")
        if not next_run_at:
            continue
        try:
            if datetime.fromisoformat(next_run_at) <= now_utc:
                due_jobs.append(job)
        except Exception:
            continue

    outcomes = []
    for job in due_jobs:
        await _mark_job(job["id"], last_status="running", last_error="")
        try:
            if job.get("schedule_type") == "task_reminder":
                result = await _execute_task_reminder_job(job)
            else:
                result = await _execute_weather_email_job(job)
            success = not result.get("error")
            is_once = job.get("recurrence") == "once"
            updates = {
                "last_run_at": now_utc.isoformat(),
                "last_status": "sent" if success else "failed",
                "last_error": result.get("error", ""),
                "next_run_at": "" if is_once else _compute_next_run_at(job.get("time_local", "18:00"), job.get("timezone", APP_TIMEZONE), now_utc=now_utc + timedelta(seconds=1)),
                "active": False if is_once and success else job.get("active", True),
            }
            await _mark_job(job["id"], **updates)
            refreshed = {**job, **updates}
            await _replace_cached_job(refreshed)
            outcomes.append({"id": job["id"], "ok": success, "result": result})
        except Exception as error:
            is_once = job.get("recurrence") == "once"
            updates = {
                "last_run_at": now_utc.isoformat(),
                "last_status": "failed",
                "last_error": str(error),
                "next_run_at": "" if is_once else _compute_next_run_at(job.get("time_local", "18:00"), job.get("timezone", APP_TIMEZONE), now_utc=now_utc + timedelta(seconds=1)),
                "active": False if is_once else job.get("active", True),
            }
            await _mark_job(job["id"], **updates)
            refreshed = {**job, **updates}
            await _replace_cached_job(refreshed)
            outcomes.append({"id": job["id"], "ok": False, "result": {"error": str(error)}})
            print(f"[ScheduleService] Schedule '{job['id']}' failed: {error}")
    return outcomes


async def scheduler_loop(stop_event: asyncio.Event):
    print(f"[ScheduleService] Scheduler loop started with {SCHEDULER_POLL_SECONDS}s polling.")
    while not stop_event.is_set():
        try:
            await run_due_schedules_once()
        except Exception as error:
            print(f"[ScheduleService] Scheduler tick failed: {error}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=SCHEDULER_POLL_SECONDS)
        except asyncio.TimeoutError:
            continue
    print("[ScheduleService] Scheduler loop stopped.")
