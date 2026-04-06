"""
Agent orchestrator and planner utilities.
"""

from __future__ import annotations

import asyncio
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta

from agent.memory import get_history, save_message
from agent.prompt import (
    GENERAL_CHAT_SYSTEM,
    INTENT_SYSTEM_PROMPT,
    INTENT_USER_TEMPLATE,
    PLANNER_SYSTEM,
)
from agent.tool_router import execute_tools
from llm.router import llm_chat

DEFAULT_WEATHER_LOCATION = "SDMCET, Dharwad, Karnataka, India"


def _strip_json_payload(raw: str) -> str:
    return raw.strip().removeprefix("```json").removesuffix("```").strip()


def _extract_duration_minutes(message: str) -> int | None:
    hour_match = re.search(r"(\d+)\s*[- ]?\s*(hour|hr)", message, re.IGNORECASE)
    minute_match = re.search(r"(\d+)\s*[- ]?\s*(minute|min)", message, re.IGNORECASE)
    if hour_match:
        return int(hour_match.group(1)) * 60
    if minute_match:
        return int(minute_match.group(1))
    return None


def _extract_time_phrase(message: str) -> str:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", message, re.IGNORECASE)
    return match.group(0) if match else ""


def _normalize_schedule_time(message: str, time_phrase: str) -> str:
    lowered = message.lower()
    if time_phrase:
        match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_phrase, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            am_pm = match.group(3).lower()
            if am_pm == "pm" and hour != 12:
                hour += 12
            if am_pm == "am" and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}"

    if "evening" in lowered:
        return "18:00"
    if "morning" in lowered:
        return "09:00"
    if "afternoon" in lowered:
        return "15:00"
    if "night" in lowered:
        return "21:00"
    return "18:00"


def _extract_email_addresses(message: str) -> list[str]:
    return re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", message)


