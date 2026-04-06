from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from agent.agent import execute_execution_plan, generate_execution_plan

router = APIRouter()


def _default_state() -> dict:
    return {
        "session_id": str(uuid4()),
        "prompt_preview": "",
        "approval_label": "Idle",
        "current_step": "Ready",
        "intent_accuracy": 98.5,
        "neural_load": "Low",
        "token_usage": {"used": 0, "limit": 128000},
        "logs": [],
        "artifacts": {
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
        },
        "plan_steps": [],
        "plan_definition": {"summary": "", "parameters": {}, "steps": []},
        "response": "",
        "error": "",
    }


dashboard_sessions: dict[str, dict] = {}
current_session_id: str | None = None


def _store_state(state: dict) -> dict:
    global current_session_id
    dashboard_sessions[state["session_id"]] = state
    current_session_id = state["session_id"]
    return state


def _get_state(session_id: str | None = None) -> dict:
    global current_session_id
    if session_id and session_id in dashboard_sessions:
        current_session_id = session_id
        return dashboard_sessions[session_id]
    if current_session_id and current_session_id in dashboard_sessions:
        return dashboard_sessions[current_session_id]
    return _store_state(_default_state())


class PromptRequest(BaseModel):
    message: str


class SessionRequest(BaseModel):
    session_id: str


@router.get("/state")
async def get_dashboard_state():
    return _get_state()


@router.post("/reset")
async def reset_dashboard_state():
    global current_session_id
    dashboard_sessions.clear()
    current_session_id = None
    fresh_state = _default_state()
    print(f"[Dashboard] Reset dashboard state. New session {fresh_state['session_id']}")
    return _store_state(fresh_state)


@router.post("/plan")
async def plan_prompt(req: PromptRequest):
    if not req.message.strip():
        state = _get_state()
        state["error"] = "Prompt cannot be empty"
        return _store_state(state)

    session_id = str(uuid4())

    try:
        plan = await generate_execution_plan(req.message)
        steps = [
            {
                "id": f"step-{index + 1}",
                "tool": step.get("tool", ""),
                "title": step.get("title", step.get("tool", "Step")),
                "description": step.get("description", ""),
                "status": "pending",
            }
            for index, step in enumerate(plan.get("steps", []))
        ]

        state = {
            "session_id": session_id,
            "prompt_preview": req.message,
            "approval_label": "Awaiting Approval",
            "current_step": "Plan Generated",
            "intent_accuracy": 98.5,
            "neural_load": "Low",
            "token_usage": {"used": min(max(len(req.message) * 14, 1200), 9000), "limit": 128000},
            "logs": [{"timestamp": "[plan_generated]", "message": f"Plan created: {len(steps)} steps"}],
            "artifacts": _default_state()["artifacts"],
            "plan_steps": steps,
            "plan_definition": plan,
            "response": "",
            "error": "",
        }
        print(f"[Dashboard] Generated plan with {len(steps)} steps for session {session_id}")
        return _store_state(state)
    except Exception as error:
        state = _get_state()
        state["error"] = f"Plan generation failed: {error}"
        state["approval_label"] = "Error"
        print(f"[Dashboard] {state['error']}")
        return _store_state(state)


@router.post("/approve")
async def approve_prompt(req: SessionRequest):
    state = _get_state(req.session_id)
    if req.session_id != state.get("session_id"):
        state["error"] = "Session ID mismatch. Generate a new plan."
        return _store_state(state)

    plan = deepcopy(state.get("plan_definition", {}))
    if not plan.get("steps"):
        state["error"] = "No plan to execute. Generate a plan first."
        return _store_state(state)

    try:
        prompt_text = state.get("prompt_preview", "")
        execution = await execute_execution_plan(req.session_id, prompt_text, plan)
        completed_steps = execution.get("steps", [])
        last_step = completed_steps[-1]["title"] if completed_steps else "Completed"

        state = {
            **state,
            "approval_label": "Execution Complete",
            "current_step": last_step,
            "neural_load": "Moderate" if completed_steps else "Low",
            "token_usage": {"used": min(max(len(prompt_text) * 28, 2200), 16000), "limit": 128000},
            "logs": execution.get("logs", []),
            "artifacts": execution.get("artifacts", state.get("artifacts", {})),
            "plan_steps": [
                {
                    "id": step.get("id", f"step-{index + 1}"),
                    "tool": step.get("tool", ""),
                    "title": step.get("title", "Step"),
                    "description": step.get("description", ""),
                    "status": step.get("status", "completed"),
                }
                for index, step in enumerate(completed_steps)
            ],
            "response": execution.get("response", ""),
            "error": "",
        }
        print(f"[Dashboard] Executed {len(completed_steps)} steps for session {req.session_id}")
        return _store_state(state)
    except Exception as error:
        state["error"] = f"Execution failed: {error}"
        state["approval_label"] = "Execution Failed"
        print(f"[Dashboard] {state['error']}")
        return _store_state(state)


@router.post("/cancel")
async def cancel_prompt(req: SessionRequest):
    state = _get_state(req.session_id)
    if req.session_id != state.get("session_id"):
        return state

    state = {
        **state,
        "approval_label": "Cancelled",
        "current_step": "Idle",
        "neural_load": "Low",
        "logs": [
            *state.get("logs", []),
            {"timestamp": "[cancelled]", "message": "Plan cancelled by user"},
        ],
        "error": "",
    }
    print(f"[Dashboard] Cancelled plan for session {req.session_id}")
    return _store_state(state)
