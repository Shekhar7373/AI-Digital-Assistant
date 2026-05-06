"""
Task Service.

Handles CRUD for tasks.
Tasks can be created manually or auto-extracted from email summaries / meeting notes.
"""

import json
import os
from datetime import datetime
from agent.prompt import TASK_EXTRACTION_SYSTEM
from db.mongodb import get_db
from services.calendar_service import schedule_meeting_mock
from services.schedule_service import create_task_reminder_schedule

TASK_CACHE: list[dict] = []


def _frontend_base_url() -> str:
    return (os.getenv("FRONTEND_BASE_URL") or os.getenv("APP_FRONTEND_URL") or "").strip().rstrip("/")


def _normalize_status(status: str) -> str:
    allowed = {"pending", "in_progress", "done"}
    return status if status in allowed else "pending"


def _normalize_priority(priority: str) -> str:
    allowed = {"high", "medium", "low"}
    return priority if priority in allowed else "medium"


async def _safe_insert_task(task: dict) -> str | None:
    db = get_db()
    if db is None:
        return None
    try:
        payload = {k: v for k, v in task.items() if k != "_id"}
        result = await db.tasks.insert_one(payload)
        return str(result.inserted_id)
    except Exception as error:
        print(f"[TaskService] Failed to persist task: {error}")
        return None


async def _safe_find_tasks(query: dict) -> list[dict]:
    db = get_db()
    if db is None:
        return []
    try:
        cursor = db.tasks.find(query, {"_id": 0})
        return await cursor.to_list(length=200)
    except Exception as error:
        print(f"[TaskService] Failed to load tasks: {error}")
        return []


async def _safe_delete_task(task_id: str) -> bool:
    db = get_db()
    if db is None:
        return False
    try:
        from bson import ObjectId

        result = await db.tasks.delete_one({"_id": ObjectId(task_id)})
        if result.deleted_count:
            return True
    except Exception:
        try:
            result = await db.tasks.delete_one({"id": task_id})
            return bool(result.deleted_count)
        except Exception as error:
            print(f"[TaskService] Failed to delete task: {error}")
    return False


async def _safe_load_summary_context() -> list[dict]:
    db = get_db()
    if db is None:
        return []
    try:
        ctx = await db.agent_context.find_one({"key": "last_email_summary"})
        if ctx:
            return ctx.get("summaries", [])
    except Exception as error:
        print(f"[TaskService] Failed to load summary context: {error}")
    return []


async def create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    source: str = "manual",
    due_date: str = "",
    status: str = "pending",
    telegram_chat_id: str = "",
    recipient_email: str = "",
) -> dict:
    """Create a single task and persist it to MongoDB."""
    task = {
        "title": title,
        "description": description,
        "priority": _normalize_priority(priority),   # high | medium | low
        "source": source,       # manual | email | meeting
        "status": _normalize_status(status),    # pending | in_progress | done
        "due_date": due_date,
        "created_at": datetime.utcnow().isoformat(),
        "url": f"{_frontend_base_url()}/" if _frontend_base_url() else "",
    }
    task["id"] = await _safe_insert_task(task) or f"task_{len(TASK_CACHE) + 1:03d}"
    TASK_CACHE.append(task.copy())

    reminder_schedule = None
    calendar_event = None
    if due_date:
        reminder_schedule = await create_task_reminder_schedule(
            {
                "task_id": task["id"],
                "task_title": task["title"],
                "due_date": due_date,
                "telegram_chat_id": telegram_chat_id,
                "recipient_email": recipient_email,
            }
        )
        if reminder_schedule.get("error"):
            task["reminder_error"] = reminder_schedule["error"]
        else:
            task["reminder_schedule_id"] = reminder_schedule.get("id", "")
            task["reminder_schedule"] = reminder_schedule

        calendar_event = await schedule_meeting_mock(
            {
                "title": f"Task: {task['title']}",
                "description": task["description"] or f"Scheduled reminder for task {task['title']}",
                "date": due_date,
                "end_date": due_date,
                "attendees": [],
                "location": "",
            }
        )
        if calendar_event.get("error"):
            task["calendar_sync_error"] = calendar_event["error"]
        else:
            task["calendar_event_id"] = calendar_event.get("id", "")
            task["calendar_event_url"] = calendar_event.get("url", "")
            task["calendar_event"] = calendar_event

    if reminder_schedule and not reminder_schedule.get("error"):
        task["reminder_schedule_id"] = reminder_schedule.get("id", "")
    return task


