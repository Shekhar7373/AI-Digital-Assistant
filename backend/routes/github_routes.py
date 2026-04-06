from fastapi import APIRouter
from pydantic import BaseModel
from services.github_service import fetch_repos, analyze_repo

router = APIRouter()

class RepoAnalyze(BaseModel):
    repo: dict

@router.get("/repos")
async def repos(username: str = "", limit: int = 6): return await fetch_repos(username, limit=limit)

@router.post("/analyze")
async def analyze(body: RepoAnalyze): return await analyze_repo(body.repo)