def _clean_city_phrase(value: str) -> str:
    city = re.split(
        r"\b(?:to|every|daily|tomorrow|today|tonight|right now|now)\b",
        value,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return city.strip(" ?.,")


def _extract_city(message: str) -> str:
    lowered = message.lower()
    if "current location" in lowered or "my location" in lowered:
        return "current location"

    patterns = [
        r"weather(?:\s+report)?\s+(?:in|for|at)\s+([A-Za-z][A-Za-z,\s-]+)",
        r"forecast\s+(?:in|for|at)\s+([A-Za-z][A-Za-z,\s-]+)",
        r"(?:in|for|at)\s+([A-Za-z][A-Za-z,\s-]+)\s+weather",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return _clean_city_phrase(match.group(1))

    direct_city_match = re.search(
        r"\b(?:for|in|at)\s+([A-Za-z][A-Za-z,\s-]+?)\s+(?:to\s+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|every day|daily|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)|\?|$)",
        message,
        re.IGNORECASE,
    )
    if direct_city_match:
        return _clean_city_phrase(direct_city_match.group(1))
    return DEFAULT_WEATHER_LOCATION


def _extract_research_query(message: str) -> str:
    lowered = message.lower()
    query = message
    for prefix in [
        "search the web for",
        "research",
        "look up",
        "find information about",
        "tell me about",
    ]:
        index = lowered.find(prefix)
        if index != -1:
            query = message[index + len(prefix):]
            break
    query = re.split(r"\b(?:and email|email|send it|send the summary)\b", query, maxsplit=1, flags=re.IGNORECASE)[0]
    return query.strip(" .?")


def _extract_task_title(message: str) -> str:
    patterns = [
        r"(?:named|name it|title it|called)\s+['\"]?([^'\"\n]+?)['\"]?(?:\s+(?:for|by|at|tomorrow|today|next)|$)",
        r"create (?:a )?task(?: for)?\s+['\"]?([^'\"\n]+?)['\"]?(?:\s+(?:for|by|at|tomorrow|today|next)|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,")
    return ""


def _extract_task_description(message: str) -> str:
    lowered = message.lower()
    if "description" in lowered:
        match = re.search(r"description\s+(?:as|to be)?\s*['\"]?([^'\"]+)['\"]?", message, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""


def _resolve_datetime_phrase(message: str, time_phrase: str) -> str:
    lowered = message.lower()
    base = datetime.now()
    if "tomorrow" in lowered:
        base = base + timedelta(days=1)
    elif "next week" in lowered:
        base = base + timedelta(days=7)

    if time_phrase:
        time_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", time_phrase, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2) or 0)
            am_pm = time_match.group(3).lower()
            if am_pm == "pm" and hour != 12:
                hour += 12
            if am_pm == "am" and hour == 12:
                hour = 0
            base = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        base = base.replace(hour=14, minute=0, second=0, microsecond=0)

    return base.isoformat()


def _is_recurring_request(message: str) -> bool:
    lowered = message.lower()
    return any(
        phrase in lowered
        for phrase in ["every day", "everyday", "daily", "recurring", "each day"]
    )


def _heuristic_parameters(message: str) -> dict:
    lowered = message.lower()
    attendees = _extract_email_addresses(message)
    time_phrase = _extract_time_phrase(message)
    duration = _extract_duration_minutes(message)
    github_match = re.search(r"github(?: user| username)\s+([A-Za-z0-9_-]+)", lowered)
    is_recurring = _is_recurring_request(message)

    priority = ""
    if "high priority" in lowered or "urgent" in lowered:
        priority = "high"
    elif "low priority" in lowered:
        priority = "low"
    elif "medium priority" in lowered:
        priority = "medium"

    date_phrase = ""
    if any(token in lowered for token in ["tomorrow", "today", "next week"]) or time_phrase:
        date_phrase = _resolve_datetime_phrase(message, time_phrase)

    github_username = github_match.group(1) if github_match else ""
    recipient_email = attendees[0] if attendees else ""

    return {
        "priority": priority,
        "date": date_phrase,
        "time": time_phrase,
        "schedule_time": _normalize_schedule_time(message, time_phrase) if is_recurring else "",
        "schedule_frequency": "daily" if is_recurring else "",
        "timezone": "Asia/Calcutta" if is_recurring else "",
        "schedule_type": "weather_email" if is_recurring else "",
        "duration_minutes": duration,
        "attendees": attendees,
        "github_username": github_username,
        "username": github_username,
        "city": _extract_city(message),
        "query": _extract_research_query(message),
        "recipient_email": recipient_email,
        "email_subject": "Agentic AI Summary" if recipient_email else "",
        "task_title": _extract_task_title(message),
        "task_description": _extract_task_description(message),
    }


def _heuristic_plan(message: str) -> dict:
    lowered = message.lower()
    params = _heuristic_parameters(message)
    steps = []

    wants_weather = "weather" in lowered
    wants_email = any(token in lowered for token in ["email", "gmail", "inbox", "mail"])
    wants_task_terms = any(token in lowered for token in ["task", "todo", "action item"])
    wants_task_list = wants_task_terms and any(token in lowered for token in ["show", "list", "what", "view", "my tasks", "all tasks"])
    wants_create_task = wants_task_terms and any(token in lowered for token in ["create", "add", "make", "new", "set"])
    wants_calendar = any(token in lowered for token in ["meeting", "calendar", "schedule"])
    wants_github = any(token in lowered for token in ["github", "repo", "pull request", "issue", "issues", "pr "])
    wants_web = any(token in lowered for token in ["search the web", "research", "look up", "internet", "web"])
    wants_send_email = any(token in lowered for token in ["send", "email me", "mail me"]) and bool(params["recipient_email"])
    wants_recurring = _is_recurring_request(message)

    if wants_recurring and wants_weather and wants_send_email:
        steps.append(
            {
                "tool": "create_recurring_weather_email_schedule",
                "title": "Create recurring delivery",
                "description": f"Scheduling a daily weather email to {params['recipient_email']}",
                "params": {
                    "recipient_email": params["recipient_email"],
                    "city": params["city"],
                    "email_subject": params["email_subject"] or f"Daily weather report for {params['city']}",
                    "schedule_frequency": params.get("schedule_frequency") or "daily",
                    "schedule_time": params.get("schedule_time") or "18:00",
                    "timezone": params.get("timezone") or "Asia/Calcutta",
                    "schedule_type": "weather_email",
                },
            }
        )
        return {"summary": f"Plan for: {message}", "parameters": params, "steps": steps}

    if wants_weather:
        steps.append(
            {
                "tool": "fetch_weather",
                "title": "Weather Agent",
                "description": f"Checking current weather for {params['city']}",
                "params": {"city": params["city"]},
            }
        )

    if wants_email and not wants_send_email:
        steps.extend(
            [
                {
                    "tool": "fetch_emails",
                    "title": "Mail Agent",
                    "description": "Loading recent inbox messages",
                    "params": {},
                },
                {
                    "tool": "summarize_emails",
                    "title": "Summarize inbox",
                    "description": "Generating a concise inbox summary",
                    "params": {},
                },
            ]
        )

    if wants_task_list:
        steps.append(
            {
                "tool": "get_tasks",
                "title": "Task Board",
                "description": "Loading the current task list",
                "params": {},
            }
        )

    if wants_create_task and (params.get("task_title") or wants_email):
        steps.append(
            {
                "tool": "create_task",
                "title": "Task Agent",
                "description": "Creating a task from explicit instructions or retrieved context",
                "params": {
                    "title": params.get("task_title", ""),
                    "description": params.get("task_description", ""),
                    "date": params.get("date", ""),
                    "priority": params.get("priority", ""),
                    "source": "manual" if params.get("task_title") else "email",
                },
            }
        )

    if wants_calendar:
        steps.append(
            {
                "tool": "fetch_meetings",
                "title": "Calendar Agent",
                "description": "Looking up upcoming meetings",
                "params": {},
            }
        )
        if any(token in lowered for token in ["schedule", "book", "create meeting"]):
            steps.append(
                {
                    "tool": "schedule_meeting",
                    "title": "Schedule meeting",
                    "description": "Creating a follow-up meeting",
                    "params": {
                        "title": "Follow-up meeting",
                        "date": params["date"],
                        "duration_minutes": params["duration_minutes"] or 60,
                        "attendees": params["attendees"],
                    },
                }
            )

    if wants_github:
        if any(token in lowered for token in ["update", "updates", "issue", "issues", "pull request", "pr", "notification"]):
            steps.append(
                {
                    "tool": "fetch_github_updates",
                    "title": "GitHub Agent",
                    "description": "Fetching recent PR and issue activity",
                    "params": {"username": params["github_username"]},
                }
            )
        if any(token in lowered for token in ["repo", "repos", "repository", "repositories", "github"]):
            steps.append(
                {
                    "tool": "fetch_github_repos",
                    "title": "Load repositories",
                    "description": "Pulling repository metadata",
                    "params": {"username": params["github_username"]},
                }
            )
        if any(token in lowered for token in ["analyze", "summary", "summarize", "tell me about"]):
            steps.append(
                {
                    "tool": "analyze_github",
                    "title": "Analyze repository",
                    "description": "Preparing a quick analysis of the latest repo",
                    "params": {},
                }
            )

    if wants_web:
        steps.append(
            {
                "tool": "web_research",
                "title": "Research Agent",
                "description": "Searching the web and collecting a concise summary",
                "params": {"query": params["query"] or message},
            }
        )

    if wants_send_email:
        steps.append(
            {
                "tool": "send_email",
                "title": "Send summary email",
                "description": f"Sending the result to {params['recipient_email']}",
                "params": {
                    "recipient_email": params["recipient_email"],
                    "email_subject": params["email_subject"] or "Agentic AI Summary",
                },
            }
        )

    if not steps:
        return {"summary": f"Answer directly: {message}", "parameters": params, "steps": []}

    deduped_steps = []
    seen_signatures = set()
    for step in steps:
        signature = (step["tool"], json.dumps(step.get("params", {}), sort_keys=True))
        if signature not in seen_signatures:
            deduped_steps.append(step)
            seen_signatures.add(signature)

    return {"summary": f"Plan for: {message}", "parameters": params, "steps": deduped_steps}


async def classify_intent(message: str) -> list[str]:
    user_prompt = INTENT_USER_TEMPLATE.format(message=message)
    try:
        raw = await asyncio.wait_for(llm_chat(INTENT_SYSTEM_PROMPT, user_prompt), timeout=12)
        tools = json.loads(_strip_json_payload(raw))
        if isinstance(tools, list):
            return tools
    except Exception as error:
        print(f"[Agent] Intent classification failed: {error}. Defaulting to general_chat.")
    return ["general_chat"]


async def compose_response(user_message: str, tool_results: dict, history: list[dict]) -> str:
    context_parts = []

    for tool, result in tool_results.items():
        if isinstance(result, dict) and result.get("error"):
            context_parts.append(f"[{tool}] Error: {result['error']}")
            continue

        if tool == "fetch_emails" and isinstance(result, list):
            context_parts.append(f"[{tool}] Retrieved {len(result)} emails")
        elif tool == "summarize_emails" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Summary: {result.get('summary', 'No summary')[:250]}")
        elif tool == "create_task" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Created {len(result.get('tasks', []))} tasks")
        elif tool == "get_tasks" and isinstance(result, list):
            context_parts.append(f"[{tool}] Retrieved {len(result)} tasks")
        elif tool == "fetch_weather" and isinstance(result, dict):
            if not result.get("error"):
                city = result.get("city", "Location")
                temp = result.get("temperature_c")
                cond = result.get("condition")
                context_parts.append(f"[{tool}] {city}: {temp} C, {cond}")
        elif tool == "fetch_github_repos" and isinstance(result, list):
            context_parts.append(f"[{tool}] Retrieved {len(result)} repositories")
        elif tool == "fetch_github_updates" and isinstance(result, dict):
            context_parts.append(f"[{tool}] {result.get('summary', 'GitHub updates loaded')}")
        elif tool == "analyze_github" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Analysis: {result.get('analysis', 'No analysis')[:300]}")
        elif tool == "fetch_meetings" and isinstance(result, list):
            context_parts.append(f"[{tool}] Retrieved {len(result)} upcoming meetings")
        elif tool == "schedule_meeting" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Scheduled: {result.get('title', 'Meeting')}")
        elif tool == "list_drive_files" and isinstance(result, list):
            context_parts.append(f"[{tool}] Retrieved {len(result)} files")
        elif tool == "summarize_file" and isinstance(result, dict):
            context_parts.append(f"[{tool}] {result.get('file_name', 'File')}: {result.get('summary', '')[:250]}")
        elif tool == "web_research" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Summary: {result.get('summary', 'No findings')[:300]}")
        elif tool == "send_email" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Sent email to {result.get('to', 'recipient')}")
        elif tool == "create_recurring_weather_email_schedule" and isinstance(result, dict):
            context_parts.append(
                f"[{tool}] Scheduled daily weather email for {result.get('city', 'preferred location')} at {result.get('time_local', '18:00')}"
            )
        elif tool == "wikipedia_search" and isinstance(result, dict):
            context_parts.append(f"[{tool}] Result: {result.get('summary', '')[:250]}")
        else:
            context_parts.append(f"[{tool}] result: {json.dumps(result, default=str)[:220]}")

    context = "\n".join(context_parts) if context_parts else "No tools were needed."
    history_text = "\n".join(f"{item['role'].capitalize()}: {item['content'][:100]}" for item in history[-6:])
    system = (
        "You are a productivity assistant. Based on the tool execution results below, "
        "answer the user's request clearly. Mention key findings, any actions taken, and any blockers. "
        "Be direct and helpful.\n\n"
        f"Tool Results:\n{context}\n\nRecent conversation:\n{history_text}"
    )

    try:
        return await asyncio.wait_for(llm_chat(system, user_message), timeout=18)
    except Exception as error:
        print(f"[Agent] Response composition failed: {error}")
        return "\n".join(context_parts) if context_parts else "I processed the request."


async def generate_execution_plan(message: str) -> dict:
    heuristics = _heuristic_parameters(message)
    try:
        raw = await asyncio.wait_for(llm_chat(PLANNER_SYSTEM, message), timeout=12)
        plan = json.loads(_strip_json_payload(raw))
        if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
            merged = deepcopy(plan)
            merged.setdefault("summary", f"Plan for: {message}")
            planner_params = {}
            for key, value in (merged.get("parameters", {}) or {}).items():
                if value not in (None, "", [], {}, "null", "User's location"):
                    planner_params[key] = value
            merged["parameters"] = {**heuristics, **planner_params}
            for step in merged["steps"]:
                step.setdefault("params", {})
                if step.get("tool") == "fetch_weather":
                    city = step["params"].get("city")
                    if city in (None, "", "null", "User's location"):
                        step["params"]["city"] = heuristics.get("city") or DEFAULT_WEATHER_LOCATION
                if step.get("tool") in {"fetch_github_repos", "fetch_github_updates"}:
                    username = step["params"].get("username")
                    if username in (None, "", "null", "and"):
                        step["params"]["username"] = heuristics.get("github_username") or ""
                if step.get("tool") == "create_task":
                    step["params"].setdefault("title", heuristics.get("task_title") or "")
                    step["params"].setdefault("description", heuristics.get("task_description") or "")
                    step["params"].setdefault("date", heuristics.get("date") or "")
                    step["params"].setdefault("priority", heuristics.get("priority") or "medium")
                    if step["params"].get("title"):
                        step["params"].setdefault("source", "manual")
                if step.get("tool") == "create_recurring_weather_email_schedule":
                    step["params"].setdefault("recipient_email", heuristics.get("recipient_email") or "")
                    step["params"].setdefault("city", heuristics.get("city") or "current location")
                    step["params"].setdefault("email_subject", heuristics.get("email_subject") or "")
                    step["params"].setdefault("schedule_frequency", heuristics.get("schedule_frequency") or "daily")
                    step["params"].setdefault("schedule_time", heuristics.get("schedule_time") or "18:00")
                    step["params"].setdefault("timezone", heuristics.get("timezone") or "Asia/Calcutta")
                    step["params"].setdefault("schedule_type", "weather_email")
            return merged
    except Exception as error:
        print(f"[Agent] Planner generation failed: {error}. Using heuristic plan.")
    return _heuristic_plan(message)


def _step_log(index: int, title: str, message: str) -> dict:
    return {"timestamp": f"[step {index + 1}]", "message": f"{title}: {message}"}


def _end_datetime(start_iso: str, duration_minutes: int | None) -> str:
    try:
        start = datetime.fromisoformat(start_iso)
    except Exception:
        return start_iso
    return (start + timedelta(minutes=duration_minutes or 60)).isoformat()


def _artifact_patch(tool: str, result: object) -> dict:
    patch = {
        "summary": "",
        "summaries": [],
        "tasks": [],
        "meetings": [],
        "repos": [],
        "emails": [],
        "weather": {},
        "research": {},
        "sent_email": {},
        "github_updates": {},
        "schedules": [],
    }
    if tool == "fetch_emails" and isinstance(result, list):
        patch["emails"] = result
    elif tool == "summarize_emails" and isinstance(result, dict):
        patch["summary"] = result.get("summary", "")
        patch["summaries"] = result.get("summaries", [])
    elif tool == "create_task" and isinstance(result, dict):
        patch["tasks"] = result.get("tasks", [])
    elif tool == "fetch_weather" and isinstance(result, dict):
        patch["weather"] = result
    elif tool in {"fetch_meetings", "schedule_meeting"}:
        patch["meetings"] = result if isinstance(result, list) else [result]
    elif tool == "fetch_github_repos" and isinstance(result, list):
        patch["repos"] = result
    elif tool == "fetch_github_updates" and isinstance(result, dict):
        patch["github_updates"] = result
        patch["repos"] = result.get("repos", [])
    elif tool in {"web_research", "wikipedia_search"} and isinstance(result, dict):
        patch["research"] = result
        patch["summary"] = result.get("summary", "")
    elif tool == "send_email" and isinstance(result, dict):
        patch["sent_email"] = result
    elif tool == "create_recurring_weather_email_schedule" and isinstance(result, dict):
        patch["schedules"] = [result]
    return patch


def _build_email_payload(message: str, artifacts: dict, params: dict) -> tuple[str, dict]:
    research = artifacts.get("research", {}) or {}
    weather = artifacts.get("weather", {}) or {}
    summary = (artifacts.get("summary") or "").strip()

    if weather.get("city") and weather.get("temperature_c") is not None:
        city = weather.get("city", "your location")
        condition = weather.get("condition", "Unknown")
        temperature = weather.get("temperature_c")
        wind_speed = weather.get("wind_speed_kmh")
        body_lines = [
            f"Weather report for {city}",
            "",
            f"Temperature: {temperature} C",
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

    if research.get("summary"):
        return research.get("summary", ""), research

    if summary:
        return summary, {
            "query": params.get("query") or "Requested summary",
            "summary": summary,
            "items": [],
        }

    return message, {
        "query": params.get("query") or "Requested summary",
        "summary": message,
        "items": [],
    }


async def execute_execution_plan(session_id: str, message: str, plan: dict) -> dict:
    params = deepcopy(plan.get("parameters", {}))
    shared_params = dict(params)
    shared_params["message"] = message

    artifacts = {
        "summary": "",
        "summaries": [],
        "tasks": [],
        "meetings": [],
        "repos": [],
        "emails": [],
        "weather": {},
        "research": {},
        "sent_email": {},
        "github_updates": {},
        "schedules": [],
    }
    logs = []
    executed_steps = []

    if not plan.get("steps"):
        history = await get_history(session_id)
        try:
            response = await asyncio.wait_for(llm_chat(GENERAL_CHAT_SYSTEM, message), timeout=18)
        except Exception:
            response = "I did not need any tools for that request."
        await save_message(session_id, "assistant", response)
        return {
            "summary": plan.get("summary", ""),
            "parameters": params,
            "steps": [],
            "artifacts": artifacts,
            "logs": [],
            "response": response,
        }

    for index, step in enumerate(plan.get("steps", [])):
        step_copy = {
            "id": f"step-{index + 1}",
            "tool": step.get("tool", ""),
            "title": step.get("title", step.get("tool", "Step")),
            "description": step.get("description", ""),
            "status": "running",
            "params": step.get("params", {}),
        }
        logs.append(_step_log(index, step_copy["title"], "started"))

        shared_params.update(step_copy["params"])
        if shared_params.get("github_username") and not shared_params.get("username"):
            shared_params["username"] = shared_params["github_username"]
        if shared_params.get("city") in (None, "", "null", "User's location"):
            shared_params["city"] = params.get("city") or DEFAULT_WEATHER_LOCATION
        if shared_params.get("username") in ("null", "and"):
            shared_params["username"] = params.get("github_username") or ""

        if step_copy["tool"] == "schedule_meeting":
            meeting_date = shared_params.get("date") or params.get("date")
            duration = shared_params.get("duration_minutes") or params.get("duration_minutes") or 60
            shared_params["date"] = meeting_date
            shared_params["end_date"] = _end_datetime(meeting_date, duration) if meeting_date else ""
            shared_params["duration_minutes"] = duration
        elif step_copy["tool"] == "send_email":
            email_body, email_context = _build_email_payload(message, artifacts, params)
            shared_params["email_body"] = email_body
            shared_params["email_context"] = email_context
            if not shared_params.get("email_subject"):
                shared_params["email_subject"] = email_context.get("query", "Agentic AI Summary")
        elif step_copy["tool"] == "create_recurring_weather_email_schedule":
            shared_params.setdefault("schedule_time", params.get("schedule_time") or "18:00")
            shared_params.setdefault("schedule_frequency", params.get("schedule_frequency") or "daily")
            shared_params.setdefault("timezone", params.get("timezone") or "Asia/Calcutta")
            shared_params.setdefault("schedule_type", "weather_email")

        result_map = await execute_tools([step_copy["tool"]], shared_params)
        result = result_map.get(step_copy["tool"], {})
        step_copy["result"] = result

        if isinstance(result, dict) and result.get("error"):
            step_copy["status"] = "failed"
            result_preview = f"failed: {result.get('error', 'unknown error')}"
        else:
            step_copy["status"] = "completed"
            result_preview = "completed"

        patch = _artifact_patch(step_copy["tool"], result)
        for key, value in patch.items():
            if value not in ("", [], {}, None):
                artifacts[key] = value

        if step_copy["tool"] == "summarize_emails" and isinstance(result, dict):
            shared_params["email_body"] = result.get("summary", "")
        elif step_copy["tool"] in {"web_research", "wikipedia_search"} and isinstance(result, dict):
            shared_params["email_body"] = result.get("summary", "")

        logs.append(_step_log(index, step_copy["title"], result_preview))
        executed_steps.append(step_copy)

    history = await get_history(session_id)
    response = await compose_response(message, {step["tool"]: step["result"] for step in executed_steps}, history)
    await save_message(session_id, "assistant", response)

    return {
        "summary": plan.get("summary", ""),
        "parameters": params,
        "steps": executed_steps,
        "artifacts": artifacts,
        "logs": logs,
        "response": response,
    }


async def run_agent(session_id: str, user_message: str) -> dict:
    await save_message(session_id, "user", user_message)
    history = await get_history(session_id)
    tools = await classify_intent(user_message)
    print(f"[Agent] Intent -> tools: {tools}")

    if tools == ["general_chat"]:
        history_text = "\n".join(f"{item['role'].capitalize()}: {item['content']}" for item in history[-6:])
        try:
            response = await asyncio.wait_for(
                llm_chat(GENERAL_CHAT_SYSTEM + f"\n\nRecent conversation:\n{history_text}", user_message),
                timeout=18,
            )
        except Exception:
            response = "I could not reach the model right now, but the dashboard is still available."
        tool_results = {}
    else:
        tool_results = await execute_tools(tools, params=_heuristic_parameters(user_message))
        response = await compose_response(user_message, tool_results, history)

    await save_message(session_id, "assistant", response)
    return {"response": response, "tools_used": tools, "tool_results": tool_results}
