from fastapi import APIRouter
from pydantic import BaseModel
from agent.agent import run_agent

router = APIRouter()

class ChatRequest(BaseModel):
    session_id: str = "default"
    message: str

@router.post("")
async def chat(req: ChatRequest):
    return await run_agent(req.session_id, req.message)