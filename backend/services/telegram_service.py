from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import httpx

from agent.agent import execute_execution_plan, generate_execution_plan


telegram_chat_sessions: dict[str, dict[str, Any]] = {}


def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _webhook_secret() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()


def _allowed_chat_ids() -> set[str]:
    raw = os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "")
    return {item.strip() for item in raw.split(",") if item.strip()}


def telegram_status() -> dict[str, Any]:
    token = _bot_token()
    secret = _webhook_secret()
    return {
        "configured": bool(token),
        "bot_token_present": bool(token),
        "webhook_secret_present": bool(secret),
        "allowed_chat_ids_configured": bool(_allowed_chat_ids()),
        "commands": ["/start", "/help", "/plan", "/run", "/cancel", "/status"],
    }


def _get_chat_state(chat_id: str) -> dict[str, Any]:
    return telegram_chat_sessions.setdefault(
        chat_id,
        {
            "session_id": "",
            "prompt_preview": "",
            "plan_definition": {"summary": "", "parameters": {}, "steps": []},
            "plan_steps": [],
            "response": "",
            "approval_label": "Idle",
            "artifacts": {},
        },
    )


def _step_summary(plan: dict[str, Any]) -> str:
    steps = plan.get("steps", [])
    if not steps:
        return "No tool steps were needed for that request."
    return "\n".join(
        f"{index + 1}. {step.get('title', step.get('tool', 'Step'))} ({step.get('tool', 'unknown')})"
        for index, step in enumerate(steps)
    )


def _artifacts_summary(artifacts: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    if artifacts.get("summary"):
        lines.append(f"Summary: {artifacts['summary']}")
    if artifacts.get("tasks"):
        task = artifacts["tasks"][0]
        task_line = f"Task created: {task.get('title', 'Untitled task')} (ID: {task.get('id', 'n/a')})"
        if task.get("url"):
            task_line += f"\nTask dashboard: {task['url']}"
        lines.append(task_line)
    if artifacts.get("meetings"):
        meeting = artifacts["meetings"][0]
        meeting_line = f"Meeting: {meeting.get('title', 'Untitled meeting')} at {meeting.get('date', 'unspecified time')}"
        if meeting.get("attendees"):
            meeting_line += f"\nAttendees: {len(meeting.get('attendees', []))}"
        if meeting.get("url"):
            meeting_line += f"\nCalendar link: {meeting['url']}"
        lines.append(meeting_line)
    if artifacts.get("drive_docs"):
        drive_doc = artifacts["drive_docs"][0]
        drive_line = f"Drive file: {drive_doc.get('name', 'Untitled file')}"
        if drive_doc.get("url"):
            drive_line += f"\nDrive link: {drive_doc['url']}"
        lines.append(drive_line)
    if artifacts.get("github_updates", {}).get("summary"):
        lines.append(f"GitHub: {artifacts['github_updates']['summary']}")
    if artifacts.get("research", {}).get("summary"):
        lines.append(f"Research: {artifacts['research']['summary']}")
    if artifacts.get("weather", {}).get("city"):
        weather = artifacts["weather"]
        lines.append(f"Weather: {weather.get('city')} {weather.get('temperature_c')} C, {weather.get('condition')}")
    if artifacts.get("sent_email", {}).get("to"):
        sent_email = artifacts["sent_email"]
        lines.append(f"Email sent to {sent_email.get('to')}")
    if artifacts.get("schedules"):
        schedule = artifacts["schedules"][0]
        schedule_line = (
            f"Schedule: {schedule.get('name', 'Recurring schedule')} at "
            f"{schedule.get('time_local', '18:00')} {schedule.get('timezone', 'Asia/Calcutta')}"
        )
        if schedule.get("next_run_at"):
            schedule_line += f"\nNext run: {schedule['next_run_at']}"
        if schedule.get("url"):
            schedule_line += f"\nDashboard link: {schedule['url']}"
        lines.append(schedule_line)
    return lines


async def send_telegram_message(chat_id: str, text: str) -> dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"ok": False, "error": "Telegram bot token not configured."}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4000],
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"[Telegram] Sent reply to chat {chat_id}")
        return data


async def set_telegram_webhook() -> dict[str, Any]:
    token = _bot_token()
    base_url = os.getenv("TELEGRAM_WEBHOOK_BASE_URL", "").strip().rstrip("/")
    secret = _webhook_secret()

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not configured.")
    if not base_url:
        raise ValueError("TELEGRAM_WEBHOOK_BASE_URL is not configured.")
    if not secret:
        raise ValueError("TELEGRAM_WEBHOOK_SECRET is not configured.")

    webhook_url = f"{base_url}/integrations/telegram/webhook/{secret}"
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {"url": webhook_url, "secret_token": secret}

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    return {"webhook_url": webhook_url, "telegram_response": data}