async def get_all_tasks(status: str = None, limit: int = 100) -> list[dict]:
    """
    Retrieve all tasks. Optionally filter by status.
    """
    query = {}
    if status:
        query["status"] = status

    tasks = await _safe_find_tasks(query)
    if tasks:
        return tasks[:limit]
    if not status:
        return TASK_CACHE[:limit]
    return [task for task in TASK_CACHE if task.get("status") == status][:limit]


async def update_task_status(task_id: str, status: str) -> dict:
    """Update a task's status by its string ID."""
    from bson import ObjectId
    normalized_status = _normalize_status(status)
    db = get_db()
    if db is not None:
        try:
            await db.tasks.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {"status": normalized_status, "updated_at": datetime.utcnow().isoformat()}},
            )
        except Exception as error:
            print(f"[TaskService] Failed to update task in DB: {error}")

    for task in TASK_CACHE:
        if task.get("id") == task_id:
            task["status"] = normalized_status
            task["updated_at"] = datetime.utcnow().isoformat()
    return {"id": task_id, "status": normalized_status}


async def delete_task(task_id: str) -> dict:
    deleted = await _safe_delete_task(task_id)
    for index, task in enumerate(list(TASK_CACHE)):
        if task.get("id") == task_id:
            TASK_CACHE.pop(index)
            deleted = True
            break
    return {"id": task_id, "deleted": deleted}


async def create_task_from_params(params: dict) -> dict:
    title = (params.get("title") or params.get("task_title") or "").strip()
    if not title:
        return {"error": "Task title is required to create a manual task."}

    description = (params.get("description") or params.get("task_description") or "").strip()
    due_date = (params.get("date") or params.get("due_date") or "").strip()
    priority = params.get("priority", "medium")
    source = params.get("source", "manual")

    task = await create_task(
        title=title,
        description=description,
        priority=priority,
        source=source,
        due_date=due_date,
        telegram_chat_id=(params.get("telegram_chat_id") or "").strip(),
        recipient_email=(params.get("recipient_email") or "").strip(),
    )
    schedules = [task["reminder_schedule"]] if task.get("reminder_schedule") else []
    meetings = [task["calendar_event"]] if task.get("calendar_event") else []
    return {
        "tasks_created": 1,
        "tasks": [task],
        "mode": "manual",
        "schedules": schedules,
        "meetings": meetings,
    }


async def create_task_from_context(params: dict) -> dict:
    title = (params.get("title") or params.get("task_title") or "").strip()
    if title:
        return await create_task_from_params(params)

    summaries = params.get("summaries") or []
    if summaries:
        return await create_tasks_from_summaries(summaries)

    return {"error": "No task details or source summaries were provided."}


async def create_tasks_from_summaries(summaries: list[dict] = None) -> dict:
    """
    Use LLM to extract tasks from email summaries or plain text.
    Auto-creates the extracted tasks in the DB.
    """
    if not summaries:
        summaries = await _safe_load_summary_context()

    if not summaries:
        return {"tasks_created": 0, "tasks": [], "message": "No summaries available to extract tasks from."}

    summary_text = "\n".join(
        f"- Subject: {s.get('subject','?')} | From: {s.get('from','?')} | Priority: {s.get('priority','medium')}"
        for s in summaries
    )

    try:
        from llm.router import llm_chat

        raw = await llm_chat(TASK_EXTRACTION_SYSTEM, summary_text)
        raw = raw.strip().strip("```json").strip("```").strip()
        extracted = json.loads(raw)
        if not isinstance(extracted, list):
            extracted = []
    except Exception as e:
        print(f"[TaskService] LLM task extraction failed: {e}")
        # Fallback: create one task per email summary
        extracted = [
            {
                "title": f"Follow up: {s.get('subject', 'Unknown')}",
                "description": f"From {s.get('from', '?')}",
                "priority": s.get("priority", "medium"),
                "source": "email",
            }
            for s in summaries
        ]

    created = []
    schedules = []
    meetings = []
    for t in extracted:
        task = await create_task(
            title=t.get("title", "Untitled task"),
            description=t.get("description", ""),
            priority=t.get("priority", "medium"),
            source=t.get("source", "email"),
            due_date=t.get("due_date", ""),
        )
        created.append(task)
        if task.get("reminder_schedule"):
            schedules.append(task["reminder_schedule"])
        if task.get("calendar_event"):
            meetings.append(task["calendar_event"])

    return {"tasks_created": len(created), "tasks": created, "schedules": schedules, "meetings": meetings}
