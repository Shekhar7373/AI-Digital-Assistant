from fastapi import APIRouter
from pydantic import BaseModel
from services.task_service import create_task, get_all_tasks, create_tasks_from_summaries, delete_task, update_task_status

router = APIRouter()

class TaskCreate(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    due_date: str = ""


class TaskStatusUpdate(BaseModel):
    status: str

@router.get("")
async def get_tasks(status: str = ""): return await get_all_tasks(status or None)

@router.post("")
async def new_task(t: TaskCreate): return await create_task(t.title, t.description, t.priority, due_date=t.due_date)

@router.post("/from-emails")
async def tasks_from_emails(): return await create_tasks_from_summaries()

@router.patch("/{task_id}/status")
async def patch_task_status(task_id: str, body: TaskStatusUpdate): return await update_task_status(task_id, body.status)

@router.delete("/{task_id}")
async def remove_task(task_id: str): return await delete_task(task_id)