def _help_text() -> str:
    return (
        "Agentic AI Telegram control\n\n"
        "Commands:\n"
        "/plan <request> - generate a workflow plan\n"
        "/run - execute the last planned workflow\n"
        "/status - show the pending plan\n"
        "/cancel - discard the pending plan\n"
        "/help - show this message\n\n"
        "Tip: sending plain text will generate a plan first, then you can approve it with /run."
    )


async def _handle_plan(chat_id: str, prompt: str) -> str:
    if not prompt.strip():
        return "Send a request after /plan. Example: /plan review my github issues and draft tasks"

    plan = await generate_execution_plan(prompt)
    state = _get_chat_state(chat_id)
    state["session_id"] = str(uuid4())
    state["prompt_preview"] = prompt
    state["plan_definition"] = plan
    state["plan_definition"].setdefault("parameters", {})
    state["plan_definition"]["parameters"]["telegram_chat_id"] = chat_id
    state["plan_steps"] = plan.get("steps", [])
    state["approval_label"] = "Awaiting Approval"
    state["response"] = ""

    return (
        f"Plan ready for: {prompt}\n\n"
        f"{_step_summary(plan)}\n\n"
        "Reply with /run to execute or /cancel to discard."
    )


async def _handle_run(chat_id: str) -> str:
    state = _get_chat_state(chat_id)
    plan = state.get("plan_definition", {})
    plan.setdefault("parameters", {})
    plan["parameters"]["telegram_chat_id"] = chat_id
    prompt = state.get("prompt_preview", "")
    if not prompt or not plan.get("steps"):
        return "There is no pending plan. Send /plan <request> first."

    execution = await execute_execution_plan(state["session_id"], prompt, plan)
    state["approval_label"] = "Execution Complete"
    state["response"] = execution.get("response", "")
    state["artifacts"] = execution.get("artifacts", {})
    state["plan_steps"] = execution.get("steps", [])

    lines = _artifacts_summary(state["artifacts"])
    extra = "\n".join(lines[:5])
    body = execution.get("response", "Execution finished.")
    if extra:
        body = f"{body}\n\n{extra}"
    return body


def _handle_status(chat_id: str) -> str:
    state = _get_chat_state(chat_id)
    prompt = state.get("prompt_preview", "")
    plan = state.get("plan_definition", {})
    if not prompt or not plan.get("steps"):
        return "No pending plan yet. Send /plan <request> or a plain message to generate one."
    return (
        f"Pending plan for: {prompt}\n\n"
        f"{_step_summary(plan)}\n\n"
        "Use /run to execute or /cancel to discard."
    )


def _handle_cancel(chat_id: str) -> str:
    state = _get_chat_state(chat_id)
    state["prompt_preview"] = ""
    state["plan_definition"] = {"summary": "", "parameters": {}, "steps": []}
    state["plan_steps"] = []
    state["response"] = ""
    state["approval_label"] = "Cancelled"
    state["artifacts"] = {}
    return "Pending plan cleared."


async def process_telegram_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message") or update.get("edited_message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    print(f"[Telegram] Incoming update for chat {chat_id or 'unknown'}: {text[:120]}")

    if not chat_id or not text:
        return {"ok": True, "message": "Ignored non-text update."}

    allowed = _allowed_chat_ids()
    if allowed and chat_id not in allowed:
        return {"ok": False, "message": f"Chat {chat_id} is not allowed."}

    lowered = text.lower()
    if lowered in {"/start", "/help"}:
        reply = _help_text()
    elif lowered.startswith("/plan"):
        reply = await _handle_plan(chat_id, text[5:].strip())
    elif lowered == "/run":
        reply = await _handle_run(chat_id)
    elif lowered == "/status":
        reply = _handle_status(chat_id)
    elif lowered == "/cancel":
        reply = _handle_cancel(chat_id)
    else:
        reply = await _handle_plan(chat_id, text)

    try:
        send_result = await send_telegram_message(chat_id, reply)
    except Exception as error:
        print(f"[Telegram] Failed to send reply to chat {chat_id}: {error}")
        raise
    return {"ok": True, "chat_id": chat_id, "reply": reply, "telegram": send_result}
